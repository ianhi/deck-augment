"""Create a NEW Bangla note type (`Bangla Card v2`) to audition before
migrating the live `Bangla (and reversed)` notes. Adds one sample note in
`Bangla::test` so all three card variants (Recognition / Production /
Listening) can be eyeballed in Anki.

Patterns adopted from the Spanish audit:
  - `EnableX` boolean per-note gates (immersion pattern) — one note, three
    enable-able card templates. Empty enable field → Anki suppresses that
    card.
  - TTS fallback: if `[sound:…]` field is empty, fall back to on-device
    Bangla TTS via `[anki:tts lang=bn_IN]{{Field}}[/anki:tts]`.
  - Sentence audio before word audio (user preference).
  - Conditional Notes block (Davies pattern) with a ⚠ marker.
  - Bangla webfont stack; blue-bold headword.

Re-running creates only the test deck/note if missing; the model is left
alone if it already exists.

Schema-bumping: `createModel` and field additions trigger Anki's one-way
sync warning. Acknowledge before running.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from lib.ankiconnect import ac

MODEL_NAME = "Bangla Card v2"
TEST_DECK = "Bangla::test"

FIELDS = [
    "Bangla",
    "Eng_trans",
    "Example",
    "ExampleCloze",
    "ExampleTranslation",
    "WordAudio",
    "ExampleAudio",
    "Image",
    "Notes",
    "EnableRecognition",
    "EnableProduction",
    "EnableListening",
]

CSS = """\
.card {
  font-family: "Noto Sans Bengali", "Hind Siliguri", "Kalpurush", sans-serif;
  font-size: 28px;
  text-align: center;
  color: #222;
  background: #fff;
}

.headword { font-size: 44px; font-weight: 700; margin: 12px 0; }
.headword b, b { color: #5586cd; }

.sentence {
  font-size: 26px;
  margin: 16px auto;
  max-width: 32em;
  line-height: 1.4;
}
.sentence-translation {
  font-size: 18px;
  color: #6a6a6a;
  margin: 6px auto;
}

.definition { font-size: 22px; margin: 10px 0; }
.image img { max-height: 240px; max-width: 90%; }

.audio-row {
  min-height: 36px;
  margin: 10px 0;
}

.sentence-hint {
  margin: 16px auto;
  max-width: 32em;
  font-size: 22px;
}
.sentence-hint a { color: #5586cd; text-decoration: none; }

/* Anki default cloze styling — bold blue [...]. Used by ExampleCloze on
   the Production front. We define it ourselves because this note type is
   not a Cloze model, so it doesn't inherit the built-in style. */
.cloze {
  font-weight: 700;
  color: #5586cd;
}

.notes {
  font-size: 15px;
  color: #777;
  font-style: italic;
  margin: 10px auto;
  max-width: 32em;
  text-align: center;
}

hr#answer { margin: 18px 0; }
"""

# ---------- Templates ------------------------------------------------------

# Sentence audio is referenced before word audio everywhere it appears.
# TTS fallback wraps every audio reference so cards remain reviewable
# before stored audio exists.

SENTENCE_AUDIO = (
    "{{#ExampleAudio}}{{ExampleAudio}}{{/ExampleAudio}}"
    "{{^ExampleAudio}}{{#Example}}[anki:tts lang=bn_IN]{{Example}}[/anki:tts]{{/Example}}{{/ExampleAudio}}"
)
WORD_AUDIO = (
    "{{#WordAudio}}{{WordAudio}}{{/WordAudio}}"
    "{{^WordAudio}}[anki:tts lang=bn_IN]{{Bangla}}[/anki:tts]{{/WordAudio}}"
)

NOTES_BLOCK = (
    "{{#Notes}}<div class=\"notes\">{{Notes}}</div>{{/Notes}}"
)

RECOGNITION_FRONT = """\
{{#EnableRecognition}}
<div class="headword">{{Bangla}}</div>
{{#Example}}<div class="sentence">{{Example}}</div>{{/Example}}
<div class="audio-row">&nbsp;</div>
{{/EnableRecognition}}
"""

RECOGNITION_BACK = f"""\
{{{{#EnableRecognition}}}}
<div class="headword">{{{{Bangla}}}}</div>
{{{{#Example}}}}<div class="sentence">{{{{Example}}}}</div>{{{{/Example}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
<hr id=answer>
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence-translation">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
{NOTES_BLOCK}
{{{{/EnableRecognition}}}}
"""

PRODUCTION_FRONT = """\
{{#EnableProduction}}
<div class="definition">{{Eng_trans}}</div>
{{#ExampleTranslation}}<div class="sentence">{{ExampleTranslation}}</div>{{/ExampleTranslation}}
{{#Image}}<div class="image">{{Image}}</div>{{/Image}}
{{#ExampleCloze}}<div class="sentence">{{ExampleCloze}}</div>{{/ExampleCloze}}
<div class="audio-row">&nbsp;</div>
{{/EnableProduction}}
"""

PRODUCTION_BACK = f"""\
{{{{#EnableProduction}}}}
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
{{{{#Example}}}}<div class="sentence">{{{{Example}}}}</div>{{{{/Example}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
<hr id=answer>
<div class="headword">{{{{Bangla}}}}</div>
{NOTES_BLOCK}
{{{{/EnableProduction}}}}
"""

LISTENING_FRONT = f"""\
{{{{#EnableListening}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
{{{{#Example}}}}<div class="sentence-hint">{{{{hint:Example}}}}</div>{{{{/Example}}}}
{{{{/EnableListening}}}}
"""

LISTENING_BACK = f"""\
{{{{#EnableListening}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
{{{{#Example}}}}<div class="sentence-hint">{{{{Example}}}}</div>{{{{/Example}}}}
<hr id=answer>
<div class="headword">{{{{Bangla}}}}</div>
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence-translation">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
{NOTES_BLOCK}
{{{{/EnableListening}}}}
"""

TEMPLATES = [
    {"Name": "Recognition", "Front": RECOGNITION_FRONT, "Back": RECOGNITION_BACK},
    {"Name": "Production", "Front": PRODUCTION_FRONT, "Back": PRODUCTION_BACK},
    {"Name": "Listening", "Front": LISTENING_FRONT, "Back": LISTENING_BACK},
]

SAMPLE_NOTE = {
    "Bangla": "বই",
    "Eng_trans": "book",
    "Example": "আমি একটা <b>বই</b> পড়ছি।",
    "ExampleCloze": 'আমি একটা <span class="cloze">[...]</span> পড়ছি।',
    "ExampleTranslation": "I am reading a book.",
    "WordAudio": "",
    "ExampleAudio": "",
    "Image": "",
    "Notes": "Common noun, masculine. Plural: বইগুলো.",
    "EnableRecognition": "1",
    "EnableProduction": "1",
    "EnableListening": "1",
}


def ensure_model() -> None:
    if MODEL_NAME in ac("modelNames"):
        # Add any new fields that aren't in the existing model yet.
        current_fields = ac("modelFieldNames", modelName=MODEL_NAME)
        for field_name in FIELDS:
            if field_name not in current_fields:
                ac(
                    "modelFieldAdd",
                    modelName=MODEL_NAME,
                    fieldName=field_name,
                    index=len(current_fields),
                )
                current_fields = current_fields + [field_name]
                print(f"  added missing field {field_name!r}")
        # Push template + CSS updates so iterating on the design is fast.
        ac(
            "updateModelTemplates",
            model={
                "name": MODEL_NAME,
                "templates": {
                    t["Name"]: {"Front": t["Front"], "Back": t["Back"]}
                    for t in TEMPLATES
                },
            },
        )
        ac("updateModelStyling", model={"name": MODEL_NAME, "css": CSS})
        print(f"Updated templates + CSS on existing model {MODEL_NAME!r}.")
        return
    ac(
        "createModel",
        modelName=MODEL_NAME,
        inOrderFields=FIELDS,
        css=CSS,
        cardTemplates=[
            {"Name": t["Name"], "Front": t["Front"], "Back": t["Back"]}
            for t in TEMPLATES
        ],
    )
    print(f"Created model {MODEL_NAME!r} with {len(FIELDS)} fields, {len(TEMPLATES)} templates.")


def ensure_test_deck() -> None:
    if TEST_DECK not in ac("deckNames"):
        ac("createDeck", deck=TEST_DECK)
        print(f"Created deck {TEST_DECK!r}.")


def ensure_sample_note() -> None:
    existing = ac(
        "findNotes",
        query=f'"deck:{TEST_DECK}" "note:{MODEL_NAME}" Bangla:"{SAMPLE_NOTE["Bangla"]}"',
    )
    if existing:
        # Refresh fields so iterating on the sample data is also fast.
        ac(
            "updateNoteFields",
            note={"id": existing[0], "fields": SAMPLE_NOTE},
        )
        print(f"Refreshed sample note fields (noteId {existing[0]}).")
        return
    note_id = ac(
        "addNote",
        note={
            "deckName": TEST_DECK,
            "modelName": MODEL_NAME,
            "fields": SAMPLE_NOTE,
            "tags": ["v2-preview"],
            "options": {"allowDuplicate": True},
        },
    )
    print(f"Added sample note (noteId {note_id}) to {TEST_DECK}.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge the schema bump warning and proceed.",
    )
    args = ap.parse_args()
    if not args.yes:
        print(
            "This will create a new note type via AnkiConnect, which bumps the\n"
            "collection's schema version and forces a one-way sync on the next\n"
            "sync. Re-run with --yes to proceed."
        )
        return

    ensure_model()
    ensure_test_deck()
    ensure_sample_note()
    print("\nOpen Anki and review the deck `Bangla::test` to audition the three card variants.")


if __name__ == "__main__":
    main()
