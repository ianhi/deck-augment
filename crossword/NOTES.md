# crossword/ — build notes

## Status (snapshot 2026-05-26)

**v1.3 deck live in user's Anki collection.** Also archived as `out/crosswordese.apkg`
(~148 KB, 173 notes, 2595 clues).

v1.3 made the deck rigorous: clue text now comes from the
**[XD Crossword Corpus](https://xd.saul.pw/data)** (8M (answer, clue) rows
across NYT, LAT, WSJ, USA Today, Newsday, indies; 1942–2026), so every
clue is ranked by actual usage count and every answer has a citeable
frequency. The v1.2 entries MU and NU were dropped (XD shows 0 and 3
appearances respectively).

- Note type: `Crosswordese` (MODEL_ID 1748100001)
- Deck: `Crosswordese::Core` (DECK_ID 1748100002)
- One card type: Clue → Answer
- Fields (21): `Answer`, `Length`, `Category`, `Definition`, `Note`, `ClueCount`, `Clue01`..`Clue15`
- Push path: AnkiConnect (`push_to_anki.py`) — **not** `importPackage` (Anki is
  flatpak-sandboxed and can't read `/home/ian/...`). See CLAUDE.md Conventions.

### Card layout

- **Front**: meta line (`N letters · CATEGORY`) → letter-pattern (`_ _ _ _`) →
  one random clue → empty extras-clues reservation (14em) → hint row
  (`+ clue`, `+ letter`). On mobile the hint row sits below the center
  reveal-back tap zone via the reservation.
- **Back**: front content reused via `{{FrontSide}}` (same active clue, same
  position). Pattern filled with the answer letters in the same slot. Hint
  row hidden, extras reservation collapsed. Below: a tinted `.meaning` panel
  with definition + optional italic note, then a `.clues-header` divider,
  then a numbered list of all clues.
- **Random-position letter reveal**: `+ letter` reveals positions in
  Fisher-Yates-shuffled order, not left-to-right.
- **Same-clue front↔back**: random clue + letter-order + revealed counts are
  persisted in `sessionStorage` keyed by answer (key prefix `cw3_`). Back
  template emits a `#back-marker` element; front.js checks for it to decide
  whether to load cached state or generate fresh. Every fresh front render =
  new shuffle.

### Styling

- No hardcoded text/background colors — inherits Anki's theme so it works in
  dark mode (mobile), Anki desktop default gray, and light themes.
  Emphasis is via font-size, weight, italic; lines/buttons use `rgba(127,127,127, X)`
  semi-transparent neutrals.

Note GUID format: `crosswordese-<ANSWER>`. Re-running `build_pack.py` and
`push_to_anki.py` is idempotent — existing notes update in place (templates +
CSS refresh on every push, field data only on `--force`).

### Pipeline

```
crossword/source_data.py   # 84 entries: answer, category, definition, note
        │
        ▼
crossword/scrape_clues.py  # 5s rate limit, on-disk cache, fail-fast, resumable
        │  (crosswordheaven.com/words/<answer>, top-15 by canonicity)
        ▼
out/crossword_clues.json   # {answer: [clue, ...]}
out/crossword_cache/*.html # raw cached HTML, one file per answer
        │
        ▼
crossword/build_pack.py    # genanki → out/crosswordese.apkg
```

## Sources

- **crosswordheaven.com** for clue lists. Free, no auth.
  Tried first: **xwordinfo.com** (requires login), **crosswordtracker.com**
  (TLS cert expired as of 2026-05), **wordplays.com** (HTTP 401),
  **crosswordheaven.com/search** (search-by-answer broken; the `/words/<answer>`
  path works and was what we used).
- Definitions hand-written by Claude against general knowledge (see issues below).

## Coverage (v1.1 — 121 entries)

**v1 (84) + v1.1 high-frequency gap batch (37 more, added 2026-05-24).** Now
covers all five "Big Five" iconic crosswordese (ETUI, OLEO, ESNE, ANOA, ADIT)
plus the canonical top-frequency short fill across 3-/4-/5-letter buckets.

v1.1 added: 6 interjections (OOH AAH OHO EEK TSE TAE), 7 compass directions
(NNE NNW SSE SSW ENE WSW WNW), 5 ultra-common 4-letter fill (ODOR ELSE ORAL
ANEW EELS), 2 Middle East giants (IRAN IRAQ), 6 rivers / niche-but-frequent
(YSER AARE ARAL EBRO ELHI UTNE), 5 ultra-common 5-letter fill (ARENA NAIVE
OCEAN INANE OZONE), 6 recurring proper nouns (ETHEL RENEE LASSO MAMET ORONO
OUTRE).

## Known issues (caught by 2026-05-24 review pass — not yet fixed)

### Definition errors (factual)

- **EMU** — "second-tallest living bird" → actually third, behind common and
  Somali ostrich. Soften to "second-largest living bird by height after the
  ostrich" or just drop the ranking.
- **ETNA** — "highest volcano in continental Europe" → Etna is on Sicily, not
  continental; should be "largest active volcano in Europe" or "tallest active
  volcano in Europe outside the Caucasus".
- **ARIL** — pomegranate seed coat is technically a sarcotesta, not an aril.
  Better example: nutmeg/mace, yew, lychee, longan.
- **EROS** — "son of Aphrodite" is one tradition; Hesiod has him as a
  primordial. Probably fine to leave but worth flagging in the `note`.

### Scraped-clue cross-reference cruft (6 clues unusable standalone)

- ALE [5] — `"See above"`
- STET [2] — `"Opposite of 65-Across"`
- OATER [12] — `"See 21-Across"`
- TAROT [7] — `"With 29-Down, source of this puzzle's theme"`
- ADIT [9] — `"Passage to get 8-Down"`
- ADIT [14] — `"Access to 2-Down"`
- ODIN [0] — `"Thor's chief love: thunder (4)"` — looks like a scrape glitch

Easy fix: filter in `scrape_clues.py` with
`re.search(r'\b\d+-(Across|Down)\b|^See \b', clue)` before keeping.
(Will need a `--refresh` re-fetch + rebuild to take effect.)

### Category taxonomy weak (see review report)

- `crosswordese` category is just "this is obscure" — semantic information is
  better expressed by the actual category (ANOA → nature, OATER → film/general,
  EWER → general, etc.). Recommendation: retire `crosswordese` category.
- `names` (24% of deck) could split into `name-actor` / `name-musician` /
  `name-athlete` / `name-other` for a more informative hint.
- `abbr` category does little work — merge into `general`.
- HORA could move from `general` to `music`.

## Clue distribution (1260 clues, 84 answers)

| Type                     | Count |   %  |
|--------------------------|------:|-----:|
| Quoted (spoken)          |    64 | 5.1% |
| Fill-in-blank (`___`)    |    45 | 3.6% |
| Wordplay (`?`)           |    33 | 2.6% |
| Abbreviation flag        |    33 | 2.6% |
| Foreign-language flag    |    30 | 2.4% |
| `e.g.` clue              |    20 | 1.6% |
| Ellipsis                 |     1 | 0.1% |
| Bracketed `[sound]`      |     0 | 0.0% |
| `Var.` clue              |     0 | 0.0% |

Median clue length: 16 chars · 2 words. Pure-trivia / proper-noun clues
dominate the rest (~80% of clues have no syntactic marker).

## Invalidation triggers (regenerate if any of these change)

| If you change …                          | Re-run …                                                       |
|------------------------------------------|----------------------------------------------------------------|
| `source_data.py` (entries added/edited)  | `scrape_clues.py` then `build_pack.py`                         |
| Want updated clues from upstream         | `scrape_clues.py --refresh` then `build_pack.py`               |
| Just card layout / CSS / template / JS   | `build_pack.py`                                                |
| `MODEL_ID` (must be unique forever)      | Bump; you'll get a new note type on next import — old reviews lost |
| `MAX_CLUES`                              | `build_pack.py` only (note type schema changes — re-import)    |
| Note type field order in `build_pack.py` | `build_pack.py`; existing notes will need a re-import          |

## Build-time safety guards (worth keeping)

- `build_pack._assert_no_mustache_in_js` — refuses to build if any JS file
  contains `{{` or `}}` anywhere (even in comments). Anki substitutes those
  tokens inside `<script>` tags; if the substituted content contains
  `</script>`, the browser ends the script element early and dumps the rest
  of the JS as visible text. Caught twice the hard way (front.js comment
  and back.js comment).
- `build_pack.assert_unique_answers` — refuses to build if two entries share
  an answer. Prevents silent `genanki.guid_for` collisions and ambiguous
  `findNotes` lookups.
- `build_pack._check_js_syntax` — `node --check` on both JS files when Node
  is on PATH. Catches plain typos before they reach Anki.

## Pipeline (v1.3 onward)

```
crossword/source_data.py        # 173 entries: answer, category, definition, note
        │
        ▼
out/xd/xd/clues.tsv             # ~8M rows from XD corpus (downloaded once)
        │
crossword/compute_xd_stats.py   # frequency + per-answer clue counts
        │
        ▼
out/xd_answer_freq.json         # {answer: total_count}, used by audit_vs_xd
out/xd_clue_freq.json           # {answer: [[clue, count], ...]}
        │
crossword/derive_clues_from_xd.py  # top-15 per answer, deduped + filtered
        │
        ▼
out/crossword_clues.json        # the build_pack source of truth
        │
crossword/build_pack.py
        │
        ▼
out/crosswordese.apkg + push to live deck via AnkiConnect
```

The earlier `scrape_clues.py` (crosswordheaven scraper) is retained as a
fallback / cross-check; its output is preserved at
`out/crossword_clues_crosswordheaven.json`.

## Done (chronological)

- 2026-05-24: filter cross-reference clues during scrape (`Across`/`Down`).
- 2026-05-24: add v1.1 high-frequency gap batch (37 entries → 121 total).
- 2026-05-24: `+ letter` reveals at Fisher-Yates-shuffled positions.
- 2026-05-24: extract templates into `crossword/templates/` so JS is real JS.
- 2026-05-24: short-form cross-reference filter (`21A`, `5D`, `12-A`).
- 2026-05-24: HTTP retry handling distinguishes 429/5xx from other 4xx.
- 2026-05-24: `--refresh` no longer wipes unrelated answers in results JSON.
- 2026-05-24: `findNotes` uses quoted answer; multi-match is now a hard error.
- 2026-05-24: `--force` syncs tags via `removeTags`/`addTags`.
- 2026-05-24: state-sharing via `#back-marker` element (replaced fragile
  `consumed` flag).
- 2026-05-25: `textContent` instead of `innerText` for clue-pool reading
  (innerText returns `""` for elements inside `display:none` in Chromium).
- 2026-05-25: build guard rejects `{{` in JS files.
- 2026-05-26: integrated XD Crossword Corpus (8M (answer, clue) rows);
  added `compute_xd_stats.py`, `audit_vs_xd.py`,
  `derive_clues_from_xd.py`; replaced crosswordheaven clues with
  XD-derived top-15-by-frequency.
- 2026-05-26: v1.3 batch — dropped MU/NU (XD freq ~0), added 24
  XD-top-frequency 3–5-letter entries (ERIE, ALA, SPA, ODE, IRA, OLE,
  NEE, ETAL, OSLO, TSAR, AHA, ALAS, ANON, ENOS, OGRE, ETON, ELAN, ALEC,
  IDLE, OPAL, ALTO, ESS, ASIA, ISLE).

## Future work / v2 ideas

- Fix EMU / ETNA / ARIL definitions (factual nits flagged in earlier review).
- Next round of additions: more Greek-letter answers (IOTA/RHO/PHI…), more
  rivers (NEVA, ELBE, PO), classical proper nouns (ENOS, ASA, IO, ECHO, NIKE),
  Roman-numeral compounds (XLIV, MCMLXIV — may not fit clue→answer cleanly
  since they're typically clued, not the clue), more brand/abbr (NCAA, GOP,
  AAA, EKG, ICU).
- Add a `Recognition` card type: show the answer + letter-pattern + category,
  recall the definition. Lower priority — Clue→Answer is the dominant direction.
- Optional: enrich `definition` from Wiktionary scrape instead of hand-writing.
