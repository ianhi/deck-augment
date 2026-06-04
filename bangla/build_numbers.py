"""Build the `Bangla Number` deck.

Three phases, all idempotent, cache in `out/bangla_numbers.jsonl`:

  1. Gemini fill — for each of ~125 seed notes, fill the missing
     bengali_word / decomposition (where seeded as None) and ALWAYS get
     a Kolkata-Bengali example sentence + English translation.
  2. Create model + deck via AnkiConnect (`createModel`, `createDeck`).
  3. Add notes via AnkiConnect (`addNotes`), tagged per seed.

Usage:
  uv run build_bangla_numbers.py --fill                # gemini pass only
  uv run build_bangla_numbers.py --fill --limit 5      # test on 5 notes
  uv run build_bangla_numbers.py --create-model        # createModel + createDeck
  uv run build_bangla_numbers.py --add-notes           # push cached notes to Anki
  uv run build_bangla_numbers.py --delete-old --dry-run  # show old number cards
  uv run build_bangla_numbers.py --delete-old          # actually delete them

Audio is handled in a separate step (see tts_run_bangla.py extension).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

from lib.ankiconnect import ac
from lib.gemini_prompts import BANGLA_NUMBER_FILL_SYSTEM, BANGLA_NUMBER_FILL_USER
from lib.numbers_seed import (
    ALL_NOTES,
    DECK_NAME,
    FIELDS,
    NOTE_TYPE_NAME,
    NumberNote,
)

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
RESULTS_PATH = OUT_DIR / "bangla_numbers.jsonl"

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_CONCURRENCY = 6


def stable_id(note: NumberNote) -> str:
    """Deterministic short key per seed note. Used as cache key + media stem.

    Includes english_word slug to disambiguate fractional/pattern entries
    whose arabic_value has special characters that strip to identical
    slugs (e.g. 1¼ and 1½ both → "1_")."""
    arabic = re.sub(r"[^A-Za-z0-9]", "_", note.arabic_value).strip("_") or "x"
    english = re.sub(r"[^A-Za-z0-9]", "_", note.english_word).strip("_")[:24] or "x"
    return f"{note.category}_{arabic}__{english}"


# ─── Cache ────────────────────────────────────────────────────────────────────

def load_cache() -> dict[str, dict]:
    if not RESULTS_PATH.exists():
        return {}
    out: dict[str, dict] = {}
    with RESULTS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            out[entry["stable_id"]] = entry
    return out


def append_cache(entry: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── Gemini fill ──────────────────────────────────────────────────────────────

def validate_example(bangla_sentence: str) -> list[str]:
    """Cheap local checks."""
    issues: list[str] = []
    bolds = re.findall(r"<b\b[^>]*>(.*?)</b>", bangla_sentence, flags=re.DOTALL | re.IGNORECASE)
    if len(bolds) != 1:
        issues.append(f"expected exactly one <b>...</b>, found {len(bolds)}")
    plain = re.sub(r"<[^>]+>", "", bangla_sentence).strip()
    wc = len(plain.split())
    if not 2 <= wc <= 14:
        issues.append(f"word count {wc} out of range 2-14")
    if not plain.endswith(("।", "?", "!")):
        issues.append("does not end with Bangla terminator")
    # No Latin alphabet inside example (except inside the bold tags themselves)
    body_without_tags = re.sub(r"<[^>]+>", "", bangla_sentence)
    if re.search(r"[A-Za-z]", body_without_tags):
        issues.append("contains Latin characters")
    return issues


async def fill_one(
    client: genai.Client,
    model_name: str,
    note: NumberNote,
    semaphore: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    sid = stable_id(note)
    user_prompt = BANGLA_NUMBER_FILL_USER.format(
        category=note.category,
        arabic_value=note.arabic_value,
        bengali_numeral=note.bengali_numeral or "(none)",
        english_word=note.english_word,
        seeded_bengali_word=note.bengali_word or "(null — please supply)",
        seeded_decomposition=(
            note.decomposition
            or "(null — please supply if morphology is decomposable)"
        ),
        notes=note.notes or "(none)",
    )
    async with semaphore:
        last_err: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_NUMBER_FILL_SYSTEM,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                payload = json.loads(resp.text or "")
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    payload = payload[0]
                if not isinstance(payload, dict):
                    raise ValueError(f"expected JSON object, got {type(payload).__name__}")
                example_bangla = payload["example_bangla"]
                issues = validate_example(example_bangla)
                if issues:
                    last_err = "validation: " + "; ".join(issues)
                    await asyncio.sleep(1 * attempt)
                    continue
                usage = getattr(resp, "usage_metadata", None)
                return {
                    "stable_id": sid,
                    "arabic_value": note.arabic_value,
                    "category": note.category,
                    "seeded_bengali_word": note.bengali_word,
                    "seeded_decomposition": note.decomposition,
                    "bengali_word": payload.get("bengali_word", "").strip(),
                    "decomposition": payload.get("decomposition", "").strip(),
                    "example_bangla": example_bangla,
                    "example_english": payload.get("example_english", "").strip(),
                    "confidence": payload.get("confidence", "medium"),
                    "model": model_name,
                    "attempt": attempt,
                    "usage": {
                        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                    },
                }
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                await asyncio.sleep(2 * attempt)
        return {
            "stable_id": sid,
            "arabic_value": note.arabic_value,
            "category": note.category,
            "error": last_err or "unknown",
            "model": model_name,
        }


async def run_fill(
    notes: list[NumberNote],
    model_name: str,
    concurrency: int,
    max_retries: int,
) -> None:
    load_dotenv(HERE / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY missing")
    client = genai.Client(api_key=api_key)
    semaphore = asyncio.Semaphore(concurrency)

    cache = load_cache()
    todo = [n for n in notes if stable_id(n) not in cache or "error" in cache.get(stable_id(n), {})]
    print(f"To fill: {len(todo)}  (cached: {len(notes) - len(todo)})", flush=True)
    if not todo:
        return

    tasks = [
        asyncio.create_task(fill_one(client, model_name, n, semaphore, max_retries))
        for n in todo
    ]
    done = 0
    for coro in asyncio.as_completed(tasks):
        entry = await coro
        append_cache(entry)
        done += 1
        marker = "OK" if "error" not in entry else "ER"
        bw = entry.get("bengali_word", "") or entry.get("error", "")
        print(f"  [{done:3d}/{len(todo)}] {marker} {entry['stable_id']:25s} {bw}", flush=True)


# ─── Anki model + deck creation ───────────────────────────────────────────────

CSS = """\
.card {
  font-family: "Noto Sans Bengali", "Hind Siliguri", "Kalpurush", sans-serif;
  font-size: 28px;
  text-align: center;
  color: #222;
  background: #fff;
}

.headword { font-size: 44px; font-weight: 700; margin: 12px 0; }
.headword b, b { color: #5586cd; }

.numeral-line { font-size: 44px; font-weight: 700; margin: 12px 0; }
.numeral-line .sep { color: #bbb; margin: 0 14px; font-weight: 400; }

.english-prompt { font-size: 30px; color: #666; margin: 8px 0; }
.english-prompt .arabic { color: #5586cd; font-weight: 600; }

.sentence {
  font-size: 26px;
  margin: 16px auto;
  max-width: 32em;
  line-height: 1.4;
}
.sentence b { color: #5586cd; }
.sentence-translation {
  font-size: 18px;
  color: #6a6a6a;
  margin: 6px auto;
}

.decomp {
  font-size: 16px;
  color: #666;
  margin: 12px auto;
  font-style: italic;
  max-width: 32em;
}

.cat {
  font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px;
  color: #888; margin-bottom: 8px;
}

.notes {
  font-size: 15px;
  color: #777;
  font-style: italic;
  margin: 10px auto;
  max-width: 32em;
}

hr#answer { margin: 18px 0; }
"""

# Templates — Mustache, each gated on EnableX so the same note can have any
# subset of the three cards. Audio fields are referenced as {{word_audio}}.

RECOGNITION_FRONT = """\
{{#EnableRecognition}}
<div class="cat">{{category}}</div>
{{#bengali_numeral}}<div class="numeral-line">{{bengali_numeral}}</div>{{/bengali_numeral}}
{{^bengali_numeral}}<div class="numeral-line">{{bengali_word}}</div>{{/bengali_numeral}}
{{/EnableRecognition}}
"""

RECOGNITION_BACK = """\
{{FrontSide}}
<hr id="answer">
{{#bengali_numeral}}<div class="numeral-line">{{bengali_word}}</div>{{/bengali_numeral}}
<div class="english-prompt"><span class="arabic">{{arabic_value}}</span> &nbsp;·&nbsp; {{english_word}}</div>
{{#decomposition}}<div class="decomp">{{decomposition}}</div>{{/decomposition}}
{{#example_bangla}}<div class="sentence">{{example_bangla}}</div>{{/example_bangla}}
{{#example_english}}<div class="sentence-translation">{{example_english}}</div>{{/example_english}}
{{word_audio}}
{{sentence_audio}}
{{#notes}}<div class="notes">{{notes}}</div>{{/notes}}
"""

PRODUCTION_FRONT = """\
{{#EnableProduction}}
<div class="cat">{{category}} · produce</div>
<div class="english-prompt"><span class="arabic">{{arabic_value}}</span> &nbsp;·&nbsp; {{english_word}}</div>
{{/EnableProduction}}
"""

PRODUCTION_BACK = """\
{{FrontSide}}
<hr id="answer">
<div class="numeral-line">{{bengali_numeral}}<span class="sep">|</span>{{bengali_word}}</div>
{{#decomposition}}<div class="decomp">{{decomposition}}</div>{{/decomposition}}
{{#example_bangla}}<div class="sentence">{{example_bangla}}</div>{{/example_bangla}}
{{#example_english}}<div class="sentence-translation">{{example_english}}</div>{{/example_english}}
{{word_audio}}
{{sentence_audio}}
"""

LISTENING_FRONT = """\
{{#EnableListening}}
<div class="cat">{{category}} · listen</div>
{{word_audio}}
{{/EnableListening}}
"""

LISTENING_BACK = """\
{{FrontSide}}
<hr id="answer">
<div class="numeral-line">{{bengali_numeral}}<span class="sep">|</span>{{bengali_word}}</div>
<div class="english-prompt"><span class="arabic">{{arabic_value}}</span> &nbsp;·&nbsp; {{english_word}}</div>
{{#decomposition}}<div class="decomp">{{decomposition}}</div>{{/decomposition}}
{{#example_bangla}}<div class="sentence">{{example_bangla}}</div>{{/example_bangla}}
{{#example_english}}<div class="sentence-translation">{{example_english}}</div>{{/example_english}}
{{sentence_audio}}
"""

TEMPLATES = [
    {"Name": "Recognition", "Front": RECOGNITION_FRONT, "Back": RECOGNITION_BACK},
    {"Name": "Production",  "Front": PRODUCTION_FRONT,  "Back": PRODUCTION_BACK},
    {"Name": "Listening",   "Front": LISTENING_FRONT,   "Back": LISTENING_BACK},
]


def create_model_and_deck(dry_run: bool) -> None:
    existing_models = set(ac("modelNames"))
    existing_decks = set(ac("deckNames"))
    actions: list[str] = []
    if NOTE_TYPE_NAME not in existing_models:
        actions.append(f"createModel {NOTE_TYPE_NAME!r}")
    else:
        actions.append(f"model {NOTE_TYPE_NAME!r} already exists — skip")
    if DECK_NAME not in existing_decks:
        actions.append(f"createDeck {DECK_NAME!r}")
    else:
        actions.append(f"deck {DECK_NAME!r} already exists — skip")
    print("\n".join("  " + a for a in actions))
    if dry_run:
        print("(dry-run — not executing)")
        return
    if NOTE_TYPE_NAME not in existing_models:
        ac(
            "createModel",
            modelName=NOTE_TYPE_NAME,
            inOrderFields=FIELDS,
            css=CSS,
            isCloze=False,
            cardTemplates=TEMPLATES,
        )
    if DECK_NAME not in existing_decks:
        ac("createDeck", deck=DECK_NAME)


# ─── Add notes ────────────────────────────────────────────────────────────────

def merge_seed_with_cache(note: NumberNote, cached: dict) -> dict[str, str]:
    """Build the Anki field dict, preferring seeded values over Gemini's where seeded."""
    bw = note.bengali_word if note.bengali_word else cached.get("bengali_word", "")
    decomp = note.decomposition if note.decomposition else cached.get("decomposition", "")
    def enable(b: bool) -> str:
        return "1" if b else ""
    return {
        "arabic_value":      note.arabic_value,
        "bengali_numeral":   note.bengali_numeral or "",
        "bengali_word":      bw,
        "english_word":      note.english_word,
        "category":          note.category,
        "decomposition":     decomp,
        "example_bangla":    cached.get("example_bangla", ""),
        "example_english":   cached.get("example_english", ""),
        "word_audio":        "",     # filled by TTS step
        "sentence_audio":    "",
        "notes":             note.notes,
        "EnableRecognition": enable(note.enable_recognition),
        "EnableProduction":  enable(note.enable_production),
        "EnableListening":   enable(note.enable_listening),
    }


def add_notes(dry_run: bool) -> None:
    cache = load_cache()
    payload = []
    missing = []
    for n in ALL_NOTES:
        sid = stable_id(n)
        cached = cache.get(sid, {})
        if "error" in cached or not cached:
            missing.append(sid)
            continue
        payload.append({
            "deckName": DECK_NAME,
            "modelName": NOTE_TYPE_NAME,
            "fields": merge_seed_with_cache(n, cached),
            "tags": n.tags + ["numbers::v1"],
            # Duplicates on first-field (arabic_value) are intentional:
            # cardinal "12" and multiplier "12" (ডজন) share the same Arabic
            # value but are semantically distinct notes.
            "options": {"allowDuplicate": True},
        })
    print(f"Ready to add: {len(payload)}.   Missing/errored: {len(missing)}")
    if missing:
        head = ", ".join(missing[:10])
        more = " …" if len(missing) > 10 else ""
        print(f"  missing stable_ids: {head}{more}")
    if dry_run:
        print("(dry-run — not adding)")
        if payload:
            print("\nFirst note preview:")
            print(json.dumps(payload[0], ensure_ascii=False, indent=2))
        return
    # AnkiConnect addNotes returns a list with one id per input; null on failure.
    BATCH = 50
    added = 0
    failed = 0
    for i in range(0, len(payload), BATCH):
        chunk = payload[i:i + BATCH]
        result = ac("addNotes", notes=chunk)
        for r in result:
            if r is None:
                failed += 1
            else:
                added += 1
        print(f"  pushed {added}; failed {failed}", flush=True)
    print(f"Done. Added {added} notes; failed {failed}.")


# ─── Delete old number cards from Bangla Vocab ────────────────────────────────

# These are the number-related notes flagged by audit_gemini_outputs.py — their
# Eng_main field contains Bengali digits or their headword is a number word.
def find_old_number_notes() -> list[tuple[int, str, str]]:
    """Find legacy number notes in the Bangla (and reversed) model."""
    query = '"note:Bangla (and reversed)"'
    nids = ac("findNotes", query=query)
    if not nids:
        return []
    info = ac("notesInfo", notes=nids)
    bengali_digit_re = re.compile(r"^[০-৯\s,.]+$")
    bengali_number_words = {n.bengali_word for n in ALL_NOTES if n.bengali_word}
    # Spelling variants not in the seed but plausible in legacy hand-typed cards.
    bengali_number_words |= {"চৌদ্দ", "পঞ্চম"}
    matches: list[tuple[int, str, str]] = []
    for n in info:
        bangla = n["fields"]["Bangla"]["value"].strip()
        eng = n["fields"].get("Eng_trans", {}).get("value", "").strip()
        is_number = (
            bangla in bengali_number_words
            or bengali_digit_re.match(eng) is not None
            or bengali_digit_re.match(bangla) is not None
        )
        if is_number:
            matches.append((n["noteId"], bangla, eng))
    return matches


def delete_old(dry_run: bool) -> None:
    matches = find_old_number_notes()
    print(f"Found {len(matches)} legacy number notes:")
    for nid, bangla, eng in matches:
        print(f"  {nid}  {bangla:15s}  {eng}")
    if dry_run:
        print("(dry-run — not deleting)")
        return
    if not matches:
        return
    ac("deleteNotes", notes=[m[0] for m in matches])
    print(f"Deleted {len(matches)} notes.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fill", action="store_true", help="Run Gemini fill pass.")
    p.add_argument("--create-model", action="store_true", help="Create note type + deck.")
    p.add_argument("--add-notes", action="store_true", help="Push cached notes to Anki.")
    p.add_argument(
        "--delete-old", action="store_true",
        help="Delete legacy number cards from Bangla Vocab.",
    )
    p.add_argument("--limit", type=int, default=None, help="Cap on notes processed.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--apply", action="store_true",
                   help="Disable dry-run for --create-model/--add-notes/--delete-old.")
    args = p.parse_args()

    if not any([args.fill, args.create_model, args.add_notes, args.delete_old]):
        p.error("Specify at least one of --fill / --create-model / --add-notes / --delete-old.")

    dry = not args.apply

    if args.fill:
        notes = ALL_NOTES if args.limit is None else ALL_NOTES[: args.limit]
        asyncio.run(run_fill(notes, args.model, args.concurrency, args.max_retries))

    if args.create_model:
        create_model_and_deck(dry_run=dry)

    if args.add_notes:
        add_notes(dry_run=dry)

    if args.delete_old:
        delete_old(dry_run=dry)


if __name__ == "__main__":
    main()
