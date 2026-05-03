"""Push conjugation audio + English translations into Anki via AnkiConnect.

For each note in the 'Ultimate Spanish Conjugation Deck (No Vosotros)':
  1. storeMediaFile  → uploads <note_id>_word.mp3 and <note_id>_sentence.mp3
                       to Anki's collection.media folder
  2. updateNoteFields → sets WordAudio = [sound:<note_id>_word.mp3]
                       sets ExampleAudio = [sound:<note_id>_sentence.mp3]
                       sets English = <translation> (adding the field at runtime
                       via modelFieldAdd if not already present)

Idempotent: skips notes whose fields are already populated, unless --force.
Run only after tts_run_conjugation.py + posttrim_word_clips.py have finished.

Usage:
  uv run python push_conjugation_to_anki.py             # full push
  uv run python push_conjugation_to_anki.py --limit 20  # smoke test first
  uv run python push_conjugation_to_anki.py --force     # overwrite existing
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

# AnkiConnect 'multi' action lets us batch many sub-actions in one HTTP request,
# eliminating the 3-RTT-per-card cost.
BATCH_SIZE = 25  # cards per HTTP round trip (75 sub-actions per request)

DECK = "Ultimate Spanish Conjugation Deck (No Vosotros)"
MODEL = "Conjugation"
ANKICONNECT = "http://localhost:8765"
HERE = Path(__file__).parent
AUDIO_DIR = HERE / "out" / "conjugation_audio"


def call(action: str, **params: object) -> Any:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(
        ANKICONNECT, data=payload, headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action} failed: {resp['error']}")
    return resp["result"]


def ensure_english_field() -> None:
    """Add an 'English' field to the Conjugation note type if missing."""
    fields = call("modelFieldNames", modelName=MODEL)
    if "English" in fields:
        print(f"Field 'English' already exists in model {MODEL!r}")
        return
    print(f"Adding 'English' field to model {MODEL!r}...")
    call("modelFieldAdd", modelName=MODEL, fieldName="English", index=len(fields))
    print("  added")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, metavar="N")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite even if fields already populated")
    args = ap.parse_args()

    if not AUDIO_DIR.exists():
        sys.exit(f"Missing {AUDIO_DIR} — run tts_run_conjugation.py first")
    translations_path = HERE / "out" / "conjugation_translations.json"
    if not translations_path.exists():
        sys.exit(f"Missing {translations_path}")
    translations = json.loads(translations_path.read_text(encoding="utf-8"))

    ensure_english_field()

    note_ids = call("findNotes", query=f'deck:"{DECK}"')
    print(f"Deck has {len(note_ids)} notes")
    info = call("notesInfo", notes=note_ids)

    pending = []
    skipped = 0
    for n in info:
        nid = n["noteId"]
        fields = n["fields"]
        word_path = AUDIO_DIR / f"{nid}_word.mp3"
        sent_path = AUDIO_DIR / f"{nid}_sentence.mp3"
        eng = translations.get(str(nid), "")
        if not (word_path.exists() and sent_path.exists()):
            print(f"  WARN missing audio for {nid}")
            continue
        already = (
            fields.get("WordAudio", {}).get("value")
            and fields.get("ExampleAudio", {}).get("value")
            and fields.get("English", {}).get("value")
        )
        if already and not args.force:
            skipped += 1
            continue
        pending.append((nid, word_path, sent_path, eng))

    if args.limit:
        pending = pending[: args.limit]
    print(f"To push: {len(pending)}, skipped (already populated): {skipped}")

    t0 = time.time()
    done = 0
    for batch_start in range(0, len(pending), BATCH_SIZE):
        batch = pending[batch_start : batch_start + BATCH_SIZE]
        actions: list[dict[str, Any]] = []
        for nid, word_path, sent_path, eng in batch:
            word_name = f"conj_{nid}_word.mp3"
            sent_name = f"conj_{nid}_sentence.mp3"
            actions.append({
                "action": "storeMediaFile",
                "params": {
                    "filename": word_name,
                    "data": base64.b64encode(word_path.read_bytes()).decode(),
                },
            })
            actions.append({
                "action": "storeMediaFile",
                "params": {
                    "filename": sent_name,
                    "data": base64.b64encode(sent_path.read_bytes()).decode(),
                },
            })
            actions.append({
                "action": "updateNoteFields",
                "params": {
                    "note": {
                        "id": nid,
                        "fields": {
                            "WordAudio": f"[sound:{word_name}]",
                            "ExampleAudio": f"[sound:{sent_name}]",
                            "English": eng,
                        },
                    },
                },
            })
        call("multi", actions=actions)
        done += len(batch)
        rate = done / (time.time() - t0)
        print(f"  [{done:>4}/{len(pending)}] pushed ({rate:.1f}/s)", flush=True)
    print(f"Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
