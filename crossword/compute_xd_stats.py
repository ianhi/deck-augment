"""Compute answer frequency + clue-frequency-per-answer from the XD corpus.

Input:  out/xd/xd/clues.tsv (downloaded once, ~256 MB uncompressed, ~8M rows)
Outputs:
  out/xd_answer_freq.json  — {answer: total_count}
  out/xd_clue_freq.json    — {answer: [[clue, count], ...]} top-N per answer

Run after `out/xd/xd-clues.zip` has been downloaded and unzipped (see README).

This gives us a real, citeable frequency source for both:
  (a) "is this answer common enough to include in the deck"
  (b) "what are the canonical clues for this answer, ranked by usage"

The output is publication-agnostic — XD spans NYT, LAT, WSJ, USA Today,
Newsday, Universal, Crosswords with Friends, and many indies.

Usage:
    uv run crossword/compute_xd_stats.py             # full
    uv run crossword/compute_xd_stats.py --top-n 30  # more clues per answer
    uv run crossword/compute_xd_stats.py --filter-min-freq 5  # drop singletons
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TSV = REPO / "out" / "xd" / "xd" / "clues.tsv"
ANSWER_FREQ_PATH = REPO / "out" / "xd_answer_freq.json"
CLUE_FREQ_PATH = REPO / "out" / "xd_clue_freq.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=20, help="keep top-N clues per answer")
    ap.add_argument(
        "--filter-min-freq",
        type=int,
        default=2,
        help="exclude answers seen fewer than this many times (drops one-offs)",
    )
    args = ap.parse_args()

    if not TSV.exists():
        print(f"missing {TSV}", file=sys.stderr)
        print(
            "Download xd-clues.zip from https://xd.saul.pw/data and unzip "
            "into out/xd/ first.",
            file=sys.stderr,
        )
        sys.exit(1)

    answer_count: Counter[str] = Counter()
    clue_count: dict[str, Counter[str]] = defaultdict(Counter)

    t0 = time.time()
    n_rows = 0
    n_skipped = 0

    with TSV.open("r", encoding="utf-8", errors="replace") as f:
        header = f.readline()
        assert header.strip().split("\t") == ["pubid", "year", "answer", "clue"], header
        for line in f:
            n_rows += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                n_skipped += 1
                continue
            _pubid, _year, answer, clue = parts
            answer = answer.strip().upper()
            clue = clue.strip()
            if not answer or not clue:
                n_skipped += 1
                continue
            answer_count[answer] += 1
            clue_count[answer][clue] += 1

    print(f"read {n_rows:,} rows in {time.time() - t0:.1f}s "
          f"(skipped {n_skipped}); {len(answer_count):,} distinct answers")

    # Drop ultra-rare singletons before writing — they bloat the JSON and
    # don't help anyone.
    kept_answers = {a: c for a, c in answer_count.items() if c >= args.filter_min_freq}
    print(f"after min-freq {args.filter_min_freq}: {len(kept_answers):,} answers")

    # Sort the freq dict by count desc, alphabetical secondary
    sorted_freq = dict(
        sorted(kept_answers.items(), key=lambda x: (-x[1], x[0]))
    )
    ANSWER_FREQ_PATH.write_text(json.dumps(sorted_freq, indent=0))
    print(f"wrote {ANSWER_FREQ_PATH} ({ANSWER_FREQ_PATH.stat().st_size / 1024:.0f} KB)")

    # For clue ranking, only keep top-N per answer.
    top_clues: dict[str, list[list]] = {}
    for answer in kept_answers:
        cc = clue_count[answer]
        top = cc.most_common(args.top_n)
        top_clues[answer] = [[clue, n] for clue, n in top]
    CLUE_FREQ_PATH.write_text(json.dumps(top_clues, indent=0, ensure_ascii=False))
    print(f"wrote {CLUE_FREQ_PATH} ({CLUE_FREQ_PATH.stat().st_size / (1024*1024):.1f} MB)")

    # Some quick sanity prints — top 10 most-frequent answers, and a known
    # crosswordese spot-check.
    print("\nTop 10 most-frequent answers across the corpus:")
    for a, c in list(sorted_freq.items())[:10]:
        top_clue = top_clues[a][0][0] if top_clues[a] else "?"
        print(f"  {a:8s} {c:>7,d}  e.g. {top_clue!r}")

    print("\nSpot-check (deck members):")
    for a in ["ETUI", "OLEO", "ANOA", "ESNE", "ADIT", "OAST", "ETNA", "ORE"]:
        c = sorted_freq.get(a, 0)
        clues = top_clues.get(a, [])
        top_clue = clues[0][0] if clues else "?"
        print(f"  {a:8s} {c:>7,d}  e.g. {top_clue!r}")


if __name__ == "__main__":
    main()
