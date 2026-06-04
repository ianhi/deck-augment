"""Use Gemini to rate the naturalness of cached Bangla sentences.

Reads an experiment-style JSONL (e.g. out/experiment_<model>.jsonl) and
asks Gemini for a 1-5 naturalness score + concrete issues per sentence.
Caches assessments to out/naturalness_<source>.jsonl keyed by note id.

Designed to run after a generation pass, before bulk apply. The
compare-models HTML renderer reads these caches and shows scores
side-by-side with the original sentences.

Usage:
  uv run assess_sentence_naturalness.py \\
      --source out/experiment_gemini-3-flash-preview.jsonl
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
import sys
from pathlib import Path

from dotenv import load_dotenv
from generate_sentences import DEFAULT_MODEL, estimate_cost_usd
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from lib.gemini_prompts import (
    BANGLA_NATURALNESS_SYSTEM,
    BANGLA_NATURALNESS_USER,
)

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"


def naturalness_cache_path(source: Path) -> Path:
    """Pair each source file with its own naturalness cache, always
    distinct from the source path."""
    stem = source.stem
    if stem.startswith("experiment_"):
        stem = "naturalness_" + stem[len("experiment_"):]
    else:
        stem = "naturalness_" + stem
    return OUT_DIR / f"{stem}.jsonl"


def load_naturalness_cache(source: Path) -> dict[int, dict]:
    path = naturalness_cache_path(source)
    if not path.exists():
        return {}
    cache: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        cache[entry["note_id"]] = entry
    return cache


def append_assessment(source: Path, entry: dict) -> None:
    path = naturalness_cache_path(source)
    OUT_DIR.mkdir(exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def summarise_form(sampled_form: dict) -> str:
    bits = [
        sampled_form.get("tense_and_aspect", "?"),
        sampled_form.get("sentence_type", "?"),
        sampled_form.get("subject_person", "?"),
    ]
    register_relevant = sampled_form.get("subject_person") == "second_person_singular" or \
        sampled_form.get("sentence_type") in ("interrogative", "imperative")
    if register_relevant:
        bits.append(sampled_form.get("second_person_register", "?"))
    if sampled_form.get("is_negative"):
        bits.append("NEGATIVE")
    return " · ".join(bits)


async def assess_one(
    client: genai.Client,
    model_name: str,
    source_entry: dict,
    semaphore: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    note_id = source_entry["note_id"]
    user_prompt = BANGLA_NATURALNESS_USER.format(
        bangla=source_entry["bangla_headword"],
        eng_trans=source_entry.get("english_gloss_input", "")
            or source_entry.get("english_translation", ""),
        form_summary=summarise_form(source_entry.get("sampled_form", {})),
        bangla_sentence=source_entry["bangla_sentence"],
        english_translation=source_entry["english_translation"],
    )

    async with semaphore:
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_NATURALNESS_SYSTEM,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                decoder = json.JSONDecoder()
                payload, _ = decoder.raw_decode(response.text.lstrip())
                score = int(payload["naturalness_score"])
                usage = getattr(response, "usage_metadata", None)
                usage_record = {
                    "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                    "cached_input_tokens": getattr(usage, "cached_content_token_count", 0) or 0,
                    "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                    "thoughts_tokens": getattr(usage, "thoughts_token_count", 0) or 0,
                }
                return {
                    "note_id": note_id,
                    "naturalness_score": score,
                    "native_would_say": bool(payload.get("native_would_say", False)),
                    "issues": payload.get("issues", []),
                    "suggested_revision": payload.get("suggested_revision", ""),
                    "judge_model": model_name,
                    "usage": usage_record,
                }
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                last_error = f"parse error: {e}"
                await asyncio.sleep(2 * attempt)
            except genai_errors.APIError as e:
                last_error = f"api error: {e}"
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code in (429, 500, 502, 503, 504):
                    base = 4 * attempt
                    await asyncio.sleep(base + random.uniform(0, base / 2))
                else:
                    await asyncio.sleep(2 * attempt)
        return {"note_id": note_id, "error": last_error, "judge_model": model_name}


async def run_assessment(
    source_entries: list[dict],
    model_name: str,
    concurrency: int,
    max_retries: int,
    source_path: Path,
) -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set — fill in .env.")
    client = genai.Client(api_key=api_key)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        assess_one(client, model_name, e, semaphore, max_retries)
        for e in source_entries
    ]

    completed = 0
    totals = {"input_tokens": 0, "cached_input_tokens": 0,
              "output_tokens": 0, "thoughts_tokens": 0}
    scores: list[int] = []
    for coro in asyncio.as_completed(tasks):
        entry = await coro
        append_assessment(source_path, entry)
        completed += 1
        if "error" in entry:
            print(f"  [{completed}/{len(tasks)}] ERR note {entry['note_id']}: {entry['error']}")
            continue
        scores.append(entry["naturalness_score"])
        for k in totals:
            totals[k] += entry["usage"].get(k, 0) or 0
        print(
            f"  [{completed}/{len(tasks)}] note {entry['note_id']} "
            f"score={entry['naturalness_score']}"
            f"{'  ⚠ ' + entry['issues'][0][:60] if entry['issues'] else ''}"
        )
    cost = estimate_cost_usd(model_name, totals)
    if scores:
        from statistics import mean
        print(f"\nMean naturalness score: {mean(scores):.2f}/5  ({len(scores)} graded)")
    print(f"Cost ~${cost:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("out/experiment_gemini-3-flash-preview.jsonl"),
        help="Cached generation results to assess.",
    )
    parser.add_argument("--judge-model", default=DEFAULT_MODEL,
                        help=f"Model to use as the judge (default {DEFAULT_MODEL}).")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--regenerate", action="store_true",
                        help="Ignore existing naturalness cache.")
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    if not args.source.exists():
        raise SystemExit(f"Source not found: {args.source}")

    source_entries: list[dict] = []
    for line in args.source.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if "error" in e:
            continue
        source_entries.append(e)

    cache = load_naturalness_cache(args.source)
    if not args.regenerate:
        before = len(source_entries)
        source_entries = [e for e in source_entries if e["note_id"] not in cache]
        print(f"{before - len(source_entries)} cached; {len(source_entries)} to assess.")

    if not source_entries:
        print("Nothing to assess.")
        return

    try:
        asyncio.run(run_assessment(
            source_entries=source_entries,
            model_name=args.judge_model,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
            source_path=args.source,
        ))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
