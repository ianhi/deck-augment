"""Split frequency-deck entries into batches for subagent bolding.

Reads ``source.apkg`` (an Anki package / ZIP), extracts the SQLite collection,
and writes one batch pair per ``BATCH_SIZE`` entries into ``out/bold_batches/``:

  - ``batch_NN_input.md``    — numbered list of ``N. **HEADWORD** — SENTENCE``
  - ``batch_NN_manifest.json`` — ordered list of ``{line, note_id, headword}``

Usage::

    python prep_bold_batches.py
    python prep_bold_batches.py --batch-size 50 --source path/to/deck.apkg

Run this once before dispatching subagents for the bolding stage.
Old batch files in the output directory are wiped first to prevent stale output.

Inputs:  source.apkg  (default: ./source.apkg)
Outputs: out/bold_batches/batch_NN_input.md
         out/bold_batches/batch_NN_manifest.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = HERE / "source.apkg"
DEFAULT_OUT_DIR = HERE / "out" / "bold_batches"
DEFAULT_BATCH_SIZE = 100

# Field indices within Anki's \x1f-delimited flds string
FIELD_RANK = 0
FIELD_HEADWORD = 1
FIELD_SENTENCE = 4


def extract_entries(source: Path, tmp_dir: Path) -> list[tuple[int, int, str, str]]:
    """Extract (note_id, rank, headword, sentence) tuples from an .apkg file.

    Args:
        source:  Path to the .apkg file.
        tmp_dir: Directory used for a temporary SQLite extraction.

    Returns:
        Entries sorted ascending by rank.
    """
    with zipfile.ZipFile(source) as z:
        with z.open("collection.anki21") as f:
            data = f.read()
    tmp = tmp_dir / "_collection.anki21"
    tmp.write_bytes(data)
    con = sqlite3.connect(tmp)
    rows = con.execute("SELECT id, flds FROM notes").fetchall()
    con.close()
    tmp.unlink()

    entries: list[tuple[int, int, str, str]] = []
    for note_id, flds in rows:
        parts = flds.split("\x1f")
        if not parts[FIELD_RANK].isdigit():
            continue
        entries.append((note_id, int(parts[FIELD_RANK]), parts[FIELD_HEADWORD], parts[FIELD_SENTENCE]))

    entries.sort(key=lambda e: e[1])
    return entries


def write_batches(entries: list[tuple[int, int, str, str]], out_dir: Path, batch_size: int) -> int:
    """Write batch input + manifest files to *out_dir*.

    Args:
        entries:    Sorted list of (note_id, rank, headword, sentence).
        out_dir:    Directory to write batch files into (created if absent).
        batch_size: Number of entries per batch.

    Returns:
        Number of batches written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Wipe old batch files to avoid stale output
    for old in out_dir.glob("batch_*"):
        old.unlink()

    for i in range(0, len(entries), batch_size):
        batch_num = i // batch_size
        chunk = entries[i : i + batch_size]

        md_lines = [
            f"{j}. **{headword}** — {sentence}"
            for j, (_nid, _rank, headword, sentence) in enumerate(chunk, start=1)
        ]
        (out_dir / f"batch_{batch_num:02d}_input.md").write_text(
            "\n".join(md_lines) + "\n", encoding="utf-8"
        )

        manifest = [
            {"line": j, "note_id": nid, "headword": hw}
            for j, (nid, _, hw, _) in enumerate(chunk, start=1)
        ]
        (out_dir / f"batch_{batch_num:02d}_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return (len(entries) + batch_size - 1) // batch_size


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split a frequency-deck .apkg into markdown+manifest batches for subagent bolding.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        metavar="FILE",
        help=f"Path to the source .apkg file (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help=f"Directory to write batch files into (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"Entries per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    args = parser.parse_args()

    tmp_dir = args.out_dir.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    entries = extract_entries(args.source, tmp_dir)
    n_batches = write_batches(entries, args.out_dir, args.batch_size)

    print(f"{len(entries)} entries -> {n_batches} batches of up to {args.batch_size}")
    print(f"written to {args.out_dir}")


if __name__ == "__main__":
    main()
