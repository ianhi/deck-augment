"""Fetch all notes from the 'Ultimate Spanish Conjugation Deck (No Vosotros)'
deck via AnkiConnect and write them to out/conjugation_notes.json.

Each entry preserves note_id, tags, and the raw field values, plus two derived
strings used for TTS:

  word_text     — the conjugated form (Conjugation field), used for WordAudio
  sentence_text — Sentence + " " + Conjugation + terminal punctuation derived
                  from the Symbol field (! → !, ? → ?, otherwise .)

Run once before tts_run_conjugation.py.
"""
from __future__ import annotations

import html
import json
import urllib.request
from pathlib import Path
from typing import Any

DECK = "Ultimate Spanish Conjugation Deck (No Vosotros)"
OUT = Path(__file__).parent / "out"
ANKICONNECT = "http://localhost:8765"


def call(action: str, **params: object) -> Any:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(
        ANKICONNECT, data=payload, headers={"Content-Type": "application/json"}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action} failed: {resp['error']}")
    return resp["result"]


def terminal_punct(symbol: str) -> str:
    s = html.unescape(symbol).strip()
    if s == "!":
        return "!"
    if s == "?":
        return "?"
    return "."


def main() -> None:
    OUT.mkdir(exist_ok=True)
    note_ids = call("findNotes", query=f'deck:"{DECK}"')
    assert isinstance(note_ids, list)
    print(f"Found {len(note_ids)} notes in {DECK!r}")

    # notesInfo handles big batches fine but chunk to keep payloads sane.
    chunk = 1000
    notes: list[dict[str, Any]] = []
    for i in range(0, len(note_ids), chunk):
        batch = note_ids[i : i + chunk]
        info = call("notesInfo", notes=batch)
        assert isinstance(info, list)
        notes.extend(info)
        print(f"  fetched {len(notes)}/{len(note_ids)}")

    out_records: list[dict[str, Any]] = []
    for n in notes:
        fields = {k: v["value"] for k, v in n["fields"].items()}
        sentence_stem = fields["Sentence"].strip()
        conj = fields["Conjugation"].strip()
        punct = terminal_punct(fields["Symbol"])
        # Capitalize first letter of the assembled sentence for prosody.
        sentence_text = f"{sentence_stem} {conj}{punct}".strip()
        out_records.append(
            {
                "note_id": n["noteId"],
                "tags": n["tags"],
                "infinitive": fields["Infinitive"].strip(),
                "conjugation": conj,
                "tense": fields["Tense"].strip(),
                "symbol": fields["Symbol"],
                "sentence_stem": sentence_stem,
                "word_text": conj,
                "sentence_text": sentence_text,
                "has_word_audio": bool(fields["WordAudio"].strip()),
                "has_example_audio": bool(fields["ExampleAudio"].strip()),
            }
        )

    out_path = OUT / "conjugation_notes.json"
    out_path.write_text(
        json.dumps(out_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(out_records)} records → {out_path}")

    # Quick sanity report.
    already_word = sum(1 for r in out_records if r["has_word_audio"])
    already_ex = sum(1 for r in out_records if r["has_example_audio"])
    print(f"Existing WordAudio: {already_word}, ExampleAudio: {already_ex}")
    chars_word = sum(len(r["word_text"]) for r in out_records)
    chars_sent = sum(len(r["sentence_text"]) for r in out_records)
    print(f"Total chars — words: {chars_word:,}, sentences: {chars_sent:,}")


if __name__ == "__main__":
    main()
