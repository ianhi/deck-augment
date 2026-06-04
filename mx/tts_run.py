"""Render TTS audio for the Mexico survival pack.

For each entry in out/mx_survival_source.json:
  - Renders the answer (`spanish` field) — always.
  - Renders the prompt (`spanish_prompt`) when non-null.

Voice strategy: male voices for prompts ("the other person"), female voices
for answers ("you"). Consistent split makes conversational cards feel like
two distinct speakers. Voice is chosen deterministically by hashing the entry
index, so re-runs produce the same audio.

Output:
  out/mx_audio/<idx>_prompt.mp3   (only if spanish_prompt is non-null)
  out/mx_audio/<idx>_answer.mp3   (always)

Idempotent: skips entries whose required audio already exists.

Reuses the silent-render retry + capper fallback from the conjugation pipeline.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from tts_tools import synthesize_async  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"
AUDIO_DIR = OUT / "mx_audio"
LANGUAGE = "es-US"
MALE_VOICES = ["Charon", "Fenrir", "Orus"]
FEMALE_VOICES = ["Kore", "Aoede", "Sulafat"]
SILENT_PEAK_DBFS = -25.0

_progress_lock = asyncio.Lock()
_done = 0


def voice_for(idx: int, voices: list[str], salt: str) -> str:
    digest = hashlib.sha1(f"{idx}-{salt}".encode()).digest()
    return voices[digest[0] % len(voices)]


def _capper(text: str) -> str:
    capped = text[:1].upper() + text[1:]
    return capped if capped.endswith((".", "!", "?")) else capped + "."


async def _render_with_retry(text: str, voice_name: str, *, label: str):
    attempts = [text, text, _capper(text)]
    result = None
    for i, t in enumerate(attempts):
        result = await synthesize_async(
            t, language=LANGUAGE, voice=voice_name, trim=False, max_retries=6,
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
        if _done % 50 == 0 or _done == total:
            print(f"  [{_done:>4}/{total}] rendered", flush=True)


async def synth_entry(
    sem: asyncio.Semaphore,
    idx: int,
    entry: dict,
    total: int,
) -> None:
    answer_path = AUDIO_DIR / f"{idx:04d}_answer.mp3"
    prompt_path = AUDIO_DIR / f"{idx:04d}_prompt.mp3"
    spanish_prompt = entry.get("spanish_prompt")
    needs_prompt = spanish_prompt and not prompt_path.exists()
    needs_answer = not answer_path.exists()
    if not needs_answer and not needs_prompt:
        await _tick(total)
        return

    answer_voice = voice_for(idx, FEMALE_VOICES, "answer")
    answer_voice_name = f"{LANGUAGE}-Chirp3-HD-{answer_voice}"

    try:
        async with sem:
            tasks = []
            if needs_answer:
                tasks.append(_render_with_retry(
                    entry["spanish"], answer_voice_name, label=f"a/{idx}",
                ))
            if needs_prompt and spanish_prompt:
                pv = voice_for(idx, MALE_VOICES, "prompt")
                tasks.append(_render_with_retry(
                    spanish_prompt, f"{LANGUAGE}-Chirp3-HD-{pv}", label=f"p/{idx}",
                ))
            results = await asyncio.gather(*tasks)
        ri = 0
        if needs_answer:
            results[ri].save(str(answer_path))
            ri += 1
        if needs_prompt:
            results[ri].save(str(prompt_path))
        await _tick(total)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED idx={idx}: {type(exc).__name__}: {exc}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, metavar="N")
    ap.add_argument("--concurrency", type=int, default=6, metavar="N")
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads((OUT / "mx_survival_source.json").read_text(encoding="utf-8"))
    if args.limit:
        data = data[: args.limit]

    pending_audio = sum(
        (1 if not (AUDIO_DIR / f"{i:04d}_answer.mp3").exists() else 0)
        + (1 if e.get("spanish_prompt") and not (AUDIO_DIR / f"{i:04d}_prompt.mp3").exists() else 0)
        for i, e in enumerate(data)
    )
    print(f"Entries: {len(data)}, missing audio clips to render: {pending_audio}")

    sem = asyncio.Semaphore(args.concurrency)
    await asyncio.gather(*[
        synth_entry(sem, i, e, len(data)) for i, e in enumerate(data)
    ])
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
