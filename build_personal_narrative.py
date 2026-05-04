# ruff: noqa: E501
"""Build out/mx_personal_narrative.apkg from out/mx_personal_narrative.json.

Cloze deck for first-person narrative practice. Each card shows a Spanish
sentence with the yo-form verb blanked out and the infinitive as the hint.
The learner produces the correct conjugation.

No audio — these are pure production cloze cards.
"""
from __future__ import annotations

import json
from pathlib import Path

import genanki

HERE = Path(__file__).parent
OUT = HERE / "out"

DECK_NAME = "Spanish::Mexico Personal Narrative"
MODEL_ID = 1746103401
DECK_ID = 1746103402

DECK_DESCRIPTION = (
    '<h3 style="margin:0 0 6px 0">Mexico Personal Narrative — Cloze drills</h3>'
    '<p style="margin:4px 0">'
    "Personal-narrative cloze cards across all major tenses. Each card is a "
    "natural Spanish sentence about yourself with the conjugated yo-form "
    "blanked out; the infinitive is shown as the hint. Drill the verb form "
    "you'll actually need on day 1 in Mexico — meeting people, in taxis, at "
    "bars, at hotels."
    "</p>"
    '<p style="color:#888;font-size:90%;margin:6px 0 0 0">'
    'Built with <a href="https://ianhuntisaak.com">ianhuntisaak.com</a> tooling.'
    " Personal placeholders (San Francisco, Estados Unidos, programador, etc.)"
    " are concrete examples — edit notes individually to match your own bio."
    "</p>"
)

CSS = """
.card {
  font-family: -apple-system, "Segoe UI", sans-serif;
  font-size: 22px;
  text-align: center;
  color: #222;
  background: #fafafa;
  padding: 16px;
}
.cloze {
  font-weight: bold;
  color: #1565c0;
}
.tense {
  color: #888;
  font-size: 70%;
  font-style: italic;
  margin-bottom: 12px;
  text-transform: lowercase;
}
.english {
  color: #888;
  font-size: 75%;
  margin-top: 14px;
}
.note {
  color: #666;
  font-size: 70%;
  margin-top: 10px;
  text-align: left;
}
.priority {
  color: #aaa;
  font-size: 60%;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}
"""

FRONT = (
    '<div class="priority">{{Priority}}</div>'
    '<div class="tense">{{Tense}}</div>'
    "{{cloze:ClozeText}}"
    '<br><br>{{hint:English}}'
)

# Audio plays only on the back so the front stays a pure production challenge.
BACK = (
    '<div class="priority">{{Priority}}</div>'
    '<div class="tense">{{Tense}}</div>'
    "{{cloze:ClozeText}}"
    "{{Audio}}"
    '<div class="english">{{English}}</div>'
    '{{#Note}}<div class="note">{{Note}}</div>{{/Note}}'
)


def main() -> None:
    data = json.loads((OUT / "mx_personal_narrative.json").read_text(encoding="utf-8"))

    model = genanki.Model(
        MODEL_ID,
        "MX Personal Narrative",
        fields=[
            {"name": "ClozeText"},
            {"name": "English"},
            {"name": "Tense"},
            {"name": "Note"},
            {"name": "Priority"},
            {"name": "Audio"},
        ],
        templates=[{"name": "Cloze", "qfmt": FRONT, "afmt": BACK}],
        css=CSS,
        model_type=genanki.Model.CLOZE,
    )

    deck = genanki.Deck(DECK_ID, DECK_NAME, description=DECK_DESCRIPTION)
    audio_dir = OUT / "mx_pn_audio"
    media_files = []
    for idx, e in enumerate(data):
        audio_path = audio_dir / f"{idx:03d}.mp3"
        audio_field = ""
        if audio_path.exists():
            fname = f"mxpn_{idx:03d}.mp3"
            audio_field = f"[sound:{fname}]"
            media_files.append(str(audio_path))
        note = genanki.Note(
            model=model,
            fields=[
                e["cloze_text"],
                e["english_context"],
                e["tense"].replace("_", " "),
                e.get("note", ""),
                e["priority"],
                audio_field,
            ],
            tags=[e["tense"], e["priority"]],
            guid=genanki.guid_for(f"mx-pn-{idx}"),
        )
        deck.add_note(note)

    out_path = OUT / "mx_personal_narrative.apkg"
    pkg = genanki.Package(deck)
    pkg.media_files = media_files
    pkg.write_to_file(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB, {len(deck.notes)} notes)")


if __name__ == "__main__":
    main()
