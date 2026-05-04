"""Build out/mx_survival.apkg from the curated source + rendered audio.

Standard (non-cloze) note type with conditional template — single card per
note. Front shows prompt audio (when present) and Spanish scene cue; back
reveals the Spanish answer with answer audio.

Fields per note:
  Spanish        — the answer phrase the learner should produce
  EnglishContext — English situational gloss (hint on front, shown on back)
  Note           — cultural / register / pronunciation note (back only)
  SpanishCue     — Spanish situational sentence (always shown on front)
  SpanishPrompt  — Spanish text of the audio prompt (hint on front)
  PromptAudio    — [sound:..] reference, played on front + back
  AnswerAudio    — [sound:..] reference, played on back only
  CardType       — production_from_audio | production_from_scene |
                   recognition | interjection (used as a CSS hook)
  Category       — for tag/filter
"""
from __future__ import annotations

import json
from pathlib import Path

import genanki

HERE = Path(__file__).parent
OUT = HERE / "out"
AUDIO_DIR = OUT / "mx_audio"

DECK_NAME = "Spanish::Mexico Survival"
MODEL_ID = 1746103301
DECK_ID = 1746103302

DECK_DESCRIPTION = (
    '<h3 style="margin:0 0 6px 0">Mexico Survival Pack</h3>'
    '<p style="margin:4px 0">'
    "248 high-leverage Mexican Spanish phrases for an imminent trip — "
    "mexicanismos with traps, taqueria/market/transport phrases, polite register, "
    "interjections, and emergency vocabulary."
    "</p>"
    '<p style="margin:4px 0">Card formats vary by entry type:</p>'
    '<ul style="margin:4px 0;padding-left:20px">'
    "<li><b>Production from audio</b>: someone says something to you (audio),"
    " you produce the response.</li>"
    "<li><b>Production from scene</b>: a Spanish situational cue, you produce"
    " the phrase.</li>"
    "<li><b>Recognition</b>: a Mexican vocabulary item, you recall its"
    " meaning.</li>"
    "<li><b>Interjection</b>: a moment described in Spanish, you react"
    " idiomatically.</li>"
    "</ul>"
    '<p style="color:#888;font-size:90%;margin:6px 0 0 0">'
    'Built with <a href="https://ianhuntisaak.com">ianhuntisaak.com</a>'
    " tooling, May 2026."
    " TTS via Google Cloud Chirp3 HD (es-US):"
    " male voices for prompts, female for answers."
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
.cue {
  color: #444;
  font-size: 80%;
  font-style: italic;
  margin: 8px 0 16px 0;
}
.cue:empty { display: none; }
.answer {
  font-size: 130%;
  font-weight: 600;
  color: #1565c0;
  margin: 12px 0;
}
.note {
  color: #666;
  font-size: 75%;
  margin-top: 16px;
  text-align: left;
}
.english-back {
  color: #555;
  font-size: 80%;
  margin-top: 12px;
}
.english-back.small { font-size: 70%; color: #888; margin-top: 4px; }
.english-back.tiny { font-size: 65%; color: #aaa; margin-top: 8px; }
.hints-row { margin-top: 14px; }
.hints-row a.hint { display: inline-block; margin: 0 8px; }
.hint-link, a.hint {
  color: #888;
  font-size: 80%;
}
.card-type {
  color: #aaa;
  font-size: 60%;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
hr {
  border: none;
  border-top: 1px solid #ddd;
  margin: 12px 0;
}
"""

# Mustache: {{#Field}}…{{/Field}} renders only if Field is non-empty.
# {{hint:Field}} renders a click-to-reveal link.
FRONT_TEMPLATE = (
    '<div class="card-type">{{CardType}} · {{Priority}}</div>'
    "{{PromptAudio}}"
    '<div class="cue">{{SpanishCue}}</div>'
    '<div class="hints-row">'
    "{{#SpanishPrompt}}{{hint:SpanishPrompt}}{{/SpanishPrompt}}"
    "{{#EnglishCue}}{{hint:EnglishCue}}{{/EnglishCue}}"
    "{{hint:EnglishAnswer}}"
    "</div>"
)

# Back: cue + audio still play (Anki replays prompt audio when card flips, and
# answer audio autoplays). Both English translations are visible for verification,
# the situational context is small at the bottom.
BACK_TEMPLATE = (
    '<div class="card-type">{{CardType}} · {{Priority}}</div>'
    "{{PromptAudio}}"
    '<div class="cue">{{SpanishCue}}</div>'
    "<hr>"
    '<div class="answer">{{Spanish}}</div>'
    "{{AnswerAudio}}"
    '<div class="english-back">{{EnglishAnswer}}</div>'
    '{{#EnglishPrompt}}<div class="english-back small">↪ {{EnglishPrompt}}</div>{{/EnglishPrompt}}'
    '{{#Note}}<div class="note">{{Note}}</div>{{/Note}}'
    '<div class="english-back tiny">{{EnglishContext}}</div>'
)


def main() -> None:
    raw = json.loads((OUT / "mx_survival_source.json").read_text(encoding="utf-8"))
    # Sort essential → likely → useful so Anki's "in order added" new-card
    # delivery surfaces day-1 must-knows first. Stable within priority by the
    # original source index, which preserves the curator's category-grouped
    # urgency ordering inside each tier.
    pri_rank = {"essential": 0, "likely": 1, "useful": 2, "": 3}
    indexed = list(enumerate(raw))
    indexed.sort(key=lambda x: (pri_rank.get(x[1].get("priority", ""), 4), x[0]))
    # Keep the original source-file index as the audio key so existing mp3s match.
    data = [(orig_idx, e) for orig_idx, e in indexed]

    model = genanki.Model(
        MODEL_ID,
        "MX Survival",
        fields=[
            {"name": "Spanish"},
            {"name": "EnglishContext"},
            {"name": "EnglishAnswer"},
            {"name": "EnglishPrompt"},
            {"name": "EnglishCue"},
            {"name": "Note"},
            {"name": "SpanishCue"},
            {"name": "SpanishPrompt"},
            {"name": "PromptAudio"},
            {"name": "AnswerAudio"},
            {"name": "CardType"},
            {"name": "Category"},
            {"name": "Priority"},
        ],
        templates=[{"name": "MX", "qfmt": FRONT_TEMPLATE, "afmt": BACK_TEMPLATE}],
        css=CSS,
    )

    deck = genanki.Deck(DECK_ID, DECK_NAME, description=DECK_DESCRIPTION)
    media_files: list[str] = []
    missing = 0

    for orig_idx, e in data:
        # `orig_idx` keys the audio files (which were rendered against the
        # un-sorted source order). The note's deck position is its iteration
        # order through the sorted `data` list.
        idx = orig_idx
        answer_path = AUDIO_DIR / f"{idx:04d}_answer.mp3"
        prompt_path = AUDIO_DIR / f"{idx:04d}_prompt.mp3"
        answer_audio_field = ""
        prompt_audio_field = ""

        if answer_path.exists():
            fname = f"mx_{idx:04d}_answer.mp3"
            answer_audio_field = f"[sound:{fname}]"
            media_files.append(str(answer_path))
        else:
            missing += 1

        if e.get("spanish_prompt") and prompt_path.exists():
            fname = f"mx_{idx:04d}_prompt.mp3"
            prompt_audio_field = f"[sound:{fname}]"
            media_files.append(str(prompt_path))

        note = genanki.Note(
            model=model,
            fields=[
                e["spanish"],
                e["english_context"],
                e.get("english_answer", ""),
                e.get("english_prompt") or "",
                e.get("english_cue", ""),
                e.get("note", ""),
                e.get("spanish_cue", ""),
                e.get("spanish_prompt") or "",
                prompt_audio_field,
                answer_audio_field,
                e["card_type"],
                e["category"],
                e.get("priority", ""),
            ],
            tags=[e["category"], e["card_type"], e.get("priority", "")],
            guid=genanki.guid_for(f"mx-{orig_idx}"),
        )
        deck.add_note(note)

    print(f"Notes: {len(deck.notes)}")
    print(f"Media files: {len(media_files)}")
    if missing:
        print(f"WARN: {missing} entries missing answer audio")

    pkg = genanki.Package(deck)
    pkg.media_files = media_files
    out_path = OUT / "mx_survival.apkg"
    pkg.write_to_file(str(out_path))
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
