"""Merge subagent batch outputs into a single bolded-sentences artefact.

Reads all ``batch_NN_output.md`` files from the bold-outputs directory,
cross-references each line against its ``batch_NN_manifest.json``, and writes:

  - ``out/bolded_sentences.json`` — list of ``{note_id, rank, headword,
    bolded_sentence, no_match, regional_note?}`` objects, one per note.
  - ``out/flags_report.md``       — markdown report of all tagged lines,
    grouped by category, for manual review.

Expected input format per output line::

    N. BOLDED_SENTENCE  [TAG: reason] [TAG: reason] ...
    N. [NO_MATCH] SENTENCE_UNCHANGED

Valid tags: ``NO_MATCH``, ``REGIONAL``, ``UNGRAMMATICAL``, ``ARCHAIC``,
``AWKWARD``, ``TYPO``.

Usage::

    python aggregate_bolded.py
    python aggregate_bolded.py --num-batches 50
    python aggregate_bolded.py --batch-dir out/bold_batches --out-dir out/bold_outputs

Inputs:  out/bold_batches/batch_NN_manifest.json
         out/bold_outputs/batch_NN_output.md
Outputs: out/bolded_sentences.json
         out/flags_report.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUT_ROOT = HERE / "out"
DEFAULT_BATCH_DIR = DEFAULT_OUT_ROOT / "bold_batches"
DEFAULT_OUTPUT_DIR = DEFAULT_OUT_ROOT / "bold_outputs"
DEFAULT_NUM_BATCHES = 50

FLAG_CATEGORIES = ("REGIONAL", "TYPO", "UNGRAMMATICAL", "AWKWARD", "ARCHAIC", "NO_MATCH")

LINE_RE = re.compile(r"^\s*(\d+)\.\s*(.*)$")
TAG_RE = re.compile(r"\[(NO_MATCH|REGIONAL|UNGRAMMATICAL|ARCHAIC|AWKWARD|TYPO)(?::\s*([^\]]*))?\]")


def parse_output_line(line: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (cleaned_sentence, [(tag, reason), ...]).

    Strips all recognised tag annotations from *line* and returns the
    remaining text alongside a list of (tag, reason) pairs.
    """
    tags: list[tuple[str, str]] = []

    def grab(m: re.Match[str]) -> str:
        tag = m.group(1)
        reason = (m.group(2) or "").strip()
        tags.append((tag, reason))
        return ""

    cleaned = TAG_RE.sub(grab, line).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned, tags


def aggregate(
    batch_dir: Path,
    output_dir: Path,
    num_batches: int,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]], list[str]]:
    """Read all batch pairs and return aggregated data.

    Args:
        batch_dir:   Directory containing manifest JSON files.
        output_dir:  Directory containing subagent output markdown files.
        num_batches: Number of batches to process (0 .. num_batches-1).

    Returns:
        A tuple of:
        - entries: list of note dicts (one per processed line).
        - flags_by_category: dict mapping tag name -> list of flag dicts.
        - line_mismatches: list of human-readable mismatch warnings.
    """
    bolded_by_note: dict[int, dict[str, object]] = {}
    flags_by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    line_mismatches: list[str] = []

    for batch_num in range(num_batches):
        out_path = output_dir / f"batch_{batch_num:02d}_output.md"
        manifest_path = batch_dir / f"batch_{batch_num:02d}_manifest.json"

        manifest: list[dict[str, object]] = json.loads(manifest_path.read_text())
        manifest_by_line: dict[int, dict[str, object]] = {int(m["line"]): m for m in manifest}  # type: ignore[arg-type]

        output_lines = out_path.read_text().splitlines()
        if len(output_lines) != len(manifest):
            line_mismatches.append(
                f"batch {batch_num:02d}: {len(output_lines)} output lines vs "
                f"{len(manifest)} manifest entries"
            )

        for raw in output_lines:
            match = LINE_RE.match(raw)
            if not match:
                continue
            lineno = int(match.group(1))
            body = match.group(2)
            manifest_entry = manifest_by_line.get(lineno)
            if not manifest_entry:
                continue
            note_id = int(manifest_entry["note_id"])  # type: ignore[arg-type]
            headword = str(manifest_entry["headword"])
            rank = (batch_num * 100) + lineno

            sentence, tags = parse_output_line(body)

            no_match = any(t[0] == "NO_MATCH" for t in tags)
            regional_notes = [t for t in tags if t[0] == "REGIONAL"]

            entry: dict[str, object] = {
                "note_id": note_id,
                "rank": rank,
                "headword": headword,
                "bolded_sentence": sentence,
                "no_match": no_match,
            }
            if regional_notes:
                entry["regional_note"] = "; ".join(reason for _, reason in regional_notes)
            bolded_by_note[note_id] = entry

            for tag, reason in tags:
                flags_by_category[tag].append({
                    "rank": rank,
                    "headword": headword,
                    "note_id": note_id,
                    "reason": reason,
                    "sentence": sentence,
                })

    return list(bolded_by_note.values()), dict(flags_by_category), line_mismatches


def write_flags_report(
    flags_by_category: dict[str, list[dict[str, object]]],
    total_entries: int,
    num_batches: int,
    dest: Path,
) -> None:
    """Write a markdown flags report to *dest*."""
    report_lines: list[str] = [
        "# Flags Report\n",
        f"Generated from {num_batches} subagent batches. Total entries: {total_entries}.\n",
    ]
    for cat in FLAG_CATEGORIES:
        items = flags_by_category.get(cat, [])
        report_lines.append(f"\n## {cat} ({len(items)})\n")
        for it in sorted(items, key=lambda x: x["rank"]):  # type: ignore[arg-type, return-value]
            reason_suffix = f" — {it['reason']}" if it["reason"] else ""
            report_lines.append(
                f"- rank {it['rank']} `{it['headword']}`: {it['sentence']}{reason_suffix}"
            )
    dest.write_text("\n".join(report_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge subagent bold-output batches into bolded_sentences.json + flags_report.md.",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=DEFAULT_BATCH_DIR,
        metavar="DIR",
        help=f"Directory containing manifest JSON files (default: {DEFAULT_BATCH_DIR})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory containing batch_NN_output.md files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--num-batches",
        type=int,
        default=DEFAULT_NUM_BATCHES,
        metavar="N",
        help=f"Number of batches to aggregate (default: {DEFAULT_NUM_BATCHES})",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_OUT_ROOT / "bolded_sentences.json",
        metavar="FILE",
        help="Destination for the merged JSON (default: out/bolded_sentences.json)",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=DEFAULT_OUT_ROOT / "flags_report.md",
        metavar="FILE",
        help="Destination for the flags report (default: out/flags_report.md)",
    )
    args = parser.parse_args()

    entries, flags_by_category, line_mismatches = aggregate(
        args.batch_dir, args.out_dir, args.num_batches
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_flags_report(flags_by_category, len(entries), args.num_batches, args.report_out)

    print(f"Aggregated {len(entries)} entries → {args.json_out}")
    print(f"Flags report → {args.report_out}")
    print()
    print("Flag counts:")
    for cat in FLAG_CATEGORIES:
        print(f"  {cat:<16} {len(flags_by_category.get(cat, []))}")
    if line_mismatches:
        print("\nMismatched batches (expected 100 lines):")
        for msg in line_mismatches:
            print(f"  {msg}")


if __name__ == "__main__":
    main()
