"""Diagnostic: list all Anki note types, their fields, and a sample note each.

Iterates every note type known to AnkiConnect and prints its field names, total
note count, and up to ``--sample`` notes with truncated field values. Run this
once to understand what's in an Anki profile before writing import or dedup
logic.

Anki Desktop must be running with AnkiConnect installed.
"""
from __future__ import annotations

import argparse
import sys

from ankiconnect import ac


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List all Anki note types with fields and a sample note each."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=1,
        metavar="N",
        help="number of sample notes per model (default: 1)",
    )
    parser.add_argument(
        "--filter",
        dest="filter",
        metavar="SUBSTR",
        help="only show models whose name contains SUBSTR (case-insensitive)",
    )
    args = parser.parse_args()

    models: list[str] = ac("modelNames")
    if args.filter:
        models = [m for m in models if args.filter.lower() in m.lower()]

    print(f"=== {len(models)} note types ===\n")

    for m in models:
        fields: list[str] = ac("modelFieldNames", modelName=m)
        print(f"[{m}]")
        print(f"  fields: {fields}")
        note_ids: list[int] = ac("findNotes", query=f'note:"{m}"')
        print(f"  note count: {len(note_ids)}")
        if note_ids:
            sample = ac("notesInfo", notes=note_ids[: args.sample])
            for note in sample:
                for f, v in note["fields"].items():
                    val = v["value"][:80].replace("\n", " ")
                    print(f"    {f}: {val!r}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
