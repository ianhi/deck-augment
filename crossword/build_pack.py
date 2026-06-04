"""Build out/crosswordese.apkg and produce the model templates.

Templates live in `crossword/templates/` as plain `.html`, `.css`, and `.js`
files (so the JS is real JS, syntax-highlightable, and lintable). This
module:
  1. reads those files,
  2. expands the `{{!-- INJECT_* --}}` placeholders for the dynamic bits
     (clue-pool span list, all-clues ol list, the embedded JS),
  3. syntax-checks both JS bundles with `node --check` if Node is on PATH,
  4. builds the model + deck, writes `out/crosswordese.apkg`.

Note type: `Crosswordese`. One card per note (Clue → Answer).

Fields:
  Answer       — uppercase answer (e.g. ETUI)
  Length       — character count, e.g. "4"
  Category     — semantic group (opera, mythology, foreign, ...)
  Definition   — dictionary-style meaning of the answer
  Note         — etymology / variants / mnemonic (optional)
  ClueCount    — number of populated Clue fields (1..15)
  Clue01..15   — verified real clues from crosswordheaven.com
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import genanki

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crossword.source_data import ENTRIES  # noqa: E402

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
OUT = REPO / "out"
CLUES_PATH = OUT / "crossword_clues.json"

DECK_NAME = "Crosswordese::Core"
MODEL_ID = 1748100001
DECK_ID = 1748100002
MAX_CLUES = 15

DECK_DESCRIPTION = (
    '<h3 style="margin:0 0 6px 0">Crosswordese: Core</h3>'
    '<p style="margin:4px 0">'
    "High-frequency short answers in American crossword puzzles — the words "
    "that show up far more often in crosswords than in everyday English: "
    "ETUI, OLEO, ESNE, ANOA, ADIT, and the rest. Each note carries up to 15 "
    "verified real clues drawn from major U.S. publications."
    "</p>"
    '<p style="margin:6px 0 2px 0"><b>Card layout</b></p>'
    '<ul style="margin:2px 0;padding-left:20px">'
    "<li>Front: a random clue from this answer's pool, plus the answer's "
    "letter pattern (<code>_ _ _ _</code>).</li>"
    "<li><b>+ clue</b> reveals another canonical clue for the same answer.</li>"
    "<li><b>+ letter</b> reveals one letter at a random position.</li>"
    "<li>Back: full answer, dictionary definition, and the complete clue "
    "list for that answer.</li>"
    "</ul>"
    '<p style="margin:6px 0 2px 0"><b>Sources</b></p>'
    '<ul style="margin:2px 0;padding-left:20px">'
    "<li><b>Frequency ranking + clue text:</b> the "
    '<a href="https://xd.saul.pw/data">XD Crossword Corpus</a> '
    "(saulpw / Saul Pwanson), ~8 million answer/clue rows from NYT, LAT, "
    "WSJ, USA Today, Newsday, Universal, and many indie publications "
    "1942–2026. Entries are ordered by total puzzle appearances; each "
    "card's clues are ranked by usage count and de-duplicated. "
    "Cross-reference clues (<code>21A</code>, <code>See 12-Down</code>, …) "
    "are filtered out.</li>"
    "<li><b>Curation of which words to include:</b> Planet Word Museum's "
    "<i>Big Five</i> obscure list; Dictionary.com's <i>Master the Secrets "
    "of Crosswordese</i>; the <i>Last-Minute Crossword Tournament Prep</i> "
    "report (2026-05); plus XD top-frequency by length.</li>"
    "<li><b>Definitions:</b> hand-written from standard dictionary references "
    "(Merriam-Webster, Wiktionary).</li>"
    "</ul>"
    '<p style="color:#888;font-size:90%;margin:6px 0 0 0">'
    "Built with <a href=\"https://ianhuntisaak.com\">ianhuntisaak.com</a> "
    "tooling, May 2026. Source at "
    "<code>deck-augment/crossword/</code>."
    "</p>"
)


# ---------- template loading + injection ---------------------------------

def _clue_pool_html() -> str:
    """Hidden DOM nodes containing each clue, for the front JS to pick from."""
    parts = []
    for i in range(1, MAX_CLUES + 1):
        n = f"{i:02d}"
        parts.append(
            f'{{{{#Clue{n}}}}}<span class="clue-pool-item" data-i="{i}">'
            f'{{{{Clue{n}}}}}</span>{{{{/Clue{n}}}}}'
        )
    return "".join(parts)


def _all_clues_list_html() -> str:
    parts = ['<ol class="back-clue-list">']
    for i in range(1, MAX_CLUES + 1):
        n = f"{i:02d}"
        parts.append(f'{{{{#Clue{n}}}}}<li>{{{{Clue{n}}}}}</li>{{{{/Clue{n}}}}}')
    parts.append("</ol>")
    return "".join(parts)


def _inject(template: str, marker: str, content: str) -> str:
    """Replace a `{{!-- MARKER --}}` placeholder. Fails loudly if missing —
    that's the whole point of doing this rather than string-concat."""
    needle = "{{!-- " + marker + " --}}"
    if needle not in template:
        raise RuntimeError(
            f"template missing required marker {needle!r}; "
            f"add it to the relevant .html file under templates/"
        )
    return template.replace(needle, content)


def _check_js_syntax(path: Path) -> None:
    """Run `node --check` if available so a JS typo fails the build."""
    node = shutil.which("node")
    if node is None:
        print(f"  (node not on PATH — skipping syntax check of {path.name})")
        return
    result = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"node --check failed for {path}")
    print(f"  syntax OK: {path.relative_to(REPO)}")


def _assert_no_mustache_in_js(path: Path, body: str) -> None:
    """Refuse to build if a JS file contains a `{{...}}` sequence anywhere
    (including inside comments). Anki's Mustache substitution doesn't respect
    HTML/JS boundaries — a stray `{{FrontSide}}` in a JS comment expands to
    the entire front HTML inside the script tag, the nested `</script>`
    closes the back script element early, and the rest of the JS is
    rendered as visible text. Caught one of these the hard way; this guard
    keeps it from happening again."""
    if "{{" in body or "}}" in body:
        raise RuntimeError(
            f"{path}: JS files must not contain '{{{{' or '}}}}' anywhere — "
            f"Anki's Mustache will substitute it inside the <script> tag and "
            f"break the template. Rewrite the offending text as plain prose."
        )


def load_templates() -> tuple[str, str, str]:
    """Return (front_html, back_html, css) with all placeholders expanded."""
    front_js_path = TEMPLATES / "front.js"
    back_js_path = TEMPLATES / "back.js"
    _check_js_syntax(front_js_path)
    _check_js_syntax(back_js_path)

    front_html = (TEMPLATES / "front.html").read_text(encoding="utf-8")
    back_html = (TEMPLATES / "back.html").read_text(encoding="utf-8")
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")

    front_js = front_js_path.read_text(encoding="utf-8")
    back_js = back_js_path.read_text(encoding="utf-8")
    _assert_no_mustache_in_js(front_js_path, front_js)
    _assert_no_mustache_in_js(back_js_path, back_js)

    front_html = _inject(front_html, "INJECT_CLUE_POOL", _clue_pool_html())
    front_html = _inject(front_html, "INJECT_FRONT_JS", front_js)

    back_html = _inject(back_html, "INJECT_ALL_CLUES_LIST", _all_clues_list_html())
    back_html = _inject(back_html, "INJECT_BACK_JS", back_js)

    return front_html, back_html, css


# ---------- validation ---------------------------------------------------

def assert_unique_answers(entries: list[dict]) -> None:
    """Guard against silent guid collisions. `genanki.guid_for(...)` is a hash
    of the answer string, so two entries with the same `answer` produce the
    same guid and genanki silently drops the duplicate."""
    seen: dict[str, int] = {}
    dupes: list[str] = []
    for e in entries:
        a = e["answer"]
        seen[a] = seen.get(a, 0) + 1
        if seen[a] == 2:
            dupes.append(a)
    if dupes:
        raise RuntimeError(
            f"duplicate `answer` values in ENTRIES (would collide on guid): {dupes}"
        )


# ---------- main build ---------------------------------------------------

def main() -> None:
    assert_unique_answers(ENTRIES)
    raw_clues: dict[str, list[str]] = json.loads(CLUES_PATH.read_text())

    front_html, back_html, css = load_templates()

    field_defs: list[dict] = [
        {"name": "Answer"},
        {"name": "Length"},
        {"name": "Category"},
        {"name": "Definition"},
        {"name": "Note"},
        {"name": "ClueCount"},
    ]
    for i in range(1, MAX_CLUES + 1):
        field_defs.append({"name": f"Clue{i:02d}"})

    model = genanki.Model(
        MODEL_ID,
        "Crosswordese",
        fields=field_defs,
        templates=[{"name": "Clue→Answer", "qfmt": front_html, "afmt": back_html}],
        css=css,
    )

    deck = genanki.Deck(DECK_ID, DECK_NAME, description=DECK_DESCRIPTION)

    n_clue_total = 0
    for e in ENTRIES:
        answer = e["answer"]
        clues = raw_clues.get(answer, [])[:MAX_CLUES]
        n_clue_total += len(clues)
        clue_fields = clues + [""] * (MAX_CLUES - len(clues))

        fields = [
            answer,
            str(len(answer)),
            e["category"],
            e["definition"],
            e.get("note", ""),
            str(len(clues)),
            *clue_fields,
        ]

        note = genanki.Note(
            model=model,
            fields=fields,
            tags=["crosswordese", e["category"]],
            guid=genanki.guid_for(f"crosswordese-{answer}"),
        )
        deck.add_note(note)

    out_path = OUT / "crosswordese.apkg"
    genanki.Package(deck).write_to_file(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"Notes: {len(deck.notes)}")
    print(f"Total clues embedded: {n_clue_total}")
    print(f"Wrote {out_path} ({size_kb:.1f} KB)")


# Re-export the rendered templates + CSS so push_to_anki.py can refresh
# them on existing models without rebuilding the apkg.
def get_templates_and_css() -> tuple[str, str, str]:
    return load_templates()


if __name__ == "__main__":
    main()
