# deck-augment

Pipeline for enhancing existing Anki decks with: LLM-assisted headword bolding
in example sentences, Google Cloud TTS (Chirp3 HD) audio generation,
per-card regional/grammar notes, dedup against the user's existing decks, and
repack into a new .apkg.

First use: Davies 5000 Spanish (artifacts still in this repo). Reusable for
other frequency/vocabulary decks (e.g. Bangla) by adapting voice codes and
note-type field indices.

**See `NOTES.md`** for pitfalls + lessons learned from the Spanish build.
**See `README.md`** for pipeline order and per-script usage.

## Source

`source.apkg` — downloaded from AnkiWeb deck `1837230494`. 5000 notes, no tags, no
audio. Sorted by raw corpus frequency (rank stored in field 0). Format and structure
match Mark Davies, *A Frequency Dictionary of Spanish* (Routledge, 2006) — 5000 entries,
distinctive frequency+dispersion footer, POS abbreviations. Treat "derived from Davies"
as strong inference, not verified fact.

## Note fields (in order)

0. rank (string, "1"..."5000")
1. headword (e.g. "el, la" or "tener")
2. POS tag (art, prep, v, nm, nf, adj, adv, pron, conj, ...)
3. English gloss (terse)
4. Spanish example sentence
5. English translation
6. frequency metadata (`<raw_count> | <dispersion>`, sometimes with trailing tag like `+o`)

## Dialect composition

Pan-Hispanic / mixed. Includes both Peninsular and Latin American headwords
side-by-side (coche/carro, ordenador/computadora, patata/papa, conducir/manejar,
vosotros + ustedes). Example sentences reference España (14), Madrid (7), México (5),
Argentina (5), Colombia (5).

The user studies **Mexican Spanish** (es-US TTS locale). Peninsular-only *headwords*
are few and should be suspended — grep `source.apkg` extract to find exact set.

## Planned enhancements

1. **Suspend Peninsular-only headwords** — small list (vosotros, ordenador, coche,
   móvil, conducir, patata, zumo, ...). Produce the exact list from the data.
2. **Bold the target headword within the example sentence** — rewrite field 4 to wrap
   the matched form in `<b>`. Use stem matching so conjugated forms are caught
   (e.g. "tener" → bold "tiene"). Do this as a one-pass Python rewrite of the notes.
3. **Add audio to the Spanish example sentence** — use sibling repo `../tts-tools`
   with Chirp3 HD voices (language `es-US`). `synthesize_batch(max_concurrent=50)`.
   ~400K chars → ~$6.50 and 3–5 min total.

   **Voice subset (3F + 3M, learner-appropriate):**
   - Female: `Kore` (neutral/informative — Google descriptor),
     `Aoede` (calm/soothing — Google descriptor), `Sulafat` (unaudited)
   - Male: `Charon` (deep/authoritative — Google descriptor),
     `Fenrir` (unaudited), `Orus` (unaudited)

   Full voice names: `es-US-Chirp3-HD-<name>`. Excludes `Puck` (Google descriptor
   "bright, expressive" — too performative for repeated listening).

   If Sulafat/Fenrir/Orus sound off when user first hears them, swap with
   Erinome / Enceladus / Iapetus.

   Assign deterministically by hashing the note id, so re-runs produce the same
   audio and individual cards can be regenerated without drift.

   **One voice per card for v1.** Across the 5000 cards the ear hears all 6
   voices (roughly evenly distributed), but any given card always plays the same
   voice. Two-voices-per-card with random playback is a possible v2 — it doesn't
   require re-rendering the v1 audio, just a second batch and a template tweak.
4. **Deduplicate against the user's existing Anki collection.** The user already has
   Spanish cards in other note types (hand-crafted, from the anki-defs pipeline, etc.).
   Before importing this deck, identify headwords that are already in the user's
   collection under *any* note type and suspend those in the frequency deck to avoid
   reviewing the same word twice.

   **Read via AnkiConnect** (HTTP on localhost:8765) — user has confirmed this
   approach. Query every Spanish-language note across all decks/note types;
   extract headwords from the relevant fields; match against this deck's field 1.
   Still need to identify which fields in the user's other note types carry the
   Spanish headword — confirm with user when implementing this step.
5. **Add a new `Notes` field** to the note type at repack time. Populated from
   REGIONAL flags produced during step 2 (bolding). Shown on the back of the card
   so the user learns "`coche` is Peninsular; LatAm uses `carro`/`auto`" as they
   review. TYPO / UNGRAMMATICAL / AWKWARD / ARCHAIC flags stay in
   `out/flags_report.md` for manual review, not on cards.

6. **Repack output** as a new `.apkg` the user can import, OR produce audio files +
   CSV to merge into the existing deck in Anki (preserves review history). Ask the
   user which they prefer before committing.

## Repo layout

Scripts are organized by project, with shared modules in `lib/`.

```
lib/      ankiconnect, gemini_prompts, sentence_sampling, numbers_seed, paths
bangla/   active Bangla pipeline (vocab + numbers): generate_sentences,
          translate_sentences, assess_naturalness, apply_revisions, audit_*,
          migrate_*, tts_run, build_numbers, …
mx/       active Mexican-Spanish work: build_pack, build_preview,
          build_personal_narrative, build_conjugation_cloze, tts_run, …
spanish/  Spanish 5000 era (mostly frozen): aggregate_bolded, repack,
          tts_run, dedup, prep_bold_batches, …
archive/  one-offs preserved for reference
```

Scripts run as before: `uv run bangla/tts_run.py --profile bangla-vocab`. Each
subdir script has a 3-line `sys.path.insert(...)` bootstrap so `from lib.foo
import bar` resolves. Don't move scripts back to root without restoring imports.

## Conventions

- Python + `uv` for dependency management.
- Reuse `../tts-tools` (don't reinvent). Import as a library; don't vendor.
- Script output goes in `out/` (gitignored).
- Intermediate audio files go in `out/audio/<note_id>.mp3`.
- When modifying the deck, never overwrite `source.apkg` — write to `out/enhanced.apkg`.
- **Interact with Anki via AnkiConnect (HTTP localhost:8765), not file imports.**
  Anki runs as a flatpak (`net.ankiweb.Anki`) with no filesystem access outside
  its sandbox, so `importPackage` with an absolute path fails. The established
  pattern is: `createDeck` + `createModel` + `addNotes` (and `storeMediaFile`
  for audio), batched via the `multi` action. See `mx/push_conjugation.py` for
  the canonical example. `genanki` is still used to produce `.apkg` artifacts
  for sharing / archival, but routine pushes to the user's collection go
  through AnkiConnect.

## What NOT to do

- Don't claim things about the deck source beyond what the data supports.
- Don't hand-maintain a list of Peninsular words from memory — derive from the data
  and confirm with the user.
- Don't generate audio for the 5000 English translations or the headwords alone —
  only the example sentence, where context lives.
- Don't pick a voice unilaterally — audition a few on a sample sentence and let the
  user choose.
