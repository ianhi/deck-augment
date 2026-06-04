"""Collapse `Bangla::beginners bangla::*` subdeck tree into two flat subdecks
(`::Vocab` and `::Grammar`) and encode the unit dimension as Anki tags.

Routing:
  1. If the source subdeck path ends in `::Vocab` or `::Grammar`, that wins.
  2. Else by note type: Cloze+ / Bangla Enhanced Cloze → Grammar;
     Bangla (and reversed) → Vocab.
  3. `::appendix N` subdecks → Vocab destination + tag `appendix::N`.
  4. Standalone `::cloze` subdeck (no unit) → Grammar, no unit tag.

Tags applied (flat, no hierarchy — matches existing tag style):
  - `unit-N` extracted from `::Unit N` in the path (1..14).
  - `appendix-N` for appendix subdecks.

Run with `--dry-run` (default) to print the plan. Pass `--apply` to execute.
Filter to one source subdeck with `--only "Bangla::beginners bangla::Unit 6"`.

Idempotent: `addTags` is a set operation; `changeDeck` on an already-moved
card is a no-op.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from lib.ankiconnect import ac

PARENT = "Bangla::beginners bangla"
DEST_VOCAB = f"{PARENT}::Vocab"
DEST_GRAMMAR = f"{PARENT}::Grammar"

GRAMMAR_NOTE_TYPES = {"Cloze+", "Bangla Enhanced Cloze"}


@dataclass
class CardPlan:
    card_id: int
    note_id: int
    model: str
    source_deck: str
    dest_deck: str
    tags_to_add: list[str]


def plan_for_subdeck(source_deck: str, cards_info: list[dict]) -> list[CardPlan]:
    """Return a CardPlan per card in the given source subdeck."""
    # Extract unit number from the source path (if any).
    unit_match = re.search(r"::Unit (\d+)(?:::|$)", source_deck)
    unit_tag = f"unit-{unit_match.group(1)}" if unit_match else None

    appendix_match = re.search(r"::appendix (\d+)$", source_deck)
    appendix_tag = f"appendix-{appendix_match.group(1)}" if appendix_match else None

    ends_with_vocab = source_deck.endswith("::Vocab")
    ends_with_grammar = source_deck.endswith("::Grammar")
    is_standalone_cloze = source_deck == f"{PARENT}::cloze"

    plans: list[CardPlan] = []
    for c in cards_info:
        model = c["modelName"]
        if ends_with_vocab:
            dest = DEST_VOCAB
        elif ends_with_grammar:
            dest = DEST_GRAMMAR
        elif appendix_match:
            dest = DEST_VOCAB
        elif is_standalone_cloze:
            dest = DEST_GRAMMAR
        elif model in GRAMMAR_NOTE_TYPES:
            dest = DEST_GRAMMAR
        else:
            dest = DEST_VOCAB

        tags = [t for t in (unit_tag, appendix_tag) if t is not None]
        plans.append(
            CardPlan(
                card_id=c["cardId"],
                note_id=c["note"],
                model=model,
                source_deck=source_deck,
                dest_deck=dest,
                tags_to_add=tags,
            )
        )
    return plans


def list_beginners_subdecks() -> list[str]:
    """Return all source subdecks under PARENT, excluding the destination
    decks themselves and the parent itself."""
    decks = ac("deckNames")
    out: list[str] = []
    for d in decks:
        if not d.startswith(f"{PARENT}::"):
            continue
        if d in (DEST_VOCAB, DEST_GRAMMAR):
            continue
        # Skip if the deck is a strict ancestor of the destinations.
        out.append(d)
    return sorted(out)


def cards_directly_in(deck: str, all_subdecks: set[str]) -> list[dict]:
    """Return cardsInfo for cards directly in `deck`, excluding any in
    descendant subdecks."""
    cards = ac("findCards", query=f'"deck:{deck}"')
    if not cards:
        return []
    info = ac("cardsInfo", cards=cards)
    descendants = {d for d in all_subdecks if d.startswith(f"{deck}::")}
    if not descendants:
        return info
    return [c for c in info if c["deckName"] not in descendants]


def apply_plans(plans: list[CardPlan]) -> None:
    """Group plans by (dest_deck, tag-set) and issue batch AnkiConnect calls."""
    by_dest: dict[str, list[int]] = defaultdict(list)
    by_tagset: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for p in plans:
        by_dest[p.dest_deck].append(p.card_id)
        if p.tags_to_add:
            by_tagset[tuple(sorted(p.tags_to_add))].add(p.note_id)

    for dest, card_ids in by_dest.items():
        ac("changeDeck", cards=card_ids, deck=dest)
        print(f"  moved {len(card_ids)} cards → {dest}")

    for tagset, note_id_set in by_tagset.items():
        note_ids = sorted(note_id_set)
        tag_str = " ".join(tagset)
        ac("addTags", notes=note_ids, tags=tag_str)
        print(f"  tagged {len(note_ids)} notes  +{tag_str}")


def summarize(plans: list[CardPlan]) -> None:
    if not plans:
        print("  (no cards)")
        return
    dest_counts = Counter(p.dest_deck for p in plans)
    tag_counts: Counter[str] = Counter()
    for p in plans:
        for t in p.tags_to_add:
            tag_counts[t] += 1
    model_counts = Counter(p.model for p in plans)

    print(f"  cards: {len(plans)}")
    for dest, n in dest_counts.most_common():
        print(f"    → {dest}: {n}")
    for tag, n in tag_counts.most_common():
        print(f"    +{tag}: {n} notes")
    for model, n in model_counts.most_common():
        print(f"    [{model}]: {n}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Execute the plan (default is dry-run).")
    ap.add_argument(
        "--only",
        help="Process only this source subdeck path (and any descendants).",
    )
    args = ap.parse_args()

    subdecks = list_beginners_subdecks()
    all_set = set(subdecks) | {PARENT, DEST_VOCAB, DEST_GRAMMAR}

    if args.only:
        matched = [
            d for d in subdecks if d == args.only or d.startswith(f"{args.only}::")
        ]
        if not matched:
            raise SystemExit(
                f"--only {args.only!r} matched no source subdecks under {PARENT}.\n"
                f"Available:\n  " + "\n  ".join(subdecks)
            )
        subdecks = matched

    print(f"Source subdecks to process: {len(subdecks)}")
    for d in subdecks:
        print(f"  - {d}")
    print()

    grand_plans: list[CardPlan] = []
    for d in subdecks:
        cards_info = cards_directly_in(d, all_set)
        plans = plan_for_subdeck(d, cards_info)
        print(f"== {d} ==")
        summarize(plans)
        if args.apply and plans:
            apply_plans(plans)
        grand_plans.extend(plans)
        print()

    print("== Grand total ==")
    summarize(grand_plans)

    if not args.apply:
        print("\nDRY RUN — pass --apply to execute.")


if __name__ == "__main__":
    main()
