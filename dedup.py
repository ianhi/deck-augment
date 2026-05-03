"""Find frequency-deck headwords that already exist in the user's other Spanish decks.

Reads headwords from ``source.apkg`` (the raw frequency deck) and queries
AnkiConnect for notes in the ES1K, anki-defs-es-MX, and spanish-cloze note
types. Any frequency-deck entry whose headword (or comma/slash-separated form)
matches a known word is written to ``out/dedup_matches.json``.

Use this before importing the frequency deck to identify words you already know
so you can suspend or skip them. Prerequisites: Anki Desktop must be running
with AnkiConnect installed, and ``source.apkg`` must exist in this directory.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from ankiconnect import ac

HERE = Path(__file__).parent
SOURCE_APKG = HERE / "source.apkg"
OUT = HERE / "out"

DEDUP_MODELS: dict[str, str] = {
    "ES1K-v2-02e18+": "Word",
    "ES1K-bangla": "Word",
    "anki-defs-es-MX": "Word",
    "spanish-cloze": "spanish",
}

CLOZE_RE = re.compile(r"\{\{c\d+::([^:}]+?)(?:::[^}]*)?\}\}")


def normalize(word: str) -> str:
    return re.sub(r"\s+", " ", word.strip().lower())


def extract_known_words() -> dict[str, list[str]]:
    """Return {normalized_word: [source_labels]} from the user's existing decks."""
    known: dict[str, list[str]] = {}
    for model, field in DEDUP_MODELS.items():
        nids = ac("findNotes", query=f'note:"{model}"')
        if not nids:
            continue
        infos = ac("notesInfo", notes=nids)
        for info in infos:
            raw = info["fields"].get(field, {}).get("value", "")
            if not raw:
                continue
            if model == "spanish-cloze":
                forms = CLOZE_RE.findall(raw)
            else:
                forms = [raw]
            for form in forms:
                for w in re.split(r"[,/]", form):
                    n = normalize(re.sub(r"<[^>]+>", "", w))
                    if n:
                        known.setdefault(n, []).append(model)
    return known


def extract_frequency_headwords() -> list[tuple[int, str, list[str]]]:
    """Return [(rank, raw_headword, [normalized_forms]), ...] from source.apkg."""
    with zipfile.ZipFile(SOURCE_APKG) as z:
        with z.open("collection.anki21") as f:
            data = f.read()
    tmp = OUT / "_collection.anki21"
    OUT.mkdir(exist_ok=True)
    tmp.write_bytes(data)
    con = sqlite3.connect(tmp)
    rows = con.execute("SELECT flds FROM notes").fetchall()
    con.close()
    tmp.unlink()

    out: list[tuple[int, str, list[str]]] = []
    for (flds,) in rows:
        parts = flds.split("\x1f")
        if not parts[0].isdigit():
            continue
        rank = int(parts[0])
        raw = parts[1]
        forms = [normalize(w) for w in re.split(r"[,/]", raw) if w.strip()]
        out.append((rank, raw, forms))
    return out


def main() -> int:
    if not SOURCE_APKG.exists():
        print(f"missing {SOURCE_APKG}", file=sys.stderr)
        return 1

    print("Extracting headwords from source.apkg...")
    freq = extract_frequency_headwords()
    print(f"  {len(freq)} frequency-deck entries")

    print("Querying AnkiConnect for known words...")
    known = extract_known_words()
    print(f"  {len(known)} unique known words across {len(DEDUP_MODELS)} models")

    matches: list[dict[str, Any]] = []
    for rank, raw, forms in freq:
        hits = {src for form in forms for src in known.get(form, [])}
        if hits:
            matches.append({
                "rank": rank,
                "headword": raw,
                "matched_forms": [f for f in forms if f in known],
                "sources": sorted(hits),
            })

    OUT.mkdir(exist_ok=True)
    out_path = OUT / "dedup_matches.json"
    out_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2))
    print(f"\n{len(matches)} frequency-deck entries match existing Anki cards")
    print(f"Written to {out_path}")

    print("\nBy source:")
    src_counts: Counter[str] = Counter()
    for m in matches:
        for s in m["sources"]:
            src_counts[s] += 1
    for src, n in src_counts.most_common():
        print(f"  {src}: {n}")

    print("\nSample (first 15 matches):")
    for m in matches[:15]:
        print(f"  rank {m['rank']:>4}  {m['headword']!r:<25} -> {','.join(m['sources'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
