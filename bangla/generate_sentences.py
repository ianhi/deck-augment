"""Generate Kolkata Bengali example sentences for the Bangla Card v2 notes
via Gemini, then optionally apply them to the deck.

Pipeline:
  1. Find Bangla notes missing an example sentence (no Example field).
  2. For each, sample form constraints from `sentence_sampling`.
  3. Build a per-note prompt (system + user) and call the Gemini API,
     one call per card (quality > batching).
  4. Validate the JSON response. Derive ExampleCloze locally by
     replacing the <b>...</b> content with <span class="cloze">[...]</span>
     (no extra LLM tokens spent on that).
  5. Cache every result to `out/bangla_sentences.jsonl` keyed by note id
     so re-runs skip work already done.
  6. With `--apply`, write Example / ExampleCloze / ExampleTranslation
     back to Anki via AnkiConnect.

Usage:
  uv run generate_bangla_sentences.py --limit 30           # 30-card sample
  uv run generate_bangla_sentences.py --note-ids 1,2,3     # specific cards
  uv run generate_bangla_sentences.py                      # full run (~2279)
  uv run generate_bangla_sentences.py --apply              # push cached to Anki
  uv run generate_bangla_sentences.py --regenerate         # ignore cache, redo
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from lib.gemini_prompts import BANGLA_SENTENCE_SYSTEM as _SYSTEM_PROMPT_FOR_HASH
from lib.gemini_prompts import BANGLA_SENTENCE_USER as _USER_TEMPLATE_FOR_HASH

# Bump this when we want all cached results invalidated (e.g. after a
# substantive prompt or distribution change). Combined with a hash of
# the current prompt strings, results from older prompts are skipped
# when re-runs are requested.
PROMPT_VERSION_TAG = "v1"


def current_prompt_signature() -> str:
    """Short hash that changes when the prompt content changes."""
    h = hashlib.sha256()
    h.update(PROMPT_VERSION_TAG.encode())
    h.update(b"\n")
    h.update(_SYSTEM_PROMPT_FOR_HASH.encode())
    h.update(b"\n")
    h.update(_USER_TEMPLATE_FOR_HASH.encode())
    return h.hexdigest()[:12]

from lib.ankiconnect import ac
from lib.gemini_prompts import BANGLA_SENTENCE_SYSTEM, BANGLA_SENTENCE_USER
from lib.sentence_sampling import sample_sentence_form_for_note

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
RESULTS_PATH = OUT_DIR / "bangla_sentences.jsonl"
CONCERNS_REPORT_PATH = OUT_DIR / "bangla_concerns_report.md"

# Gemini pricing in USD per 1M tokens. Values are best-effort as of
# 2026-05; verify on https://ai.google.dev/pricing before relying on the
# cost summary. cached_input_per_million is the implicit-cache rate (the
# Gemini API automatically discounts repeated prefixes long enough to
# qualify; check usage_metadata.cached_content_token_count to see how
# much actually got cached).
MODEL_PRICING_PER_MILLION_USD: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {
        "input": 0.30,
        "cached_input": 0.075,
        "output": 2.50,
    },
    "gemini-2.5-flash-lite": {
        "input": 0.10,
        "cached_input": 0.025,
        "output": 0.40,
    },
    "gemini-3-flash-preview": {
        # Treat as a placeholder until verified; structured the same as
        # 2.5-flash so the cost line stays in scale.
        "input": 0.30,
        "cached_input": 0.075,
        "output": 2.50,
    },
}

ANKI_MODEL_NAME = "Bangla (and reversed)"

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_CONCURRENCY = 6
DEFAULT_MAX_RETRIES = 3

# Legacy sense / disambig fields, used to feed Gemini extra semantic context.
DISAMBIG_SOURCE_FIELDS = (
    "eng-disambig",
    "bangla-def",
    "type",
    "bangla-disambig",
    "explanation",
)


# ---------- Helpers --------------------------------------------------------

def derive_example_cloze_from_bolded(bangla_sentence: str) -> str:
    """Replace <b>...</b> content with a styled bracketed blank.

    Output uses <span class="cloze">[...]</span>, matching Anki's default
    cloze look. Robust across Anki Desktop / Mobile / Droid (pure HTML,
    no JS)."""
    return re.sub(
        r"<b\b[^>]*>.*?</b>",
        '<span class="cloze">[...]</span>',
        bangla_sentence,
        flags=re.IGNORECASE | re.DOTALL,
    )


def validate_bangla_sentence(sentence: str, headword: str) -> list[str]:
    """Local quality gates — no LLM tokens spent. Return a list of issues
    (empty list means the sentence passes).

    Word count is allowed down to 2 words to accommodate interjections
    like ধন্যবাদ. The bold check also confirms the bolded text shares a
    Bangla-character prefix with the headword (loose morphological
    relatedness check — catches the LLM bolding the wrong word).
    """
    issues: list[str] = []
    bold_matches = re.findall(r"<b\b[^>]*>(.*?)</b>", sentence, flags=re.DOTALL | re.IGNORECASE)
    if len(bold_matches) == 0:
        issues.append("missing <b>...</b> bolded headword")
    elif len(bold_matches) > 1:
        issues.append(f"expected exactly one <b>...</b>, found {len(bold_matches)}")
    # Note: we used to require a 3-char prefix match between bolded text
    # and headword, but that fails on Bangla suppletive (আছে → থাকত) and
    # ablaut (চেনা → চিনে, ঢোকা → ঢুকছে) verb forms. Wrong-word bolding
    # is caught downstream by the LLM's headword_concern flag and the
    # naturalness assessor.
    plain_text = re.sub(r"<[^>]+>", "", sentence).strip()
    word_count = len(plain_text.split())
    if not 2 <= word_count <= 18:
        issues.append(f"word count {word_count} out of range 2-18")
    if not plain_text.endswith(("।", "?", "!")):
        issues.append("sentence does not end with a Bangla terminator (।?!)")
    return issues


HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html_to_plain(value: str) -> str:
    """Cheap HTML → plain text for disambig fields that may contain markup."""
    # Replace <br> variants with a space so words don't run together.
    text = re.sub(r"<\s*br\s*/?\s*>", " ", value, flags=re.IGNORECASE)
    text = HTML_TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def build_disambig_block(note_fields: dict[str, dict]) -> str:
    """Concatenate non-empty legacy disambig fields for prompt injection.

    Strips HTML — these legacy fields sometimes contain <br>, <i>, image
    refs, etc. that would confuse the LLM if passed raw.
    """
    parts: list[str] = []
    for field_name in DISAMBIG_SOURCE_FIELDS:
        if field_name not in note_fields:
            continue
        value = strip_html_to_plain(note_fields[field_name]["value"])
        if value:
            parts.append(f"- {field_name}: {value}")
    if not parts:
        return "(no hints — pick the most common sense)"
    return "\n".join(parts)


def load_results_cache() -> dict[int, dict]:
    """Load previously generated sentences keyed by note id."""
    if not RESULTS_PATH.exists():
        return {}
    cache: dict[int, dict] = {}
    with RESULTS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cache[entry["note_id"]] = entry
    return cache


def append_result(entry: dict) -> None:
    """Append one result to the JSONL cache (atomic per line)."""
    OUT_DIR.mkdir(exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find_notes_needing_sentences() -> list[int]:
    """Notes of the Bangla model with an empty Example field.

    Anki search syntax: `-Example:_*` means "Example field does NOT match
    any non-empty string", i.e. empty. (Earlier we used `Example:` which
    Anki parses as a free-text search, not a field-empty check.)
    """
    query = f'"note:{ANKI_MODEL_NAME}" -Example:_*'
    return ac("findNotes", query=query)


# ---------- Generation ----------------------------------------------------

async def generate_one_sentence(
    client: genai.Client,
    model_name: str,
    note: dict,
    semaphore: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    """Single-note generation with retries. Returns a result entry.

    On validation failure, the next retry includes the previous failed
    sentence + the issues so the model can correct itself rather than
    blindly resampling.
    """
    note_id = note["noteId"]
    headword = note["fields"]["Bangla"]["value"]
    form = sample_sentence_form_for_note(note_id)
    base_user_prompt = BANGLA_SENTENCE_USER.format(
        bangla=headword,
        eng_trans=strip_html_to_plain(note["fields"]["Eng_trans"]["value"]),
        disambig_block=build_disambig_block(note["fields"]),
        form_block=form.describe_for_prompt(),
    )

    async with semaphore:
        last_error: str | None = None
        prior_failure_text: str | None = None
        for attempt in range(1, max_retries + 1):
            user_prompt = base_user_prompt
            if prior_failure_text:
                user_prompt = (
                    f"{base_user_prompt}\n\n"
                    f"# Previous attempt failed local validation\n"
                    f"{prior_failure_text}\n"
                    f"Produce a corrected JSON object addressing the issues."
                )
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_SENTENCE_SYSTEM,
                        response_mime_type="application/json",
                        # Disable thinking — generating one short Bengali
                        # sentence with structured output doesn't benefit
                        # from chain-of-thought, and the thoughts tokens
                        # are billed at the output rate. Empirically this
                        # was ~560 wasted tokens/call on 2.5-flash.
                        thinking_config=genai_types.ThinkingConfig(
                            thinking_budget=0
                        ),
                    ),
                )
                payload = json.loads(response.text)
                # Occasionally Gemini wraps the object in a single-element
                # list. Unwrap if so; otherwise let the type check fail.
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    payload = payload[0]
                if not isinstance(payload, dict):
                    raise ValueError(f"expected JSON object, got {type(payload).__name__}")
                bangla_sentence = payload["bangla_sentence"]
                validation_issues = validate_bangla_sentence(bangla_sentence, headword)
                if validation_issues:
                    last_error = "validation: " + "; ".join(validation_issues)
                    prior_failure_text = (
                        f"prior bangla_sentence: {bangla_sentence}\n"
                        f"issues: {'; '.join(validation_issues)}"
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                usage = getattr(response, "usage_metadata", None)
                usage_record = {
                    "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                    "cached_input_tokens":
                        getattr(usage, "cached_content_token_count", 0) or 0,
                    "output_tokens":
                        getattr(usage, "candidates_token_count", 0) or 0,
                    "thoughts_tokens":
                        getattr(usage, "thoughts_token_count", 0) or 0,
                }
                return {
                    "note_id": note_id,
                    "bangla_headword": note["fields"]["Bangla"]["value"],
                    "english_gloss_input": note["fields"]["Eng_trans"]["value"],
                    "bangla_sentence": bangla_sentence,
                    "example_cloze": derive_example_cloze_from_bolded(bangla_sentence),
                    "english_translation": payload["english_translation"],
                    "produced_form": payload.get("produced_form", {}),
                    "form_overrides": payload.get("form_overrides", []),
                    "confidence": payload.get("confidence", "unknown"),
                    "flags": payload.get("flags", []),
                    "headword_concern": payload.get("headword_concern", {"suspected": False}),
                    "definition_concern": payload.get("definition_concern", {"suspected": False}),
                    "sampled_form": {
                        "tense_and_aspect": form.tense_and_aspect,
                        "second_person_register": form.second_person_register,
                        "subject_person": form.subject_person,
                        "sentence_type": form.sentence_type,
                        "is_negative": form.is_negative,
                    },
                    "model": model_name,
                    "attempt": attempt,
                    "usage": usage_record,
                    "prompt_signature": current_prompt_signature(),
                }
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                last_error = f"parse error: {e}"
                await asyncio.sleep(2 * attempt)
            except genai_errors.APIError as e:
                # 429 / 5xx: back off harder with jitter so concurrent
                # tasks don't retry in lockstep.
                last_error = f"api error: {e}"
                status_code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if status_code in (429, 500, 502, 503, 504):
                    base = 4 * attempt
                    jitter = random.uniform(0, base / 2)
                    await asyncio.sleep(base + jitter)
                else:
                    await asyncio.sleep(2 * attempt)
        return {
            "note_id": note_id,
            "bangla_headword": note["fields"]["Bangla"]["value"],
            "error": last_error,
            "model": model_name,
        }


def estimate_cost_usd(model_name: str, totals: dict[str, int]) -> float:
    """Estimate USD cost from cumulative usage totals for a model run."""
    pricing = MODEL_PRICING_PER_MILLION_USD.get(model_name)
    if not pricing:
        return 0.0
    billable_input = totals["input_tokens"] - totals["cached_input_tokens"]
    return (
        billable_input * pricing["input"]
        + totals["cached_input_tokens"] * pricing["cached_input"]
        + (totals["output_tokens"] + totals["thoughts_tokens"]) * pricing["output"]
    ) / 1_000_000


async def run_generation(
    notes: list[dict],
    model_name: str,
    concurrency: int,
    max_retries: int,
) -> None:
    """Generate sentences for the supplied notes, streaming results to disk."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set — fill in .env.")
    client = genai.Client(api_key=api_key)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        generate_one_sentence(client, model_name, n, semaphore, max_retries)
        for n in notes
    ]

    completed = 0
    successes = 0
    errors = 0
    cumulative_usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "thoughts_tokens": 0,
    }
    for coroutine in asyncio.as_completed(tasks):
        entry = await coroutine
        append_result(entry)
        completed += 1
        if "error" in entry:
            errors += 1
            print(
                f"  [{completed}/{len(tasks)}] ERR note {entry['note_id']} "
                f"({entry['bangla_headword']}): {entry['error']}"
            )
            continue
        successes += 1
        usage = entry.get("usage", {})
        for key in cumulative_usage:
            cumulative_usage[key] += usage.get(key, 0) or 0
        running_cost = estimate_cost_usd(model_name, cumulative_usage)
        print(
            f"  [{completed}/{len(tasks)}] OK note {entry['note_id']} "
            f"({entry['bangla_headword']}) conf={entry['confidence']} "
            f"tokens in/out/cached={usage.get('input_tokens', 0)}/"
            f"{usage.get('output_tokens', 0)}/{usage.get('cached_input_tokens', 0)} "
            f"run ~${running_cost:.4f}"
        )

    final_cost = estimate_cost_usd(model_name, cumulative_usage)
    cached_fraction = (
        cumulative_usage["cached_input_tokens"] / cumulative_usage["input_tokens"]
        if cumulative_usage["input_tokens"]
        else 0.0
    )
    print()
    print(f"Done. {successes} succeeded, {errors} errored.")
    print(
        f"Token totals  input={cumulative_usage['input_tokens']:,}  "
        f"output={cumulative_usage['output_tokens']:,}  "
        f"cached={cumulative_usage['cached_input_tokens']:,} "
        f"({100 * cached_fraction:.1f}% of input)  "
        f"thoughts={cumulative_usage['thoughts_tokens']:,}"
    )
    print(
        f"Estimated cost  ${final_cost:.4f} "
        f"(model={model_name!r}; verify pricing on ai.google.dev/pricing)"
    )
    write_concerns_report()


# ---------- Apply (write cached results back to Anki) ---------------------

def write_concerns_report() -> None:
    """Render headword + definition concerns from cached results to markdown."""
    cache = load_results_cache()
    headword_concerns: list[dict] = []
    definition_concerns: list[dict] = []
    for entry in cache.values():
        if "error" in entry:
            continue
        hc = entry.get("headword_concern", {})
        dc = entry.get("definition_concern", {})
        if hc.get("suspected"):
            headword_concerns.append(entry)
        if dc.get("suspected"):
            definition_concerns.append(entry)

    OUT_DIR.mkdir(exist_ok=True)
    lines: list[str] = [
        "# Bangla input-quality concerns flagged by Gemini",
        "",
        "Each row is a note where the model suspected a typo or definition issue ",
        "while generating the example sentence. Review and apply manually in Anki.",
        "",
        f"## Headword spelling concerns ({len(headword_concerns)})",
        "",
        "| Note id | Current Bangla | Suggested | Reason | English gloss |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(headword_concerns, key=lambda x: x["note_id"]):
        hc = e["headword_concern"]
        lines.append(
            f"| {e['note_id']} | {e['bangla_headword']} | "
            f"{hc.get('suggested', '')} | {hc.get('reason', '')} | "
            f"{e.get('english_gloss_input', '')} |"
        )
    lines += [
        "",
        f"## Definition concerns ({len(definition_concerns)})",
        "",
        "| Note id | Bangla | Current gloss | Suggested | Reason |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(definition_concerns, key=lambda x: x["note_id"]):
        dc = e["definition_concern"]
        lines.append(
            f"| {e['note_id']} | {e['bangla_headword']} | "
            f"{e.get('english_gloss_input', '')} | "
            f"{dc.get('suggested', '')} | {dc.get('reason', '')} |"
        )

    CONCERNS_REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(
        f"Wrote {CONCERNS_REPORT_PATH}: "
        f"{len(headword_concerns)} headword + {len(definition_concerns)} definition concerns."
    )


def apply_cached_results_to_anki() -> None:
    cache = load_results_cache()
    successful = [e for e in cache.values() if "error" not in e]
    print(f"{len(successful)} successful results in cache.")

    confidence_counts = Counter(e.get("confidence", "unknown") for e in successful)
    print(f"  by confidence: {dict(confidence_counts)}")

    # Batch-fetch current values so we skip notes whose three fields
    # already match the cached entry (idempotent re-apply).
    note_ids = [e["note_id"] for e in successful]
    current: dict[int, dict[str, str]] = {}
    for i in range(0, len(note_ids), 500):
        for n in ac("notesInfo", notes=note_ids[i : i + 500]):
            current[n["noteId"]] = {
                "Example": n["fields"].get("Example", {}).get("value", ""),
                "ExampleCloze": n["fields"].get("ExampleCloze", {}).get("value", ""),
                "ExampleTranslation":
                    n["fields"].get("ExampleTranslation", {}).get("value", ""),
            }

    updated = 0
    unchanged = 0
    skipped_low = 0
    for entry in successful:
        if entry.get("confidence") == "low":
            skipped_low += 1
            continue
        nid = entry["note_id"]
        desired = {
            "Example": entry["bangla_sentence"],
            "ExampleCloze": entry["example_cloze"],
            "ExampleTranslation": entry["english_translation"],
        }
        if current.get(nid) == desired:
            unchanged += 1
            continue
        ac("updateNoteFields", note={"id": nid, "fields": desired})
        updated += 1
    print(
        f"Pushed {updated}; {unchanged} already up-to-date; "
        f"skipped {skipped_low} low-confidence."
    )


# ---------- CLI ------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate at most N notes (default: all needing sentences).",
    )
    parser.add_argument(
        "--note-ids",
        help="Comma-separated note ids to generate; overrides discovery.",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Ignore the cache and call Gemini again for every selected note.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Push cached results to Anki (no Gemini calls).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Regenerate out/bangla_concerns_report.md from cached results.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        help=f"Gemini model id (default: env GEMINI_MODEL or {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent Gemini calls (default {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Per-note retry budget (default {DEFAULT_MAX_RETRIES}).",
    )
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    if args.report:
        write_concerns_report()
        return

    if args.apply:
        apply_cached_results_to_anki()
        return

    # Decide which note ids to operate on.
    if args.note_ids:
        target_ids = [int(x) for x in args.note_ids.split(",") if x.strip()]
    else:
        target_ids = find_notes_needing_sentences()
        print(f"{len(target_ids)} notes have empty Example field.")

    # Filter against cache unless --regenerate.
    cache = load_results_cache()
    current_sig = current_prompt_signature()
    if not args.regenerate:
        before = len(target_ids)
        fresh_cache_ids = {
            nid for nid, entry in cache.items()
            if "error" not in entry
            and entry.get("prompt_signature") == current_sig
        }
        target_ids = [nid for nid in target_ids if nid not in fresh_cache_ids]
        skipped = before - len(target_ids)
        stale = sum(
            1 for nid in cache
            if cache[nid].get("prompt_signature") != current_sig
        )
        print(
            f"  {skipped} cached with current prompt {current_sig!r}; "
            f"{stale} stale (will be regenerated); {len(target_ids)} to do."
        )

    if args.limit is not None:
        target_ids = target_ids[: args.limit]
        print(f"Limited to {len(target_ids)} notes.")

    if not target_ids:
        print("Nothing to generate. Use --apply to push cached results to Anki.")
        return

    # Pull note bodies once.
    notes: list[dict] = []
    chunk = 200
    for i in range(0, len(target_ids), chunk):
        notes.extend(ac("notesInfo", notes=target_ids[i : i + chunk]))

    print(
        f"Generating with model={args.model!r} concurrency={args.concurrency} "
        f"retries={args.max_retries}"
    )
    try:
        asyncio.run(
            run_generation(
                notes=notes,
                model_name=args.model,
                concurrency=args.concurrency,
                max_retries=args.max_retries,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Partial results in", RESULTS_PATH)
        sys.exit(130)


if __name__ == "__main__":
    main()
