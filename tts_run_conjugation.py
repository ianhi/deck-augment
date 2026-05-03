"""Generate TTS audio for the Ultimate Spanish Conjugation deck.

Reads out/conjugation_notes.json (produced by fetch_conjugation_notes.py).
For each note, synthesizes two clips with the same deterministically-assigned
Chirp3 HD es-US voice:

  out/conjugation_audio/<note_id>_word.mp3      ← Conjugation field
  out/conjugation_audio/<note_id>_sentence.mp3  ← stem + conjugation + punct

The word render passes ``trim=False`` so librosa's silence trim cannot clip
short monosyllabic conjugations ("es", "ha", "voy", "fue"). Sentence renders
use the default ``trim=True`` — long-enough that trimming is safe.

Idempotent: cards whose both files already exist are skipped.

Usage:
  uv run python tts_run_conjugation.py                  # all notes
  uv run python tts_run_conjugation.py --limit 20       # smoke test
  uv run python tts_run_conjugation.py --voices Kore    # restrict voice subset
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from tts_tools import synthesize_async  # type: ignore[import-untyped]

# Chirp3 HD occasionally returns near-silent audio on bare monosyllables ("ha",
# "fue"). Anything quieter than this peak dBFS is treated as a failed render.
SILENT_PEAK_DBFS = -25.0

HERE = Path(__file__).parent
OUT = HERE / "out"
AUDIO_DIR = OUT / "conjugation_audio"
INDEX_PATH = OUT / "conjugation_audio_index.jsonl"
LANGUAGE = "es-US"
ALL_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]

_progress_lock = asyncio.Lock()
_done_count = 0


def voice_for_note(note_id: int, voices: list[str]) -> str:
    digest = hashlib.sha1(str(note_id).encode()).digest()
    return voices[digest[0] % len(voices)]


async def _tick(entry: dict, total: int) -> None:
    global _done_count
    async with _progress_lock:
        with INDEX_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _done_count += 1
        if _done_count % 50 == 0 or _done_count == total:
            print(f"  [{_done_count:>4}/{total}] synthesized", flush=True)


def _capper(text: str) -> str:
    """Capitalize first letter and add period if missing — stabilizes Chirp3 on monosyllables."""
    capped = text[:1].upper() + text[1:]
    return capped if capped.endswith((".", "!", "?")) else capped + "."


async def _render_with_retry(
    text: str, voice_name: str, *, trim: bool, label: str,
):
    """Render text; retry on silent output, then fall back to capitalized+punctuated form."""
    attempts = [text, text, _capper(text)]
    result = await synthesize_async(
        attempts[0], language=LANGUAGE, voice=voice_name, trim=trim, max_retries=6,
    )
    for i, t in enumerate(attempts):
        if i > 0:
            result = await synthesize_async(
                t, language=LANGUAGE, voice=voice_name, trim=trim, max_retries=6,
            )
        peak = result.as_segment().max_dBFS
        if peak > SILENT_PEAK_DBFS:
            return result
        print(
            f"    silent render ({label} attempt {i+1}, peak={peak:.1f} dBFS, "
            f"text={t!r}) — retrying",
            flush=True,
        )
    return result  # give up; save whatever we have so the audit pass can flag it


async def synth_note(
    sem: asyncio.Semaphore,
    voice: str,
    note_id: int,
    word_text: str,
    sentence_text: str,
    total: int,
) -> None:
    voice_name = f"{LANGUAGE}-Chirp3-HD-{voice}"
    try:
        async with sem:
            word_result, sent_result = await asyncio.gather(
                # trim=False protects short conjugations from leading/trailing clipping.
                _render_with_retry(word_text, voice_name, trim=False, label=f"word/{note_id}"),
                _render_with_retry(sentence_text, voice_name, trim=True, label=f"sent/{note_id}"),
            )
        word_result.save(str(AUDIO_DIR / f"{note_id}_word.mp3"))
        sent_result.save(str(AUDIO_DIR / f"{note_id}_sentence.mp3"))
        await _tick(
            {
                "note_id": note_id,
                "voice": voice,
                "word_path": f"conjugation_audio/{note_id}_word.mp3",
                "sentence_path": f"conjugation_audio/{note_id}_sentence.mp3",
                "chars": len(word_text) + len(sentence_text),
            },
            total,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED note_id={note_id} voice={voice}: {type(exc).__name__}: {exc}", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, metavar="N")
    parser.add_argument("--concurrency", type=int, default=4, metavar="N")
    parser.add_argument("--voices", default=",".join(ALL_VOICES), metavar="V,...")
    args = parser.parse_args()

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads((OUT / "conjugation_notes.json").read_text(encoding="utf-8"))
    if args.limit:
        data = data[: args.limit]

    to_process: list[tuple[str, int, str, str]] = []
    skipped_existing = 0
    for r in data:
        note_id = int(r["note_id"])
        word_path = AUDIO_DIR / f"{note_id}_word.mp3"
        sent_path = AUDIO_DIR / f"{note_id}_sentence.mp3"
        if word_path.exists() and sent_path.exists():
            skipped_existing += 1
            continue
        voice = voice_for_note(note_id, voices)
        to_process.append((voice, note_id, r["word_text"], r["sentence_text"]))

    buckets = {v: 0 for v in voices}
    total_chars = 0
    for voice, _nid, w, s in to_process:
        buckets[voice] += 1
        total_chars += len(w) + len(s)
    print(f"To synthesize: {len(to_process)} notes × 2 clips, {total_chars:,} chars")
    print(f"Skipped (already exist): {skipped_existing}")
    print("Per-voice distribution:")
    for v in voices:
        print(f"  {v:<10} {buckets[v]}")
    print(flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    total = len(to_process)
    await asyncio.gather(*[
        synth_note(sem, voice, nid, w, s, total)
        for voice, nid, w, s in to_process
    ])

    by_note: dict[int, dict] = {}
    if INDEX_PATH.exists():
        for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            by_note[int(entry["note_id"])] = entry
    (OUT / "conjugation_audio_index.json").write_text(
        json.dumps(list(by_note.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Done. conjugation_audio_index.json has {len(by_note)} notes.")


if __name__ == "__main__":
    asyncio.run(main())
