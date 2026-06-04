"""Measure n+1 forward-reference coverage in the frequency deck.

A "forward reference" occurs when a card's example sentence contains a word
that is itself a headword but appears *later* in the deck (higher rank number).
This is a floor estimate: tokenization is exact-match only, so conjugated forms
that differ from the headword are not counted.

Reads: out/bolded_sentences.json

Output columns:
  - Cards with ≥1 forward-referenced headword (count + %)
  - Total forward references across the deck
  - Top 20 most-referenced future words
  - The 5 cards with the most forward refs

--known-through RANK: treat all headwords at rank ≤ RANK as already known and
exclude them from the forward-reference count. Useful for estimating coverage
at a given point in study (e.g. "as if I already know the top 500 words").
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"

BOLD_RE = re.compile(r"</?b>")
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


def normalize(s: str) -> str:
    """Lowercase and strip; preserve accents (él vs el are distinct)."""
    return s.lower().strip()


def build_form_to_rank(data: list[dict[str, object]]) -> dict[str, int]:
    """Map each normalized headword form to its lowest (earliest) rank."""
    form_to_rank: dict[str, int] = {}
    for e in data:
        rank = int(e["rank"])  # type: ignore[arg-type]
        for form in re.split(r"[,/]", str(e["headword"])):
            f = normalize(form)
            if f and (f not in form_to_rank or form_to_rank[f] > rank):
                form_to_rank[f] = rank
    return form_to_rank


def analyze(
    data: list[dict[str, object]],
    form_to_rank: dict[str, int],
    known_through: int,
) -> tuple[list[int], Counter[str], list[tuple[int, str, list[tuple[str, int]]]]]:
    """Return per-card forward-ref counts, aggregated word counts, and per-card detail."""
    card_forward_count: list[int] = []
    all_forward_refs: Counter[str] = Counter()
    per_card_issues: list[tuple[int, str, list[tuple[str, int]]]] = []

    for e in data:
        rank = int(e["rank"])  # type: ignore[arg-type]
        headword_forms = {normalize(f) for f in re.split(r"[,/]", str(e["headword"]))}
        plain = BOLD_RE.sub("", str(e["bolded_sentence"]))
        tokens = [normalize(t) for t in TOKEN_RE.findall(plain)]

        seen_forward: list[tuple[str, int]] = []
        for tok in set(tokens):
            if tok in headword_forms:
                continue  # the target word itself — not a forward ref
            other_rank = form_to_rank.get(tok)
            if other_rank is not None and other_rank > rank and other_rank > known_through:
                seen_forward.append((tok, other_rank))

        card_forward_count.append(len(seen_forward))
        for tok, _ in seen_forward:
            all_forward_refs[tok] += 1
        if seen_forward:
            per_card_issues.append((rank, str(e["headword"]), seen_forward))

    return card_forward_count, all_forward_refs, per_card_issues


def print_report(
    card_forward_count: list[int],
    all_forward_refs: Counter[str],
    per_card_issues: list[tuple[int, str, list[tuple[str, int]]]],
    form_to_rank: dict[str, int],
    known_through: int,
) -> None:
    n = len(card_forward_count)
    if n == 0:
        print("No cards found.")
        return

    cards_with_any = sum(1 for c in card_forward_count if c > 0)
    total_refs = sum(card_forward_count)
    max_refs = max(card_forward_count)

    if known_through > 0:
        print(f"(treating ranks 1–{known_through} as already known)")
    print(f"Cards analyzed:                        {n}")
    print(f"Cards with ≥1 forward-referenced word: {cards_with_any} ({cards_with_any * 100 / n:.1f}%)")
    print(f"Total forward references:              {total_refs}")
    print(f"Avg per card (all):                    {total_refs / n:.2f}")
    print(f"Avg per affected card:                 {total_refs / max(cards_with_any, 1):.2f}")
    print(f"Max refs in one card:                  {max_refs}")

    print("\nTop 20 most-forward-referenced words (word → how many earlier cards use it):")
    for word, count in all_forward_refs.most_common(20):
        rank = form_to_rank[word]
        print(f"  rank {rank:>4}  {word!r:<20}  appears in {count} earlier cards")

    per_card_issues.sort(key=lambda x: -len(x[2]))
    print("\nCards with the most forward references (top 5):")
    for rank, headword, refs in per_card_issues[:5]:
        print(f"  rank {rank:>4}  {headword!r}: {len(refs)} refs")
        for word, wrank in refs[:5]:
            print(f"      {word!r} (rank {wrank})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--known-through",
        metavar="RANK",
        type=int,
        default=0,
        help=(
            "Treat headwords at rank ≤ RANK as already known; "
            "exclude them from forward-reference counts. Default: 0 (none known)."
        ),
    )
    parser.add_argument(
        "--input",
        metavar="FILE",
        type=Path,
        default=OUT / "bolded_sentences.json",
        help="Path to bolded_sentences.json (default: out/bolded_sentences.json).",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    data: list[dict[str, object]] = json.loads(input_path.read_text())
    form_to_rank = build_form_to_rank(data)
    card_forward_count, all_forward_refs, per_card_issues = analyze(
        data, form_to_rank, known_through=args.known_through
    )
    print_report(card_forward_count, all_forward_refs, per_card_issues, form_to_rank, args.known_through)
    return 0


if __name__ == "__main__":
    sys.exit(main())
