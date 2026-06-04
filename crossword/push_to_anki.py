"""Push the Crosswordese deck into the user's Anki collection via AnkiConnect.

Idempotent: creates the deck + note type on first run, updates existing notes
on later runs (matched by guid `crosswordese-<ANSWER>`).

Why not importPackage: Anki runs as a flatpak with no filesystem access outside
its sandbox, so `importPackage` with a path under /home/ian/... fails. The
established convention in this repo is to push via the AnkiConnect API.

Usage:
    uv run crossword/push_to_anki.py            # full push
    uv run crossword/push_to_anki.py --limit 5  # smoke test
    uv run crossword/push_to_anki.py --force    # overwrite existing fields
    uv run crossword/push_to_anki.py --dry-run  # show plan, change nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crossword.build_pack import (  # noqa: E402
    DECK_NAME,
    MAX_CLUES,
    assert_unique_answers,
    get_templates_and_css,
)
from crossword.source_data import ENTRIES  # noqa: E402
from lib.ankiconnect import ac  # noqa: E402

MODEL_NAME = "Crosswordese"
GUID_PREFIX = "crosswordese-"


def field_names() -> list[str]:
    fields = ["Answer", "Length", "Category", "Definition", "Note", "ClueCount"]
    fields += [f"Clue{i:02d}" for i in range(1, MAX_CLUES + 1)]
    return fields


def ensure_deck(name: str, dry_run: bool) -> None:
    if name in ac("deckNames"):
        print(f"  deck exists: {name}")
        return
    if dry_run:
        print(f"  [dry-run] would create deck: {name}")
        return
    ac("createDeck", deck=name)
    print(f"  created deck: {name}")


def ensure_model(dry_run: bool) -> None:
    existing = ac("modelNames")
    if MODEL_NAME in existing:
        # Verify field schema matches; if not, warn — adding/renaming model
        # fields after notes exist is destructive and the user should decide.
        current_fields = ac("modelFieldNames", modelName=MODEL_NAME)
        if current_fields != field_names():
            print(
                f"  WARN: model '{MODEL_NAME}' exists with different fields:\n"
                f"    have: {current_fields}\n"
                f"    want: {field_names()}\n"
                f"  Skipping schema update. Delete the model in Anki and re-run if you want to reset."
            )
            return
        # Template / CSS drift: re-push them so edits to templates/ propagate.
        if not dry_run:
            front_html, back_html, css = get_templates_and_css()
            ac(
                "updateModelTemplates",
                model={
                    "name": MODEL_NAME,
                    "templates": {
                        "Clue→Answer": {"Front": front_html, "Back": back_html},
                    },
                },
            )
            ac("updateModelStyling", model={"name": MODEL_NAME, "css": css})
            print(f"  refreshed templates + CSS on existing model: {MODEL_NAME}")
        else:
            print(f"  [dry-run] would refresh templates/CSS on existing model")
        return
    if dry_run:
        print(f"  [dry-run] would create model: {MODEL_NAME}")
        return
    front_html, back_html, css = get_templates_and_css()
    ac(
        "createModel",
        modelName=MODEL_NAME,
        inOrderFields=field_names(),
        css=css,
        isCloze=False,
        cardTemplates=[
            {"Name": "Clue→Answer", "Front": front_html, "Back": back_html},
        ],
    )
    print(f"  created model: {MODEL_NAME}")


def build_note_payload(entry: dict, clues: list[str]) -> dict:
    answer = entry["answer"]
    padded = clues[:MAX_CLUES] + [""] * (MAX_CLUES - len(clues))
    fields = {
        "Answer": answer,
        "Length": str(len(answer)),
        "Category": entry["category"],
        "Definition": entry["definition"],
        "Note": entry.get("note", ""),
        "ClueCount": str(len(clues)),
    }
    for i, c in enumerate(padded, start=1):
        fields[f"Clue{i:02d}"] = c
    return {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": fields,
        "tags": ["crosswordese", entry["category"]],
        "options": {"allowDuplicate": False},
    }


def find_existing_note(answer: str) -> int | None:
    # Match by a stable signal: the Answer field equals this answer AND model
    # is ours. Quote the answer value so Anki's search does exact-match rather
    # than substring (otherwise `Answer:ALOE` would also match a hypothetical
    # ALOES note).
    nids = ac("findNotes", query=f'"note:{MODEL_NAME}" Answer:"{answer}"')
    if not nids:
        return None
    if len(nids) > 1:
        raise RuntimeError(
            f"{len(nids)} existing notes match Answer:\"{answer}\" "
            f"(nids={nids}) — refusing to guess which one to update"
        )
    return nids[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="overwrite fields on existing notes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    assert_unique_answers(ENTRIES)

    clues_by_answer: dict[str, list[str]] = json.loads(
        (REPO / "out" / "crossword_clues.json").read_text()
    )

    print(f"AnkiConnect version: {ac('version')}")
    ensure_deck(DECK_NAME, args.dry_run)
    ensure_model(args.dry_run)

    entries = ENTRIES if args.limit is None else ENTRIES[: args.limit]

    to_add: list[dict] = []
    to_update: list[tuple[int, dict, list[str]]] = []  # (note_id, fields, tags)
    skipped = 0

    for e in entries:
        clues = clues_by_answer.get(e["answer"], [])
        payload = build_note_payload(e, clues)
        nid = find_existing_note(e["answer"])
        if nid is None:
            to_add.append(payload)
        else:
            if args.force:
                to_update.append((nid, payload["fields"], payload["tags"]))
            else:
                skipped += 1

    print(f"\nPlan: add={len(to_add)}  update={len(to_update)}  skip={skipped}")

    if args.dry_run:
        for p in to_add[:3]:
            print(f"  + {p['fields']['Answer']}: {p['fields']['Clue01']!r} ...")
        return

    if to_add:
        # addNotes returns a list aligned with input — `null` means rejected
        # (e.g. duplicate). For a fresh deck everything should succeed.
        result = ac("addNotes", notes=to_add)
        n_ok = sum(1 for r in result if r is not None)
        print(f"  added: {n_ok}/{len(to_add)}")
        if n_ok < len(to_add):
            failed = [
                to_add[i]["fields"]["Answer"]
                for i, r in enumerate(result)
                if r is None
            ]
            print(f"  rejected (likely duplicates): {failed}")

    if to_update:
        for nid, fields, tags in to_update:
            ac("updateNoteFields", note={"id": nid, "fields": fields})
            # Re-sync tags so a category change in source_data.py propagates
            # (otherwise the old `crosswordese <old-category>` tag lingers).
            current_info = ac("notesInfo", notes=[nid])[0]
            current_tags = set(current_info.get("tags", []))
            desired_tags = set(tags)
            stale = current_tags - desired_tags
            missing = desired_tags - current_tags
            if stale:
                ac("removeTags", notes=[nid], tags=" ".join(sorted(stale)))
            if missing:
                ac("addTags", notes=[nid], tags=" ".join(sorted(missing)))
        print(f"  updated: {len(to_update)}")

    final = ac("findNotes", query=f'deck:"{DECK_NAME}"')
    print(f"\nDeck '{DECK_NAME}' now contains {len(final)} notes.")


if __name__ == "__main__":
    main()
