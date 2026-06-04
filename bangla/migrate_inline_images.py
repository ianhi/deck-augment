"""Move <img> tags from the `Eng_trans` field to the dedicated `Image`
field for `Bangla (and reversed)` notes.

Old data shape (from when notes were typed quickly in the Anki editor):
  Eng_trans = 'wardrobe<br><br><img src="...jpg">'
  Image     = ''

New shape:
  Eng_trans = 'wardrobe'
  Image     = '<img src="...jpg">'

Only touches notes where:
  - `Eng_trans` contains an `<img>` tag, AND
  - `Image` is empty (we never overwrite existing Image content).

Dry-run by default. Pass `--apply` to write via AnkiConnect.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import re

from lib.ankiconnect import ac

ANKI_MODEL_NAME = "Bangla (and reversed)"

IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
BR_RE = re.compile(r"(?:<br\s*/?\s*>\s*)+", re.IGNORECASE)


def split_gloss_and_images(value: str) -> tuple[str, str]:
    """Return (clean_gloss, image_html). Image html is the joined <img>
    tags (in order); clean_gloss is the rest of the field with trailing
    <br>s trimmed."""
    imgs = IMG_TAG_RE.findall(value)
    remainder = IMG_TAG_RE.sub("", value)
    # Collapse trailing <br>...<br> left dangling after image removal.
    remainder = BR_RE.sub("\n", remainder).strip()
    # If the only remaining whitespace is breaks/newlines, leave empty.
    if remainder in {"", "\n"}:
        remainder = ""
    return remainder, " ".join(imgs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = parser.parse_args()

    candidate_ids = ac(
        "findNotes",
        query=f'"note:{ANKI_MODEL_NAME}" Eng_trans:*img*',
    )
    print(f"{len(candidate_ids)} notes with <img> in Eng_trans.")

    notes: list[dict] = []
    for i in range(0, len(candidate_ids), 200):
        notes.extend(ac("notesInfo", notes=candidate_ids[i : i + 200]))

    skipped_image_filled: list[int] = []
    migrations: list[tuple[int, str, str, str, str]] = []  # nid, hw, old_gloss, new_gloss, new_image
    for n in notes:
        old_gloss = n["fields"].get("Eng_trans", {}).get("value", "")
        old_image = n["fields"].get("Image", {}).get("value", "").strip()
        if old_image:
            skipped_image_filled.append(n["noteId"])
            continue
        clean_gloss, image_html = split_gloss_and_images(old_gloss)
        if not image_html:
            continue
        headword = n["fields"].get("Bangla", {}).get("value", "")
        migrations.append((n["noteId"], headword, old_gloss, clean_gloss, image_html))

    print(f"  {len(skipped_image_filled)} skipped (Image already populated)")
    print(f"  {len(migrations)} will migrate")
    print()
    for nid, hw, old_gloss, new_gloss, new_image in migrations[:8]:
        print(f"  nid={nid}  {hw}")
        print(f"    Eng_trans:  {old_gloss[:80]!r}")
        print(f"    → Eng_trans: {new_gloss[:80]!r}")
        print(f"    → Image:     {new_image[:80]!r}")
        print()
    if len(migrations) > 8:
        print(f"  ... ({len(migrations) - 8} more)")

    if not args.apply:
        print("\nDRY RUN — pass --apply to write.")
        return

    for nid, _, _, new_gloss, new_image in migrations:
        ac(
            "updateNoteFields",
            note={
                "id": nid,
                "fields": {"Eng_trans": new_gloss, "Image": new_image},
            },
        )
    print(f"\nApplied {len(migrations)} migrations.")


if __name__ == "__main__":
    main()
