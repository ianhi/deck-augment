# Mexican Spanish — Notes

Multiple parallel sub-pipelines for Mexican-Spanish-flavoured Anki decks: an
MX "survival" pack, a personal-narrative deck, and a conjugation cloze deck.
TTS uses the `es-US` Chirp3 HD voices.

## Sub-pipelines

- **`build_pack.py`** — assembles `out/mx_survival.apkg` from a curated
  source JSON + rendered audio. Standard (non-cloze) single-card-per-note
  template with prompt audio + Spanish scene cue.
- **`build_conjugation_cloze.py`** — Cloze deck driven by
  `out/conjugation_notes.json`. The cloze text is `<stem> {{c1::<conj>::<infinitive>}}<punct>`
  so the back surface shows the verb's infinitive as a hint while the front
  blanks the conjugated form.
- **`build_personal_narrative.py`** — narrative-paragraph cards;
  hand-curated source.
- **`fetch_conjugation_notes.py`** / **`push_conjugation.py`** — pull from
  / push to Anki the live conjugation source set.
- **`tts_run*.py`** — per-deck TTS runners; **NOT** unified under the
  Bangla `Profile` system yet. If you do a third MX-style deck, consider
  generalizing `bangla/tts_run.py`'s Profile to cover MX too.

## Known caveats

- Several `build_*.py` here read their source JSON at *module import time*
  before argparse runs. If the JSON isn't on disk, even `--help` errors. Not
  worth fixing for one-shot scripts but be aware when smoke-testing the
  repo.
- `posttrim_word_clips.py` was added after the conjugation TTS pass to
  cleanup over-bright word audio — keep this around if you re-render
  conjugation audio.
