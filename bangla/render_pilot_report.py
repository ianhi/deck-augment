"""Render a single-model HTML pilot report combining:
  - generated Bangla sentences (out/bangla_sentences.jsonl)
  - Gemini naturalness assessments (out/naturalness_bangla_sentences.jsonl)
  - the original note data (Bangla headword, gloss, disambig) from Anki

Sorts by naturalness score ascending so low-scoring cards are at the top
for review. Drops nothing — every entry gets a card.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import re
from pathlib import Path

from lib.ankiconnect import ac

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_sentence_with_bold(value: str) -> str:
    open_marker, close_marker = "\x01B\x01", "\x01b\x01"
    value = re.sub(r"<b\b[^>]*>", open_marker, value, flags=re.IGNORECASE)
    value = re.sub(r"</b>", close_marker, value, flags=re.IGNORECASE)
    return html_escape(value).replace(open_marker, "<b>").replace(close_marker, "</b>")


def render_concern(label: str, concern: dict | None) -> str:
    if not concern or not concern.get("suspected"):
        return ""
    return (
        f'<div class="concern"><span class="concern-label">{label}:</span> '
        f'{html_escape(concern.get("suggested") or "(no suggestion)")} '
        f'<span class="reason">— {html_escape(concern.get("reason", ""))}</span></div>'
    )


def render_naturalness(entry: dict | None) -> str:
    if not entry or "error" in entry:
        return ""
    score = entry.get("naturalness_score")
    if score is None:
        return ""
    native = entry.get("native_would_say", False)
    issues = entry.get("issues") or []
    revision = entry.get("suggested_revision") or ""
    issues_html = (
        f'<div class="nat-issues">{html_escape("; ".join(issues))}</div>'
        if issues else ""
    )
    revision_html = (
        f'<div class="nat-revision">→ {render_sentence_with_bold(revision)}</div>'
        if revision else ""
    )
    native_label = "✓ native" if native else "✗ native-says-no"
    return (
        f'<div class="nat-block nat-{score}">'
        f'<span class="nat-score">naturalness {score}/5</span>'
        f'<span class="nat-native">{native_label}</span>'
        f'{issues_html}{revision_html}</div>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=OUT_DIR / "bangla_sentences.jsonl",
        help="Generated-sentences JSONL.",
    )
    parser.add_argument(
        "--naturalness",
        type=Path,
        default=OUT_DIR / "naturalness_bangla_sentences.jsonl",
        help="Naturalness-scores JSONL.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_DIR / "pilot_report.html",
        help="Where to write the HTML.",
    )
    parser.add_argument(
        "--sort",
        choices=("score-asc", "score-desc", "note-id"),
        default="score-asc",
        help="Card order in the report.",
    )
    args = parser.parse_args()

    src_entries = [
        json.loads(line)
        for line in args.source.read_text().splitlines()
        if line.strip()
    ]
    src = {e["note_id"]: e for e in src_entries if "error" not in e}

    nat_entries = (
        [json.loads(line) for line in args.naturalness.read_text().splitlines() if line.strip()]
        if args.naturalness.exists() else []
    )
    nat = {e["note_id"]: e for e in nat_entries if "error" not in e}

    note_ids = list(src.keys())
    note_info: dict[int, dict] = {}
    for i in range(0, len(note_ids), 200):
        for n in ac("notesInfo", notes=note_ids[i : i + 200]):
            note_info[n["noteId"]] = n

    def sort_key(nid: int) -> tuple:
        score = nat.get(nid, {}).get("naturalness_score", 5)
        if args.sort == "score-asc":
            return (score, nid)
        if args.sort == "score-desc":
            return (-score, nid)
        return (nid,)

    sorted_ids = sorted(note_ids, key=sort_key)

    blocks: list[str] = []
    for nid in sorted_ids:
        entry = src[nid]
        note = note_info.get(nid, {})
        fields = note.get("fields", {})
        headword = entry["bangla_headword"]
        gloss = fields.get("Eng_trans", {}).get("value", "")

        sampled = entry.get("sampled_form", {})
        produced = entry.get("produced_form", {})
        confidence = entry.get("confidence", "?")
        flags = entry.get("flags") or []
        overrides = entry.get("form_overrides") or []
        bangla_html = render_sentence_with_bold(entry["bangla_sentence"])
        english_html = html_escape(entry["english_translation"])

        sampled_text = " · ".join(filter(None, [
            sampled.get("tense_and_aspect"),
            sampled.get("sentence_type"),
            sampled.get("subject_person"),
            (sampled.get("second_person_register")
             if sampled.get("subject_person") == "second_person_singular"
             or sampled.get("sentence_type") in ("interrogative", "imperative")
             else None),
            ("NEG" if sampled.get("is_negative") else None),
        ]))
        flags_html = (
            f'<div class="flags">flags: {html_escape(", ".join(flags))}</div>'
            if flags else ""
        )
        overrides_html = (
            "<div class=\"overrides\"><strong>form overrides:</strong><ul>"
            + "".join(f"<li>{html_escape(o)}</li>" for o in overrides)
            + "</ul></div>"
        ) if overrides else ""

        blocks.append(
            f'<article class="note">'
            f'<header><h2>{html_escape(headword)} '
            f'<span class="gloss">— {html_escape(gloss)}</span></h2>'
            f'<div class="meta">note {nid} · '
            f'<span class="conf conf-{confidence}">{html_escape(confidence)}</span> · '
            f'sampled: {html_escape(sampled_text)}</div></header>'
            f'<div class="bn">{bangla_html}</div>'
            f'<div class="en">{english_html}</div>'
            f'{flags_html}{overrides_html}'
            f'{render_concern("headword", entry.get("headword_concern"))}'
            f'{render_concern("definition", entry.get("definition_concern"))}'
            f'{render_naturalness(nat.get(nid))}'
            f'</article>'
        )

    counts = {2: 0, 3: 0, 4: 0, 5: 0}
    for nid in note_ids:
        s = nat.get(nid, {}).get("naturalness_score")
        if s in counts:
            counts[s] += 1
    summary = " · ".join(f"{n}×{s}/5" for s, n in sorted(counts.items()))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bangla sentence pilot — {len(note_ids)} cards</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #fafafa; color: #222; margin: 0; padding: 24px; }}
  h1 {{ font-size: 22px; margin: 0 0 8px 0; }}
  .summary {{ color: #555; margin-bottom: 24px; }}
  article.note {{ background: #fff; border-radius: 8px; padding: 14px 18px;
                  margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  article.note header h2 {{ font-family: "Noto Sans Bengali", sans-serif;
                            font-size: 20px; margin: 0; }}
  article.note .gloss {{ color: #666; font-size: 16px; font-weight: 400; }}
  article.note .meta {{ font-size: 12px; color: #888; margin: 4px 0 10px 0; }}
  .bn {{ font-family: "Noto Sans Bengali", "Hind Siliguri", sans-serif;
         font-size: 20px; line-height: 1.4; }}
  .bn b {{ color: #5586cd; }}
  .en {{ color: #444; font-size: 14px; margin-top: 4px; }}
  .conf {{ font-weight: 600; }}
  .conf-high {{ color: #2e7d32; }} .conf-medium {{ color: #b07000; }}
  .conf-low {{ color: #c62828; }}
  .flags, .overrides {{ font-size: 12px; color: #b07000; margin-top: 6px; }}
  .overrides ul {{ margin: 2px 0 0 16px; padding: 0; }}
  .concern {{ font-size: 13px; color: #c62828; margin-top: 6px; }}
  .concern-label {{ font-weight: 600; }}
  .nat-block {{ margin-top: 10px; padding: 8px 10px; border-radius: 4px;
                font-size: 12px; }}
  .nat-5 {{ background: #e6f4ea; color: #1e6b32; }}
  .nat-4 {{ background: #f4f8e6; color: #5a6b1e; }}
  .nat-3 {{ background: #fff4e0; color: #8a5a00; }}
  .nat-2, .nat-1 {{ background: #fdecea; color: #b22222; }}
  .nat-score {{ font-weight: 700; margin-right: 8px; }}
  .nat-native {{ font-style: italic; }}
  .nat-issues {{ margin-top: 4px; }}
  .nat-revision {{ margin-top: 4px; font-family: "Noto Sans Bengali", sans-serif;
                   font-size: 16px; }}
</style>
</head>
<body>
<h1>Bangla sentence-generation pilot: {len(note_ids)} cards</h1>
<div class="summary">Naturalness distribution: {summary}. Sorted by score
ascending — low-quality cards at the top for review.</div>
{"".join(blocks)}
</body>
</html>
"""
    args.out.write_text(html)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
