"""Cross-reference source_data.ENTRIES against the XD-corpus frequency data.

Reports:
  1. Current entries with their XD frequency — flags low-frequency outliers
     that probably shouldn't be in the deck.
  2. Top-N highest-frequency XD answers NOT in the deck — candidates for
     v1.3 additions.

Run after `compute_xd_stats.py` has produced `out/xd_answer_freq.json`.

Usage:
    uv run crossword/audit_vs_xd.py
    uv run crossword/audit_vs_xd.py --top 100  # candidate count
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crossword.source_data import ENTRIES  # noqa: E402

ANSWER_FREQ_PATH = REPO / "out" / "xd_answer_freq.json"
CLUE_FREQ_PATH = REPO / "out" / "xd_clue_freq.json"

# Words we'd skip even if XD-frequent: ultra-common English that doesn't
# need a flashcard. Trim conservatively.
SKIP_TRIVIAL = {
    "ONE", "TWO", "TEN", "ALL", "AND", "ARE", "BUT", "CAN", "DAY", "ETC",
    "FOR", "GET", "HAS", "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY",
    "NEW", "NOT", "NOW", "OFF", "OLD", "OUR", "OUT", "PUT", "SAY", "SEE",
    "SET", "SHE", "TAX", "THE", "TOO", "TOP", "USE", "WAS", "WAY", "WHO",
    "WHY", "YES", "YET", "YOU",
    "ABLE", "ALSO", "ANTI", "AUTO", "AWAY", "BACK", "BAD", "BAR", "BED",
    "BEST", "BIG", "BIT", "BOX", "BOY", "CAR", "CAT", "CITY", "DOG", "DOOR",
    "DOWN", "EACH", "EAT", "EGG", "END", "EVEN", "EVER", "FACE", "FACT",
    "FAR", "FEW", "FIND", "FIRE", "FISH", "FIVE", "FLY", "FOOD", "FOOT",
    "FOUR", "FREE", "FROM", "FULL", "FUN", "GAME", "GAVE", "GET", "GIRL",
    "GIVE", "GOD", "GONE", "GOOD", "GOT", "GUN", "HAD", "HAIR", "HALF",
    "HARD", "HEAD", "HEAR", "HELP", "HERE", "HIGH", "HOLD", "HOLE", "HOME",
    "HOT", "HOUR", "HOUSE", "HUH", "IDEA", "INTO", "IRON", "JOB", "JUST",
    "KEEP", "KEY", "KIND", "KING", "KISS", "KNEW", "KNOW", "LADY", "LAID",
    "LATE", "LAW", "LEFT", "LESS", "LIE", "LIFE", "LIKE", "LINE", "LIST",
    "LIVE", "LONG", "LOOK", "LORD", "LOSE", "LOST", "LOT", "LOVE", "LOW",
    "MADE", "MAKE", "MAN", "MANY", "MAYBE", "ME", "MEAN", "MEET", "MEN",
    "MET", "MILE", "MIND", "MISS", "MORE", "MOST", "MOVE", "MUCH", "MUST",
    "NAME", "NEAR", "NEED", "NEW", "NEXT", "NICE", "NIGHT", "NINE", "NOSE",
    "NOTE", "NOW", "OFF", "OK", "OLD", "ONCE", "ONLY", "OPEN", "OUT",
    "OVER", "OWN", "PAGE", "PAGE", "PAID", "PAIN", "PAIR", "PARK", "PART",
    "PAST", "PATH", "PAY", "PEN", "PEOPLE", "PER", "PICK", "PIN", "PIPE",
    "PLAN", "PLAY", "POOR", "PUT", "RACE", "RAIN", "RAN", "REAL", "RED",
    "REST", "RICH", "RIDE", "RING", "RISE", "ROAD", "ROCK", "ROLE", "ROLL",
    "ROOM", "ROSE", "RUN", "SAFE", "SAID", "SAME", "SAVE", "SAY", "SEA",
    "SEE", "SEEK", "SEEN", "SELL", "SEND", "SENT", "SET", "SEW", "SEX",
    "SHIP", "SHOE", "SHOP", "SHOT", "SHOW", "SHUT", "SICK", "SIDE", "SIGN",
    "SING", "SIR", "SIT", "SITE", "SIX", "SIZE", "SKIN", "SKY", "SLOW",
    "SMALL", "SNOW", "SO", "SOFT", "SOME", "SON", "SONG", "SOON", "SORT",
    "SOUL", "SPOT", "STAR", "STAY", "STEP", "STILL", "STOP", "SUCH", "SUM",
    "SUN", "TAKE", "TALK", "TALL", "TAPE", "TASK", "TAX", "TAXI", "TEA",
    "TEACH", "TEAM", "TELL", "TEN", "TEND", "TEST", "TEXT", "THAN", "THAT",
    "THE", "THEM", "THEN", "THERE", "THEY", "THIN", "THIS", "THOSE",
    "THREE", "THROW", "THUS", "TIE", "TIME", "TINY", "TIP", "TIRE", "TO",
    "TOGETHER", "TOLD", "TONE", "TOO", "TOP", "TORE", "TRAIN", "TREE",
    "TRIP", "TRUE", "TRY", "TURN", "TWICE", "TYPE", "UP", "UPON", "US",
    "USE", "USED", "VAN", "VAST", "VERY", "VIEW", "VOTE", "WAIT", "WALK",
    "WALL", "WAR", "WARM", "WARN", "WAS", "WASH", "WATCH", "WATER", "WAVE",
    "WAY", "WE", "WEAK", "WEAR", "WEEK", "WELL", "WENT", "WERE", "WEST",
    "WHAT", "WHEEL", "WHEN", "WHERE", "WHITE", "WHO", "WHOM", "WHOSE",
    "WHY", "WIDE", "WIFE", "WILL", "WIN", "WIND", "WINE", "WING", "WISE",
    "WISH", "WITH", "WOMAN", "WON", "WOOD", "WORD", "WORE", "WORK", "WORLD",
    "WORN", "WRITE", "WRONG", "WROTE", "YEAR", "YES", "YET", "YOU", "YOUNG",
    "YOUR",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="candidate count")
    ap.add_argument("--min-len", type=int, default=3)
    ap.add_argument("--max-len", type=int, default=5)
    args = ap.parse_args()

    if not ANSWER_FREQ_PATH.exists():
        print(f"missing {ANSWER_FREQ_PATH}", file=sys.stderr)
        print("Run compute_xd_stats.py first.", file=sys.stderr)
        sys.exit(1)

    freq: dict[str, int] = json.loads(ANSWER_FREQ_PATH.read_text())
    have = {e["answer"] for e in ENTRIES}

    # 1. Audit current entries
    print(f"=== Current deck ({len(ENTRIES)} entries) — XD frequency ===\n")
    rows = []
    for e in ENTRIES:
        rows.append((e["answer"], freq.get(e["answer"], 0)))
    rows.sort(key=lambda x: x[1])
    print(f"{'Rank':>5}  {'Answer':<8} {'XD freq':>8}  Verdict")
    print("-" * 50)
    for i, (a, c) in enumerate(rows[:20]):
        if c < 50:
            verdict = "VERY LOW — consider dropping"
        elif c < 200:
            verdict = "low"
        elif c < 1000:
            verdict = "ok"
        else:
            verdict = "high"
        print(f"  {i + 1:>3}  {a:<8} {c:>8,d}  {verdict}")
    print(f"  ... ({len(rows) - 20} more entries with freq ≥ {rows[20][1]})")

    # 2. Top-N missing
    print(f"\n=== Top {args.top} missing answers (length {args.min_len}-{args.max_len}) ===\n")
    candidates: list[tuple[str, int]] = []
    for a, c in freq.items():
        if a in have:
            continue
        if a in SKIP_TRIVIAL:
            continue
        if not (args.min_len <= len(a) <= args.max_len):
            continue
        # require all-uppercase letters; XD has some weird tokens (numbers,
        # rebus pieces) we don't want.
        if not a.isalpha() or not a.isupper():
            continue
        candidates.append((a, c))
    candidates.sort(key=lambda x: -x[1])

    print(f"{'Answer':<8} {'XD freq':>8}")
    print("-" * 22)
    for a, c in candidates[: args.top]:
        print(f"{a:<8} {c:>8,d}")

    # 3. Length distribution of misses
    print("\n=== Length distribution of top candidates ===")
    from collections import Counter
    by_len = Counter(len(a) for a, _ in candidates[: args.top])
    for L in sorted(by_len):
        print(f"  {L} letters: {by_len[L]}")


if __name__ == "__main__":
    main()
