"""Render TTS audio for the personal narrative cloze deck.

One sentence audio per entry — the full Spanish sentence (cloze filled in).
Uses the same 6-voice Chirp3 HD pool as the conjugation deck, deterministic by
entry index.

Output: out/mx_pn_audio/<idx>.mp3

Idempotent: skips entries whose audio already exists.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from tts_tools import synthesize_async  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"
AUDIO_DIR = OUT / "mx_pn_audio"
LANGUAGE = "es-US"
ALL_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]
SILENT_PEAK_DBFS = -25.0


def voice_for(idx: int) -> str:
    digest = hashlib.sha1(f"mxpn-{idx}".encode()).digest()
    return ALL_VOICES[digest[0] % len(ALL_VOICES)]


def _capper(text: str) -> str:
    capped = text[:1].upper() + text[1:]
    return capped if capped.endswith((".", "!", "?")) else capped + "."


async def _render(text: str, voice: str, label: str):
    attempts = [text, text, _capper(text)]
    result = None
    for i, t in enumerate(attempts):
        result = await synthesize_async(
            t, language=LANGUAGE, voice=voice, max_retries=6,
        )
        peak = result.as_segment().max_dBFS
        if peak > SILENT_PEAK_DBFS:
            return result
        print(f"  silent ({label} attempt {i+1} peak={peak:.1f}) — retry", flush=True)
    return result


async def synth_one(sem, idx, sentence):
    p = AUDIO_DIR / f"{idx:03d}.mp3"
    if p.exists():
        return
    voice = f"{LANGUAGE}-Chirp3-HD-{voice_for(idx)}"
    try:
        async with sem:
            r = await _render(sentence, voice, label=f"pn/{idx}")
        if r is not None:
            r.save(str(p))
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED {idx}: {type(exc).__name__}: {exc}", flush=True)


async def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads((OUT / "mx_personal_narrative.json").read_text(encoding="utf-8"))
    sem = asyncio.Semaphore(6)
    print(f"Rendering {len(data)} personal-narrative sentences...")
    await asyncio.gather(*[synth_one(sem, i, e["spanish_full"]) for i, e in enumerate(data)])
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
