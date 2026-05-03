# Deck Augmentation Tool

Pipeline for enhancing an Anki `.apkg` with: LLM-bolded target words, Chirp3 HD
audio per card, regional notes, dedup against existing decks, and repack into
a new `.apkg`.

First target: Davies 5000 Spanish frequency deck (`source.apkg`). Designed to
be reusable for other vocabulary/frequency decks.

See `NOTES.md` for pitfalls + lessons learned from the Spanish build.

## Dependencies

```bash
uv sync                     # core deps
```

Requires:
- Python 3.11+
- `ffmpeg` on PATH (for audio re-encoding)
- Anki Desktop + AnkiConnect add-on (for dedup / diagnostics)
- Google Cloud credentials via ADC (`gcloud auth application-default login`)

## Scripts (in pipeline order)

| Step | Script | Purpose |
|---|---|---|
| 0 | `explore_models.py`, `explore_decks.py` | Inspect user's Anki collection |
| 1 | `dedup.py` | Find deck headwords already in user's other decks |
| 2 | `prep_bold_batches.py` | Split notes into markdown batches for subagents |
| 3 | *(dispatch subagents to bold each batch)* | see `NOTES.md` for prompt |
| 4 | `aggregate_bolded.py` | Merge batch outputs → `bolded_sentences.json` + flags report |
| 5 | `audition.py` | Generate one sample per voice for quality comparison |
| 6 | `tts_run.py` | Generate Chirp3 HD audio (word + sentence per card) |
| 7 | `compress_audio.py` | Re-encode to smaller bitrate (Opus or low-kbps MP3) |
| 8 | `repack.py` | Build final `enhanced.apkg` |

Analysis / utility scripts (run ad-hoc):
- `analyze_forward_refs.py` — n+1 coverage metric
- `compare_spectrograms.py` — visually compare audio bitrates (`uv run` inline deps)
- `build_opus_test.py` — 1-card test apkg for AnkiDroid playback check
- `fix_due_via_ankiconnect.py` — rewrite `due = rank` via AnkiConnect
- `check_remaining.py` — diagnostic deck inspection

## Outputs

Everything lands in `out/` (gitignored):

- `out/bolded_sentences.json`, `out/flags_report.md` — from step 4
- `out/audio/`, `out/audio_index.jsonl` — from step 6
- `out/audio_mp3_64k/`, `out/audio_opus_48k/` — from step 7
- `out/enhanced.apkg` — final deliverable

## Conventions

- All scripts accept `--help`.
- All scripts are idempotent: rerun safely; skip work already done.
- Never overwrite `source.apkg` — write to `out/enhanced.apkg`.
- `ankiconnect.py` is a shared helper; import `from ankiconnect import ac`.
