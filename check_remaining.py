"""Diagnostic: inspect a sample of notes in each target Spanish deck.

For each deck name provided (defaults to a hardcoded list of the main Spanish
decks), fetches up to ``--sample`` notes via AnkiConnect and prints their note
type and non-empty field values. Useful for verifying field names before
writing import or dedup logic.

Anki Desktop must be running with AnkiConnect installed.
"""
from __future__ import annotations

import argparse
import sys

from ankiconnect import ac

DEFAULT_DECKS = [
    "Spanish::Complete Spanish",
    "Spanish::immersion",
    "Spanish::ES-Cloze",
]


def inspect_deck(deck: str, sample: int) -> None:
    print(f"\n=== {deck} ===")
    nids = ac("findNotes", query=f'deck:"{deck}"')
    if not nids:
        print("  (no notes found)")
        return
    infos = ac("notesInfo", notes=nids[:sample])
    for n in infos:
        print(f"  [{n['modelName']}]")
        for f, v in n["fields"].items():
            val = v["value"][:100].replace("\n", " ")
            if val:
                print(f"    {f}: {val}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a sample of notes in each target Spanish deck."
    )
    parser.add_argument(
        "decks",
        nargs="*",
        default=DEFAULT_DECKS,
        metavar="DECK",
        help="deck names to inspect (default: hardcoded Spanish deck list)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        metavar="N",
        help="number of sample notes per deck (default: 3)",
    )
    args = parser.parse_args()

    for deck in args.decks:
        inspect_deck(deck, args.sample)

    return 0


if __name__ == "__main__":
    sys.exit(main())
