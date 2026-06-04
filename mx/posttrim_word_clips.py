"""Post-process word mp3s in out/conjugation_audio/ with a gentle silence trim.

The TTS render uses ``trim=False`` so librosa cannot clip soft consonant onsets
or vowel-decay tails on short conjugations. But Google occasionally returns
clips with several hundred ms of leading silence, which is annoying during
review. This pass uses pydub with a conservative -40 dBFS threshold and keeps
``KEEP_PAD_MS`` of silence on each end so nothing sounds chopped.

Idempotent: rerunning on already-trimmed files is safe (further silence will
already be at/below the threshold's residual pad).

Usage:
  uv run python posttrim_word_clips.py            # process all word mp3s
  uv run python posttrim_word_clips.py --limit 20 # smoke test
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_leading_silence

AUDIO_DIR = Path(__file__).resolve().parents[1] / "out" / "conjugation_audio"
SILENCE_THRESHOLD_DBFS = -40.0  # gentler than librosa's default 30dB top
KEEP_PAD_MS = 40  # leave this much silence on each end for a natural feel


def trim_clip(seg: AudioSegment) -> AudioSegment:
    lead = detect_leading_silence(seg, silence_threshold=SILENCE_THRESHOLD_DBFS)
    trail = detect_leading_silence(seg.reverse(), silence_threshold=SILENCE_THRESHOLD_DBFS)
    start = max(0, lead - KEEP_PAD_MS)
    end = len(seg) - max(0, trail - KEEP_PAD_MS)
    if start >= end:  # whole clip below threshold (unlikely) — return original
        return seg
    return seg[start:end]


def _process_one(path_str: str) -> int:
    """Worker — load clip, trim, write back. Returns ms trimmed."""
    path = Path(path_str)
    seg = AudioSegment.from_mp3(path)
    before = len(seg)
    out = trim_clip(seg)
    delta = before - len(out)
    if delta > 0:
        out.export(path, format="mp3")
    return delta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, metavar="N")
    ap.add_argument(
        "--workers", type=int, default=os.cpu_count() or 4, metavar="N",
        help="Parallel worker processes (default: CPU count)",
    )
    args = ap.parse_args()

    files = sorted(AUDIO_DIR.glob("*_word.mp3"))
    if args.limit:
        files = files[: args.limit]
    print(
        f"Trimming {len(files)} word clips with {args.workers} workers "
        f"(threshold {SILENCE_THRESHOLD_DBFS} dBFS, pad {KEEP_PAD_MS}ms)"
    )

    total_trimmed_ms = 0
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_process_one, str(p)): p for p in files}
        for fut in as_completed(futures):
            total_trimmed_ms += fut.result()
            done += 1
            if done % 500 == 0 or done == len(files):
                print(f"  [{done:>4}/{len(files)}] trimmed {total_trimmed_ms/1000:.1f}s total")


if __name__ == "__main__":
    main()
