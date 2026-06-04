"""Prompts for Gemini-driven passes in the deck-augment pipeline.

Each prompt is a tuple of (system_instruction, user_template). The system
instruction is constant — eligible for prompt caching in the Gemini API.
The user template is `str.format`-able with the per-note fields.

Bangla sentence-generation prompt targets **Kolkata (West Bengal, India)
Bengali**, not Bangladeshi. Form constraints (tense / register / person /
sentence-type / polarity) are sampled externally by
`sentence_sampling.py` and passed in as soft constraints — Gemini may
override when the headword forbids the form and must report which
constraint was overridden.
"""
from __future__ import annotations

# ---------- Shared, verified principles ------------------------------------
#
# Building blocks composed into newer prompts. The originals (BANGLA_SENTENCE_*,
# BANGLA_TRANSLATION_*, BANGLA_NATURALNESS_*) embed their own verbatim copy and
# are intentionally NOT refactored — their literal text is hashed into the
# cache signature for `generate_sentences.py`, so any rewording invalidates
# all 2,279 cached Bangla sentences. Build new prompts using these constants;
# don't change the originals.

KOLKATA_REGISTER = """\
Kolkata (West Bengal, India) Bengali only. Casual everyday register (চলিত
ভাষা / Standard Colloquial Bengali as spoken in West Bengal). Real
collocations, natural word order, native rhythm. Reject anything that reads
like a translated English template, a textbook drill, or "learner-simplified"
speech. Avoid Bangladeshi-marked vocabulary, kin terms, and religious-cultural
register. Light English code-mixing of nouns is fine where natural; don't
reach for it."""

BANGLA_GRAMMATICALITY_RULE = """\
The sentence MUST be grammatical. Verb agreement, particle placement, case
marking, classifier choice, sandhi — all correct. Ungrammatical output is the
worst possible failure."""

BANGLA_HEADWORD_BOLDING = """\
The sentence must contain the headword in its citation form OR a naturally
inflected/declined form. Wrap **exactly one** occurrence in <b>...</b> — the
most pedagogically informative one. If your best sentence repeats the
headword, pick a different sentence. Never put the English gloss verbatim
inside the Bangla."""

BANGLA_SENTENCE_LENGTH = """\
Length: aim for 4–6 words, 8 the ceiling. Bias hard toward the shortest
natural sentence in which the headword fits. Add a modifier only when the
bare sentence is ambiguous or implausible without it — never to pad or to
sound literary."""


# ---------- Bangla example sentence generation -----------------------------

BANGLA_SENTENCE_SYSTEM = """\
You write one short, natural example sentence in Kolkata (West Bengal,
India) Bengali for a vocabulary flashcard. One call, one sentence, one
JSON object. No prose, no markdown fences.

# The sentence

**CRITICAL: the sentence MUST be grammatical.** Verb agreement, particle
placement, case marking, classifier choice, sandhi — all correct.
Ungrammatical output is the worst possible failure; if you can't write
a grammatical sentence under the sampled constraints, override a
constraint (and record the override) rather than emit broken Bangla.

Beyond grammaticality, the single most important property is: **a
literate Kolkata native would actually say this**. Casual everyday
register (চলিত ভাষা / Standard Colloquial Bengali as spoken in West
Bengal). Real collocations, natural word order, native rhythm. Reject
anything that reads like a translated English template, a textbook
drill, or "learner-simplified" speech. Avoid Bangladeshi-marked
vocabulary, kin terms, and religious-cultural register unless the
disambig explicitly says Bangladeshi. Light English code-mixing of
nouns is fine where natural; don't reach for it.

Length: aim for **4–6 words**, 8 the ceiling. Bias hard toward the
shortest natural sentence in which the headword fits. Add a modifier
only when the bare sentence is ambiguous or implausible without it —
never to pad or to sound literary.

Headword: the sentence must contain the headword in its citation form
OR a naturally inflected/declined form. Wrap **exactly one** occurrence
in <b>...</b> — the most pedagogically informative one. If your best
sentence repeats the headword, pick a different sentence. Never put the
English gloss verbatim inside the Bangla.

Sense: honour the disambig hints strictly. Never invent a sense the
headword does not have. If multiple senses are listed, pick the one
that matches the hints and produces a natural sentence in the sampled
form.

# Form constraints

The user passes sampled constraints: tense/aspect, sentence type,
subject person, optionally a 2nd-person register, optionally negative
polarity. Each tense/aspect label names ONE specific Bangla form (e.g.
present_habitual ≠ present_continuous). Produce **that** form.

Find a natural sentence that genuinely hosts the sampled combination —
change the subject, time-adverbial, or scene to make the form land
gracefully. Do not flatten to a default form because the sampled one
felt awkward; variety across the deck is the point.

When the sampled subject is 1st-person and the sentence type is
2nd-person-oriented (imperative, or an interrogative addressed at "you"),
the structure may force one constraint to give way. Drop only what the
structure structurally absorbs (e.g. imperative subsumes subject person)
and record it in `form_overrides`. If 1sg + declarative + no addressee
make a 2nd-person register vacuous, simply ignore the register — that's
not an override, the register field just doesn't surface.

Override a sampled form ONLY when no native speaker could grammatically
inflect this headword that way (invariant particles, stative predicates
that cannot host the requested aspect, etc.). "Sounds nicer otherwise"
is never a reason. Pronoun choice that satisfies both register and
person is compliance, not override.

Negative polarity uses the negation form that fits the sentence type
(declarative na/ni, imperative na with non-finite, copular nay) in its
correct position.

# Output schema (all fields required)

- "bangla_sentence": string in Bangla script with exactly one <b>...</b>.
- "english_translation": idiomatic English of the sentence you ACTUALLY
  wrote. Not the sampled-form sentence, not a literal gloss. Match
  register. Render meaning in whatever English tense reads naturally —
  do not mirror Bangla tense slavishly, but do not contradict it either
  (don't translate a simple-past Bangla sentence as past-perfect English).
- "produced_form": object — what your sentence actually expresses.
  Keys: "tense_and_aspect", "sentence_type", "subject_person",
  "second_person_register" (string or null — null when no 2nd person
  surfaces), "is_negative" (boolean). Use the exact vocabulary of the
  sampled constraints.
- "form_overrides": list of strings. One entry per sampled field where
  `produced_form` differs from the sample, naming the field and the
  grammatical/semantic blocker. Empty list when produced_form matches
  the sample on every field. A vacuous 2nd-person-register (1sg
  declarative etc.) is NOT an override.
- "confidence": "low" | "medium" | "high". "high" only when the sentence
  is grammatical, natural, and uses the intended sense.
- "flags": list of short tags ("ambiguous_headword", "archaic",
  "requires_context", "polysemous_sense_chosen"). Empty list if none.
- "headword_concern": {"suspected": bool, "suggested": str, "reason": str}.
  Flag when the Bangla headword looks wrong: misspelling, missing/extra
  diacritic, wrong vowel sign, transliteration artefact, obsolete
  spelling, or a conjugated/declined form where the citation form was
  expected. Put the most likely intended form in "suggested".
- "definition_concern": same shape. Flag when the English gloss is
  misspelled, names the wrong sense, names the wrong part of speech,
  or contradicts the disambig. Do NOT flag a gloss merely for being
  narrow or omitting other senses — the user prefers specific glosses
  over compound definitions.

# Self-audit before emitting

Before writing the JSON, check each field of your sentence against the
sample:

  1. Does the verb form match the sampled tense/aspect label exactly?
     (present_habitual is `করি/করে`, not `করছি/করছে`. simple_past is
     `করলাম/করল`, not `করেছিলাম/করেছিল`. Etc.)
  2. Does the subject pronoun realise the sampled person AND register
     simultaneously?
  3. Is polarity right?
  4. Sentence type — is it actually a question / command / exclamation
     if the sample asked for one?

For each field that does not match, either (a) rewrite the sentence
until it matches, or (b) accept the mismatch and record it in
`form_overrides` with the real reason. Do not silently mismatch. Do
not claim to have produced a form you did not produce. The user
mechanically compares `produced_form` against the sample; honest
mismatches with a reason are fine, dishonest matches are the worst
failure mode.

Then check the English translation: does it describe THIS Bangla
sentence, not the one the constraints asked for? Adjust if not.

# Concern flagging

The user typed many notes early in their learning. Spelling slips and
wrong-sense glosses are common. Prefer false positives to silent passes
— a flag the user can dismiss costs less than a bad card. Generate the
sentence anyway, using the most likely intended sense.
"""

BANGLA_SENTENCE_USER = """\
Headword (Bangla):  {bangla}
English gloss:      {eng_trans}
Sense / disambig hints (may be empty):
{disambig_block}

Sampled form constraints:
{form_block}

Write one natural Kolkata-Bengali sentence using this headword under
the sampled constraints, then run the self-audit, then emit the JSON
object. JSON only."""


# ---------- Bangla → English translation of existing sentences -------------

# Used for notes that already have a Bangla `Example` (handwritten or
# imported) but no `ExampleTranslation`. We do NOT regenerate the Bangla;
# we just translate it.

BANGLA_TRANSLATION_SYSTEM = """\
You translate a single Bangla example sentence into natural, idiomatic
English. The user studies Kolkata (West Bengal, India) Bengali.

Output ONLY a JSON object — no prose, no markdown fences. Fields:

- "english_translation" — string. Natural English. Match the register of
  the Bangla (formal Bangla → formal English; চলিত colloquial → colloquial
  English). Do NOT mirror Bangla word order; render the MEANING.
- "confidence" — "low", "medium", or "high".
- "sentence_concern" — object. If the Bangla sentence itself looks wrong
  (typo, ungrammatical, awkward, incomplete), flag it:
    - "suspected" (boolean)
    - "suggested" (string, corrected Bangla if you have a guess, else "")
    - "reason" (string, short explanation, else "")
- "headword_concern" — object, same shape. Flag if the Bangla headword
  itself looks wrong (typo, not in citation form, etc.).
- "definition_concern" — object, same shape. Flag if the **English
  gloss given for the Bangla headword** (the `Eng_trans` value in the
  input) is **wrong for the sense actually used in this sentence**
  (mis-sensed, misspelled, wrong part of speech, contradicts the
  disambig). Do NOT flag a gloss merely because it is narrow or omits
  other senses — the user prefers single specific glosses.
- "flags" — list of strings, optional (e.g. "archaic", "polysemous").

Rules:
1. Translate naturally — what an English speaker would actually say in the
   same situation. Not word-for-word.
2. The headword's intended sense is given for context — disambiguate
   homonyms using that sense, not the most common one.
3. Preserve any HTML inside the Bangla sentence (the <b>...</b> markup
   around the headword) by NOT including it in the translation; the
   translation is plain text.
4. If the Bangla sentence is incomplete or ungrammatical, still produce
   the best translation you can AND set `sentence_concern.suspected: true`.
"""

BANGLA_TRANSLATION_USER = """\
Translate this Bangla sentence to English.

Headword (Bangla):  {bangla}
Headword gloss:     {eng_trans}
Sense / disambig hints:
{disambig_block}

Bangla sentence (HTML may include <b>...</b> around the headword):
{bangla_sentence}

Return only the JSON object."""


# ---------- Notes filter (used in Phase 4 cleanup) -------------------------

NOTES_FILTER_SYSTEM = """\
You decide whether a legacy disambiguator string is still useful as a
visible Note on a vocabulary card, given that the card already shows a
generated example sentence and translation.

Return JSON:
  {"decision": "keep" | "drop" | "rephrase", "value": "<new text if rephrase>"}

Keep when the hint adds info the sentence does NOT convey (regional flag,
register, grammatical category, polysemy warning).
Drop when the hint is redundant once the sentence is shown.
Rephrase when keeping but the wording should be cleaner / shorter."""

# User template filled in when the Notes-filter pass is implemented.


BANGLA_NATURALNESS_SYSTEM = """\
You evaluate a single Bangla sentence for naturalness in **Kolkata
(West Bengal, India) Bengali** — written/spoken by an educated native
speaker in casual everyday context.

Output ONLY a JSON object. Fields:

- "naturalness_score" — integer 1 to 5.
    5 = indistinguishable from a native speaker;
    4 = native-like with very minor stiffness;
    3 = comprehensible but noticeably awkward / textbook;
    2 = clearly non-native phrasing or collocation;
    1 = ungrammatical or wrong dialect / register.
- "native_would_say" — boolean. Would a Kolkata native actually utter
  this sentence in the implied context? `false` if any natural speaker
  would rephrase substantially.
- "issues" — list of strings, each one a specific concrete complaint
  (e.g. "word order is English-shaped", "collocation X is unusual",
  "register doesn't match the sampled tui_intimate"). Empty list if none.
- "suggested_revision" — string. If you would rephrase the sentence,
  provide your version (Bangla, with the headword wrapped in <b>...</b>
  exactly once). Empty string if no change needed.

Be strict but fair. The sentence is for a learner; we want high quality,
not perfection. Score 4 is acceptable; score 3 needs revision; score
1-2 needs rewriting.
"""

BANGLA_NATURALNESS_USER = """\
Evaluate this Bangla sentence.

Headword:           {bangla}
Gloss:              {eng_trans}
Sampled form:       {form_summary}
Bangla sentence:    {bangla_sentence}
English translation: {english_translation}

Return only the JSON object."""


# ---------- Bangla number-card fill ----------------------------------------

# Single-call-per-note fill for the Numbers deck. For most categories the
# `bengali_word` and (sometimes) `decomposition` are pre-seeded; Gemini's
# job is the example sentence in both languages. For cardinals 21–99 the
# seeded `bengali_word` is missing and Gemini supplies it as well.

BANGLA_NUMBER_FILL_SYSTEM = """\
You fill the missing fields of one Kolkata-Bengali number flashcard.
One call, one note, one JSON object. No prose, no markdown fences.

# Output fields

- "bengali_word" — string. Citation form of the number in Kolkata Bengali
  (চলিত ভাষা). Single token where the number is a fused form
  (e.g. সাতচল্লিশ); a short phrase where the number is composed
  (e.g. দুশো চৌত্রিশ for 234). NEVER include Arabic digits.

- "decomposition" — string, may contain HTML. Show the substructure that
  helps a learner remember the form. Examples of the *shape* (not content)
  expected:
    fused 21–99:   "<unit-root> (X) + <tens-root> (Y0)"
    উন-9 numbers:  "উন- (one less than) + <next-ten> (Y0)"
    ordinal 5+:    "<cardinal> (N) + -তম (ordinal suffix)"
    100+ compound: "<digit> (D) + শো / হাজার / লাখ / কোটি"
  For irregular Sanskritic forms with no productive decomposition, return
  "" (empty string) — do not invent a fake morpheme split.

- "example_bangla" — one short, fully natural Kolkata-Bengali sentence
  using this number. **Wrap exactly one occurrence of the number-phrase
  in <b>...</b>.** Casual everyday register (চলিত). 4–8 words. Real
  collocations a literate Kolkata native would actually say. Reject
  textbook-drill phrasing. The number must appear in a *natural usage
  context* — bus numbers, prices, age, time, quantity at the shop, etc.
  Bias toward the shortest natural sentence that fits.

- "example_english" — natural idiomatic English translation of the
  Bangla. Match register. Use Arabic digits for the number itself
  ("19", not "nineteen") *unless* English idiom prefers the spelled-out
  form ("a hundred miles away", "half past three"). Render meaning, not
  word-for-word.

- "confidence" — "low" | "medium" | "high".

# Rules

1. **Grammaticality is non-negotiable.** Verb agreement, classifier
   choice, particle placement, case marking — all correct.

2. Use Kolkata West-Bengal register. No Bangladeshi-marked vocabulary.

3. If the input includes a seeded `bengali_word`, ECHO IT EXACTLY in
   your output — do not "improve" or normalize it. Only supply your own
   value when the seed is null/empty.

4. If the input includes a seeded `decomposition`, ECHO IT EXACTLY.

5. For pattern/rule cards (category="pattern"), the example_bangla
   should be a short sentence that USES the pattern in a real context
   (e.g. for পৌনে: a sentence telling time as পৌনে চারটে). The
   number-phrase wrapped in <b>...</b> is the pattern-applied phrase.

6. For multiplier cards (লাখ, কোটি, ডজন, হাজার), the example should
   use the multiplier in a real quantity (price, population, count of
   eggs in a ডজন, etc.).

7. For fractional cards (সিকি, আধ, পৌনে, সওয়া, দেড়, আড়াই), the
   example must use the fractional in a time, weight, or quantity
   context where it idiomatically appears.

8. Do not put English numerals or Latin script inside example_bangla
   (other than the <b>/</b> tags themselves).
"""

BANGLA_NUMBER_FILL_USER = """\
Fill this number-card.

category:             {category}
arabic_value:         {arabic_value}
bengali_numeral:      {bengali_numeral}
english_word:         {english_word}
seeded bengali_word:  {seeded_bengali_word}
seeded decomposition: {seeded_decomposition}
notes (context):      {notes}

Return only the JSON object with fields: bengali_word, decomposition,
example_bangla, example_english, confidence."""


# ---------- Bangla conjugation example sentences -------------------------

# For the Bangla Conjugations deck. Each call generates a sentence that
# teaches ONE specific conjugated verb form. The sentence must contain
# the EXACT form verbatim (per feedback_conjugation_form_preservation —
# Gemini silently swaps inflections, so prompt + post-validate strictly).

BANGLA_CONJUGATION_SYSTEM = f"""\
You write one short, natural Kolkata-Bengali sentence that teaches a
specific conjugated verb form for a flashcard. One call, one sentence,
one JSON object. No prose, no markdown fences.

# CRITICAL constraints

1. The sentence MUST contain the EXACT form supplied (no character
   substitutions, no nasal-mark drift, no alternative forms of the same
   verb). The flashcard depends on this — a near-miss is a broken card.

2. The sentence MUST make the conjugation INFERABLE: include the
   subject pronoun explicitly (don't drop it as Bengali commonly does),
   and include a tense/aspect marker if the form's tense isn't already
   obvious from the verb morphology. The learner sees the sentence
   with the form blanked out and has to recall it — so the rest of the
   sentence must give enough context.

3. {BANGLA_GRAMMATICALITY_RULE}

# Register & length

{KOLKATA_REGISTER}

{BANGLA_SENTENCE_LENGTH}

# Output fields

- "sentence_bangla" — the natural Kolkata-Bengali sentence. Plain text,
  no HTML tags, no cloze markup. The build code wraps the form in
  cloze syntax after validating it appears verbatim.
- "sentence_english" — natural idiomatic English translation. Match
  register. Render meaning, not word-for-word.
- "confidence" — "low" | "medium" | "high".

# Style tips

- Bias toward concrete, everyday contexts: family, food, weather,
  transport, work, school, market, time-of-day. NOT abstract /
  philosophical / literary.
- Use the supplied subject pronoun. If the form is 3rd-honorific and
  the pronoun is তিনি, the sentence should plausibly refer to a
  respected person (teacher, elder relative, etc.).
- For 2nd-intimate (তুই, -বি ending): only natural between close
  childhood friends, young siblings, or addressing children. Sentence
  context should match.
- For Perfect tense in Bangla (-েছ stem), idiomatic English is the
  present perfect ("have done") or simple past ("did") depending on
  context. Pick what's natural.
"""

BANGLA_CONJUGATION_USER = """\
Generate the example sentence for this card.

Verb (infinitive):  {infinitive}  ({english_inf})
Required form:      {form}
Tense:              {tense}
Person:             {person}
Register:           {register}
Subject pronoun:    {subject_pronoun}  ({english_subject})

The sentence MUST contain `{form}` verbatim AND start with (or include
prominently) the subject pronoun `{subject_pronoun}`.

Return only the JSON object."""


__all__ = [
    "BANGLA_SENTENCE_SYSTEM",
    "BANGLA_SENTENCE_USER",
    "BANGLA_TRANSLATION_SYSTEM",
    "BANGLA_TRANSLATION_USER",
    "BANGLA_NATURALNESS_SYSTEM",
    "BANGLA_NATURALNESS_USER",
    "BANGLA_NUMBER_FILL_SYSTEM",
    "BANGLA_NUMBER_FILL_USER",
    "BANGLA_SIMPLIFY_SYSTEM",
    "BANGLA_SIMPLIFY_USER",
    "BANGLA_CONJUGATION_SYSTEM",
    "BANGLA_CONJUGATION_USER",
    "NOTES_FILTER_SYSTEM",
]


# ---------- Immersion-card simplification --------------------------------

BANGLA_SIMPLIFY_SYSTEM = f"""\
You rewrite one Bangla vocabulary card to make it learnable. The card was
auto-generated from a literary source (Mahabharata) and currently has a
sprawling multi-sense gloss and/or an example sentence that's a fragment
of epic prose. Replace both with a focused single-sense gloss and a
natural, casual Kolkata-Bengali example sentence.

One call, one JSON object. No prose, no markdown fences.

# Register & grammaticality

**CRITICAL:** {BANGLA_GRAMMATICALITY_RULE}

{KOLKATA_REGISTER}

# Output fields

- "english_gloss" — single sense, the most everyday-useful meaning of the
  Bangla word in modern Kolkata Bengali. NOT a list. NOT "X, Y, Z". Pick
  the sense a Kolkata native would land on first if asked "what does this
  word mean?". One sense, one short English phrase. (The user prefers
  single specific glosses over compound "X; Y" definitions.)

- "example_bangla" — a short, natural Kolkata-Bengali sentence using the
  headword. {BANGLA_SENTENCE_LENGTH} Real-world context only: market,
  kitchen, street, family, work, weather, transport. NOT a Mahabharata-bound
  scene, NOT a literary fragment.

  {BANGLA_HEADWORD_BOLDING}

- "example_english" — natural idiomatic English of the new Bangla sentence.
  Match register. Render meaning, not word-for-word.

- "rationale" — one short sentence: which sense you chose and why.

# Sense selection

If the original gloss had three senses, two of them rare/archaic, choose
the common one and DO NOT mention the others in the gloss. If the word
really is too obscure for everyday use even under its best sense, set
example_bangla to "" and rationale to say so — the caller will drop it.
"""

BANGLA_SIMPLIFY_USER = """\
Simplify this immersion card.

Bangla headword:     {bangla}
Current gloss:       {current_gloss}
Current example:     {current_example}

Return only the JSON object with fields: english_gloss, example_bangla,
example_english, rationale."""
