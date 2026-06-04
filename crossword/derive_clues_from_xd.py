"""Derive top-N clues per answer from the XD corpus stats.

Replaces the crosswordheaven-scraped clue list with frequency-ranked clues
from XD. XD gives us real usage counts ('Needle case' 151 puzzles vs 'Small
case' 74), so the top-N is a defensible 'most canonical' set rather than
crosswordheaven's heuristic order.

Filtering rules:
  - Drop cross-reference clues ("See 21-Across", "21A", "With 5-Down, ...")
    — same regex set as scrape_clues.py.
  - Strip trailing periods (XD has both "Needle case" and "Needle case." as
    distinct entries; treat them as the same clue and sum their counts).
  - Strip trailing cryptic enumeration "(4)" / "(3,5)".
  - Dedup case-insensitively, keeping the first/highest-count spelling.

Run after `compute_xd_stats.py` has produced `out/xd_clue_freq.json`.

Usage:
    uv run crossword/derive_clues_from_xd.py
    uv run crossword/derive_clues_from_xd.py --top 15
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crossword.source_data import ENTRIES  # noqa: E402

XD_CLUES_PATH = REPO / "out" / "xd_clue_freq.json"
OUT_PATH = REPO / "out" / "crossword_clues.json"
BACKUP_PATH = REPO / "out" / "crossword_clues_crosswordheaven.json"

# Same filters as scrape_clues.py — keep the deck consistent regardless of
# clue source.
CROSSREF_RE = re.compile(r"\b\d+[-\s](Across|Down)\b", re.IGNORECASE)
CROSSREF_SHORT_RE = re.compile(r"\b\d+[-\s]?[AD]\b")
SEE_REF_RE = re.compile(r"^See (above|below|\d)", re.IGNORECASE)
CRYPTIC_ENUM_RE = re.compile(r"\s*\(\d+(?:[,\s\-]\d+)*\)\s*$")


def clean(raw_clue: str) -> str:
    """Normalize and return the cleaned clue, or '' to drop it."""
    c = raw_clue.strip()
    c = CRYPTIC_ENUM_RE.sub("", c).strip()
    # Strip trailing period — XD treats "Needle case" and "Needle case." as
    # different clues, but they're the same.
    if c.endswith("."):
        c = c[:-1].strip()
    if not c:
        return ""
    if CROSSREF_RE.search(c) or CROSSREF_SHORT_RE.search(c) or SEE_REF_RE.search(c):
        return ""
    return c


def select_top(xd_entries: list[list], n: int) -> list[str]:
    """xd_entries is [[clue, count], ...] sorted desc by count.
    Return up to N cleaned, deduped clues preserving order."""
    seen_lower: set[str] = set()
    # Use an OrderedDict to merge equivalent clues (case-insensitive after
    # period strip) and sum their counts.
    merged: "OrderedDict[str, tuple[str, int]]" = OrderedDict()
    for raw, count in xd_entries:
        c = clean(raw)
        if not c:
            continue
        key = c.lower()
        if key in merged:
            label, total = merged[key]
            merged[key] = (label, total + count)
        else:
            merged[key] = (c, count)
            seen_lower.add(key)
    # Sort by merged total desc, then by first appearance for stability.
    items = sorted(merged.values(), key=lambda x: -x[1])
    return [label for label, _ in items[:n]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--backup", action="store_true", default=True,
                    help="back up existing crossword_clues.json (default on)")
    args = ap.parse_args()

    if not XD_CLUES_PATH.exists():
        print(f"missing {XD_CLUES_PATH}", file=sys.stderr)
        print("Run compute_xd_stats.py first.", file=sys.stderr)
        sys.exit(1)

    xd: dict[str, list[list]] = json.loads(XD_CLUES_PATH.read_text())

    out: dict[str, list[str]] = {}
    n_filled = 0
    n_missing = 0
    n_short = 0
    for e in ENTRIES:
        a = e["answer"]
        entries = xd.get(a, [])
        if not entries:
            print(f"WARN {a}: not in XD corpus")
            out[a] = []
            n_missing += 1
            continue
        clues = select_top(entries, args.top)
        out[a] = clues
        n_filled += 1
        if len(clues) < args.top:
            n_short += 1

    # Back up the crosswordheaven-scraped JSON before overwriting.
    if args.backup and OUT_PATH.exists() and not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(OUT_PATH.read_text())
        print(f"backed up existing clues to {BACKUP_PATH.name}")

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {OUT_PATH} — {n_filled} entries, {n_missing} missing, "
          f"{n_short} with < {args.top} clues")


if __name__ == "__main__":
    main()
