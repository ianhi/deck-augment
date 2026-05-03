"""Re-encode a directory of audio files with ffmpeg using ThreadPoolExecutor.

Idempotent: skips files already present in the destination directory.

Default: re-encodes out/audio/*.mp3 → out/audio_mp3_64k/ at 64 kbps mono MP3.
After compression, update AUDIO_DIR in repack.py to point at the compressed output.

Usage:
  uv run python compress_audio.py
  uv run python compress_audio.py --src out/audio --dst out/audio_64k
  uv run python compress_audio.py --bitrate 32k --codec opus
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).parent

CODEC_EXT: dict[str, str] = {
    "mp3": ".mp3",
    "opus": ".opus",
}
CODEC_LIB: dict[str, str] = {
    "mp3": "libmp3lame",
    "opus": "libopus",
}


def encode(src: Path, dst_dir: Path, bitrate: str, codec: str) -> tuple[Path, int, int]:
    """Encode one file. Returns (src, src_bytes, dst_bytes)."""
    ext = CODEC_EXT[codec]
    dst = dst_dir / (src.stem + ext)
    if dst.exists():
        return src, src.stat().st_size, dst.stat().st_size
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-i", str(src),
            "-b:a", bitrate,
            "-ar", "24000",
            "-ac", "1",
            "-codec:a", CODEC_LIB[codec],
            str(dst),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {src.name}: {result.stderr.strip()}")
    return src, src.stat().st_size, dst.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-encode audio files with ffmpeg in parallel.",
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=HERE / "out" / "audio",
        help="Source directory containing MP3 files (default: out/audio)",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        default=HERE / "out" / "audio_mp3_64k",
        help="Destination directory for encoded files (default: out/audio_mp3_64k)",
    )
    parser.add_argument(
        "--bitrate",
        default="64k",
        help="Target audio bitrate passed to ffmpeg -b:a (default: 64k)",
    )
    parser.add_argument(
        "--codec",
        choices=list(CODEC_LIB),
        default="mp3",
        help="Output codec: mp3 (libmp3lame) or opus (libopus) (default: mp3)",
    )
    args = parser.parse_args()

    src_dir: Path = args.src
    dst_dir: Path = args.dst
    bitrate: str = args.bitrate
    codec: str = args.codec

    if not src_dir.exists():
        print(f"error: source directory not found: {src_dir}", file=sys.stderr)
        return 1

    dst_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_dir.glob("*.mp3"))
    if not files:
        print(f"no .mp3 files found in {src_dir}", file=sys.stderr)
        return 1

    workers = os.cpu_count() or 4
    print(f"{len(files)} files to process, {workers} workers, codec={codec}, bitrate={bitrate}")

    total_src = 0
    total_dst = 0
    skipped = 0
    done = 0
    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(encode, f, dst_dir, bitrate, codec): f for f in files}
        for fut in as_completed(futures):
            src_path, src_size, dst_size = fut.result()
            total_src += src_size
            total_dst += dst_size
            dst_path = dst_dir / (src_path.stem + CODEC_EXT[codec])
            if dst_path.stat().st_mtime < start:
                skipped += 1
            done += 1
            if done % 500 == 0 or done == len(files):
                print(
                    f"  [{done:>4}/{len(files)}] {total_src/1e6:.1f} MB → {total_dst/1e6:.1f} MB",
                    flush=True,
                )

    ratio = total_dst / total_src if total_src else 0.0
    print(f"\nDone: {done} files, {skipped} already existed")
    print(f"Source:  {total_src/1e6:.1f} MB")
    print(f"Encoded: {total_dst/1e6:.1f} MB  ({ratio*100:.1f}% of source)")
    print(f"Elapsed: {time.perf_counter() - start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
