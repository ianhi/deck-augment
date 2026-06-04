"""Translate existing Bangla `Example` sentences to English for notes that
already have a Bangla sentence but a missing `ExampleTranslation`.

Unlike `generate_bangla_sentences.py` this does NOT generate Bangla — it
only renders an English translation for whatever Bangla the user (or a
prior pipeline) already wrote. Useful for the ~77 hand-typed example
sentences whose translation slot was left empty.

Cache lives at `out/bangla_translations.jsonl`; --apply writes back to
the `ExampleTranslation` field via AnkiConnect.
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
import sys
from pathlib import Path

from dotenv import load_dotenv
from generate_sentences import (
    ANKI_MODEL_NAME,
    DEFAULT_MODEL,
    build_disambig_block,
    estimate_cost_usd,
)
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from lib.ankiconnect import ac
from lib.gemini_prompts import (
    BANGLA_TRANSLATION_SYSTEM,
    BANGLA_TRANSLATION_USER,
)

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
RESULTS_PATH = OUT_DIR / "bangla_translations.jsonl"


def current_prompt_signature() -> str:
    h = hashlib.sha256()
    h.update(BANGLA_TRANSLATION_SYSTEM.encode())
    h.update(b"\n")
    h.update(BANGLA_TRANSLATION_USER.encode())
    return h.hexdigest()[:12]


def find_notes_needing_translation() -> list[int]:
    """Notes with Example populated and ExampleTranslation empty."""
    has_example = set(ac("findNotes", query=f'"note:{ANKI_MODEL_NAME}" Example:_*'))
    has_translation = set(
        ac("findNotes", query=f'"note:{ANKI_MODEL_NAME}" ExampleTranslation:_*')
    )
    return sorted(has_example - has_translation)


def load_results_cache() -> dict[int, dict]:
    if not RESULTS_PATH.exists():
        return {}
    cache: dict[int, dict] = {}
    for line in RESULTS_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        cache[entry["note_id"]] = entry
    return cache


def append_result(entry: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def translate_one(
    client: genai.Client,
    model_name: str,
    note: dict,
    semaphore: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    note_id = note["noteId"]
    headword = note["fields"]["Bangla"]["value"]
    bangla_sentence = note["fields"]["Example"]["value"]
    user_prompt = BANGLA_TRANSLATION_USER.format(
        bangla=headword,
        eng_trans=note["fields"]["Eng_trans"]["value"],
        disambig_block=build_disambig_block(note["fields"]),
        bangla_sentence=bangla_sentence,
    )

    async with semaphore:
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_TRANSLATION_SYSTEM,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                # Tolerate "Extra data" — some Gemini responses emit a
                # valid JSON object followed by stray trailing text.
                decoder = json.JSONDecoder()
                payload, _ = decoder.raw_decode(response.text.lstrip())
                english = payload.get("english_translation", "").strip()
                if not english:
                    last_error = "validation: empty english_translation"
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
                    "bangla_headword": headword,
                    "bangla_sentence": bangla_sentence,
                    "english_translation": english,
                    "confidence": payload.get("confidence", "unknown"),
                    "flags": payload.get("flags", []),
                    "sentence_concern": payload.get("sentence_concern", {"suspected": False}),
                    "headword_concern": payload.get("headword_concern", {"suspected": False}),
                    "definition_concern": payload.get("definition_concern", {"suspected": False}),
                    "model": model_name,
                    "attempt": attempt,
                    "usage": usage_record,
                    "prompt_signature": current_prompt_signature(),
                }
            except (json.JSONDecodeError, KeyError) as e:
                last_error = f"parse error: {e}"
                await asyncio.sleep(2 * attempt)
            except genai_errors.APIError as e:
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
            "bangla_headword": headword,
            "error": last_error,
            "model": model_name,
        }


async def run_translation(
    notes: list[dict],
    model_name: str,
    concurrency: int,
    max_retries: int,
) -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set — fill in .env.")
    client = genai.Client(api_key=api_key)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        translate_one(client, model_name, n, semaphore, max_retries)
        for n in notes
    ]

    completed = 0
    successes = 0
    errors = 0
    totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "thoughts_tokens": 0}
    for coro in asyncio.as_completed(tasks):
        entry = await coro
        append_result(entry)
        completed += 1
        if "error" in entry:
            errors += 1
            print(f"  [{completed}/{len(tasks)}] ERR note {entry['note_id']} ({entry['bangla_headword']}): {entry['error']}")
            continue
        successes += 1
        usage = entry.get("usage", {})
        for k in totals:
            totals[k] += usage.get(k, 0) or 0
        print(
            f"  [{completed}/{len(tasks)}] OK note {entry['note_id']} ({entry['bangla_headword']}) "
            f"conf={entry['confidence']} → {entry['english_translation'][:60]!r}"
        )
    cost = estimate_cost_usd(model_name, totals)
    print(f"\nDone. {successes} succeeded, {errors} errored. Cost ~${cost:.4f}")


def apply_cached_translations() -> None:
    cache = load_results_cache()
    successful = [e for e in cache.values() if "error" not in e]
    print(f"{len(successful)} cached translations.")

    # Batch-fetch current field values so we can skip notes that already
    # match the cached translation (idempotent re-apply).
    note_ids = [e["note_id"] for e in successful]
    current_translation: dict[int, str] = {}
    for i in range(0, len(note_ids), 500):
        for n in ac("notesInfo", notes=note_ids[i : i + 500]):
            current_translation[n["noteId"]] = (
                n["fields"].get("ExampleTranslation", {}).get("value", "")
            )

    updated = 0
    unchanged = 0
    skipped_low = 0
    for entry in successful:
        if entry.get("confidence") == "low":
            skipped_low += 1
            continue
        nid = entry["note_id"]
        desired = entry["english_translation"]
        if current_translation.get(nid, "") == desired:
            unchanged += 1
            continue
        ac(
            "updateNoteFields",
            note={"id": nid, "fields": {"ExampleTranslation": desired}},
        )
        updated += 1
    print(
        f"Pushed {updated}; {unchanged} already up-to-date; "
        f"skipped {skipped_low} low-confidence."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--apply", action="store_true",
                        help="Push cached translations to Anki.")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    if args.apply:
        apply_cached_translations()
        return

    target_ids = find_notes_needing_translation()
    print(f"{len(target_ids)} notes have Bangla Example but empty ExampleTranslation.")

    cache = load_results_cache()
    current_sig = current_prompt_signature()
    if not args.regenerate:
        fresh = {nid for nid, e in cache.items()
                 if "error" not in e and e.get("prompt_signature") == current_sig}
        before = len(target_ids)
        target_ids = [nid for nid in target_ids if nid not in fresh]
        print(f"  {before - len(target_ids)} already cached; {len(target_ids)} to translate.")

    if args.limit is not None:
        target_ids = target_ids[: args.limit]
        print(f"Limited to {len(target_ids)}.")

    if not target_ids:
        print("Nothing to do. Use --apply to push cached translations to Anki.")
        return

    notes: list[dict] = []
    for i in range(0, len(target_ids), 200):
        notes.extend(ac("notesInfo", notes=target_ids[i : i + 200]))

    print(f"Translating with model={args.model!r}")
    try:
        asyncio.run(run_translation(
            notes=notes,
            model_name=args.model,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
        ))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
