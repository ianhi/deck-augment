"""Apply Gemini's `suggested_revision` to low-scoring cards in the main
sentence cache.

For each card where the naturalness assessor scored <= --threshold AND
returned a non-empty `suggested_revision`, this script:
  1. Replaces `bangla_sentence` in the cache entry with the revision.
  2. Recomputes `example_cloze` locally.
  3. Calls Gemini to translate the revised sentence into English (the
     original translation is no longer accurate).
  4. Tags the entry with `revision_source: "gemini_qa"` so we can audit.

The original entry is preserved under `revision_history` in case we
want to roll back.

Dry-run by default. Pass `--apply` to write the updated cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from generate_sentences import (
    DEFAULT_MODEL,
    RESULTS_PATH,
    build_disambig_block,
    derive_example_cloze_from_bolded,
    load_results_cache,
)
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from lib.ankiconnect import ac
from lib.gemini_prompts import BANGLA_TRANSLATION_SYSTEM, BANGLA_TRANSLATION_USER

HERE = Path(__file__).resolve().parents[1]
NATURALNESS_PATH = HERE / "out" / "naturalness_bangla_sentences.jsonl"


def load_naturalness() -> dict[int, dict]:
    if not NATURALNESS_PATH.exists():
        raise SystemExit(f"No naturalness cache at {NATURALNESS_PATH}")
    out: dict[int, dict] = {}
    for line in NATURALNESS_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if "error" not in entry:
            out[entry["note_id"]] = entry
    return out


def find_revision_candidates(threshold: int) -> list[tuple[dict, dict]]:
    """Return (source_entry, naturalness_entry) tuples for cards eligible
    for revision. Filters out revisions that drop the headword — those
    need full regeneration, not a substitution."""
    import re

    nat = load_naturalness()
    source = load_results_cache()
    candidates: list[tuple[dict, dict]] = []
    skipped_headword_lost: list[tuple[str, str]] = []
    for note_id, src in source.items():
        if "error" in src:
            continue
        if src.get("revision_source"):
            continue
        n = nat.get(note_id)
        if not n or n.get("naturalness_score", 5) > threshold:
            continue
        revision = (n.get("suggested_revision") or "").strip()
        if not revision:
            continue
        headword = src["bangla_headword"].strip()
        revision_plain = re.sub(r"<[^>]+>", "", revision)
        # Accept the revision only if the headword (or its first 3 chars,
        # to allow inflection) appears anywhere in the revised sentence.
        prefix = headword[:3]
        if prefix and prefix not in revision_plain:
            skipped_headword_lost.append((src["bangla_headword"], revision))
            continue
        candidates.append((src, n))

    if skipped_headword_lost:
        print(
            f"Skipping {len(skipped_headword_lost)} revisions that drop the headword "
            "(needs regen, not substitution):"
        )
        for hw, rev in skipped_headword_lost:
            print(f"  {hw}: {rev}")
        print()

    return candidates


async def translate_revision(
    client: genai.Client,
    model_name: str,
    note: dict,
    revised_bangla: str,
) -> dict:
    """Call Gemini for an English translation of the revised sentence."""
    user_prompt = BANGLA_TRANSLATION_USER.format(
        bangla=note["fields"]["Bangla"]["value"],
        eng_trans=note["fields"]["Eng_trans"]["value"],
        disambig_block=build_disambig_block(note["fields"]),
        bangla_sentence=revised_bangla,
    )
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=BANGLA_TRANSLATION_SYSTEM,
            response_mime_type="application/json",
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(response.text.lstrip())
    return payload


async def revise_one(
    client: genai.Client,
    model_name: str,
    semaphore: asyncio.Semaphore,
    src_entry: dict,
    nat_entry: dict,
    anki_note: dict,
) -> dict:
    """Build the revised cache entry. Does NOT write anywhere — caller
    decides."""
    async with semaphore:
        revision = nat_entry["suggested_revision"].strip()
        new_cloze = derive_example_cloze_from_bolded(revision)
        try:
            translation_payload = await translate_revision(
                client, model_name, anki_note, revision
            )
        except genai_errors.APIError as e:
            return {"note_id": src_entry["note_id"], "error": f"translation api error: {e}"}
        new_english = translation_payload.get("english_translation", "").strip()
        if not new_english:
            return {"note_id": src_entry["note_id"], "error": "empty translation"}
        revised = dict(src_entry)
        revised["revision_history"] = revised.get("revision_history", []) + [
            {
                "from": src_entry["bangla_sentence"],
                "english_was": src_entry["english_translation"],
                "naturalness_score_before": nat_entry.get("naturalness_score"),
                "qa_issues": nat_entry.get("issues", []),
            }
        ]
        revised["bangla_sentence"] = revision
        revised["example_cloze"] = new_cloze
        revised["english_translation"] = new_english
        revised["revision_source"] = "gemini_qa"
        return revised


async def run(
    candidates: list[tuple[dict, dict]],
    apply: bool,
    model_name: str,
    concurrency: int,
) -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set.")
    client = genai.Client(api_key=api_key)

    # Fetch note bodies once (translation prompt needs the legacy disambig fields).
    note_ids = [src["note_id"] for src, _ in candidates]
    note_info: dict[int, dict] = {}
    for i in range(0, len(note_ids), 200):
        for n in ac("notesInfo", notes=note_ids[i : i + 200]):
            note_info[n["noteId"]] = n

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        revise_one(client, model_name, semaphore, src, nat, note_info[src["note_id"]])
        for src, nat in candidates
        if src["note_id"] in note_info
    ]

    revised_by_id: dict[int, dict] = {}
    for coro in asyncio.as_completed(tasks):
        revised = await coro
        if "error" in revised:
            print(f"  ERR {revised['note_id']}: {revised['error']}")
            continue
        revised_by_id[revised["note_id"]] = revised
        print(
            f"  note {revised['note_id']} ({revised['bangla_headword']}): "
            f"{revised['bangla_sentence'][:80]}"
        )

    print(f"\nPrepared {len(revised_by_id)} revisions.")

    if not apply:
        print("DRY RUN — pass --apply to rewrite the cache.")
        return

    # Rewrite the cache file: replace revised entries, keep everything else.
    full = load_results_cache()
    full.update(revised_by_id)
    RESULTS_PATH.write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in full.values())
    )
    print(f"Wrote {RESULTS_PATH} with {len(full)} entries.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Apply revisions when naturalness score is <= threshold (default 3).",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    candidates = find_revision_candidates(args.threshold)
    print(f"{len(candidates)} cards eligible for revision (score <= {args.threshold}).")
    for src, nat in candidates:
        print(
            f"  note {src['note_id']} ({src['bangla_headword']}) "
            f"score={nat['naturalness_score']}"
        )
        print(f"    current: {src['bangla_sentence']}")
        print(f"    revised: {nat['suggested_revision']}")
        print()

    if not candidates:
        return

    try:
        asyncio.run(run(
            candidates, args.apply, args.model, args.concurrency,
        ))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
