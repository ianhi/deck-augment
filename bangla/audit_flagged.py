"""Audit flagged cards in the user's Anki Bangla deck.

Read-only: queries AnkiConnect for any card in `deck:Bangla` with a flag set,
groups by note, and reports likely problems — especially notes where the
English translation field contains Bangla (Unicode U+0980–U+09FF) characters.

Usage:
    uv run audit_flagged_bangla.py [--deck Bangla] [--out PATH]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import re
from collections import defaultdict
from pathlib import Path

from lib.ankiconnect import ac

BANGLA_RE = re.compile(r"[ঀ-৿]")
LATIN_RE = re.compile(r"[A-Za-z]")
HTML_TAG_RE = re.compile(r"<[^>]+>")

FLAG_NAMES = {
    0: "none",
    1: "red",
    2: "orange",
    3: "green",
    4: "blue",
    5: "pink",
    6: "turquoise",
    7: "purple",
}

# Fields we treat as "should be English" / "should be Bangla".
ENGLISH_FIELDS = {"Eng_main", "Eng_trans", "English", "Meaning", "Translation"}
BANGLA_FIELDS = {"Bangla", "Example", "Word", "Sentence"}


def strip_html(s: str) -> str:
    return HTML_TAG_RE.sub("", s).strip()


def has_bangla(s: str) -> bool:
    return bool(BANGLA_RE.search(s))


def has_latin(s: str) -> bool:
    return bool(LATIN_RE.search(s))


def find_flagged_cards(deck: str) -> list[int]:
    # Use -flag:0 to capture any non-zero flag.
    return ac("findCards", query=f'deck:"{deck}" -flag:0')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--deck", default="Bangla", help="Top-level deck name")
    p.add_argument(
        "--out",
        default="out/flagged_cards_audit.md",
        help="Path for markdown report",
    )
    args = p.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Querying flagged cards in deck:{args.deck} ...")
    card_ids = find_flagged_cards(args.deck)
    print(f"  {len(card_ids)} flagged cards")

    if not card_ids:
        out_path.write_text("# Flagged Bangla cards audit\n\nNo flagged cards found.\n")
        print(f"Wrote {out_path}")
        return

    cards = ac("cardsInfo", cards=card_ids)

    # Group cards by note id and collect flag colors per note.
    note_flags: dict[int, set[int]] = defaultdict(set)
    note_decks: dict[int, set[str]] = defaultdict(set)
    note_card_ids: dict[int, list[int]] = defaultdict(list)
    for c in cards:
        nid = c["note"]
        flag = c.get("flags", 0)
        if flag:
            note_flags[nid].add(flag)
        note_decks[nid].add(c.get("deckName", ""))
        note_card_ids[nid].append(c["cardId"])

    note_ids = list(note_flags.keys())
    print(f"  {len(note_ids)} unique flagged notes")

    notes = ac("notesInfo", notes=note_ids)
    notes_by_id = {n["noteId"]: n for n in notes}

    # Classify each note.
    bangla_in_english: list[dict] = []
    english_in_bangla: list[dict] = []
    empty_fields: list[dict] = []
    duplicate_fields: list[dict] = []
    broken_html: list[dict] = []
    other: list[dict] = []

    for nid in note_ids:
        n = notes_by_id.get(nid)
        if not n:
            continue
        fields = {fname: fdata["value"] for fname, fdata in n["fields"].items()}
        model = n.get("modelName", "")

        issues = []

        # 1. Bangla in English fields (HIGH PRIORITY)
        for fname in fields:
            if fname in ENGLISH_FIELDS:
                txt = strip_html(fields[fname])
                if txt and has_bangla(txt):
                    issues.append(("bangla_in_english", fname))

        # 2. English-only (no Bangla) in fields that should be Bangla
        for fname in fields:
            if fname in BANGLA_FIELDS:
                txt = strip_html(fields[fname])
                if txt and has_latin(txt) and not has_bangla(txt):
                    issues.append(("english_in_bangla", fname))

        # 3. Empty required fields
        for fname in fields:
            if fname in ENGLISH_FIELDS or fname in BANGLA_FIELDS:
                if not strip_html(fields[fname]):
                    issues.append(("empty", fname))

        # 4. Duplicate content between content-bearing fields (skip toggle
        # fields like EnableRecognition="y"). Only consider fields long enough
        # to be meaningful and not in a known toggle/config set.
        SKIP_DUP = {
            "EnableRecognition",
            "EnableProduction",
            "EnableListening",
            "AudioReverse",
            "Add Reverse",
        }
        normalized = {
            fname: strip_html(v).lower()
            for fname, v in fields.items()
            if strip_html(v) and fname not in SKIP_DUP and len(strip_html(v)) >= 4
        }
        seen: dict[str, str] = {}
        for fname, v in normalized.items():
            if v in seen and fname != seen[v]:
                issues.append(("duplicate", f"{seen[v]}=={fname}"))
            else:
                seen[v] = fname

        # 5. Broken HTML (unclosed tag heuristic)
        for fname, v in fields.items():
            if v.count("<") != v.count(">"):
                issues.append(("broken_html", fname))

        record = {
            "note_id": nid,
            "model": model,
            "flags": sorted(note_flags[nid]),
            "decks": sorted(note_decks[nid]),
            "fields": fields,
            "issues": issues,
        }

        kinds = {k for k, _ in issues}
        if "bangla_in_english" in kinds:
            bangla_in_english.append(record)
        elif "english_in_bangla" in kinds:
            english_in_bangla.append(record)
        elif "empty" in kinds:
            empty_fields.append(record)
        elif "duplicate" in kinds:
            duplicate_fields.append(record)
        elif "broken_html" in kinds:
            broken_html.append(record)
        else:
            other.append(record)

    # Build report.
    lines: list[str] = []
    lines.append("# Flagged Bangla cards audit\n")
    lines.append(f"Deck queried: `{args.deck}`  ")
    lines.append(f"Flagged cards: **{len(card_ids)}**  ")
    lines.append(f"Unique flagged notes: **{len(note_ids)}**\n")

    # Summary by flag color (count cards, not notes).
    flag_card_counts: dict[int, int] = defaultdict(int)
    for c in cards:
        f = c.get("flags", 0)
        if f:
            flag_card_counts[f] += 1
    lines.append("## Summary by flag color (cards)\n")
    for f in sorted(flag_card_counts):
        lines.append(f"- {FLAG_NAMES[f]} ({f}): {flag_card_counts[f]}")
    lines.append("")

    flag_note_counts: dict[int, int] = defaultdict(int)
    for nid, flags in note_flags.items():
        for f in flags:
            flag_note_counts[f] += 1
    lines.append("## Summary by flag color (notes)\n")
    for f in sorted(flag_note_counts):
        lines.append(f"- {FLAG_NAMES[f]} ({f}): {flag_note_counts[f]}")
    lines.append("")

    lines.append("## Issue category counts\n")
    lines.append(f"- Bangla in English-translation field: **{len(bangla_in_english)}**")
    lines.append(f"- English text in Bangla field: {len(english_in_bangla)}")
    lines.append(f"- Empty required field: {len(empty_fields)}")
    lines.append(f"- Duplicate content between fields: {len(duplicate_fields)}")
    lines.append(f"- Broken HTML: {len(broken_html)}")
    lines.append(f"- No automated issue detected: {len(other)}")
    lines.append("")

    def dump_record(r: dict) -> list[str]:
        out = []
        flags_label = ", ".join(FLAG_NAMES[f] for f in r["flags"])
        out.append(f"### note {r['note_id']} — flag(s): {flags_label}")
        out.append(f"- model: `{r['model']}`")
        out.append(f"- deck(s): {', '.join(r['decks'])}")
        issues_str = "; ".join(f"{k}:{v}" for k, v in r["issues"]) or "—"
        out.append(f"- issues: {issues_str}")
        out.append("")
        for fname, val in r["fields"].items():
            shown = val if len(val) < 600 else val[:600] + " ...[truncated]"
            out.append(f"  - **{fname}**: {shown!r}")
        out.append("")
        return out

    lines.append("## HIGH PRIORITY: Bangla in English-translation field\n")
    if not bangla_in_english:
        lines.append("_None detected._\n")
    else:
        for r in bangla_in_english:
            lines.extend(dump_record(r))

    lines.append("## English text in Bangla field\n")
    if not english_in_bangla:
        lines.append("_None detected._\n")
    else:
        for r in english_in_bangla:
            lines.extend(dump_record(r))

    lines.append("## Empty required field\n")
    if not empty_fields:
        lines.append("_None detected._\n")
    else:
        for r in empty_fields:
            lines.extend(dump_record(r))

    lines.append("## Duplicate content between fields\n")
    if not duplicate_fields:
        lines.append("_None detected._\n")
    else:
        for r in duplicate_fields:
            lines.extend(dump_record(r))

    lines.append("## Broken HTML\n")
    if not broken_html:
        lines.append("_None detected._\n")
    else:
        for r in broken_html:
            lines.extend(dump_record(r))

    lines.append("## No automated issue detected (manual review)\n")
    if not other:
        lines.append("_None._\n")
    else:
        for r in other:
            lines.extend(dump_record(r))

    # Plain list of note_ids per flag color for follow-up.
    lines.append("## Note IDs by flag color (for follow-up)\n")
    by_color: dict[int, list[int]] = defaultdict(list)
    for nid, flags in note_flags.items():
        for f in flags:
            by_color[f].append(nid)
    for f in sorted(by_color):
        ids = sorted(by_color[f])
        lines.append(f"### {FLAG_NAMES[f]} ({f}) — {len(ids)} notes")
        lines.append("```")
        lines.append(" ".join(str(x) for x in ids))
        lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
