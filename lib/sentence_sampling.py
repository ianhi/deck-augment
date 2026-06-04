"""Deterministic per-note sampling of grammatical form constraints for the
Bangla sentence-generation pass.

For each note we sample (tense/aspect, 2nd-person register, subject person,
sentence type, optional negative overlay) from usage-weighted distributions.
The sampled form is passed into the Gemini prompt as a *soft* constraint —
the model may override it and emit a `form_override` flag when the
headword forbids the requested form.

Output is a plain example sentence with the headword bolded in <b>...</b>.
NO cloze deletion — clozes are only used by the Spanish conjugation deck.

Distribution sources (honest provenance):

  - TENSE_AND_ASPECT_DISTRIBUTION: tense totals (present/past/future) are
    loosely anchored to Dash, N.S. "Frequency of Use of Words in Bengali"
    (5M-token mixed-register written Bengali corpus, 1981-1995, mostly
    West Bengal sources; academia.edu/107785597). I under-weight past and
    over-weight future relative to Dash on purpose — a learner deck wants
    more future-tense practice than naturalistic written corpora contain.
    The intra-tense aspect split (habitual vs continuous vs perfect inside
    each tense bucket) is NOT in Dash; those weights are pedagogical
    judgment, audit-pending.
  - SECOND_PERSON_REGISTER_DISTRIBUTION: NO corpus source found. Skewed
    toward তুমি (the safe learner default). Audit-pending.
  - SUBJECT_PERSON_DISTRIBUTION: NO Bengali source. Generic conversational
    skew. Audit-pending.
  - SENTENCE_TYPE_DISTRIBUTION: NO Bengali source. Generic conversational
    defaults. Audit-pending.
  - NEGATIVE_SENTENCE_RATE: NO source. Audit-pending.

Cite in downstream prose:
  - Dash, N.S. "Frequency of Use of Words in Bengali" (academia.edu/107785597).
  - Thompson, H.-R. (2010). *Bengali: A Comprehensive Grammar*. Routledge.
  - UD_Bengali-BRU treebank (universaldependencies.org/treebanks/bn_bru).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

# ---------- Distributions --------------------------------------------------

TENSE_AND_ASPECT_DISTRIBUTION: dict[str, float] = {
    "present_habitual":   0.30,  # সে রোজ আসে — habitual / generic
    "present_continuous": 0.15,  # সে আসছে
    "present_perfect":    0.08,  # সে এসেছে
    "simple_past":        0.15,  # সে গেল
    "past_habitual":      0.08,  # সে আসত
    "past_continuous":    0.05,  # সে আসছিল
    "past_perfect":       0.03,  # সে এসেছিল
    "simple_future":      0.12,  # সে আসবে
    "future_continuous":  0.02,  # সে আসতে থাকবে
    "imperative":         0.02,
}

SECOND_PERSON_REGISTER_DISTRIBUTION: dict[str, float] = {
    # Used when the sampled sentence type or subject involves a 2nd
    # person (interrogative, imperative, or declarative with 2sg subject).
    "tumi_informal":   0.55,
    "apni_formal":     0.35,
    "tui_intimate":    0.10,
}

SUBJECT_PERSON_DISTRIBUTION: dict[str, float] = {
    "first_person_singular":  0.30,
    "second_person_singular": 0.15,
    "third_person_singular":  0.35,
    "first_person_plural":    0.08,
    "third_person_plural":    0.12,
}

SENTENCE_TYPE_DISTRIBUTION: dict[str, float] = {
    "declarative":   0.72,
    "interrogative": 0.15,
    "imperative":    0.05,
    "exclamative":   0.03,
    # remaining ~5% absorbed by rounding
}

NEGATIVE_SENTENCE_RATE: float = 0.12  # orthogonal to type/tense


# ---------- Prompt-facing descriptions -------------------------------------

TENSE_AND_ASPECT_DESCRIPTIONS: dict[str, str] = {
    "present_habitual":   "present habitual (e.g. 'সে রোজ আসে' — he comes every day)",
    "present_continuous": "present continuous (e.g. 'সে এখন আসছে' — he is coming now)",
    "present_perfect":    "present perfect (e.g. 'সে এসেছে' — he has come)",
    "simple_past":        "simple past (e.g. 'সে গেল' — he went)",
    "past_habitual":      "past habitual (e.g. 'সে আসত' — he used to come)",
    "past_continuous":    "past continuous (e.g. 'সে আসছিল' — he was coming)",
    "past_perfect":       "past perfect (e.g. 'সে এসেছিল' — he had come)",
    "simple_future":      "simple future (e.g. 'সে আসবে' — he will come)",
    "future_continuous":  "future continuous (e.g. 'সে আসতে থাকবে')",
    "imperative":         "imperative (a command or request)",
}

SECOND_PERSON_REGISTER_DESCRIPTIONS: dict[str, str] = {
    "tumi_informal": "তুমি — informal 2nd person, used among peers / family / friends",
    "apni_formal":   "আপনি — formal/honorific 2nd person, used for elders, strangers, professionals",
    "tui_intimate":  "তুই — intimate 2nd person, used with very close friends, siblings, or small children",
}

SUBJECT_PERSON_DESCRIPTIONS: dict[str, str] = {
    "first_person_singular":  "1st person singular (আমি)",
    "second_person_singular": "2nd person singular (form chosen by the register hint)",
    "third_person_singular":  "3rd person singular (সে / উনি / এটা / ও)",
    "first_person_plural":    "1st person plural (আমরা)",
    "third_person_plural":    "3rd person plural (তারা / এরা / ওরা)",
}

SENTENCE_TYPE_DESCRIPTIONS: dict[str, str] = {
    "declarative":   "a plain declarative statement",
    "interrogative": "a question (yes/no, or wh-)",
    "imperative":    "a command, request, or suggestion",
    "exclamative":   "an exclamation or short emotional remark",
}


# ---------- Sampler --------------------------------------------------------

@dataclass(frozen=True)
class SampledSentenceForm:
    """The grammatical-form constraints we pass into the Gemini prompt."""
    tense_and_aspect: str
    second_person_register: str  # always sampled; used only when 2sg involved
    subject_person: str
    sentence_type: str
    is_negative: bool

    def describe_for_prompt(self) -> str:
        """Render a short multi-line constraint block for the Gemini prompt."""
        lines = [
            f"- Tense / aspect: {TENSE_AND_ASPECT_DESCRIPTIONS[self.tense_and_aspect]}",
            f"- Sentence type: {SENTENCE_TYPE_DESCRIPTIONS[self.sentence_type]}",
            f"- Subject: {SUBJECT_PERSON_DESCRIPTIONS[self.subject_person]}",
        ]
        second_person_appears = (
            self.subject_person == "second_person_singular"
            or self.sentence_type in ("interrogative", "imperative")
        )
        if second_person_appears:
            register_label = SECOND_PERSON_REGISTER_DESCRIPTIONS[self.second_person_register]
            lines.append(f"- 2nd-person register: {register_label}")
        if self.is_negative:
            lines.append("- Polarity: negative (negate the main verb).")
        return "\n".join(lines)


def _pick_weighted(distribution: dict[str, float], rng: random.Random) -> str:
    keys = list(distribution.keys())
    weights = [distribution[k] for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]


def sample_sentence_form_for_note(note_id: int) -> SampledSentenceForm:
    """Deterministically sample a SampledSentenceForm for the given note id.

    Seeding by note id makes re-runs stable — the same note always gets
    the same form, so we can regenerate a single bad sentence without
    drifting the rest of the corpus.
    """
    seed_bytes = hashlib.sha1(str(note_id).encode()).digest()
    seed_integer = int.from_bytes(seed_bytes[:8], "big")
    rng = random.Random(seed_integer)
    return SampledSentenceForm(
        tense_and_aspect=_pick_weighted(TENSE_AND_ASPECT_DISTRIBUTION, rng),
        second_person_register=_pick_weighted(
            SECOND_PERSON_REGISTER_DISTRIBUTION, rng
        ),
        subject_person=_pick_weighted(SUBJECT_PERSON_DISTRIBUTION, rng),
        sentence_type=_pick_weighted(SENTENCE_TYPE_DISTRIBUTION, rng),
        is_negative=rng.random() < NEGATIVE_SENTENCE_RATE,
    )


# ---------- CLI: audit a batch of samples ----------------------------------

def audit_distribution() -> None:
    """`uv run sentence_sampling.py --n N` prints a histogram of N samples."""
    import argparse
    from collections import Counter

    ap = argparse.ArgumentParser(description="Audit the sampled-form distribution.")
    ap.add_argument("--n", type=int, default=2279, help="How many notes to sample.")
    args = ap.parse_args()

    forms = [sample_sentence_form_for_note(i) for i in range(args.n)]
    print(f"Sampled {len(forms)} forms.\n")

    def histogram(label: str, values: list[str]) -> None:
        counts = Counter(values)
        total = sum(counts.values())
        print(f"{label}:")
        for key, n in counts.most_common():
            print(f"  {key:<26} {n:>5}  {100 * n / total:5.1f}%")
        print()

    histogram("Tense / aspect", [f.tense_and_aspect for f in forms])
    histogram("Sentence type", [f.sentence_type for f in forms])
    histogram("Subject person", [f.subject_person for f in forms])
    histogram("2nd-person register", [f.second_person_register for f in forms])
    negatives = sum(f.is_negative for f in forms)
    print(f"Negative polarity: {negatives}/{len(forms)}  ({100 * negatives / len(forms):.1f}%)")


if __name__ == "__main__":
    audit_distribution()
