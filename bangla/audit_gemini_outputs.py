"""Audit Gemini-generated artifacts in `out/` against the live Anki Bangla deck.

Cross-references:
  - out/bangla_sentences.jsonl   (LLM-generated example sentences)
  - out/bangla_translations.jsonl (LLM-translated existing sentences)
  - out/naturalness_*.jsonl       (naturalness scores)
  - out/bangla_concerns_report.md (already-rendered concerns rows)

…with the live state of each note (via AnkiConnect on localhost:8765) to surface
notes that still need updating. Read-only on Anki; produces a Markdown report.

Categories produced:
  1. bangla_in_english        — Bengali chars (U+0980–U+09FF) in an English field
                                (live `Eng_trans` / `ExampleTranslation`, or LLM
                                translation outputs)
  2. low_naturalness_unfixed  — naturalness score ≤ 3 and the live `Example`
                                field still matches the originally-scored
                                sentence (no revision yet applied)
  3. llm_concerns             — sentence-generation LLM raised a
                                headword/definition concern
  4. sentence_as_headword     — `Bangla` field holds a full sentence
                                (multi-word + sentence-final punctuation)
  5. broken_html              — `<img>` tags in non-image text fields, or
                                unbalanced tag counts

Usage:
    uv run audit_gemini_outputs.py [--out out/gemini_output_audit.md]
                                   [--deck Bangla]
                                   [--no-anki]   # skip live cross-check
                                   [--apply]     # reserved; this script is
                                                 # always read-only on Anki
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import re
from pathlib import Path
from typing import Any

from lib.ankiconnect import ac

BANGLA_RE = re.compile(r"[ঀ-৿]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
IMG_TAG_RE = re.compile(r"<img\b", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[।?!.]\s*$")

ENGLISH_FIELDS = {"Eng_trans", "ExampleTranslation", "eng-disambig"}
BANGLA_FIELDS = {"Bangla", "Example", "bangla-def", "bangla-disambig"}
IMAGE_OK_FIELDS = {"Image"}  # <img> expected here

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "out"


def strip_html(s: str) -> str:
    return HTML_TAG_RE.sub("", s).strip()


def has_bangla(s: str) -> bool:
    return bool(BANGLA_RE.search(s))


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def normalize_for_compare(s: str) -> str:
    """Strip HTML and collapse whitespace for sentence equality checks."""
    return re.sub(r"\s+", " ", strip_html(s)).strip()


def parse_concerns_report(path: Path) -> tuple[dict[int, dict], dict[int, dict]]:
    """Parse the rendered concerns report into headword + definition maps."""
    headword: dict[int, dict] = {}
    definition: dict[int, dict] = {}
    if not path.exists():
        return headword, definition
    section: str | None = None
    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("## Headword spelling concerns"):
            section = "headword"
            continue
        if line.startswith("## Definition concerns"):
            section = "definition"
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not cells[0].isdigit():
            continue
        nid = int(cells[0])
        if section == "headword" and len(cells) >= 5:
            headword[nid] = {
                "current": cells[1],
                "suggested": cells[2],
                "reason": cells[3],
                "gloss": cells[4],
            }
        elif section == "definition" and len(cells) >= 5:
            definition[nid] = {
                "bangla": cells[1],
                "current_gloss": cells[2],
                "suggested": cells[3],
                "reason": cells[4],
            }
    return headword, definition


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(OUT_DIR / "gemini_output_audit.md"))
    p.add_argument("--deck", default="Bangla")
    p.add_argument("--no-anki", action="store_true",
                   help="Skip live AnkiConnect cross-check (use only JSONL artifacts)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="No-op; this script is always read-only. Present for convention.",
    )
    args = p.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load all artifacts.
    # ------------------------------------------------------------------
    sentences = load_jsonl(OUT_DIR / "bangla_sentences.jsonl")
    translations = load_jsonl(OUT_DIR / "bangla_translations.jsonl")
    naturalness_files = [
        OUT_DIR / "naturalness_bangla_sentences.jsonl",
        OUT_DIR / "naturalness_gemini-3-flash-preview.jsonl",
    ]
    naturalness: list[dict] = []
    for nf in naturalness_files:
        naturalness.extend(load_jsonl(nf))
    headword_concerns, definition_concerns = parse_concerns_report(
        OUT_DIR / "bangla_concerns_report.md"
    )

    sentences_by_nid: dict[int, dict] = {r["note_id"]: r for r in sentences}
    translations_by_nid: dict[int, dict] = {r["note_id"]: r for r in translations}
    # Keep best (lowest) naturalness per note when duplicated.
    naturalness_by_nid: dict[int, dict] = {}
    for r in naturalness:
        nid = r.get("note_id")
        if nid is None:
            continue
        prev = naturalness_by_nid.get(nid)
        if prev is None or r.get("naturalness_score", 5) < prev.get(
            "naturalness_score", 5
        ):
            naturalness_by_nid[nid] = r

    print(f"Loaded sentences:     {len(sentences_by_nid)}")
    print(f"Loaded translations:  {len(translations_by_nid)}")
    print(f"Loaded naturalness:   {len(naturalness_by_nid)}")
    print(f"Headword concerns:    {len(headword_concerns)}")
    print(f"Definition concerns:  {len(definition_concerns)}")

    # ------------------------------------------------------------------
    # Fetch live Anki notes for cross-reference.
    # ------------------------------------------------------------------
    live_by_nid: dict[int, dict[str, str]] = {}
    if not args.no_anki:
        print(f"Querying AnkiConnect for deck:{args.deck} ...")
        live_nids: list[int] = ac(
            "findNotes", query='"note:Bangla (and reversed)"'
        )
        print(f"  {len(live_nids)} notes in 'Bangla (and reversed)' model")
        # Fetch in batches.
        BATCH = 500
        infos: list[dict[str, Any]] = []
        for i in range(0, len(live_nids), BATCH):
            infos.extend(ac("notesInfo", notes=live_nids[i : i + BATCH]))
        for n in infos:
            live_by_nid[n["noteId"]] = {
                k: v["value"] for k, v in n["fields"].items()
            }

    # ------------------------------------------------------------------
    # Compute issues.
    # ------------------------------------------------------------------
    bangla_in_english: list[dict] = []
    low_naturalness_unfixed: list[dict] = []
    llm_concerns: list[dict] = []
    sentence_as_headword: list[dict] = []
    broken_html: list[dict] = []

    # Union of all note IDs we might need to consider.
    all_nids: set[int] = set()
    all_nids.update(sentences_by_nid)
    all_nids.update(translations_by_nid)
    all_nids.update(naturalness_by_nid)
    all_nids.update(headword_concerns)
    all_nids.update(definition_concerns)
    all_nids.update(live_by_nid)

    for nid in sorted(all_nids):
        live = live_by_nid.get(nid)

        # ---- 1. Bangla characters in English field --------------------
        details: list[str] = []
        # LLM artifacts
        s = sentences_by_nid.get(nid)
        if s and has_bangla(s.get("english_translation", "") or ""):
            details.append(
                f"bangla_sentences.jsonl english_translation = "
                f"{s['english_translation']!r}"
            )
        t = translations_by_nid.get(nid)
        if t and has_bangla(t.get("english_translation", "") or ""):
            details.append(
                f"bangla_translations.jsonl english_translation = "
                f"{t['english_translation']!r}"
            )
        if live:
            for fname in ENGLISH_FIELDS:
                v = strip_html(live.get(fname, ""))
                if v and has_bangla(v):
                    details.append(f"live `{fname}` contains Bangla: {v!r}")
        if details:
            bangla_in_english.append(
                {"note_id": nid, "details": details, "live": live}
            )

        # ---- 2. Low naturalness, not yet fixed ------------------------
        nat = naturalness_by_nid.get(nid)
        if nat and nat.get("naturalness_score", 5) <= 3:
            generated_sentence = (s or {}).get("bangla_sentence", "") if s else ""
            live_example = (live or {}).get("Example", "")
            still_same = bool(generated_sentence) and (
                normalize_for_compare(generated_sentence)
                == normalize_for_compare(live_example)
            )
            # If we don't have Anki access, list it anyway as "needs check".
            include = (not live) or still_same or not generated_sentence
            if include:
                low_naturalness_unfixed.append(
                    {
                        "note_id": nid,
                        "score": nat.get("naturalness_score"),
                        "issues": nat.get("issues", []),
                        "suggested_revision": nat.get("suggested_revision", ""),
                        "native_would_say": nat.get("native_would_say"),
                        "generated_sentence": generated_sentence,
                        "live_example": live_example,
                        "matches_generated": still_same,
                        "live": live,
                    }
                )

        # ---- 3. LLM-flagged concerns ----------------------------------
        hc = headword_concerns.get(nid)
        dc = definition_concerns.get(nid)
        # Also pick up concerns embedded inline in JSONL records.
        inline_h = None
        inline_d = None
        for src in (s, t):
            if not src:
                continue
            h = src.get("headword_concern") or {}
            if h.get("suspected"):
                inline_h = h
            d = src.get("definition_concern") or {}
            if d.get("suspected"):
                inline_d = d
        if hc or dc or inline_h or inline_d:
            llm_concerns.append(
                {
                    "note_id": nid,
                    "headword_concern": hc or inline_h,
                    "definition_concern": dc or inline_d,
                    "live": live,
                }
            )

        # ---- 4. Sentence-as-headword data issues ----------------------
        bangla_field = (live or {}).get("Bangla", "") if live else ""
        bangla_stripped = strip_html(bangla_field)
        if bangla_stripped:
            looks_like_sentence = (
                SENTENCE_END_RE.search(bangla_stripped) is not None
                and len(bangla_stripped.split()) >= 3
            )
            if looks_like_sentence:
                sentence_as_headword.append(
                    {
                        "note_id": nid,
                        "bangla_field": bangla_stripped,
                        "eng_trans": (live or {}).get("Eng_trans", ""),
                        "suggested": (hc or {}).get("suggested", ""),
                        "live": live,
                    }
                )

        # ---- 5. Broken HTML / misfiled <img> --------------------------
        broken_details: list[str] = []
        if live:
            for fname, v in live.items():
                if fname in IMAGE_OK_FIELDS:
                    continue
                if fname in {
                    "EnableRecognition",
                    "EnableProduction",
                    "EnableListening",
                    "WordAudio",
                    "ExampleAudio",
                    "type",
                }:
                    continue
                if IMG_TAG_RE.search(v or ""):
                    broken_details.append(f"`{fname}` contains <img>: {v[:160]!r}")
                if (v or "").count("<") != (v or "").count(">"):
                    broken_details.append(
                        f"`{fname}` has unbalanced angle brackets: {v[:160]!r}"
                    )
        if broken_details:
            broken_html.append(
                {"note_id": nid, "details": broken_details, "live": live}
            )

    # ------------------------------------------------------------------
    # Render report.
    # ------------------------------------------------------------------
    lines: list[str] = []
    lines.append("# Gemini-output audit vs live Anki Bangla deck\n")
    if args.no_anki:
        lines.append("_Generated with `--no-anki`; live deck not consulted._\n")
    lines.append("## Counts\n")
    lines.append(f"- Bangla text in English field: **{len(bangla_in_english)}**")
    lines.append(
        f"- Low naturalness (≤3) not yet revised: **{len(low_naturalness_unfixed)}**"
    )
    lines.append(f"- LLM headword/definition concerns: **{len(llm_concerns)}**")
    lines.append(f"- Sentence-as-headword data issues: **{len(sentence_as_headword)}**")
    lines.append(f"- Broken HTML / mis-fielded <img>: **{len(broken_html)}**")
    lines.append("")

    def live_snippet(live: dict[str, str] | None) -> list[str]:
        if not live:
            return ["  - _(no live Anki data fetched for this note)_"]
        keys = ["Bangla", "Eng_trans", "Example", "ExampleTranslation", "Notes"]
        out = []
        for k in keys:
            v = live.get(k, "")
            shown = v if len(v) < 300 else v[:300] + " ...[truncated]"
            out.append(f"  - **{k}**: {shown!r}")
        return out

    # --- 1
    lines.append("## 1. Bangla text in English field (HIGH PRIORITY)\n")
    if not bangla_in_english:
        lines.append("_None detected._\n")
    else:
        for r in bangla_in_english:
            lines.append(f"### note {r['note_id']}")
            for d in r["details"]:
                lines.append(f"  - {d}")
            lines.extend(live_snippet(r["live"]))
            lines.append("")

    # --- 2
    lines.append("## 2. Low-naturalness sentences not yet revised\n")
    if not low_naturalness_unfixed:
        lines.append("_None detected._\n")
    else:
        for r in sorted(low_naturalness_unfixed, key=lambda x: x["score"]):
            lines.append(f"### note {r['note_id']} — score {r['score']}")
            if r.get("issues"):
                lines.append(f"  - issues: {r['issues']}")
            if r.get("suggested_revision"):
                lines.append(
                    f"  - suggested revision: {r['suggested_revision']!r}"
                )
            lines.append(
                f"  - matches originally-generated sentence in Anki? "
                f"{r['matches_generated']}"
            )
            lines.append(f"  - generated: {r['generated_sentence']!r}")
            lines.append(f"  - live Example: {r['live_example']!r}")
            lines.extend(live_snippet(r["live"]))
            lines.append("")

    # --- 3
    lines.append("## 3. LLM-flagged headword/definition concerns\n")
    if not llm_concerns:
        lines.append("_None detected._\n")
    else:
        for r in llm_concerns:
            lines.append(f"### note {r['note_id']}")
            hc = r.get("headword_concern")
            dc = r.get("definition_concern")
            if hc:
                lines.append(
                    f"  - **headword**: current={hc.get('current', '')!r} → "
                    f"suggested={hc.get('suggested', '')!r}; "
                    f"reason: {hc.get('reason', '')}"
                )
            if dc:
                lines.append(
                    f"  - **definition**: current_gloss="
                    f"{dc.get('current_gloss', dc.get('current', ''))!r} → "
                    f"suggested={dc.get('suggested', '')!r}; "
                    f"reason: {dc.get('reason', '')}"
                )
            lines.extend(live_snippet(r["live"]))
            lines.append("")

    # --- 4
    lines.append("## 4. Sentence-as-headword data issues\n")
    if not sentence_as_headword:
        lines.append("_None detected._\n")
    else:
        for r in sentence_as_headword:
            lines.append(f"### note {r['note_id']}")
            lines.append(f"  - Bangla field (full sentence): {r['bangla_field']!r}")
            lines.append(f"  - Eng_trans: {r['eng_trans']!r}")
            if r.get("suggested"):
                lines.append(f"  - LLM-suggested headword: {r['suggested']!r}")
            lines.extend(live_snippet(r["live"]))
            lines.append("")

    # --- 5
    lines.append("## 5. Broken HTML / mis-fielded <img>\n")
    if not broken_html:
        lines.append("_None detected._\n")
    else:
        for r in broken_html:
            lines.append(f"### note {r['note_id']}")
            for d in r["details"]:
                lines.append(f"  - {d}")
            lines.extend(live_snippet(r["live"]))
            lines.append("")

    # --- batch lists
    lines.append("## Note-ID batch lists (for re-processing)\n")
    categories = [
        ("bangla_in_english", bangla_in_english),
        ("low_naturalness_unfixed", low_naturalness_unfixed),
        ("llm_concerns", llm_concerns),
        ("sentence_as_headword", sentence_as_headword),
        ("broken_html", broken_html),
    ]
    for name, recs in categories:
        ids = sorted({r["note_id"] for r in recs})
        lines.append(f"### {name} — {len(ids)} notes")
        lines.append("```")
        lines.append(" ".join(str(x) for x in ids) if ids else "(empty)")
        lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"Wrote {out_path}")

    # Console summary.
    print("\n=== Counts ===")
    print(f"  bangla_in_english:        {len(bangla_in_english)}")
    print(f"  low_naturalness_unfixed:  {len(low_naturalness_unfixed)}")
    print(f"  llm_concerns:             {len(llm_concerns)}")
    print(f"  sentence_as_headword:     {len(sentence_as_headword)}")
    print(f"  broken_html:              {len(broken_html)}")


if __name__ == "__main__":
    main()
