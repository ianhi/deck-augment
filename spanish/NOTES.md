# Spanish 5000 — Notes

The original use of this repo: enhancing the Davies *Frequency Dictionary of
Spanish* deck (AnkiWeb `1837230494`). Mostly frozen — these scripts shipped
the v1 deck. Kept here for reference and in case the user wants to re-render
audio or rebuild the apkg.

The root `NOTES.md` has the deeper lessons learned during this build (source
data caveats, AnkiConnect quirks, voice selection process). This file just
points at the active artifacts.

## Pipeline order (Spanish era)

1. `prep_bold_batches.py` — splits Davies sentences into markdown batches for
   the LLM-bolding pass.
2. `aggregate_bolded.py` — merges bolded outputs back.
3. `tts_run.py` — Chirp3 HD `es-US-*` voices, 3F + 3M (Kore, Aoede, Sulafat /
   Charon, Fenrir, Orus). One voice per card, deterministic by note id.
4. `compress_audio.py` — bitrate normalization for size.
5. `dedup.py` — suspends headwords that already exist in the user's other
   Spanish note types (ES1K, anki-defs-es-MX, spanish-cloze).
6. `repack.py` — writes the final `.apkg` with a `Notes` field carrying
   REGIONAL flags from the bolding pass.

## What didn't generalize

- The field indices (rank=0, word=1, example=4) are Davies-specific —
  hardcoded in `prep_bold_batches.py` and `repack.py`. When reusing the
  pipeline for Bangla we ended up writing a parallel set under `bangla/`
  rather than parameterizing these.
- `dedup.py` knows the user's specific Spanish note types by name. If you
  rerun it after the user reorganizes their collection, expect to update
  those constants.

## Hardcoded paths

`build_mx_pack_old.py` has a hardcoded absolute path
(`/home/claude/dev/deck-augment/...`) from a previous environment. Pre-existing
bug — the file is archived, don't bother fixing.
