"""Audition Chirp3-HD voices on a sample Bangla sentence.

Tries the same six voices used for the Spanish 5000 build (Kore, Aoede,
Sulafat / Charon, Fenrir, Orus) at the bn-IN locale, plus a couple of
spare alternates. Writes each MP3 to out/audition_bn/<voice>.mp3 so the
user can listen and pick the final set.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from tts_tools import AudioFormat, Engine, synthesize

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out" / "audition_bn"

SAMPLE_SENTENCE = "আমি প্রতিদিন সকালে চা খাই। তুমি কেমন আছ?"

# Same shortlist as Spanish, ordered female-then-male; with a couple
# alternates the user can fall back to if any sound off.
CANDIDATE_VOICES = [
    ("Kore", "FEMALE"),
    ("Aoede", "FEMALE"),
    ("Sulafat", "FEMALE"),
    ("Charon", "MALE"),
    ("Fenrir", "MALE"),
    ("Orus", "MALE"),
    # Spares (Spanish NOTES.md flagged these as backup):
    ("Erinome", "FEMALE"),
    ("Enceladus", "MALE"),
    ("Iapetus", "MALE"),
]

LANGUAGE_CODE = "bn-IN"


def synthesize_one(voice_short: str, text: str, api_key: str | None) -> bytes:
    """Synth via tts-tools. Falls back to ADC when api_key is empty."""
    result = synthesize(
        text,
        language=LANGUAGE_CODE,
        voice=f"{LANGUAGE_CODE}-Chirp3-HD-{voice_short}",
        engine=Engine.GOOGLE_CLOUD,
        format=AudioFormat.MP3,
        api_key=api_key or None,
    )
    return result.audio_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=SAMPLE_SENTENCE, help="Sentence to audition.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only try the first N candidate voices (default: all).",
    )
    args = parser.parse_args()

    load_dotenv(HERE / ".env")
    api_key = os.environ.get("GOOGLE_CLOUD_TTS_API_KEY", "").strip() or None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    voices = CANDIDATE_VOICES[: args.limit] if args.limit else CANDIDATE_VOICES

    print(f"Auth: {'API key' if api_key else 'ADC (gcloud)'}")
    print(f"Sample text: {args.text!r}")
    print(f"Writing to {OUT_DIR}")
    print()

    for voice, gender in voices:
        out_path = OUT_DIR / f"{voice}_{gender.lower()}.mp3"
        try:
            audio = synthesize_one(voice, args.text, api_key)
            out_path.write_bytes(audio)
            print(f"  ✓ {voice:<11} ({gender:<6}) → {out_path.relative_to(HERE)}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {voice:<11} ({gender:<6}) — {e}")


if __name__ == "__main__":
    main()
