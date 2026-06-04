"""Apply the 8 example-field fixes from out/example_issues.jsonl review.

Updates Anki notes via AnkiConnect, deletes stale TTS audio files so the
next `tts_run --profile bangla-vocab` pass regenerates them.

Idempotent: re-running after success is safe (notes already updated; audio
files already deleted/regenerated).

Run:
    uv run bangla/fix_example_junk.py             # dry-run
    uv run bangla/fix_example_junk.py --apply     # write to Anki + delete audio
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.ankiconnect import ac


AUDIO_DIR = Path(__file__).resolve().parents[1] / "out" / "audio_bn"


# nid -> dict of field updates. Each rewrite includes the new Bangla example
# (with <b>headword</b>) and a fresh ExampleTranslation matching the new
# sentence. #9 also clears up the wrong Eng_trans/bangla-def for খোয়া.
FIXES: list[dict] = [
    {
        "nid": 1756427001859,
        "headword": "দেশান্তর",
        "fields": {
            "Example": "গত বছর তাঁরা <b>দেশান্তরে</b> চলে গেছেন।",
            "ExampleTranslation": "Last year they emigrated.",
        },
    },
    {
        "nid": 1767516699804,
        "headword": "প্রযুক্তি",
        "fields": {
            "Example": "নতুন <b>প্রযুক্তি</b> জীবনকে সহজ করে।",
            "ExampleTranslation": "New technology makes life easier.",
        },
    },
    {
        "nid": 1768738835598,
        "headword": "ধনুর্ধর",
        "fields": {
            "Example": "অর্জুন ছিলেন শ্রেষ্ঠ <b>ধনুর্ধর</b>।",
            "ExampleTranslation": "Arjun was the greatest archer.",
        },
    },
    {
        "nid": 1768739385152,
        "headword": "মহারথী",
        "fields": {
            "Example": "সব <b>মহারথী</b> মিলে অভিমন্যুকে বধ করেছিল।",
            "ExampleTranslation": "All the great warriors together killed Abhimanyu.",
        },
    },
    {
        "nid": 1768739723281,
        "headword": "বধ",
        "fields": {
            "Example": "রাবণকে <b>বধ</b> করেছিলেন রাম।",
            "ExampleTranslation": "Ram killed Ravan.",
        },
    },
    {
        "nid": 1774224819099,
        "headword": "ঝোলা",
        "fields": {
            "Example": "বারান্দার রেলিং থেকে একটা বোর্ড <b>ঝুলছে</b>।",
            "ExampleTranslation": "A board is hanging from the verandah railing.",
        },
    },
    # #7 অচেনা skipped — book quote, leave alone
    {
        "nid": 1774327754174,
        "headword": "তাও",
        "fields": {
            "Example": "অনেক দিন আগের কথা, <b>তাও</b> মনে আছে।",
            "ExampleTranslation": "It was long ago; even so, I remember.",
        },
    },
    {
        "nid": 1774327755099,
        "headword": "খোয়া",
        "fields": {
            "Eng_trans": "to lose",
            "bangla-def": "হারানো; নষ্ট করা",
            "Example": "সাবধান, হাত থেকে চাবিটা <b>খুইয়ো</b> না।",
            "ExampleTranslation": "Careful, don't lose the key from your hand.",
        },
    },
]


# Alphabet card with trailing &nbsp; in example-word-1.
ALPHABET_FIX = {
    "nid": 1769196161341,
    "field": "example-word-1",
    "old_value": "টাকা&nbsp;",
    "new_value": "টাকা",
}


def stale_audio_paths(nid: int) -> list[Path]:
    return [
        AUDIO_DIR / f"bn_{nid}_sentence.mp3",
        AUDIO_DIR / f"bn_{nid}_sentence_raw.mp3",
    ]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="write to Anki + delete audio files")
    args = p.parse_args()

    print(f"{'APPLY' if args.apply else 'DRY-RUN'}: {len(FIXES)} example rewrites + 1 alphabet fix\n")

    for fix in FIXES:
        nid = fix["nid"]
        print(f"  nid={nid} ({fix['headword']})")
        for k, v in fix["fields"].items():
            print(f"    {k} → {v[:80]}")
        stale = [p for p in stale_audio_paths(nid) if p.exists()]
        if stale:
            print(f"    audio to delete: {[p.name for p in stale]}")
        if args.apply:
            ac("updateNoteFields", note={"id": nid, "fields": fix["fields"]})
            for p in stale:
                p.unlink()
        print()

    print(f"  alphabet nid={ALPHABET_FIX['nid']} field={ALPHABET_FIX['field']}")
    print(f"    {ALPHABET_FIX['old_value']!r} → {ALPHABET_FIX['new_value']!r}")
    if args.apply:
        ac(
            "updateNoteFields",
            note={
                "id": ALPHABET_FIX["nid"],
                "fields": {ALPHABET_FIX["field"]: ALPHABET_FIX["new_value"]},
            },
        )

    if args.apply:
        print("\nDONE. Now run:")
        print("  uv run bangla/tts_run.py --profile bangla-vocab")
        print("  uv run bangla/tts_run.py --profile bangla-vocab --apply")
    else:
        print("\n(dry run — re-run with --apply to write)")


if __name__ == "__main__":
    main()
