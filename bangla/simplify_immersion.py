"""Rewrite SIMPLIFY-flagged immersion cards to a focused gloss + natural example.

Reads SIMPLIFY note IDs from `out/immersion_triage_aggregate.json`. For each
note, asks Gemini to rewrite the gloss to a single sense and replace the
literary example with a natural Kolkata sentence. Caches results in
`out/immersion_simplify.jsonl`.

With `--apply`, pushes the new fields back to Anki and deletes the old
sentence audio file so the next `tts_run.py` pass regenerates it.

Usage:
  uv run bangla/simplify_immersion.py --limit 5    # dry-run, gemini only
  uv run bangla/simplify_immersion.py              # full gemini pass, dry-run apply
  uv run bangla/simplify_immersion.py --apply      # push to Anki + invalidate audio
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

from lib.ankiconnect import ac
from lib.gemini_prompts import BANGLA_SIMPLIFY_SYSTEM, BANGLA_SIMPLIFY_USER

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
AUDIO_DIR = OUT_DIR / "audio_bn"
RESULTS_PATH = OUT_DIR / "immersion_simplify.jsonl"
TRIAGE_PATH = OUT_DIR / "immersion_triage_aggregate.json"

DEFAULT_MODEL = "gemini-3-flash-preview"
CONCURRENCY = 6


def load_cache() -> dict[int, dict]:
    if not RESULTS_PATH.exists():
        return {}
    out: dict[int, dict] = {}
    with RESULTS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            out[e["note_id"]] = e
    return out


def append_cache(entry: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def simplify_one(
    client: genai.Client,
    model_name: str,
    note: dict,
    sem: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    nid = note["noteId"]
    f = note["fields"]
    user_prompt = BANGLA_SIMPLIFY_USER.format(
        bangla=f["Bangla"]["value"],
        current_gloss=f["Eng_trans"]["value"],
        current_example=f["Example"]["value"],
    )
    async with sem:
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_SIMPLIFY_SYSTEM,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                payload = json.loads(resp.text or "")
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    payload = payload[0]
                if not isinstance(payload, dict):
                    raise ValueError(f"expected object, got {type(payload).__name__}")
                return {
                    "note_id": nid,
                    "bangla": f["Bangla"]["value"],
                    "old_gloss": f["Eng_trans"]["value"],
                    "old_example": f["Example"]["value"],
                    "new_gloss": payload.get("english_gloss", "").strip(),
                    "new_example_bangla": payload.get("example_bangla", "").strip(),
                    "new_example_english": payload.get("example_english", "").strip(),
                    "rationale": payload.get("rationale", "").strip(),
                    "attempt": attempt,
                }
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                await asyncio.sleep(2 * attempt)
        return {"note_id": nid, "error": last_err}


async def run_fill(note_ids: list[int], model_name: str, max_retries: int) -> None:
    load_dotenv(HERE / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY missing")
    cache = load_cache()
    todo_ids = [nid for nid in note_ids if nid not in cache or "error" in cache.get(nid, {})]
    print(f"To fill: {len(todo_ids)}  (cached: {len(note_ids) - len(todo_ids)})", flush=True)
    if not todo_ids:
        return
    notes = ac("notesInfo", notes=todo_ids)
    client = genai.Client(api_key=api_key)
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        asyncio.create_task(simplify_one(client, model_name, n, sem, max_retries))
        for n in notes
    ]
    done = 0
    for coro in asyncio.as_completed(tasks):
        entry = await coro
        append_cache(entry)
        done += 1
        marker = "OK" if "error" not in entry else "ER"
        label = entry.get("new_gloss") or entry.get("error", "")
        print(f"  [{done:3d}/{len(todo_ids)}] {marker} nid={entry['note_id']} {label}", flush=True)


def apply_to_anki(dry_run: bool) -> None:
    cache = load_cache()
    triage = json.loads(TRIAGE_PATH.read_text())
    nids = triage["SIMPLIFY"]
    updates = []
    drops = []
    for nid in nids:
        e = cache.get(nid)
        if not e or "error" in e:
            continue
        if not e["new_example_bangla"]:
            drops.append((nid, e["bangla"], e.get("rationale", "")))
            continue
        updates.append(e)
    print(f"To update: {len(updates)}    Gemini-declared-obscure (will quarantine): {len(drops)}")
    if dry_run:
        print("\n--- Sample updates (first 3) ---")
        for e in updates[:3]:
            print(f"  nid={e['note_id']}  {e['bangla']}")
            print(f"    old gloss:   {e['old_gloss']!r}")
            print(f"    new gloss:   {e['new_gloss']!r}")
            print(f"    old example: {e['old_example'][:80]!r}")
            print(f"    new example: {e['new_example_bangla'][:80]!r}")
            print()
        print("(dry-run — not pushing. Pass --apply to push.)")
        return

    actions: list[dict] = []
    for e in updates:
        actions.append({
            "action": "updateNoteFields",
            "params": {"note": {"id": e["note_id"], "fields": {
                "Eng_trans": e["new_gloss"],
                "Example": e["new_example_bangla"],
                "ExampleTranslation": e["new_example_english"],
            }}},
        })
        sent_file = AUDIO_DIR / f"bn_{e['note_id']}_sentence.mp3"
        raw_file = AUDIO_DIR / f"bn_{e['note_id']}_sentence_raw.mp3"
        for p in (sent_file, raw_file):
            if p.exists():
                p.unlink()
    BATCH = 25
    for i in range(0, len(actions), BATCH):
        ac("multi", actions=actions[i:i + BATCH])
        print(f"  pushed {min(i + BATCH, len(actions))}/{len(actions)} field updates", flush=True)
    if drops:
        stale_deck = "Bangla::Immersion::mahabharat::stale"
        cids: list[int] = []
        for nid, _, _ in drops:
            cids.extend(ac("findCards", query=f"nid:{nid}"))
        ac("changeDeck", cards=cids, deck=stale_deck)
        print(f"Moved {len(drops)} Gemini-declared-obscure notes ({len(cids)} cards) to {stale_deck}")

    print(f"\nDone. Next: re-run TTS to regenerate the {len(updates)} invalidated sentence "
          "audio files:")
    print("  uv run bangla/tts_run.py --profile bangla-vocab")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="Gemini-pass cap.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument(
        "--apply", action="store_true",
        help="Push field updates to Anki + invalidate old sentence audio "
             "(no Gemini work). Defaults to dry-run preview.",
    )
    args = p.parse_args()

    triage = json.loads(TRIAGE_PATH.read_text())
    note_ids = triage["SIMPLIFY"]
    if args.limit:
        note_ids = note_ids[:args.limit]

    if args.apply:
        apply_to_anki(dry_run=False)
        return

    asyncio.run(run_fill(note_ids, args.model, args.max_retries))
    apply_to_anki(dry_run=True)


if __name__ == "__main__":
    main()
