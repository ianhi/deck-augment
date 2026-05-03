# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "scipy",
#     "soundfile",
# ]
# ///
"""Render spectrograms of audio samples for visual quality comparison.

Reads all .mp3 / .ogg files from a directory (default: out/compare/), plots one
spectrogram per file stacked vertically, and writes the result to
<compare-dir>/spectrograms.png.

Interpretation:
  - X axis: time (seconds)
  - Y axis: frequency (Hz, capped at 12 kHz)
  - Colour: power in dB (brighter = louder at that frequency)
  - Higher-bitrate files retain more energy at upper frequencies; low-bitrate
    files will show a sharp cutoff (dark band) above their codec's frequency
    ceiling.

Run with:
  uv run compare_spectrograms.py
  uv run compare_spectrograms.py --compare-dir out/my-samples
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import spectrogram  # type: ignore[import-untyped]

HERE = Path(__file__).parent


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Read an audio file and return (mono samples, sample_rate)."""
    data, sr = sf.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, int(sr)


def render(compare_dir: Path) -> int:
    files = sorted(f for f in compare_dir.iterdir() if f.suffix in {".mp3", ".ogg"})
    if not files:
        print(f"no .mp3/.ogg files found in {compare_dir}", file=sys.stderr)
        return 1

    fig, axes = plt.subplots(len(files), 1, figsize=(11, 2.2 * len(files)), sharex=True)
    ax_list: list[plt.Axes] = [axes] if len(files) == 1 else list(axes)  # type: ignore[arg-type]

    for ax, f in zip(ax_list, files):
        samples, sr = load_audio(f)
        freqs, times, sxx = spectrogram(samples, fs=sr, nperseg=1024, noverlap=512)
        sxx_db: np.ndarray = 10 * np.log10(sxx + 1e-12)
        im = ax.pcolormesh(times, freqs, sxx_db, shading="gouraud", cmap="viridis")
        ax.set_ylabel("Hz")
        ax.set_ylim(0, min(12000, sr / 2))
        size_kb = f.stat().st_size / 1024
        ax.set_title(f"{f.name}  ({size_kb:.1f} KB)", loc="left", fontsize=10)
        fig.colorbar(im, ax=ax, label="dB", pad=0.01)

    ax_list[-1].set_xlabel("time (s)")
    fig.suptitle("Spectrogram comparison: same sentence at different bitrates", y=0.995)
    fig.tight_layout()

    out_path = compare_dir / "spectrograms.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"wrote {out_path}")
    plt.show()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--compare-dir",
        metavar="DIR",
        type=Path,
        default=HERE / "out" / "compare",
        help="Directory containing audio samples to compare (default: out/compare/).",
    )
    args = parser.parse_args()

    compare_dir: Path = args.compare_dir
    if not compare_dir.is_dir():
        print(f"ERROR: directory not found: {compare_dir}", file=sys.stderr)
        return 1

    return render(compare_dir)


if __name__ == "__main__":
    sys.exit(main())
