"""Diagnostic: list all Anki decks whose names match Spanish-related keywords.

Prints every deck matching "spanish", "refold", "es1k", or names starting with
"es", along with its note count. Then prints a second section with full detail
(note types, field names, sample values) for every Refold deck found.

Useful as a one-shot survey when setting up a new machine or verifying what
decks are present before running import/dedup scripts. Anki Desktop must be
running with AnkiConnect installed.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import sys

from lib.ankiconnect import ac


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Spanish/Refold Anki decks and their note counts."
    )
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=["spanish", "refold", "es1k"],
        metavar="KW",
        help="keywords to filter deck names (case-insensitive; default: spanish refold es1k)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        metavar="N",
        help="sample size for Refold deck detail (default: 3)",
    )
    args = parser.parse_args()

    decks = ac("deckNames")
    keywords = [kw.lower() for kw in args.keywords]

    print(f"=== All decks matching {keywords} ===")
    for d in sorted(decks):
        low = d.lower()
        if any(kw in low for kw in keywords) or low.startswith("es"):
            n = len(ac("findNotes", query=f'deck:"{d}"'))
            print(f"  [{n:>5}] {d}")

    print("\n=== All Refold matches (any case) ===")
    for d in sorted(decks):
        if "refold" in d.lower():
            print(f"  {d}")
            nids = ac("findNotes", query=f'deck:"{d}"')
            if nids:
                info = ac("notesInfo", notes=nids[: args.sample])
                models_in_deck = {n["modelName"] for n in info}
                print(f"    model types (from sample): {models_in_deck}")
                print(f"    sample fields: {list(info[0]['fields'].keys())}")
                print(f"    sample word/front: {list(info[0]['fields'].values())[:2]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
