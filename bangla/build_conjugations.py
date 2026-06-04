"""Build the Bangla Conjugations deck (Spanish-style cloze format).

Pipeline:
  1. Generate one example sentence per conjugated form via Gemini, with
     strict EXACT-FORM validation per `feedback_conjugation_form_preservation`.
     Cache to out/bangla_conjugations.jsonl.
  2. Create model + deck via AnkiConnect.
  3. For existing notes (20 of 24): updateNoteModel to convert in-place,
     preserving the note id (and the Recognition card's review history;
     the extra Production/Listening cards become orphans).
  4. For new notes (4 future forms): addNotes.
  5. Cloze Text: `<stem_before> {{c1::<form>::<infinitive>}}<stem_after>`.

Usage:
  uv run bangla/build_conjugations.py --fill                  # gemini pass
  uv run bangla/build_conjugations.py --fill --limit 3        # smoke test
  uv run bangla/build_conjugations.py --create-model          # createModel + createDeck
  uv run bangla/build_conjugations.py --apply-notes           # migrate + create notes
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types as genai_types  # noqa: E402

from lib.ankiconnect import ac  # noqa: E402
from lib.conjugation_seed import (  # noqa: E402
    ALL_FORMS,
    DECK_NAME,
    FIELDS,
    NOTE_TYPE_NAME,
    ConjForm,
)
from lib.gemini_prompts import (  # noqa: E402
    BANGLA_CONJUGATION_SYSTEM,
    BANGLA_CONJUGATION_USER,
)

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
RESULTS_PATH = OUT_DIR / "bangla_conjugations.jsonl"

DEFAULT_MODEL = "gemini-3-flash-preview"
CONCURRENCY = 4


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
            e = json.loads(line)
            out[e["form"]] = e
    return out


def append_cache(entry: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── Gemini fill ──────────────────────────────────────────────────────────────

async def fill_one(
    client: genai.Client,
    model_name: str,
    cf: ConjForm,
    sem: asyncio.Semaphore,
    max_retries: int,
) -> dict:
    user_prompt = BANGLA_CONJUGATION_USER.format(
        infinitive=cf.infinitive,
        english_inf=cf.english_inf,
        form=cf.form,
        tense=cf.tense,
        person=cf.person,
        register=cf.register or "(none)",
        subject_pronoun=cf.subject_pronoun,
        english_subject=cf.english_subject,
    )
    async with sem:
        last_err: str | None = None
        prior_failure: str | None = None
        for attempt in range(1, max_retries + 1):
            prompt = user_prompt
            if prior_failure:
                prompt = (
                    f"{user_prompt}\n\n"
                    f"# Previous attempt failed validation\n{prior_failure}\n"
                    f"Generate a corrected sentence."
                )
            try:
                resp = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=BANGLA_CONJUGATION_SYSTEM,
                        response_mime_type="application/json",
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                payload = json.loads(resp.text or "")
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    payload = payload[0]
                if not isinstance(payload, dict):
                    raise ValueError(f"expected object, got {type(payload).__name__}")
                sent = (payload.get("sentence_bangla") or "").strip()
                # NFC-normalize both before comparison — Gemini sometimes returns
                # the same-looking text in NFD/mixed form (য়/য + ◌়, ZWJ variants)
                sent_nfc = unicodedata.normalize("NFC", sent)
                form_nfc = unicodedata.normalize("NFC", cf.form)
                # CRITICAL validation: the exact form must appear verbatim
                if form_nfc not in sent_nfc:
                    last_err = f"validation: form `{cf.form}` not present in sentence `{sent}`"
                    prior_failure = (
                        f"prior sentence: {sent!r}\n"
                        f"the required form `{cf.form}` was NOT present (you may have substituted "
                        f"a different conjugation). Use the EXACT characters."
                    )
                    await asyncio.sleep(attempt)
                    continue
                # Subject pronoun must also appear (the "/" pronoun case is a fallback —
                # accept either side)
                pronouns = [unicodedata.normalize("NFC", p) for p in cf.subject_pronoun.split("/")]
                if not any(p in sent_nfc for p in pronouns):
                    last_err = f"validation: no subject pronoun {cf.subject_pronoun!r} in `{sent}`"
                    prior_failure = (
                        f"prior sentence: {sent!r}\n"
                        f"missing required subject pronoun {cf.subject_pronoun}. Include it explicitly."
                    )
                    await asyncio.sleep(attempt)
                    continue
                # Plain-text sanity: no Latin in the Bangla sentence
                if re.search(r"[A-Za-z]", sent):
                    last_err = f"validation: Latin chars in `{sent}`"
                    await asyncio.sleep(attempt)
                    continue
                return {
                    "form": cf.form,
                    "infinitive": cf.infinitive,
                    "tense": cf.tense,
                    "person": cf.person,
                    "register": cf.register,
                    "subject_pronoun": cf.subject_pronoun,
                    "existing_nid": cf.existing_nid,
                    "sentence_bangla": sent_nfc,
                    "sentence_english": (payload.get("sentence_english") or "").strip(),
                    "confidence": payload.get("confidence", "medium"),
                    "attempt": attempt,
                }
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                await asyncio.sleep(2 * attempt)
        return {"form": cf.form, "error": last_err or "unknown"}


async def run_fill(forms: list[ConjForm], model_name: str, max_retries: int) -> None:
    load_dotenv(HERE / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY missing")
    cache = load_cache()
    todo = [f for f in forms if f.form not in cache or "error" in cache.get(f.form, {})]
    print(f"To fill: {len(todo)}   (cached: {len(forms) - len(todo)})", flush=True)
    if not todo:
        return
    client = genai.Client(api_key=api_key)
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [asyncio.create_task(fill_one(client, model_name, f, sem, max_retries)) for f in todo]
    done = 0
    for coro in asyncio.as_completed(tasks):
        entry = await coro
        append_cache(entry)
        done += 1
        marker = "OK" if "error" not in entry else "ER"
        snippet = entry.get("sentence_bangla", "") or entry.get("error", "")
        print(f"  [{done:2d}/{len(todo)}] {marker} {entry['form']:10s}  {snippet[:60]}", flush=True)


# ─── Note type + deck ─────────────────────────────────────────────────────────

CSS = """\
.card {
  font-family: "Noto Sans Bengali", "Hind Siliguri", "Kalpurush", sans-serif;
  font-size: 26px;
  text-align: center;
  color: #222;
  background: #fff;
}
.tense {
  color: #888;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  margin-bottom: 16px;
}
.tense .person { color: #aaa; font-style: italic; text-transform: none; letter-spacing: 0; }
.cloze { font-weight: 700; color: #5586cd; }
.audio-row { margin-top: 16px; min-height: 32px; }
.english { color: #888; font-size: 16px; margin-top: 12px; }
.infinitive-hint { color: #aaa; font-size: 14px; }
"""

TENSE_HEADER = (
    '<div class="tense">'
    '{{Tense}}'
    '{{#Person}} <span class="person">· {{Person}}</span>{{/Person}}'
    '</div>'
)

FRONT_TEMPLATE = (
    f"{TENSE_HEADER}\n"
    "{{cloze:Text}}\n"
    '<div class="audio-row">&nbsp;</div>\n'
)

BACK_TEMPLATE = (
    f"{TENSE_HEADER}\n"
    "{{cloze:Text}}\n"
    '<div class="audio-row">{{SentenceAudio}}</div>\n'
    '<div class="english">{{English}}</div>\n'
)

TEMPLATES = [{"Name": "Conjugation", "Front": FRONT_TEMPLATE, "Back": BACK_TEMPLATE}]


def create_model_and_deck(dry_run: bool) -> None:
    existing_models = set(ac("modelNames"))
    existing_decks = set(ac("deckNames"))
    if NOTE_TYPE_NAME in existing_models:
        print(f"model {NOTE_TYPE_NAME!r} already exists — skip")
    else:
        print(f"createModel {NOTE_TYPE_NAME!r}")
    if DECK_NAME in existing_decks:
        print(f"deck {DECK_NAME!r} already exists — skip")
    else:
        print(f"createDeck {DECK_NAME!r}")
    if dry_run:
        print("(dry-run)")
        return
    if NOTE_TYPE_NAME not in existing_models:
        ac(
            "createModel",
            modelName=NOTE_TYPE_NAME,
            inOrderFields=FIELDS,
            css=CSS,
            isCloze=True,
            cardTemplates=TEMPLATES,
        )
    if DECK_NAME not in existing_decks:
        ac("createDeck", deck=DECK_NAME)


# ─── Build cloze Text ─────────────────────────────────────────────────────────

def build_cloze_text(sentence: str, form: str, infinitive: str) -> str:
    """Wrap the first occurrence of `form` in {{c1::form::infinitive}} cloze syntax."""
    # Infinitive may not contain ::
    safe_inf = infinitive.replace("::", ":")
    idx = sentence.find(form)
    if idx < 0:
        raise ValueError(f"form {form!r} not in sentence {sentence!r}")
    return sentence[:idx] + f"{{{{c1::{form}::{safe_inf}}}}}" + sentence[idx + len(form):]


# ─── Apply: migrate existing + add new ────────────────────────────────────────

def _existing_conjugation_nids() -> dict[str, int]:
    """Map of {form_string: note_id} for notes already in the Conjugation note type.

    Used so re-running --apply-notes doesn't create duplicates of forms that
    were already added in a prior run."""
    try:
        nids = ac("findNotes", query=f'"note:{NOTE_TYPE_NAME}"')
    except Exception:  # noqa: BLE001
        return {}
    if not nids:
        return {}
    info = ac("notesInfo", notes=nids)
    by_form: dict[str, int] = {}
    cloze_re = re.compile(r'\{\{c1::([^:}]+)(?:::[^}]+)?\}\}')
    for n in info:
        text = n["fields"].get("Text", {}).get("value", "")
        m = cloze_re.search(text)
        if m:
            by_form[m.group(1)] = n["noteId"]
    return by_form


def apply_notes(dry_run: bool) -> None:
    cache = load_cache()
    already_present = _existing_conjugation_nids() if not dry_run else {}
    migrations = []
    creations = []
    skipped_present = []
    missing = []
    for cf in ALL_FORMS:
        entry = cache.get(cf.form)
        if not entry or "error" in entry:
            missing.append(cf.form)
            continue
        try:
            cloze_text = build_cloze_text(entry["sentence_bangla"], cf.form, cf.infinitive)
        except ValueError as e:
            missing.append(f"{cf.form} ({e})")
            continue
        fields = {
            "Text": cloze_text,
            "English": entry["sentence_english"],
            "Tense": cf.tense,
            "Person": cf.person,
            "Register": cf.register,
            "Infinitive": cf.infinitive,
            "SentenceAudio": "",
        }
        if cf.existing_nid:
            migrations.append((cf.existing_nid, fields))
        elif cf.form in already_present:
            skipped_present.append(cf.form)
        else:
            creations.append({
                "deckName": DECK_NAME,
                "modelName": NOTE_TYPE_NAME,
                "fields": fields,
                "tags": ["conjugation::v1", f"verb::{cf.infinitive}"],
                "options": {"allowDuplicate": True},
            })

    print(f"Cached & ready: {len(migrations)} migrate + {len(creations)} create"
          + (f" ({len(skipped_present)} already in Anki, skipped)" if skipped_present else ""))
    if missing:
        print(f"Missing/errored ({len(missing)}): {missing}")

    if dry_run:
        print("(dry-run — passing --apply will run)")
        if migrations:
            n, f = migrations[0]
            print(f"\nSample migration:  nid={n}")
            print(f"  Text: {f['Text']}")
            print(f"  English: {f['English']}")
            print(f"  Tense/Person: {f['Tense']} · {f['Person']}")
        if creations:
            print(f"\nSample creation:")
            print(f"  Text: {creations[0]['fields']['Text']}")
            print(f"  English: {creations[0]['fields']['English']}")
        return

    # Migrate existing in batches
    for nid, fields in migrations:
        ac("updateNoteModel", note={
            "id": nid,
            "modelName": NOTE_TYPE_NAME,
            "fields": fields,
            "tags": ["conjugation::v1"],
        })
    print(f"Migrated {len(migrations)} notes via updateNoteModel.")

    # Move migrated cards to new deck
    nids = [n for n, _ in migrations]
    cids: list[int] = []
    for n in nids:
        cids.extend(ac("findCards", query=f"nid:{n}"))
    if cids:
        ac("changeDeck", cards=cids, deck=DECK_NAME)
        print(f"Moved {len(cids)} cards to {DECK_NAME}.")

    # Create new notes
    if creations:
        result = ac("addNotes", notes=creations)
        added = sum(1 for r in result if r is not None)
        print(f"Created {added}/{len(creations)} new notes.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fill", action="store_true")
    p.add_argument("--create-model", action="store_true")
    p.add_argument("--apply-notes", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-retries", type=int, default=4)
    p.add_argument("--apply", action="store_true", help="Actually mutate Anki for --create-model / --apply-notes.")
    args = p.parse_args()

    if not any([args.fill, args.create_model, args.apply_notes]):
        p.error("Specify at least one of --fill / --create-model / --apply-notes.")

    forms = ALL_FORMS if args.limit is None else ALL_FORMS[: args.limit]

    if args.fill:
        asyncio.run(run_fill(forms, args.model, args.max_retries))

    if args.create_model:
        create_model_and_deck(dry_run=not args.apply)

    if args.apply_notes:
        apply_notes(dry_run=not args.apply)


if __name__ == "__main__":
    main()
