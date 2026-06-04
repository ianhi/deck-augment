"""Estimate Gemini API cost for the full Bangla sentence-generation run,
extrapolating from a cached sample.

Reads the per-call token usage from an experiment JSONL (or the main
results JSONL), computes per-call averages, scales to a target note
count, and prices it using the constants in generate_bangla_sentences.

Note: the per-million-token prices in `MODEL_PRICING_PER_MILLION_USD`
are best-effort estimates. Verify against ai.google.dev/pricing before
trusting the absolute USD figure — the cost SCALE (sample vs full run)
is reliable regardless.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import statistics
from pathlib import Path

from generate_sentences import (
    ANKI_MODEL_NAME,
    MODEL_PRICING_PER_MILLION_USD,
    estimate_cost_usd,
    find_notes_needing_sentences,
)


def load_usage_records(jsonl_path: Path) -> list[dict[str, int]]:
    """Return the per-call `usage` records from a sentence-gen JSONL."""
    records: list[dict[str, int]] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if "error" in entry:
            continue
        usage = entry.get("usage") or {}
        records.append(
            {
                "input_tokens": usage.get("input_tokens", 0) or 0,
                "cached_input_tokens": usage.get("cached_input_tokens", 0) or 0,
                "output_tokens": usage.get("output_tokens", 0) or 0,
                "thoughts_tokens": usage.get("thoughts_tokens", 0) or 0,
            }
        )
    return records


def mean(values: list[int]) -> float:
    return statistics.mean(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=Path("out/experiment_gemini-3-flash-preview.jsonl"),
        help="Per-call results to extrapolate from.",
    )
    parser.add_argument(
        "--model",
        default="gemini-3-flash-preview",
        help="Model name for pricing lookup.",
    )
    parser.add_argument(
        "--target-n",
        type=int,
        default=None,
        help="Target note count for the full run "
        "(default: live count of notes missing Example).",
    )
    args = parser.parse_args()

    records = load_usage_records(args.jsonl)
    if not records:
        raise SystemExit(f"No usable records in {args.jsonl}.")

    avg_input = mean([r["input_tokens"] for r in records])
    avg_cached = mean([r["cached_input_tokens"] for r in records])
    avg_output = mean([r["output_tokens"] for r in records])
    avg_thoughts = mean([r["thoughts_tokens"] for r in records])

    target_n = args.target_n
    if target_n is None:
        target_n = len(find_notes_needing_sentences())

    projected_totals = {
        "input_tokens": int(round(avg_input * target_n)),
        "cached_input_tokens": int(round(avg_cached * target_n)),
        "output_tokens": int(round(avg_output * target_n)),
        "thoughts_tokens": int(round(avg_thoughts * target_n)),
    }

    pricing = MODEL_PRICING_PER_MILLION_USD.get(args.model)
    if not pricing:
        raise SystemExit(
            f"No pricing entry for {args.model!r} — add one to "
            "generate_bangla_sentences.MODEL_PRICING_PER_MILLION_USD."
        )

    sample_cost = estimate_cost_usd(
        args.model,
        {
            "input_tokens": sum(r["input_tokens"] for r in records),
            "cached_input_tokens": sum(r["cached_input_tokens"] for r in records),
            "output_tokens": sum(r["output_tokens"] for r in records),
            "thoughts_tokens": sum(r["thoughts_tokens"] for r in records),
        },
    )
    projected_cost = estimate_cost_usd(args.model, projected_totals)

    # Cost breakdown for the projected run.
    billable_input = projected_totals["input_tokens"] - projected_totals["cached_input_tokens"]
    breakdown = {
        "input (non-cached)":
            billable_input * pricing["input"] / 1_000_000,
        "input (cached)":
            projected_totals["cached_input_tokens"] * pricing["cached_input"] / 1_000_000,
        "output":
            projected_totals["output_tokens"] * pricing["output"] / 1_000_000,
        "thoughts":
            projected_totals["thoughts_tokens"] * pricing["output"] / 1_000_000,
    }

    print(f"Source: {args.jsonl}  ({len(records)} cards)")
    print(f"Model:  {args.model}")
    print("Pricing (USD per 1M tokens, ESTIMATED — verify at ai.google.dev/pricing):")
    for key in ("input", "cached_input", "output"):
        print(f"  {key:<14} ${pricing[key]:.4f}")
    print()
    print("Per-call averages:")
    print(f"  input         {avg_input:>8.1f}")
    print(f"  cached input  {avg_cached:>8.1f}  ({100*avg_cached/avg_input:.1f}% of input)")
    print(f"  output        {avg_output:>8.1f}")
    print(f"  thoughts      {avg_thoughts:>8.1f}")
    print()
    print(f"Sample cost ({len(records)} cards):    ${sample_cost:.4f}")
    print()
    print(f"Projected for {target_n} cards:")
    print(f"  input tokens         {projected_totals['input_tokens']:>10,}")
    print(f"  cached input tokens  {projected_totals['cached_input_tokens']:>10,}")
    print(f"  output tokens        {projected_totals['output_tokens']:>10,}")
    print(f"  thoughts tokens      {projected_totals['thoughts_tokens']:>10,}")
    print()
    print("Cost breakdown:")
    for label, dollars in breakdown.items():
        print(f"  {label:<20} ${dollars:>7.4f}")
    print(f"  {'TOTAL':<20} ${projected_cost:>7.4f}")
    print()
    print(
        f"Note: {ANKI_MODEL_NAME!r} currently has "
        f"{len(find_notes_needing_sentences())} notes with empty Example."
    )


if __name__ == "__main__":
    main()
