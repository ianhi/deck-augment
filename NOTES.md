# Deck Augmentation Notes

This project started as a Spanish frequency deck enhancer but the pipeline
applies to any frequency/vocabulary Anki deck. When reusing for other
languages (e.g. Bangla), the pieces to adapt:

- `prep_bold_batches.py` — reads `source.apkg` → splits sentences into
  markdown batches. The field indices (rank=0, word=1, example sentence=4)
  are specific to the Davies 5000 note type — check new deck's schema.
- `aggregate_bolded.py` — language-agnostic
- `tts_run.py` — voice list is `es-US-Chirp3-HD-*`. Swap to the target
  language's Chirp3 voices (e.g. `bn-IN-Chirp3-HD-*` for Bengali).
- `compress_audio.py` — language-agnostic
- `repack.py` — note-type-specific: the field layout and which field the
  bolded sentence replaces. Adapt per deck.
- `dedup.py` — model/field names are language-specific (targets ES1K,
  anki-defs-es-MX, spanish-cloze); swap to the user's Bangla note types
  when doing Bangla.

## Ask the user before

Decisions that recur across decks and shouldn't be made unilaterally:

- **Voice selection** — audition Chirp3 HD voices on a sample sentence and let
  the user choose. Don't pick from the catalog alone.
- **Output format** — final `.apkg` (fresh import, loses review history) vs.
  audio files + CSV merged into the user's existing deck (preserves history).
- **Schema-bumping changes** — adding fields, modifying templates, etc. force
  one-way sync. Warn before doing it.
- **Dedup field mapping** — which fields in the user's other note types carry
  the target-language headword. Don't guess; confirm per note type.
- **Suspend lists** — derive candidates from the data (e.g. Peninsular-only
  headwords), then confirm the exact set with the user before suspending.
- **LLM choice for a new pass** — default is Gemini API (see above), but
  confirm model + temperature when starting a new generation/translation task.

## Pitfalls worth remembering

### Source data: don't trust structural assumptions

Always verify the source `.apkg`'s internal state before building a pipeline:

- `due` field may NOT be in rank order even on frequency decks (the Davies
  source had ~1.9M offset on ranks 1–2084). Fix: explicitly set due = rank
  in repack, or have the user run Reposition in Anki after import.
- Empty sentence fields exist in the Davies source — 3 cards had blank
  example sentences.
- Source may have built-in OS `{{tts ...}}` template tags that conflict with
  custom audio — strip during repack.

Add a sanity-check script that prints (id, rank, due, queue, sample field
values) at the START of work on a new deck.

### tts-tools bugs hit during this project

- **gRPC client per-call**: the Google Cloud engine was creating a new
  `TextToSpeechAsyncClient` per synthesis call (~5–15s overhead each).
  Patched by caching singleton clients. Similar issue for httpx in REST
  path.
- **Blocking post-processing**: `_process_raw` (librosa trim + ffmpeg mp3)
  was synchronous inside async flow — blocked the event loop.
  Wrapped in `asyncio.to_thread`.
- **Serial word+sentence per card**: our script was awaiting word first,
  then sentence. Parallelized with `asyncio.gather` to double per-card
  throughput.
- **Design cleanup TODO**: engine files shouldn't know about librosa/mp3.
  Post-processing belongs in the dispatcher. Note in
  `tts-tools/DESIGN_TODO_process_raw_separation.md`.
- **No Opus output**: only MP3/WAV. Opus would save 70%+ on disk for
  speech. Note in `tts-tools/DESIGN_TODO_opus_format.md`.

### AnkiDroid / mobile compatibility

- **Opus playback on AnkiDroid is flaky**. Native `.opus` extension works
  better than Opus-in-`.ogg` but isn't guaranteed. For broad compatibility,
  ship MP3. We settled on 64 kbps MP3 (159 MB total for 5000 cards) as the
  universal option.

### Anki schema operations

- Adding fields to an existing note type bumps the collection's schema
  version → forces one-way sync. Warn the user ahead of time.
- Anki's Reposition command works on NEW cards only (queue=0); reviewed
  cards are untouched. Safe to run after the user has already started
  studying.
- `setSpecificValueOfCard` in AnkiConnect requires `warning_check=True`
  for scheduling-related fields like `due`.

### Subagent task design

- Haiku 4.5 was not accurate enough for lemma-based bolding (missed
  plurals, 3rd-person conjugations). Used Sonnet 4.6 instead.
- JSON Lines output was fragile — agents sometimes produced malformed
  JSON. Switched to a simple numbered-markdown format (one line per entry)
  which was reliable.
- Keep concurrency at ~10–15 parallel agents; higher caused spawning
  issues in the Task tool.

### AnkiConnect: what works and what doesn't for card audio / scheduling

**Read operations (all stable, no side effects):**
- `deckNames` — list all decks
- `modelNames` / `modelFieldNames` — inspect note types
- `findNotes` / `findCards` — query by deck, tag, state (`is:new`, `is:suspended`, `-is:new`)
- `notesInfo` / `cardsInfo` — full details including fields, queue, due, type,
  reps, lapses
- `getReviewsOfCards` — historical revlog (pressed Again/Hard/Good/Easy + ivl)

**Write operations for card audio / scheduling:**
- To add audio to an existing card: **`updateNoteFields`** with `[sound:...]`
  tags in the field value. Anki's own sound player takes over on display.
  No special media upload call; the MP3/OGG must already exist in the
  collection's `collection.media` folder (`storeMediaFile` can put it there).
- `storeMediaFile` — upload a base64-encoded file into media folder. Use before
  referencing it in a note field.
- `setSpecificValueOfCard` — low-level edit; can set `due`, `queue`, etc.
  Requires `warning_check=True` when touching scheduling fields, otherwise
  it refuses. Bypasses Anki's safety checks — use sparingly.
- `suspend` / `unsuspend` — by card id. Does not require a schema bump.
- `forgetCards` / `relearnCards` — reset to new / put into re-learning.
- `setDueDate` — sets the next review date for reviewed cards (takes days
  offset or "ISO string"). Not for new-card positioning.
- **No direct Reposition action** in AnkiConnect. Either:
  - iterate with `setSpecificValueOfCard` on each card (slow for thousands),
    or
  - tell the user to Reposition in the GUI (fast, atomic, safer).

**Schema-bumping operations (trigger one-way sync):**
- Anything that modifies `col.models` via AnkiConnect: `createModel`,
  `updateModelTemplates`, `updateModelStyling`, field additions.
- These force the next sync to be one-way.

**Things to remember for audio workflows:**
- Don't build `[sound:...]` tags in the TEMPLATE (e.g. `[sound:{{Word}}.mp3]`)
  — AnkiDroid won't resolve them. Build them in the FIELD VALUE.
- Media filenames must be exact matches. Case-sensitive on mobile.
- Large decks (5000+ audio files): prefer building the .apkg locally and
  importing, rather than using `storeMediaFile` per file (slow and the user
  has to sit through it).

### Planned: Bangla deck cleanup (future use of this pipeline)

User has multiple Bangla Anki decks that need:
- Consolidation: many decks → a single deck, organized by tags
- **Duplicate detection**: user believes they have duplicate headwords across
  their various note types. Need a script that normalizes and groups.
- **Spell check**: user believes some words are misspelled. Need Gemini to
  flag anomalies (don't auto-fix — report for manual review).
- Audio added to cards that don't have it
- Example sentences added where missing

**Architecture note:** for Claude Code workflows, build as permanent Python
scripts in the project (not an MCP). Scripts are direct to run, version-
controlled, and don't pay the per-tool token tax. MCP would be overkill.

New script types needed beyond what Spanish has:

- `find_duplicates.py` — query all Bangla notes across note types via
  AnkiConnect, normalize (strip punctuation, case-fold, optionally accents),
  group by canonical form. Report exact + near-duplicate clusters.
- `spellcheck.py` — Gemini pass: "Is this a valid modern Bangla word? If
  misspelled, give correct form." Output a report; don't auto-fix.
- `consolidate_decks.py` — move notes from many decks into one, preserving
  review history, applying tags based on the source deck.

Differences from the Spanish build:

- **No dedup step** — all Bangla decks are user's own, not a frequency
  source vs. existing-user-decks situation. Instead, the operation is
  "consolidate across decks using existing notes" — more like de-duplication
  of the user's own data than merging with external content.
- **Gemini API for translation / sentence work** — user prefers Gemini over
  Claude Code subagents for translation, bolding, and sentence improvements
  (better quality). Subagents are fine for codebase tasks but not for the
  language-generation passes.
- **Chirp3 voice: `bn-IN-Chirp3-HD-Kore`** (confirmed in `../tts-compare`
  and user's memory).
- **User's note types** to audit first (from earlier AnkiConnect survey):
  - `Bangla (and reversed)` (2280 notes) — field `Bangla`
  - `Bangla Enhanced Cloze` (73 notes) — cloze field `Text`
  - `BanglaAlphabet` (6 notes)
  - `Bangla Alphabet` (10 notes)
  - `Cloze+` (305 notes) — field `bangla`
  - `Picture-Bangla (optional reversed card)` (33 notes)
  - ES1K-bangla (1000 notes) — already has audio from a different pipeline

- **Reorganization hints**: tags for proficiency level, topic, source.
- **Typo detection**: Gemini can flag typos in the same pass as sentence
  generation, similar to how Sonnet subagents flagged typos here.

### TTS throughput tuning

- Google Cloud TTS default quota: ~1000 requests/minute for Chirp3 HD.
- Safe concurrency: `Semaphore(4)` cards with parallel word+sentence gives
  ~8 concurrent calls = well under quota.
- Don't trust linear extrapolation from small batches — startup overhead
  dominates small runs.
- Cache gRPC clients (see tts-tools patch).
