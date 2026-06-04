"""Seed data for the Bangla Conjugations deck.

Mirrors the Spanish conjugation cloze model (mx/build_conjugation_cloze.py):
one note per conjugated form, cloze hides the form, infinitive shows as
hint. Tense + Person + Register fields drive front-of-card chrome.

Coverage (24 notes):
  করা "to do" — continuous (4), perfect (4), future (4)
  খাওয়া "to eat" — continuous (4), perfect (4), future (4)

20 of these already exist in `Bangla::beginners bangla::Vocab` as
bare-form notes (model `Bangla (and reversed)`); their nids are mapped
here so the build can update-in-place via `updateNoteModel`. The 4
future forms (করব, করবি, খাব, খাবি) are new and need addNotes.
"""
from __future__ import annotations

from dataclasses import dataclass

NOTE_TYPE_NAME = "Bangla Conjugation"
DECK_NAME = "Bangla::beginners bangla::Conjugations"

FIELDS = [
    "Text",            # cloze sentence: "<stem> {{c1::form::infinitive}}<punct>"
    "English",         # natural translation
    "Tense",           # e.g. "Present Continuous"
    "Person",          # e.g. "1st person sg."
    "Register",        # "" / "familiar" / "polite" / "intimate" / "honorific"
    "Infinitive",      # e.g. "করা"
    "SentenceAudio",   # filled by TTS step
]


@dataclass(frozen=True)
class ConjForm:
    form: str               # the conjugated form, e.g. "করছি"
    infinitive: str         # citation form, e.g. "করা"
    english_inf: str        # English of infinitive: "to do"
    tense: str              # "Present Continuous" / "Perfect" / "Simple Future"
    person: str             # "1st sg." / "2nd familiar" / "2nd polite" / "3rd familiar" / "3rd honorific" / "2nd intimate"
    register: str           # "" | "familiar" | "polite" | "intimate" | "honorific"
    subject_pronoun: str    # the Bengali pronoun to seed the sentence ("আমি"/"তুমি"/"আপনি"/"সে"/"তিনি"/"তুই")
    english_subject: str    # English subject for the gloss
    existing_nid: int | None  # AnkiConnect note id if migrating; None if creating new


# === Helper: build all 12 forms for one verb ===

def _build_verb_paradigm(
    inf: str, eng_inf: str,
    cont_root: str,  # e.g. "করছ" → adds endings -ি, '', -ে, -েন → করছি, করছ, করছে, করছেন
    perf_root: str,  # e.g. "করেছ"
    fut_root: str,   # e.g. "কর" → adds endings -ব, -বি, -বে, -বেন
    nids: dict[str, int],
) -> list[ConjForm]:
    forms = []

    # Present Continuous: 1sg / 2-fam / 3-fam / 2-polite-or-3-honorific
    for f, person, reg, pron, en_subj in [
        (cont_root + "ি",  "1st sg.",          "",          "আমি", "I"),
        (cont_root,         "2nd familiar",     "familiar",  "তুমি", "you"),
        (cont_root + "ে",  "3rd familiar",     "familiar",  "সে",   "he/she"),
        (cont_root + "েন", "3rd honorific",    "honorific", "তিনি", "he/she (formal)"),
    ]:
        forms.append(ConjForm(
            form=f, infinitive=inf, english_inf=eng_inf,
            tense="Present Continuous", person=person, register=reg,
            subject_pronoun=pron, english_subject=en_subj,
            existing_nid=nids.get(f),
        ))

    # Perfect: same person pattern
    for f, person, reg, pron, en_subj in [
        (perf_root + "ি",  "1st sg.",          "",          "আমি", "I"),
        (perf_root,         "2nd familiar",     "familiar",  "তুমি", "you"),
        (perf_root + "ে",  "3rd familiar",     "familiar",  "সে",   "he/she"),
        (perf_root + "েন", "3rd honorific",    "honorific", "তিনি", "he/she (formal)"),
    ]:
        forms.append(ConjForm(
            form=f, infinitive=inf, english_inf=eng_inf,
            tense="Perfect", person=person, register=reg,
            subject_pronoun=pron, english_subject=en_subj,
            existing_nid=nids.get(f),
        ))

    # Simple Future
    for f, person, reg, pron, en_subj in [
        (fut_root + "ব",   "1st sg.",          "",          "আমি", "I"),
        (fut_root + "বি",  "2nd intimate",     "intimate",  "তুই",  "you (intimate)"),
        (fut_root + "বে",  "2nd familiar / 3rd familiar", "familiar", "তুমি/সে", "you/he"),
        (fut_root + "বেন", "3rd honorific",    "honorific", "তিনি", "he/she (formal)"),
    ]:
        forms.append(ConjForm(
            form=f, infinitive=inf, english_inf=eng_inf,
            tense="Simple Future", person=person, register=reg,
            subject_pronoun=pron, english_subject=en_subj,
            existing_nid=nids.get(f),
        ))

    return forms


# Extended tenses — each row is a (tense_name, [(form_for_person_slot, person, register, pron, en_subj)])
# where the 4 slots are 1sg / 2-fam / 3-fam / 3-hon. Stems vary per tense because
# of vowel-alternation and -ছিল- intrusion; pass explicit form lists.
def _build_extra_tenses(
    inf: str, eng_inf: str,
    habitual: list[str],         # [1sg, 2fam, 3fam, 3hon] for present habitual
    past_indef: list[str],       # simple past
    past_habitual: list[str],    # past habitual / conditional
    past_continuous: list[str],
    past_perfect: list[str],
    nids: dict[str, int],
) -> list[ConjForm]:
    SLOTS = [
        ("1st sg.",        "",          "আমি",  "I"),
        ("2nd familiar",   "familiar",  "তুমি", "you"),
        ("3rd familiar",   "familiar",  "সে",   "he/she"),
        ("3rd honorific",  "honorific", "তিনি", "he/she (formal)"),
    ]
    TENSES = [
        ("Present Habitual", habitual),
        ("Past Indefinite",  past_indef),
        ("Past Habitual",    past_habitual),
        ("Past Continuous",  past_continuous),
        ("Past Perfect",     past_perfect),
    ]
    out = []
    for tense_name, forms_list in TENSES:
        for (person, reg, pron, en_subj), form_val in zip(SLOTS, forms_list, strict=True):
            out.append(ConjForm(
                form=form_val, infinitive=inf, english_inf=eng_inf,
                tense=tense_name, person=person, register=reg,
                subject_pronoun=pron, english_subject=en_subj,
                existing_nid=nids.get(form_val),
            ))
    return out


# Existing nid mappings — wired up at build time from inventory
KORA_NIDS = {
    "করছি": 1754964719153, "করছ": 1754964729509,
    "করছে": 1754964737700, "করছেন": 1754964766387,
    "করেছি": 1754964832475, "করেছ": 1754964843247,
    "করেছে": 1754964851479, "করেছেন": 1754964995597,
    "করবে": 1754965206736, "করবেন": 1754965288119,
}

KHAOA_NIDS = {
    "খাচ্ছি": 1754964777833, "খাচ্ছ": 1754964788619,
    "খাচ্ছে": 1754964800008, "খাচ্ছেন": 1754964812934,
    "খেয়েছি": 1754965022312, "খেয়েছ": 1754965033342,
    "খেয়েছে": 1754965088970, "খেয়েছেন": 1754965106822,
    "খাবে": 1754965302361, "খাবেন": 1754965338246,
}

ALL_FORMS: list[ConjForm] = (
    _build_verb_paradigm("করা", "to do",   "করছ", "করেছ", "কর", KORA_NIDS)
    + _build_verb_paradigm("খাওয়া", "to eat", "খাচ্ছ", "খেয়েছ", "খা", KHAOA_NIDS)
    + _build_extra_tenses(
        "করা", "to do",
        habitual       = ["করি",         "করো",         "করে",         "করেন"],
        past_indef     = ["করলাম",       "করলে",        "করল",         "করলেন"],
        past_habitual  = ["করতাম",       "করতে",        "করত",         "করতেন"],
        past_continuous= ["করছিলাম",     "করছিলে",      "করছিল",       "করছিলেন"],
        past_perfect   = ["করেছিলাম",    "করেছিলে",     "করেছিল",      "করেছিলেন"],
        nids           = {},  # all new
    )
    + _build_extra_tenses(
        "খাওয়া", "to eat",
        habitual       = ["খাই",         "খাও",         "খায়",         "খান"],
        past_indef     = ["খেলাম",       "খেলে",        "খেল",         "খেলেন"],
        past_habitual  = ["খেতাম",       "খেতে",        "খেত",         "খেতেন"],
        past_continuous= ["খাচ্ছিলাম",   "খাচ্ছিলে",    "খাচ্ছিল",     "খাচ্ছিলেন"],
        past_perfect   = ["খেয়েছিলাম",  "খেয়েছিলে",   "খেয়েছিল",    "খেয়েছিলেন"],
        nids           = {},
    )
)


def summary() -> str:
    lines = [f"Total forms: {len(ALL_FORMS)}"]
    existing = sum(1 for f in ALL_FORMS if f.existing_nid is not None)
    lines.append(f"  existing (update-in-place):  {existing}")
    lines.append(f"  new (addNotes):              {len(ALL_FORMS) - existing}")
    from collections import Counter
    by_tense = Counter(f.tense for f in ALL_FORMS)
    for t, c in sorted(by_tense.items()):
        lines.append(f"  {t:<22} {c}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
    print("\nAll forms:")
    for f in ALL_FORMS:
        marker = "MIGRATE" if f.existing_nid else "NEW    "
        print(f"  {marker}  {f.form:10s}  {f.tense:<22} {f.person:<30} {f.subject_pronoun:8s} → {f.english_subject}")
