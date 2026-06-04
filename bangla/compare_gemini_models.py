"""Side-by-side comparison of two Gemini models on the same Bangla notes.

Pick N notes, call each model with identical prompts (and identical
sampled form constraints, since `sentence_sampling` is deterministic by
note id). Write a markdown report so we can eyeball quality and cost
tradeoff.

Usage:
  # Compare on 20 randomly-chosen missing-sentence notes:
  uv run compare_gemini_models.py --limit 20

  # Compare on specific notes:
  uv run compare_gemini_models.py --note-ids 1748038956299,1748038956300

The result file `out/model_comparison_<model_a>_vs_<model_b>.md` has one
section per note with both candidate sentences, their translations, and
the LLM-reported confidence / flags / concerns for each.

Cache: every call also appends to `out/experiment_<model_name>.jsonl`
so re-running is cheap (skips notes already in the per-model cache).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path

from assess_naturalness import (
    load_naturalness_cache,
)
from dotenv import load_dotenv
from generate_sentences import (
    ANKI_MODEL_NAME,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_RETRIES,
    OUT_DIR,
    generate_one_sentence,
)
from google import genai

from lib.ankiconnect import ac
from lib.sentence_sampling import sample_sentence_form_for_note

HERE = Path(__file__).resolve().parents[1]


def cache_path_for_model(model_name: str) -> Path:
    safe = model_name.replace("/", "_")
    return OUT_DIR / f"experiment_{safe}.jsonl"


def load_per_model_cache(model_name: str) -> dict[int, dict]:
    path = cache_path_for_model(model_name)
    if not path.exists():
        return {}
    cache: dict[int, dict] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cache[entry["note_id"]] = entry
    return cache


def append_to_per_model_cache(model_name: str, entry: dict) -> None:
    path = cache_path_for_model(model_name)
    OUT_DIR.mkdir(exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def run_one_model(
    notes: list[dict],
    model_name: str,
    concurrency: int,
    max_retries: int,
) -> list[dict]:
    """Generate (or load from cache) one sentence per note for one model."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set — fill in .env.")
    client = genai.Client(api_key=api_key)

    cache = load_per_model_cache(model_name)
    notes_to_call = [n for n in notes if n["noteId"] not in cache]
    print(
        f"[{model_name}] {len(cache)} cached, {len(notes_to_call)} to call."
    )
    if notes_to_call:
        semaphore = asyncio.Semaphore(concurrency)
        tasks = [
            generate_one_sentence(client, model_name, n, semaphore, max_retries)
            for n in notes_to_call
        ]
        for completed_index, coro in enumerate(asyncio.as_completed(tasks), start=1):
            entry = await coro
            append_to_per_model_cache(model_name, entry)
            cache[entry["note_id"]] = entry
            label = "ERR" if "error" in entry else entry.get("confidence", "?")
            print(
                f"  [{model_name}] {completed_index}/{len(notes_to_call)} "
                f"note={entry['note_id']} {label}"
            )

    return [cache[n["noteId"]] for n in notes if n["noteId"] in cache]


def render_comparison_html(
    model_a: str,
    model_b: str,
    notes: list[dict],
    results_a: dict[int, dict],
    results_b: dict[int, dict],
) -> Path:
    """Standalone HTML page with side-by-side cards for eyeball comparison."""
    safe_a = model_a.replace("/", "_")
    safe_b = model_b.replace("/", "_")
    html_path = OUT_DIR / f"model_comparison_{safe_a}_vs_{safe_b}.html"

    # If the assessor has been run for either model's experiment file,
    # load its scores so we can display them inline.
    naturalness_a = load_naturalness_cache(
        OUT_DIR / f"experiment_{safe_a}.jsonl"
    )
    naturalness_b = load_naturalness_cache(
        OUT_DIR / f"experiment_{safe_b}.jsonl"
    )

    def html_escape(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def render_sentence_with_bold(value: str) -> str:
        # Allow the LLM's <b>...</b> markup through, escape everything else.
        placeholder_open = "\x01BOPEN\x01"
        placeholder_close = "\x01BCLOSE\x01"
        value = re.sub(r"<b\b[^>]*>", placeholder_open, value, flags=re.IGNORECASE)
        value = re.sub(r"</b>", placeholder_close, value, flags=re.IGNORECASE)
        escaped = html_escape(value)
        return escaped.replace(placeholder_open, "<b>").replace(placeholder_close, "</b>")

    def render_concern(label: str, concern: dict | None) -> str:
        if not concern or not concern.get("suspected"):
            return ""
        suggested = html_escape(concern.get("suggested", "") or "(no suggestion)")
        reason = html_escape(concern.get("reason", ""))
        return (
            f'<div class="concern"><span class="concern-label">{label}:</span> '
            f'<span class="suggested">{suggested}</span> '
            f'<span class="reason">— {reason}</span></div>'
        )

    def render_naturalness(score_entry: dict | None) -> str:
        if not score_entry or "error" in score_entry:
            return ""
        score = score_entry.get("naturalness_score")
        if score is None:
            return ""
        native = score_entry.get("native_would_say", False)
        issues = score_entry.get("issues") or []
        revision = score_entry.get("suggested_revision") or ""
        issues_html = (
            f'<div class="nat-issues">{html_escape("; ".join(issues))}</div>'
            if issues else ""
        )
        revision_html = (
            f'<div class="nat-revision">→ {render_sentence_with_bold(revision)}</div>'
            if revision else ""
        )
        native_html = "✓" if native else "✗ native-says=no"
        return (
            f'<div class="nat-block nat-{score}">'
            f'<span class="nat-score">nat {score}/5</span>'
            f'<span class="nat-native">{native_html}</span>'
            f'{issues_html}{revision_html}</div>'
        )

    def render_result_cell(model_label: str, result: dict | None, naturalness_cache: dict[int, dict]) -> str:
        if result is None:
            return f'<div class="cell"><div class="model">{html_escape(model_label)}</div><div class="missing">(no result)</div></div>'
        if "error" in result:
            return (
                f'<div class="cell error"><div class="model">{html_escape(model_label)}</div>'
                f'<div class="errmsg">ERROR: {html_escape(result["error"])}</div></div>'
            )
        confidence = result.get("confidence", "?")
        flags = result.get("flags") or []
        overrides = result.get("form_overrides") or []
        usage = result.get("usage") or {}
        bangla_html = render_sentence_with_bold(result["bangla_sentence"])
        english = html_escape(result["english_translation"])
        meta_bits = [
            f'<span class="conf conf-{confidence}">{html_escape(confidence)}</span>',
            f'<span class="attempt">attempt {result.get("attempt", "?")}</span>',
        ]
        if usage:
            meta_bits.append(
                f'<span class="tokens">in/out/cached '
                f'{usage.get("input_tokens", 0)}/'
                f'{usage.get("output_tokens", 0)}/'
                f'{usage.get("cached_input_tokens", 0)}</span>'
            )
        meta_line = " · ".join(meta_bits)
        flags_html = (
            f'<div class="flags">flags: {html_escape(", ".join(flags))}</div>'
            if flags else ""
        )
        overrides_html = (
            f'<div class="overrides">form overrides: {html_escape(", ".join(overrides))}</div>'
            if overrides else ""
        )
        nat_html = render_naturalness(naturalness_cache.get(result["note_id"]))
        return (
            f'<div class="cell"><div class="model">{html_escape(model_label)}</div>'
            f'<div class="meta">{meta_line}</div>'
            f'<div class="bn">{bangla_html}</div>'
            f'<div class="en">{english}</div>'
            f'{flags_html}{overrides_html}'
            f'{render_concern("headword", result.get("headword_concern"))}'
            f'{render_concern("definition", result.get("definition_concern"))}'
            f'{nat_html}'
            f'</div>'
        )

    note_blocks: list[str] = []
    for note in notes:
        note_id = note["noteId"]
        headword = note["fields"]["Bangla"]["value"]
        gloss = note["fields"]["Eng_trans"]["value"]
        form = sample_sentence_form_for_note(note_id)
        form_text = (
            f"{form.tense_and_aspect} · {form.sentence_type} · "
            f"{form.subject_person}"
            + (f" · 2p={form.second_person_register}" if form.sentence_type in ("interrogative", "imperative") or form.subject_person == "second_person_singular" else "")
            + (" · NEG" if form.is_negative else "")
        )
        note_blocks.append(
            f'<article class="note">'
            f'<header><h2>{html_escape(headword)} — {html_escape(gloss)}</h2>'
            f'<div class="noteid">note {note_id}</div>'
            f'<div class="form">sampled form: {html_escape(form_text)}</div></header>'
            f'<div class="row">{render_result_cell(model_a, results_a.get(note_id), naturalness_a)}'
            f'{render_result_cell(model_b, results_b.get(note_id), naturalness_b)}</div>'
            f'</article>'
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bangla sentence gen: {html_escape(model_a)} vs {html_escape(model_b)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #fafafa; color: #222; margin: 0; padding: 24px; }}
  h1 {{ font-size: 22px; margin: 0 0 16px 0; }}
  .intro {{ color: #555; margin-bottom: 24px; max-width: 64em; }}
  article.note {{ background: #fff; border-radius: 8px; padding: 16px 20px;
                  margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  article.note header h2 {{ font-family: "Noto Sans Bengali", sans-serif;
                            font-size: 22px; margin: 0; }}
  article.note .noteid {{ font-size: 12px; color: #888; }}
  article.note .form {{ font-size: 12px; color: #5586cd; margin-bottom: 12px; }}
  .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .cell {{ background: #f6f8fb; border-radius: 6px; padding: 12px 14px; }}
  .cell .model {{ font-size: 12px; color: #666; text-transform: uppercase;
                 letter-spacing: 1px; margin-bottom: 6px; }}
  .cell .meta {{ font-size: 11px; color: #888; margin-bottom: 8px; }}
  .cell .bn {{ font-family: "Noto Sans Bengali", "Hind Siliguri", sans-serif;
              font-size: 20px; line-height: 1.4; margin-bottom: 8px; }}
  .cell .bn b {{ color: #5586cd; }}
  .cell .en {{ color: #444; font-size: 14px; }}
  .cell .flags, .cell .overrides {{ font-size: 12px; color: #b07000; margin-top: 6px; }}
  .conf {{ font-weight: 600; }}
  .conf-high {{ color: #2e7d32; }} .conf-medium {{ color: #b07000; }}
  .conf-low {{ color: #c62828; }}
  .concern {{ font-size: 12px; color: #c62828; margin-top: 4px; }}
  .concern-label {{ font-weight: 600; }}
  .cell.error {{ background: #fdecea; }}
  .cell .errmsg {{ font-family: ui-monospace, monospace; font-size: 12px; color: #c62828; }}
  .cell .missing {{ font-style: italic; color: #888; }}
  .nat-block {{ margin-top: 10px; padding: 8px 10px; border-radius: 4px;
                font-size: 12px; }}
  .nat-5 {{ background: #e6f4ea; color: #1e6b32; }}
  .nat-4 {{ background: #f4f8e6; color: #5a6b1e; }}
  .nat-3 {{ background: #fff4e0; color: #8a5a00; }}
  .nat-2, .nat-1 {{ background: #fdecea; color: #b22222; }}
  .nat-score {{ font-weight: 700; margin-right: 8px; }}
  .nat-issues {{ margin-top: 4px; font-style: italic; }}
  .nat-revision {{ margin-top: 4px; font-family: "Noto Sans Bengali", sans-serif;
                   font-size: 16px; }}
</style>
</head>
<body>
<h1>Bangla sentence generation: <code>{html_escape(model_a)}</code> vs <code>{html_escape(model_b)}</code></h1>
<div class="intro">Sample size: {len(notes)} notes. Both models receive
identical prompts and (deterministic) sampled form constraints. Eyeball
quality side-by-side and pick the model that wins more often.</div>
{"".join(note_blocks)}
</body>
</html>
"""
    html_path.write_text(html)
    return html_path


def render_comparison_report(
    model_a: str,
    model_b: str,
    notes: list[dict],
    results_a: dict[int, dict],
    results_b: dict[int, dict],
) -> Path:
    safe_a = model_a.replace("/", "_")
    safe_b = model_b.replace("/", "_")
    report_path = OUT_DIR / f"model_comparison_{safe_a}_vs_{safe_b}.md"

    lines: list[str] = [
        f"# Bangla sentence generation: `{model_a}` vs `{model_b}`",
        "",
        f"Sample size: {len(notes)} notes.",
        "",
        "Both models receive identical prompts and (deterministic) form constraints.",
        "Compare quality side-by-side; pick the model that wins more often.",
        "",
    ]

    def format_concern(label: str, concern: dict | None) -> str:
        if not concern or not concern.get("suspected"):
            return ""
        suggested = concern.get("suggested", "")
        reason = concern.get("reason", "")
        return f"  - **{label} concern:** {suggested or '(no suggestion)'} — {reason}\n"

    for note in notes:
        note_id = note["noteId"]
        bangla = note["fields"]["Bangla"]["value"]
        gloss = note["fields"]["Eng_trans"]["value"]
        result_a = results_a.get(note_id)
        result_b = results_b.get(note_id)

        lines.append(f"## {bangla} — {gloss} (note {note_id})\n")
        for model_label, result in ((model_a, result_a), (model_b, result_b)):
            if result is None:
                lines.append(f"**{model_label}**: (no result)\n")
                continue
            if "error" in result:
                lines.append(f"**{model_label}**: ERROR — {result['error']}\n")
                continue
            lines.append(
                f"**{model_label}** ({result.get('confidence', '?')}, "
                f"attempt {result.get('attempt', '?')}):  \n"
                f"  - BN: {result['bangla_sentence']}  \n"
                f"  - EN: {result['english_translation']}  \n"
            )
            if result.get("flags"):
                lines.append(f"  - flags: {', '.join(result['flags'])}\n")
            if result.get("form_overrides"):
                lines.append(
                    f"  - form overrides: {', '.join(result['form_overrides'])}\n"
                )
            lines.append(format_concern("headword", result.get("headword_concern")))
            lines.append(format_concern("definition", result.get("definition_concern")))
        lines.append("")

    report_path.write_text("".join(line if line.endswith("\n") else line + "\n" for line in lines))
    return report_path


def pick_notes(args: argparse.Namespace) -> list[dict]:
    if args.note_ids:
        target_ids = [int(x) for x in args.note_ids.split(",") if x.strip()]
    else:
        # Sample from notes missing an example sentence (see note in
        # generate_bangla_sentences.find_notes_needing_sentences).
        all_missing = ac(
            "findNotes", query=f'"note:{ANKI_MODEL_NAME}" -Example:_*'
        )
        if args.seed is not None:
            random.Random(args.seed).shuffle(all_missing)
        else:
            random.shuffle(all_missing)
        target_ids = all_missing[: args.limit]

    notes: list[dict] = []
    chunk = 200
    for i in range(0, len(target_ids), chunk):
        notes.extend(ac("notesInfo", notes=target_ids[i : i + chunk]))
    return notes


async def main_async(args: argparse.Namespace) -> None:
    notes = pick_notes(args)
    print(f"Comparing on {len(notes)} notes.")

    # Run both models in parallel — independent APIs / quotas.
    results_a_list, results_b_list = await asyncio.gather(
        run_one_model(notes, args.model_a, args.concurrency, args.max_retries),
        run_one_model(notes, args.model_b, args.concurrency, args.max_retries),
    )

    results_a = {e["note_id"]: e for e in results_a_list}
    results_b = {e["note_id"]: e for e in results_b_list}

    report_path = render_comparison_report(
        args.model_a, args.model_b, notes, results_a, results_b
    )
    html_path = render_comparison_html(
        args.model_a, args.model_b, notes, results_a, results_b
    )
    print(f"\nWrote {report_path}")
    print(f"Wrote {html_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-a", default="gemini-3-flash-preview")
    parser.add_argument("--model-b", default="gemini-2.5-flash")
    parser.add_argument("--limit", type=int, default=20, help="Sample size (default 20).")
    parser.add_argument("--note-ids", help="Comma-separated note ids; overrides --limit.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
