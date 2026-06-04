"""Reposition NEW cards in `Bangla::beginners bangla::{Vocab,Grammar}` so that
they appear Unit 1 → Unit 14 (then untagged cloze, then appendix) in the
order a fresh recipient of the .apkg would see.

Why new-cards-only:
  - For queue=0 (new) cards, `due` == position; rewriting it changes display
    order with no scheduling side-effects.
  - For reviewed/learning cards, `due` is a date and rewriting it would
    reschedule the user's review queue. We do NOT touch those.
  - When exporting `.apkg` without scheduling, Anki strips review state; the
    recipient sees all cards as new with positions inherited from `due`, so
    repositioning new cards now is the minimum needed for a logical export.
    For full export ordering across already-reviewed cards, the user can run
    Anki's Reposition GUI command after this script.

Ordering rule for new cards:
  primary key: unit number (1..14), with untagged → 99 (after all units),
               appendix-N → unit_N + 0.5 (immediately after unit_N)
  secondary  : current `due` (preserves intra-unit order from original deck)
  tertiary   : card id (deterministic tiebreaker)

Dry-run by default. Pass `--apply` to write via setSpecificValueOfCard.
Per NOTES.md, that requires warning_check=True for scheduling fields.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import re
from collections import Counter

from lib.ankiconnect import ac

PARENT = "Bangla::beginners bangla"
DECKS = [f"{PARENT}::Vocab", f"{PARENT}::Grammar"]


def unit_sort_key(tags: list[str]) -> tuple[int, int]:
    """Return (primary, secondary) sort tuple from the tag set.

    Primary is the unit number; appendix-N becomes (unit_N, 1) so it sorts
    after the matching unit's main cards. Untagged → (99, 0)."""
    unit_n: int | None = None
    appendix_n: int | None = None
    for t in tags:
        m = re.fullmatch(r"unit-(\d+)", t)
        if m:
            unit_n = int(m.group(1))
        m = re.fullmatch(r"appendix-(\d+)", t)
        if m:
            appendix_n = int(m.group(1))
    if appendix_n is not None:
        # Place appendix-N after unit-N's main cards.
        return (appendix_n, 1)
    if unit_n is not None:
        return (unit_n, 0)
    return (99, 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Write new positions (default: dry-run).")
    args = ap.parse_args()

    for deck in DECKS:
        new_cards = ac("findCards", query=f'"deck:{deck}" is:new')
        print(f"== {deck}: {len(new_cards)} new cards ==")
        if not new_cards:
            continue

        info = ac("cardsInfo", cards=new_cards)
        # Pull tags for each note in one batch.
        note_ids = sorted({c["note"] for c in info})
        notes = ac("notesInfo", notes=note_ids)
        tags_by_note = {n["noteId"]: n["tags"] for n in notes}

        # Build sort keys.
        ranked = []
        for c in info:
            key = unit_sort_key(tags_by_note[c["note"]])
            ranked.append((key, c["due"], c["cardId"], c))
        ranked.sort(key=lambda r: (r[0], r[1], r[2]))

        # Preview distribution.
        unit_counts: Counter[tuple[int, int]] = Counter(r[0] for r in ranked)
        for key in sorted(unit_counts):
            primary, secondary = key
            label = (
                "untagged" if primary == 99
                else f"appendix-{primary}" if secondary == 1
                else f"unit-{primary}"
            )
            print(f"  {unit_counts[key]:>4}  {label}")

        if args.apply:
            for new_due, (_, _, _, c) in enumerate(ranked, start=1):
                if c["due"] == new_due:
                    continue
                ac(
                    "setSpecificValueOfCard",
                    card=c["cardId"],
                    keys=["due"],
                    newValues=[str(new_due)],
                    warning_check=True,
                )
            print(f"  applied: due values 1..{len(ranked)}")

    if not args.apply:
        print("\nDRY RUN — pass --apply to write.")


if __name__ == "__main__":
    main()
