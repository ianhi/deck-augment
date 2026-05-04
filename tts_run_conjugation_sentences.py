"""Render ONLY sentence audio for conjugation cards.

Skips word audio entirely (we don't use it in the cloze deck — only sentences
get attached to notes). Saves ~30% time and the corresponding TTS spend vs.
the dual-render tts_run_conjugation.py.

Idempotent: skips entries whose <nid>_sentence.mp3 already exists.

Reuses the silent-render retry + capper fallback from the conjugation pipeline.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from tts_tools import synthesize_async  # type: ignore[import-untyped]

HERE = Path(__file__).parent
OUT = HERE / "out"
AUDIO_DIR = OUT / "conjugation_audio"
LANGUAGE = "es-US"
ALL_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]
SILENT_PEAK_DBFS = -25.0

_progress_lock = asyncio.Lock()
_done = 0


def voice_for_note(note_id: int, voices: list[str]) -> str:
    digest = hashlib.sha1(str(note_id).encode()).digest()
    return voices[digest[0] % len(voices)]


def _capper(text: str) -> str:
    capped = text[:1].upper() + text[1:]
    return capped if capped.endswith((".", "!", "?")) else capped + "."


async def _render_with_retry(text: str, voice_name: str, *, label: str):
    attempts = [text, text, _capper(text)]
    result = None
    for i, t in enumerate(attempts):
        result = await synthesize_async(
            t, language=LANGUAGE, voice=voice_name, max_retries=6,
        )
        peak = result.as_segment().max_dBFS
        if peak > SILENT_PEAK_DBFS:
            return result
        print(
            f"    silent ({label} attempt {i+1} peak={peak:.1f} text={t!r}) — retry",
            flush=True,
        )
    return result


async def _tick(total: int) -> None:
    global _done
    async with _progress_lock:
        _done += 1
        if _done % 100 == 0 or _done == total:
            print(f"  [{_done:>4}/{total}] synthesized", flush=True)


async def synth_sentence(
    sem: asyncio.Semaphore,
    voice: str,
    note_id: int,
    sentence: str,
    total: int,
) -> None:
    voice_name = f"{LANGUAGE}-Chirp3-HD-{voice}"
    sent_path = AUDIO_DIR / f"{note_id}_sentence.mp3"
    try:
        async with sem:
            result = await _render_with_retry(
                sentence, voice_name, label=f"sent/{note_id}",
            )
        if result is not None:
            result.save(str(sent_path))
        await _tick(total)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED note_id={note_id}: {type(exc).__name__}: {exc}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, metavar="N")
    ap.add_argument("--concurrency", type=int, default=12, metavar="N")
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    notes = json.loads((OUT / "conjugation_notes.json").read_text(encoding="utf-8"))
    if args.limit:
        notes = notes[: args.limit]

    to_process = []
    for n in notes:
        nid = int(n["note_id"])
        if (AUDIO_DIR / f"{nid}_sentence.mp3").exists():
            continue
        voice = voice_for_note(nid, ALL_VOICES)
        to_process.append((voice, nid, n["sentence_text"]))

    print(f"To synthesize: {len(to_process)} sentences (skipped {len(notes) - len(to_process)})")
    print(f"Concurrency: {args.concurrency}")
    print(flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    await asyncio.gather(*[
        synth_sentence(sem, v, nid, s, len(to_process))
        for v, nid, s in to_process
    ])
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
