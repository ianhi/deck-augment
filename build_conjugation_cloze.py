"""Build a fresh Cloze-style .apkg from out/conjugation_notes.json + translations.

Each output note:
  - Text field carries the cloze sentence: "<stem> {{c1::<conj>::<infinitive>}}<punct>"
  - English field = translation (rendered via {{hint:English}} on the back)
  - Tense, Symbol = passed through for visual cue / CSS hooks
  - Sentence audio reference embedded as [sound:conj_<nid>_sentence.mp3]

Bundles all <nid>_sentence.mp3 files into the apkg's media folder. Word mp3s
are NOT included — the cloze layout doesn't need a separate word clip.

Output: out/conjugation_cloze.apkg

Reuses the original AnkiConnect note_id as the genanki note.guid (via
genanki.guid_for) so re-imports replace cleanly.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import genanki

HERE = Path(__file__).parent
OUT = HERE / "out"
AUDIO_DIR = OUT / "conjugation_audio"
DECK_NAME = "Spanish::Ultimate Conjugation Cloze"

# Stable IDs — change only if you intentionally want a new deck.
MODEL_ID = 1746103201
DECK_ID = 1746103202

DECK_DESCRIPTION = (
    '<h3 style="margin:0 0 6px 0">Ultimate Spanish Conjugation Deck'
    " — Cloze edition with audio &amp; English</h3>"
    '<p style="margin:4px 0">Rebuild of '
    '<a href="https://ankiweb.net/shared/info/383891389">'
    "The Ultimate Spanish Conjugation Deck (No Vosotros)</a>, with three changes:</p>"
    '<ul style="margin:4px 0;padding-left:20px">'
    "<li>Converted to <b>cloze</b> format (sentence with the conjugation"
    " blanked out, infinitive shown as the hint).</li>"
    "<li>Added <b>English translations</b>, hidden behind a hint link on the front.</li>"
    "<li>Added <b>TTS audio</b> (Google Cloud Chirp3 HD, es-US) using the voices"
    " Kore, Aoede, Sulafat, Charon, Fenrir, and Orus — one per card,"
    " distributed deterministically.</li>"
    "</ul>"
    '<p style="color:#888;font-size:90%;margin:6px 0 0 0">'
    'Updates by <a href="https://ianhuntisaak.com">ianhuntisaak.com</a>, May 3, 2026.'
    " Sentence and verb content remain the work of the original deck's author.</p>"
)

CSS = """
.card {
  font-family: -apple-system, "Segoe UI", sans-serif;
  font-size: 22px;
  text-align: center;
  color: #222;
  background: #fafafa;
}
.tense {
  color: #888;
  font-size: 70%;
  font-style: italic;
  margin-bottom: 12px;
}
.symbol {
  color: #888;
  font-size: 90%;
  margin: 0 6px;
}
.cloze {
  font-weight: bold;
  color: #1565c0;
}
.audio-row {
  margin-top: 16px;
  min-height: 32px;
}
.english {
  color: #888;
  font-size: 80%;
  margin-top: 12px;
}
.hint-link, a.hint {
  color: #888;
  font-size: 80%;
}
"""

_TENSE_HEADER = (
    '<div class="tense">'
    '<span class="symbol">{{Symbol}}</span>'
    "{{Tense}}"
    '<span class="symbol">{{Symbol}}</span>'
    "</div>"
)

FRONT_TEMPLATE = (
    f"{_TENSE_HEADER}\n"
    "{{cloze:Text}}\n"
    '<div class="audio-row">&nbsp;</div>\n'  # placeholder reserves vertical space
    '<div class="english">{{hint:English}}</div>\n'
)

# Audio only on the back — playing on the front would speak the answer aloud
# and trivialize the cloze. The .audio-row div matches the front's reserved
# space, so flipping the card doesn't shift the sentence or English line
# vertically.
BACK_TEMPLATE = (
    f"{_TENSE_HEADER}\n"
    "{{cloze:Text}}\n"
    '<div class="audio-row">{{SentenceAudio}}</div>\n'
    '<div class="english">{{English}}</div>\n'
)


def build_text(stem: str, conj: str, infinitive: str, punct: str) -> str:
    # Cloze hint must not contain ::, which is the cloze separator.
    safe_inf = infinitive.replace("::", ":")
    return f"{stem} {{{{c1::{conj}::{safe_inf}}}}}{punct}"


def terminal_punct(symbol_field: str) -> str:
    s = html.unescape(symbol_field).strip()
    return s if s in ("!", "?") else "."


def main() -> None:
    notes_data = json.loads((OUT / "conjugation_notes.json").read_text(encoding="utf-8"))
    translations = json.loads((OUT / "conjugation_translations.json").read_text(encoding="utf-8"))

    model = genanki.Model(
        MODEL_ID,
        "Conjugation Cloze",
        fields=[
            {"name": "Text"},
            {"name": "English"},
            {"name": "Tense"},
            {"name": "Symbol"},
            {"name": "SentenceAudio"},
        ],
        templates=[
            {
                "name": "Cloze",
                "qfmt": FRONT_TEMPLATE,
                "afmt": BACK_TEMPLATE,
            },
        ],
        css=CSS,
        model_type=genanki.Model.CLOZE,
    )

    deck = genanki.Deck(DECK_ID, DECK_NAME, description=DECK_DESCRIPTION)
    media_files: list[str] = []
    missing_audio = 0

    for n in notes_data:
        nid = n["note_id"]
        stem = n["sentence_stem"]
        conj = n["conjugation"]
        infinitive = n["infinitive"]
        punct = terminal_punct(n["symbol"])
        text = build_text(stem, conj, infinitive, punct)

        # Sentence audio in its own field so the back template can play it
        # while the front stays silent (audio in the cloze text would spoil the
        # answer). Word audio dropped — sentences are short enough that a
        # separate single-word clip adds little.
        sent_path = AUDIO_DIR / f"{nid}_sentence.mp3"
        sent_field = ""
        if sent_path.exists():
            sent_filename = f"conj_{nid}_sentence.mp3"
            sent_field = f"[sound:{sent_filename}]"
            media_files.append(str(sent_path))
        else:
            missing_audio += 1

        eng = translations.get(str(nid), "")

        note = genanki.Note(
            model=model,
            fields=[text, eng, n["tense"], n["symbol"], sent_field],
            tags=list(n["tags"]),
            guid=genanki.guid_for(nid),  # stable across rebuilds
        )
        deck.add_note(note)

    print(f"Notes built: {len(deck.notes)}")
    print(f"Media files bundled: {len(media_files)}")
    if missing_audio:
        print(f"WARN: {missing_audio} notes missing sentence audio")

    # Sentence audio file references duplicate the same physical file naming as the
    # apkg media — but genanki rewrites file names by basename, which is what we want.
    pkg = genanki.Package(deck)
    # Set media files via attribute since constructor copies the basename
    pkg.media_files = media_files

    out_path = OUT / "conjugation_cloze.apkg"
    pkg.write_to_file(str(out_path))
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
