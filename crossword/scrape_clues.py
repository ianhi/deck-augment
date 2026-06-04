"""Scrape verified crossword clues for each answer from crosswordheaven.com.

Why crosswordheaven: free, no auth (xwordinfo requires login; crosswordtracker's
TLS cert is expired). Each /words/<answer> page lists every clue used for that
answer across major US publications, roughly in canonicity order.

Polite: 1.2s sleep between requests, on-disk HTML cache, skips already-fetched
words. Run once per source_data edit; results land in out/crossword_clues.json.

Usage:
    uv run crossword/scrape_clues.py            # fetch missing only
    uv run crossword/scrape_clues.py --refresh  # re-fetch everything
    uv run crossword/scrape_clues.py --limit 5  # spot-check
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crossword.source_data import ENTRIES  # noqa: E402

OUT_DIR = REPO / "out"
CACHE_DIR = OUT_DIR / "crossword_cache"
RESULTS_PATH = OUT_DIR / "crossword_clues.json"

UA = "Mozilla/5.0 (deck-augment crossword scraper; one-shot, polite)"
SLEEP_SECONDS = 5.0  # be very gentle — one-shot scrape, no need to hurry
MAX_CLUES_PER_WORD = 15  # keep top-N most-canonical clues

CLUE_RE = re.compile(r'<a href="/clues/[^"]+">([^<]+)</a>')

# Filters for unusable scraped clues:
#  - cross-references like "See 21-Across", "With 29-Down, ...", "Opposite of 65-Across"
#  - bare "See above" / "See below"
CROSSREF_RE = re.compile(r"\b\d+[-\s](Across|Down)\b", re.IGNORECASE)
# Short-form cross-references like "21A", "5D", "12-A", "8 d". The leading
# digits and the boundary between digit and letter are what distinguish these
# from legitimate clues that happen to contain a number followed by a word
# starting with A or D — we require the A/D to be a standalone token.
CROSSREF_SHORT_RE = re.compile(r"\b\d+[-\s]?[AD]\b")
SEE_REF_RE = re.compile(r"^See (above|below)\b", re.IGNORECASE)
# Strip trailing cryptic-style enumeration "(4)" / "(3,5)" etc.
CRYPTIC_ENUM_RE = re.compile(r"\s*\(\d+(?:[,\s\-]\d+)*\)\s*$")


def fetch_word_page(answer: str) -> str:
    cache = CACHE_DIR / f"{answer.lower()}.html"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    url = f"https://crosswordheaven.com/words/{answer.lower()}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            # 429 (rate-limited) and 5xx (server errors) are transient and
            # worth retrying with backoff. Other 4xx are permanent — raise.
            if e.code == 429 or 500 <= e.code < 600:
                last_err = e
                time.sleep(2.0 * (attempt + 1))
                continue
            raise RuntimeError(f"{answer}: HTTP {e.code}") from e
        except (TimeoutError, OSError) as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    else:
        raise RuntimeError(f"{answer}: {last_err}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(body, encoding="utf-8")
    time.sleep(SLEEP_SECONDS)
    return body


def parse_clues(body: str, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in CLUE_RE.finditer(body):
        clue = html_lib.unescape(m.group(1)).strip()
        # Strip trailing cryptic-enumeration "(4)" / "(3,5)".
        clue = CRYPTIC_ENUM_RE.sub("", clue).strip()
        if not clue:
            continue
        # Drop cross-references that are useless out of their original grid.
        if (
            CROSSREF_RE.search(clue)
            or CROSSREF_SHORT_RE.search(clue)
            or SEE_REF_RE.search(clue)
        ):
            continue
        key = clue.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clue)
        if len(out) >= limit:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore HTML cache")
    ap.add_argument("--limit", type=int, default=None, help="only first N entries")
    ap.add_argument("--max-clues", type=int, default=MAX_CLUES_PER_WORD)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.refresh and CACHE_DIR.exists():
        for f in CACHE_DIR.iterdir():
            f.unlink()

    entries = ENTRIES if args.limit is None else ENTRIES[: args.limit]
    # Always load existing results so a scoped run (--limit / --refresh) only
    # updates the entries in scope, rather than wiping everything else.
    # `--refresh` means "ignore cached HTML and re-fetch", not "discard results".
    results: dict[str, list[str]] = {}
    if RESULTS_PATH.exists():
        results = json.loads(RESULTS_PATH.read_text())

    n_new = 0
    n_empty = 0
    for e in entries:
        answer = e["answer"]
        if answer in results and results[answer] and not args.refresh:
            continue
        try:
            body = fetch_word_page(answer)
        except RuntimeError as ex:
            print(f"FAIL {answer}: {ex}")
            # Fail fast: persist what we have, exit so the user can inspect
            # before continuing to hammer the server.
            RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            print(f"\nWrote partial results to {RESULTS_PATH}")
            print(f"  fetched so far: {n_new}, total: {len(results)}")
            sys.exit(1)
        clues = parse_clues(body, args.max_clues)
        if not clues:
            print(f"WARN {answer}: no clues parsed")
            n_empty += 1
        else:
            n_new += 1
            print(f"  {answer}: {len(clues)} clues — top: {clues[0]!r}")
        results[answer] = clues

    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {RESULTS_PATH}")
    print(f"  fetched: {n_new}, empty: {n_empty}, total: {len(results)}")


if __name__ == "__main__":
    main()
