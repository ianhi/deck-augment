"""Generate one sample sentence across Chirp3 HD voices for listening comparison.

Synthesizes a short Spanish sentence with each specified voice and writes MP3s to
out/auditions/. Listen before committing to the full 5000-card run.

Usage:
  uv run python audition.py
  uv run python audition.py --text "Hola mundo" --voices Kore,Aoede
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tts_tools import synthesize_batch  # type: ignore[import-untyped]

DEFAULT_TEXT = "Prefiero no recordar esa época de mi vida."
DEFAULT_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]
LANGUAGE = "es-US"
OUT_DIR = Path(__file__).resolve().parents[1] / "out" / "auditions"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sample MP3s across Chirp3 HD voices for audition.",
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="Text to synthesize (default: built-in sample sentence)",
    )
    parser.add_argument(
        "--voices",
        default=",".join(DEFAULT_VOICES),
        help="Comma-separated voice names to audition (default: all 6 Chirp3 voices)",
    )
    args = parser.parse_args()

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    text: str = args.text

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [
        synthesize_batch(
            [text],
            language=LANGUAGE,
            voice=f"{LANGUAGE}-Chirp3-HD-{v}",
            max_concurrent=1,
        )
        for v in voices
    ]
    results_per_voice = await asyncio.gather(*tasks)
    for voice, results in zip(voices, results_per_voice):
        out_path = OUT_DIR / f"{voice}.mp3"
        results[0].save(str(out_path))
        print(f"  {voice:<10} -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
