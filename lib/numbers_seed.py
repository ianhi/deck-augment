"""Seed data for the `Bangla Number` deck.

Pure data module — no I/O, no execution. Build scripts import this.

Coverage (~125 notes):
  - digits 0–9 (10)
  - cardinals 0–100 (101) — overlaps 0–9, kept under both tags
  - ordinals 1st–10th (10)
  - fractional quantifiers (6)
  - multipliers (5)
  - pattern reference cards (4)

For cardinals 21–99, `bengali_word` and `decomposition` are left as None and
will be filled by a Gemini pass at build time — these are highly irregular
fused forms and I don't want to seed them from memory and get them wrong.
The Arabic→Bengali numeral conversion is mechanical and is precomputed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NOTE_TYPE_NAME = "Bangla Number"
DECK_NAME = "Bangla::Numbers"

# Anki field order
FIELDS = [
    "arabic_value",        # "5" or "47" or "1/2"
    "bengali_numeral",     # "৫" / "৪৭" — auto from arabic for cardinals; manual for fractions
    "bengali_word",        # "পাঁচ", "সাতচল্লিশ", "প্রথম", "দেড়"
    "english_word",        # "five", "forty-seven", "first", "one and a half"
    # "digit" | "cardinal" | "ordinal" | "fractional" | "multiplier" | "pattern"
    "category",
    "decomposition",       # "সাত (7) + চল্লিশ (40)" — HTML allowed
    "example_bangla",      # filled by Gemini
    "example_english",     # filled by Gemini
    "word_audio",          # [sound:bn_num_<id>_word.mp3]
    "sentence_audio",      # [sound:bn_num_<id>_sentence.mp3]
    "notes",               # cultural/usage notes
    "EnableRecognition",   # "1" / ""
    "EnableProduction",
    "EnableListening",
]

ARABIC_TO_BENGALI_DIGIT = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def to_bengali_numeral(s: str) -> str:
    """Mechanical digit-by-digit Arabic → Bengali numeral conversion."""
    return s.translate(ARABIC_TO_BENGALI_DIGIT)


@dataclass
class NumberNote:
    arabic_value: str
    english_word: str
    category: str
    bengali_word: str | None = None     # None ⇒ fill from Gemini
    bengali_numeral: str | None = None  # None ⇒ auto from arabic_value
    decomposition: str | None = None    # None ⇒ Gemini (for fused 21-99) or auto (for ordinals 5+)
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    enable_recognition: bool = True
    enable_production: bool = True
    enable_listening: bool = True

    def __post_init__(self) -> None:
        auto_categories = {"digit", "cardinal", "ordinal", "multiplier"}
        if self.bengali_numeral is None and self.category in auto_categories:
            # Only auto-fill for things with a clean Arabic representation.
            if self.arabic_value.replace(",", "").isdigit():
                self.bengali_numeral = to_bengali_numeral(self.arabic_value)


# ─── DIGITS 0–9 ───────────────────────────────────────────────────────────────
# These are the same as cardinals 0–9 but we tag them under "digit" so the
# numeral-recognition drill is its own category.

_DIGITS_WORDS = {
    "0": ("শূন্য",  "zero"),
    "1": ("এক",     "one"),
    "2": ("দুই",    "two"),
    "3": ("তিন",    "three"),
    "4": ("চার",    "four"),
    "5": ("পাঁচ",   "five"),
    "6": ("ছয়",     "six"),
    "7": ("সাত",    "seven"),
    "8": ("আট",     "eight"),
    "9": ("নয়",     "nine"),
}

DIGITS = [
    NumberNote(
        arabic_value=k,
        bengali_word=bw,
        english_word=ew,
        category="digit",
        tags=["numbers::digit", "numbers::cardinal::0-20"],
    )
    for k, (bw, ew) in _DIGITS_WORDS.items()
]


# ─── CARDINALS 10–20 (irregular, known) ───────────────────────────────────────

_CARDINALS_10_20 = {
    10: ("দশ",       "ten"),
    11: ("এগারো",    "eleven"),
    12: ("বারো",     "twelve"),
    13: ("তেরো",     "thirteen"),
    14: ("চোদ্দো",   "fourteen"),
    15: ("পনেরো",    "fifteen"),
    16: ("ষোলো",     "sixteen"),
    17: ("সতেরো",    "seventeen"),
    18: ("আঠারো",    "eighteen"),
    19: ("উনিশ",     "nineteen"),  # উন- ("one less than") + কুড়ি
    20: ("কুড়ি",     "twenty"),
}

CARDINALS_10_20 = [
    NumberNote(
        arabic_value=str(k),
        bengali_word=bw,
        english_word=ew,
        category="cardinal",
        decomposition=("উন- (one less than) + কুড়ি (20)" if k == 19 else None),
        tags=["numbers::cardinal::0-20"],
    )
    for k, (bw, ew) in _CARDINALS_10_20.items()
]


# ─── CARDINAL TENS (30, 40, ..., 90) — irregular roots ────────────────────────

_CARDINAL_TENS = {
    30: ("ত্রিশ",    "thirty"),
    40: ("চল্লিশ",   "forty"),
    50: ("পঞ্চাশ",   "fifty"),
    60: ("ষাট",      "sixty"),
    70: ("সত্তর",    "seventy"),
    80: ("আশি",      "eighty"),
    90: ("নব্বই",    "ninety"),
}

CARDINAL_TENS = [
    NumberNote(
        arabic_value=str(k),
        bengali_word=bw,
        english_word=ew,
        category="cardinal",
        tags=["numbers::cardinal::tens"],
    )
    for k, (bw, ew) in _CARDINAL_TENS.items()
]


# ─── CARDINALS 21–99 (gaps filled by Gemini) ──────────────────────────────────

_ENGLISH_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_ENGLISH_TENS = {
    2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
    6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety",
}


def _english_two_digit(n: int) -> str:
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _ENGLISH_TENS[tens]
    return f"{_ENGLISH_TENS[tens]}-{_ENGLISH_ONES[ones]}"


CARDINALS_21_99 = [
    NumberNote(
        arabic_value=str(n),
        bengali_word=None,    # ← Gemini fills
        english_word=_english_two_digit(n),
        category="cardinal",
        decomposition=None,   # ← Gemini fills (fused-form breakdown)
        tags=[f"numbers::cardinal::{(n // 10) * 10}s"],
    )
    for n in range(21, 100) if n not in (30, 40, 50, 60, 70, 80, 90)
]


# ─── 100 and multipliers ──────────────────────────────────────────────────────

MULTIPLIERS = [
    NumberNote(
        arabic_value="100",
        bengali_word="একশো",
        english_word="one hundred",
        category="cardinal",
        decomposition="এক (1) + শো (hundred)",
        tags=["numbers::cardinal::big", "numbers::multiplier"],
        notes="The bare শো / শত multiplier; combines as দুশো (200), তিনশো (300), …",
    ),
    NumberNote(
        arabic_value="1,000",
        bengali_word="হাজার",
        english_word="one thousand",
        category="multiplier",
        decomposition=None,
        tags=["numbers::multiplier"],
        notes="দুই হাজার = 2,000.",
    ),
    NumberNote(
        arabic_value="100,000",
        bengali_word="লাখ",
        english_word="one lakh (100,000)",
        category="multiplier",
        tags=["numbers::multiplier"],
        notes="South Asian system. 1 lakh = 100,000. Indian English also uses 'lakh'.",
    ),
    NumberNote(
        arabic_value="10,000,000",
        bengali_word="কোটি",
        english_word="one crore (10,000,000)",
        category="multiplier",
        tags=["numbers::multiplier"],
        notes="South Asian system. 1 crore = 10 million = 100 lakh.",
    ),
    NumberNote(
        arabic_value="12",
        bengali_word="ডজন",
        english_word="dozen",
        category="multiplier",
        tags=["numbers::multiplier"],
        notes="Borrowed from English. Same shopping-vocabulary register.",
    ),
]


# ─── ORDINALS 1st–10th ─────────────────────────────────────────────────────────
# 1st–4th irregular (Sanskrit-derived); 5th+ = cardinal + -তম in everyday use,
# though Sanskrit forms (পঞ্চম, ষষ্ঠ, …) exist in literary register.

_ORDINALS_IRREG = {
    "1st":  ("প্রথম",   "first"),
    "2nd":  ("দ্বিতীয়", "second"),
    "3rd":  ("তৃতীয়",  "third"),
    "4th":  ("চতুর্থ",  "fourth"),
}

_CARDINAL_FOR_ORDINAL = {
    5: "পাঁচ", 6: "ছয়", 7: "সাত", 8: "আট", 9: "নয়", 10: "দশ",
}

ORDINALS = []
for k, (bw, ew) in _ORDINALS_IRREG.items():
    ORDINALS.append(NumberNote(
        arabic_value=k,
        bengali_word=bw,
        english_word=ew,
        category="ordinal",
        bengali_numeral=None,  # ordinal — no clean numeral form
        tags=["numbers::ordinal"],
        notes="Sanskrit-derived irregular ordinal.",
    ))
for k in (5, 6, 7, 8, 9, 10):
    ORDINALS.append(NumberNote(
        arabic_value=f"{k}th",
        bengali_word=f"{_CARDINAL_FOR_ORDINAL[k]}তম",
        english_word={
            5: "fifth", 6: "sixth", 7: "seventh",
            8: "eighth", 9: "ninth", 10: "tenth",
        }[k],
        category="ordinal",
        bengali_numeral=None,
        decomposition=f"{_CARDINAL_FOR_ORDINAL[k]} ({k}) + -তম (ordinal suffix)",
        tags=["numbers::ordinal"],
    ))


# ─── FRACTIONAL QUANTIFIERS ───────────────────────────────────────────────────
# Closed set; characteristically Bengali. পৌনে/সওয়া are productive prefixes.

FRACTIONALS = [
    NumberNote(
        arabic_value="1/4",
        bengali_word="সিকি",
        english_word="one quarter",
        category="fractional",
        bengali_numeral=None,
        tags=["numbers::fractional"],
        notes="Also a colloquial term for the 25-paisa coin.",
    ),
    NumberNote(
        arabic_value="1/2",
        bengali_word="আধ",
        english_word="one half",
        category="fractional",
        bengali_numeral=None,
        tags=["numbers::fractional"],
        notes="Formal/Sanskritic variant: অর্ধ.",
    ),
    NumberNote(
        arabic_value="3/4",
        bengali_word="পৌনে",
        english_word="three-quarters of (the next whole)",
        category="fractional",
        bengali_numeral=None,
        decomposition="পৌনে + N = N − ¼.  E.g., পৌনে চার = 3¾, পৌনে এক = ¾.",
        tags=["numbers::fractional", "numbers::pattern"],
        notes="Productive prefix. Means '¼ less than next integer'.",
    ),
    NumberNote(
        arabic_value="1¼",
        bengali_word="সওয়া",
        english_word="a quarter past (the integer)",
        category="fractional",
        bengali_numeral=None,
        decomposition="সওয়া + N = N + ¼.  E.g., সওয়া তিন = 3¼, সওয়া এক = 1¼.",
        tags=["numbers::fractional", "numbers::pattern"],
        notes="Productive prefix. Means '¼ more than the integer'.",
    ),
    NumberNote(
        arabic_value="1½",
        bengali_word="দেড়",
        english_word="one and a half",
        category="fractional",
        bengali_numeral=None,
        tags=["numbers::fractional"],
        notes="Used only for 1½ specifically. For 2½ use আড়াই; 3½ and up: সাড়ে + N.",
    ),
    NumberNote(
        arabic_value="2½",
        bengali_word="আড়াই",
        english_word="two and a half",
        category="fractional",
        bengali_numeral=None,
        tags=["numbers::fractional"],
        notes="Used only for 2½. From 3½ up, use সাড়ে + N (সাড়ে তিন = 3½).",
    ),
]


# ─── PATTERN / RULE REFERENCE CARDS ───────────────────────────────────────────
# Recognition-only. Front: the pattern itself. Back: 2–3 worked examples.

PATTERNS = [
    NumberNote(
        arabic_value="উন-",
        bengali_word="উন-",
        english_word="prefix: 'one less than the next ten'",
        category="pattern",
        bengali_numeral=None,
        decomposition=(
            "19 = উনিশ (one less than 20)<br>"
            "29 = উনত্রিশ (one less than 30)<br>"
            "39 = উনচল্লিশ &nbsp; 49 = উনপঞ্চাশ &nbsp; 59 = উনষাট<br>"
            "69 = উনসত্তর &nbsp; 79 = উনআশি &nbsp; 89 = উননব্বই"
        ),
        tags=["numbers::pattern"],
        enable_production=False,
        enable_listening=False,
    ),
    NumberNote(
        arabic_value="-তম",
        bengali_word="-তম",
        english_word="suffix: ordinal marker (5th and up)",
        category="pattern",
        bengali_numeral=None,
        decomposition=(
            "cardinal + তম = ordinal<br>"
            "পাঁচ → পাঁচতম (5th) &nbsp; দশ → দশতম (10th)<br>"
            "1st–4th use the irregular Sanskrit forms প্রথম / দ্বিতীয় / তৃতীয় / চতুর্থ."
        ),
        tags=["numbers::pattern"],
        enable_production=False,
        enable_listening=False,
    ),
    NumberNote(
        arabic_value="পৌনে / সওয়া",
        bengali_word="পৌনে / সওয়া",
        english_word="fractional prefixes (−¼ / +¼)",
        category="pattern",
        bengali_numeral=None,
        decomposition=(
            "<b>পৌনে</b> N = N − ¼. পৌনে চার = 3¾.<br>"
            "<b>সওয়া</b> N = N + ¼. সওয়া তিন = 3¼.<br>"
            "Used heavily for time/price: পৌনে চারটে = 3:45, সওয়া এগারোটা = 11:15."
        ),
        tags=["numbers::pattern"],
        enable_production=False,
        enable_listening=False,
    ),
    NumberNote(
        arabic_value="সাড়ে",
        bengali_word="সাড়ে",
        english_word="prefix: '+ ½' (for 3½ and up)",
        category="pattern",
        bengali_numeral=None,
        decomposition=(
            "সাড়ে N = N + ½ (for N ≥ 3).<br>"
            "সাড়ে তিন = 3½ &nbsp; সাড়ে পাঁচ = 5½ &nbsp; সাড়ে দশ = 10½.<br>"
            "Exceptions: 1½ = দেড়, 2½ = আড়াই (these don't use সাড়ে)."
        ),
        tags=["numbers::pattern"],
        enable_production=False,
        enable_listening=False,
    ),
]


# ─── EVERYTHING ───────────────────────────────────────────────────────────────

ALL_NOTES: list[NumberNote] = (
    DIGITS
    + CARDINALS_10_20
    + CARDINAL_TENS
    + CARDINALS_21_99
    + MULTIPLIERS
    + ORDINALS
    + FRACTIONALS
    + PATTERNS
)


def summary() -> str:
    lines = [f"Total notes: {len(ALL_NOTES)}"]
    by_cat: dict[str, int] = {}
    needs_gemini = 0
    for n in ALL_NOTES:
        by_cat[n.category] = by_cat.get(n.category, 0) + 1
        is_21_99_cardinal = (
            n.category == "cardinal"
            and n.arabic_value.isdigit()
            and 21 <= int(n.arabic_value) <= 99
        )
        if n.bengali_word is None or (n.decomposition is None and is_21_99_cardinal):
            needs_gemini += 1
    for cat, c in sorted(by_cat.items()):
        lines.append(f"  {cat:12s} {c}")
    lines.append(f"\nNotes needing Gemini fill (bengali_word + decomposition): {needs_gemini}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
