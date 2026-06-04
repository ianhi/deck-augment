"""Generate TTS audio for all cards in out/bolded_sentences.json.

Assigns each note to one of the Chirp3 HD es-US voices deterministically (SHA-1 of
note_id), then synthesizes the headword and sentence in parallel per card using an
asyncio.Semaphore to stay within API quota.

Writes per card:
  out/audio/<note_id>_word.mp3
  out/audio/<note_id>_sentence.mp3

Appends one JSON record per card to out/audio_index.jsonl (lock-protected), then
consolidates into out/audio_index.json on completion.

Idempotent: cards whose both output files already exist are skipped.

Usage:
  uv run python tts_run.py                        # all cards
  uv run python tts_run.py --limit 100            # first 100 by rank (testing)
  uv run python tts_run.py --concurrency 8        # raise semaphore (caution: quota)
  uv run python tts_run.py --voices Kore,Aoede    # restrict to a voice subset
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path

from tts_tools import synthesize_async  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"
AUDIO_DIR = OUT / "audio"
INDEX_PATH = OUT / "audio_index.jsonl"
LANGUAGE = "es-US"
ALL_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]

BOLD_RE = re.compile(r"</?b>")

_progress_lock = asyncio.Lock()
_done_count = 0


def voice_for_note(note_id: int, voices: list[str]) -> str:
    """Return a deterministic voice for a note_id by hashing."""
    # digest[0] % n has ~2% bias (256 % 6 == 4), negligible for n=5000.
    digest = hashlib.sha1(str(note_id).encode()).digest()
    return voices[digest[0] % len(voices)]


def plain_text(bolded: str) -> str:
    """Strip HTML bold tags and surrounding whitespace."""
    return BOLD_RE.sub("", bolded).strip()


async def _tick_and_record(entry: dict[str, object], total: int) -> None:
    """Append one entry to the JSONL index and print a progress tick."""
    global _done_count
    async with _progress_lock:
        with INDEX_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _done_count += 1
        if _done_count % 25 == 0 or _done_count == total:
            print(f"  [{_done_count:>4}/{total}] synthesized", flush=True)


async def synth_card(
    sem: asyncio.Semaphore,
    voice: str,
    note_id: int,
    headword: str,
    sentence: str,
    total: int,
) -> None:
    """Synthesize headword + sentence for one card, save files, and record progress.

    Exceptions (quota, timeout, etc.) are logged but not re-raised so one failed
    card does not abort sibling tasks. An idempotent rerun will pick up any missing
    cards.
    """
    voice_name = f"{LANGUAGE}-Chirp3-HD-{voice}"
    try:
        async with sem:
            # Parallelize word + sentence within the single semaphore slot.
            word_result, sent_result = await asyncio.gather(
                synthesize_async(headword, language=LANGUAGE, voice=voice_name, max_retries=6),
                synthesize_async(sentence, language=LANGUAGE, voice=voice_name, max_retries=6),
            )
        word_result.save(str(AUDIO_DIR / f"{note_id}_word.mp3"))
        sent_result.save(str(AUDIO_DIR / f"{note_id}_sentence.mp3"))
        await _tick_and_record(
            {
                "note_id": note_id,
                "voice": voice,
                "word_path": f"audio/{note_id}_word.mp3",
                "sentence_path": f"audio/{note_id}_sentence.mp3",
                "chars": len(headword) + len(sentence),
            },
            total,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"  FAILED note_id={note_id} voice={voice}: {type(exc).__name__}: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001 — catch-all so one card never kills the run
        print(f"  FAILED note_id={note_id} voice={voice}: {type(exc).__name__}: {exc}", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize TTS audio for all cards in out/bolded_sentences.json.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N cards by rank (useful for testing)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        metavar="N",
        help="asyncio.Semaphore size — concurrent card slots (default: 4; each slot fires 2 calls)",
    )
    parser.add_argument(
        "--voices",
        default=",".join(ALL_VOICES),
        metavar="VOICE,...",
        help="Comma-separated subset of Chirp3 voice names to use (default: all 6)",
    )
    args = parser.parse_args()

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    data: list[dict[str, object]] = json.loads((OUT / "bolded_sentences.json").read_text())
    data.sort(key=lambda e: e["rank"])
    if args.limit:
        data = data[: args.limit]

    # Build the work list, skipping empty entries and already-complete cards.
    to_process: list[tuple[str, int, str, str]] = []
    skipped_empty = 0
    skipped_existing = 0
    for e in data:
        sent = plain_text(str(e["bolded_sentence"]))
        hw = str(e["headword"]).strip()
        if not sent or not hw:
            skipped_empty += 1
            continue
        note_id = int(str(e["note_id"]))
        word_path = AUDIO_DIR / f"{note_id}_word.mp3"
        sent_path = AUDIO_DIR / f"{note_id}_sentence.mp3"
        if word_path.exists() and sent_path.exists():
            skipped_existing += 1
            continue
        voice = voice_for_note(note_id, voices)
        to_process.append((voice, note_id, hw, sent))

    # Print pre-run summary.
    buckets: dict[str, int] = {v: 0 for v in voices}
    total_chars = 0
    for voice, _nid, hw, sent in to_process:
        buckets[voice] += 1
        total_chars += len(hw) + len(sent)

    print(f"Total: {len(to_process)} cards × 2 (word + sentence), {total_chars:,} chars", flush=True)
    print(f"Skipped (empty): {skipped_empty}", flush=True)
    print(f"Skipped (already generated): {skipped_existing}", flush=True)
    print("Per-voice distribution:", flush=True)
    for v in voices:
        print(f"  {v:<10} {buckets[v]}", flush=True)
    print(flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    total = len(to_process)
    tasks = [
        synth_card(sem, voice, note_id, hw, sent, total)
        for voice, note_id, hw, sent in to_process
    ]
    await asyncio.gather(*tasks)

    # Consolidate JSONL → JSON (dedup by note_id, last-write-wins).
    by_note: dict[int, dict[str, object]] = {}
    if INDEX_PATH.exists():
        for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry: dict[str, object] = json.loads(line)
            by_note[int(str(entry["note_id"]))] = entry
    (OUT / "audio_index.json").write_text(
        json.dumps(list(by_note.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Done. audio_index.json has {len(by_note)} cards.")


if __name__ == "__main__":
    asyncio.run(main())
