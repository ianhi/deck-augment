"""Fix scrambled ``due`` ordering in the imported frequency deck via AnkiConnect.

The source apkg has non-sequential ``due`` values (see ``repack.py``
``set_card_due_to_rank``). This script rewrites ``due = rank`` for all NEW
(queue=0) cards in the target deck, so Anki presents them in frequency order.
Cards with review history (queue != 0) are left untouched.

Always run with ``--dry-run`` first to verify the plan before applying changes.
Anki Desktop must be running with AnkiConnect installed.

Usage::

    uv run python fix_due_via_ankiconnect.py --dry-run   # preview changes
    uv run python fix_due_via_ankiconnect.py             # apply changes
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import sys

from lib.ankiconnect import ac


def pick_deck() -> str:
    """Find the frequency deck by name, prompting if multiple candidates exist."""
    decks: list[str] = ac("deckNames")
    candidates = [
        d for d in decks
        if "frequency" in d.lower() or "5000 spanish" in d.lower() or "davies" in d.lower()
    ]
    if not candidates:
        print("No frequency deck found. Deck names available:", file=sys.stderr)
        for d in sorted(decks):
            if "spanish" in d.lower():
                print(f"  {d}", file=sys.stderr)
        sys.exit(1)
    if len(candidates) == 1:
        return candidates[0]
    print("Multiple candidates:")
    for i, d in enumerate(candidates):
        print(f"  [{i}] {d}")
    idx = input("Pick one (number): ").strip()
    return candidates[int(idx)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite due=rank for new cards in the frequency deck."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change, do not apply",
    )
    parser.add_argument(
        "--deck",
        help="deck name (auto-detected from known frequency-deck name patterns if omitted)",
    )
    args = parser.parse_args()

    deck = args.deck or pick_deck()
    print(f"Deck: {deck}")

    new_card_ids: list[int] = ac("findCards", query=f'deck:"{deck}" is:new')
    all_card_ids: list[int] = ac("findCards", query=f'deck:"{deck}"')
    print(f"Total cards: {len(all_card_ids)}")
    print(f"New cards (queue=0): {len(new_card_ids)}")
    print(f"Already-reviewed cards (will be untouched): {len(all_card_ids) - len(new_card_ids)}")

    if not new_card_ids:
        print("No new cards to update.")
        return 0

    print("\nFetching card info...")
    infos = ac("cardsInfo", cards=new_card_ids)
    print(f"  got {len(infos)} cards")

    # Build plan: (card_id, current_due, target_rank)
    plan: list[tuple[int, int, int]] = []
    missing_rank = 0
    already_correct = 0
    for info in infos:
        cid: int = info["cardId"]
        current_due: int = info["due"]
        rank_str: str = info["fields"].get("Rank", {}).get("value", "").strip()
        if not rank_str or not rank_str.isdigit():
            missing_rank += 1
            continue
        rank = int(rank_str)
        if current_due == rank:
            already_correct += 1
            continue
        plan.append((cid, current_due, rank))

    print("\nPlan:")
    print(f"  Cards with no/bad Rank field: {missing_rank}")
    print(f"  Cards already correct (due == rank): {already_correct}")
    print(f"  Cards to update: {len(plan)}")

    if plan:
        print("\n  First 5 changes preview:")
        for cid, old, new in plan[:5]:
            print(f"    card {cid}: due {old} -> {new}")
        if len(plan) > 5:
            print(f"    ... and {len(plan) - 5} more")

    if args.dry_run:
        print("\nDry-run: no changes made. Re-run without --dry-run to apply.")
        return 0

    if not plan:
        print("\nNothing to do.")
        return 0

    print(f"\nApplying {len(plan)} updates via setSpecificValueOfCard...")
    for i, (cid, _old, new) in enumerate(plan, 1):
        ac(
            "setSpecificValueOfCard",
            card=cid,
            keys=["due"],
            newValues=[str(new)],
            # Required to allow modifying scheduling-related fields
            warning_check=True,
        )
        if i % 250 == 0 or i == len(plan):
            print(f"  [{i}/{len(plan)}] updated")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
