# Bangla — Notes

Target dialect is **Kolkata (West Bengal, India) Bengali**, never Bangladeshi /
Dhaka. Register is চলিত ভাষা (Standard Colloquial). This shapes every prompt,
voice choice, and example-sentence audit.

## What worked

- **Gemini 3-flash-preview with `thinking_budget=0`** — sentence generation
  quality is materially better than `2.5-flash`. Empirical: 2.5-flash silently
  flattened form constraints (~60% adherence) vs ~93% for 3-flash on the same
  prompt. Don't downgrade to "save cost" — the rerun cost exceeds the savings.
- **External form sampling** (`lib.sentence_sampling.sample_sentence_form_for_note`)
  — sample tense/register/person/sentence-type/polarity in Python, hand to the
  LLM as soft constraints. Trusting the LLM to self-randomize collapses
  distributions toward present-indicative-declarative.
- **One Gemini call per item.** Batching saves dollars but the per-call attention
  drift on a 50-item batch is visible in the output. Single-item calls let us
  use a richer prompt without dilution.
- **Tight LLM output schemas** — ask only for fields the LLM is uniquely
  positioned to produce (Bengali sentence, English gloss, concerns). Derive
  everything else locally: `ExampleCloze` is just `<b>…</b>` → `<span
  class="cloze">[...]</span>` via regex in `generate_sentences.py`.
- **Principles in prompts, not anecdotes.** Listing specific blacklisted
  phrases ("don't use লেক, use জলাশয়") doesn't generalize. Encode the
  principle ("avoid Bangladeshi-marked vocabulary") and let the model apply
  it.
- **Sentence audio before word audio** in the field-value layout. Anki Mobile
  plays them in field order; the user wants context-then-word.

## Chirp3 HD bn-IN quirks

- Short Bangla monosyllables (ভাই, কাক) sometimes synthesize as near-silent
  (~−48 dB peak). Mitigated in `tts_run.py` by detecting peak < −30 dB and
  retrying with alternate voices in deterministic order. Persistent
  silent-after-3-retries notes (~12 / 2279 in vocab) need device-TTS fallback
  on the Anki side.
- Always save the raw (untrimmed) MP3 alongside the trimmed file. The trim
  pipeline (Silero VAD → ffmpeg fallback → raw passthrough) occasionally
  destroys very short clips; keeping the raw lets you recover without
  re-billing TTS.
- Voice assignment is deterministic via SHA-1(note_id) — same card always
  plays the same voice across re-renders.

## Note-type / AnkiConnect gotchas

- `addNotes` with `allowDuplicate: False` and an in-batch first-field
  duplicate rejects the *whole* batch — but AnkiConnect *had already
  committed* the notes up to the failure. We discovered this when the
  numbers deck ended up with 100 stray duplicates after the retry. Either
  precheck for collisions or use `allowDuplicate: True`.
- Schema-bumping (changing fields or templates on a note type) forces a
  one-way sync. Make a `backups/` `.apkg` first; `migrate_to_v2.py` does this.
- `findNotes` query `Example:` is parsed as free-text search, not
  field-empty. Use `-Example:_*` to mean "Example field is empty".
- Images sometimes end up in the wrong field (text-typed into `Eng_trans`
  rather than `Image`). `migrate_inline_images.py` lifts them; the Gemini
  prompts also defensively `strip_html_to_plain` on Eng_trans inputs.

## Bengali numbers — pattern map

Captured in `lib/numbers_seed.py` and the build:

- **0–10**: pure memorization. **20, 30, …, 90**: pure memorization,
  irregular roots.
- **11–99**: fused single words; the *unit prefix* is recognizable
  (পাঁচ → পঁচাশি etc.) but you can't compositionally derive them. Memorize
  whole.
- **উন- (−1 of next 10)**: productive prefix for 19, 29, 39, …, 89. The
  single most useful pattern to teach explicitly.
- **100+**: regular. একশো / দুশো / … হাজার / লাখ / কোটি.
- **Ordinals**: 1st–4th are Sanskrit-irregular (প্রথম / দ্বিতীয় / তৃতীয় /
  চতুর্থ). From 5th onward, productive `-তম` suffix.
- **Fractional quantifiers (closed set, ~6)**: সিকি / আধ / পৌনে / সওয়া /
  দেড় / আড়াই. পৌনে / সওয়া are productive prefixes; দেড় / আড়াই are
  only for 1½ / 2½. From 3½+ use সাড়ে.

## Active scripts in this dir

- `generate_sentences.py`, `translate_sentences.py`,
  `assess_naturalness.py`, `apply_revisions.py` — main vocab pipeline.
- `tts_run.py` — profile-driven (`--profile bangla-vocab` or
  `bangla-numbers`).
- `build_numbers.py` — numbers deck pipeline; seeds from
  `lib.numbers_seed`.
- `audit_*.py`, `migrate_*.py` — one-shot but kept (checked-in, idempotent,
  with `--dry-run` defaults).
