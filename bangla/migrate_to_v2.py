"""In-place migration of the `Bangla (and reversed)` note type to the new
v2 design (Recognition / Production / Listening templates with EnableX gates).

This is an IN-PLACE update of the existing model so all 2279 notes keep
their card ids and review history. The model name stays
`Bangla (and reversed)` (AnkiConnect doesn't expose model renaming).

Operations performed (in order, each idempotent):

  1. Snapshot the current model state (fields, templates, CSS) to
     `backups/model-bangla-and-reversed-<timestamp>.json` so the migration
     is fully reversible.
  2. Rename fields:
        `example sentence` → `Example`
        `sentence-trans`   → `ExampleTranslation`
        `image`            → `Image`
     (Field rename preserves data on every note.)
  3. Add new fields (skip if already present):
        `WordAudio`, `ExampleAudio`, `Notes`,
        `EnableRecognition`, `EnableProduction`, `EnableListening`.
     Existing fields `bangla-def`, `eng-disambig`, `type`, `explanation`,
     `bangla-disambig` are LEFT IN PLACE so no data is lost. They simply
     stop being referenced by the templates.
  4. Rename templates:
        `Card 1` → `Recognition`
        `Card 2` → `Production`
        `Card 3` → `Listening`   (handles the bidi-isolate marks in the
                                  source template name)
  5. Replace template HTML and CSS with the v2 design.
  6. Bulk-update every note:
        - `EnableRecognition` = "1"
        - `EnableProduction`  = "1"
        - `EnableListening`   = "1"
        - Copy `explanation` → `Notes` where `Notes` is empty and
          `explanation` is non-empty.

Run `--dry-run` (default) to print the plan and detect drift. Pass
`--apply` to execute. Schema-bumping operations (createModel-class
changes) force one-way sync — acknowledge by re-running with `--yes`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import datetime as dt
import json
import re
from pathlib import Path

from lib.ankiconnect import ac

BIDI_RE = re.compile(r"[\u2066-\u2069\u200e\u200f\u202a-\u202e\u200b-\u200d\ufeff]")

MODEL = "Bangla (and reversed)"

FIELD_RENAMES: list[tuple[str, str]] = [
    ("example sentence", "Example"),
    ("sentence-trans", "ExampleTranslation"),
    ("image", "Image"),
]

# Order matters only for the editor's display; AnkiConnect appends.
NEW_FIELDS: list[str] = [
    "WordAudio",
    "ExampleAudio",
    "Notes",
    "EnableRecognition",
    "EnableProduction",
    "EnableListening",
]

# Template name renames, applied AFTER any prior partial migration so it's
# safe to re-run.
TEMPLATE_RENAMES: list[tuple[str, str]] = [
    ("Card 1", "Recognition"),
    ("Card 2", "Production"),
    ("Card \u20683\u2069", "Listening"),  # bidi-isolated "3"
    # Fallbacks in case the bidi name was already normalised on disk:
    ("Card 3", "Listening"),
]

BACKUP_DIR = Path(__file__).resolve().parents[1] / "backups"


# ---------- Template HTML (mirrors create_bangla_v2_test.py) ---------------

SENTENCE_AUDIO = (
    "{{#ExampleAudio}}{{ExampleAudio}}{{/ExampleAudio}}"
    "{{^ExampleAudio}}{{#Example}}[anki:tts lang=bn_IN]{{Example}}[/anki:tts]{{/Example}}{{/ExampleAudio}}"
)
WORD_AUDIO = (
    "{{#WordAudio}}{{WordAudio}}{{/WordAudio}}"
    "{{^WordAudio}}[anki:tts lang=bn_IN]{{Bangla}}[/anki:tts]{{/WordAudio}}"
)
NOTES_BLOCK = '{{#Notes}}<div class="notes">{{Notes}}</div>{{/Notes}}'

RECOGNITION_FRONT = """\
{{#EnableRecognition}}
<div class="headword">{{Bangla}}</div>
{{#Example}}<div class="sentence">{{Example}}</div>{{/Example}}
<div class="audio-row">&nbsp;</div>
{{/EnableRecognition}}
"""

RECOGNITION_BACK = f"""\
{{{{#EnableRecognition}}}}
<div class="headword">{{{{Bangla}}}}</div>
{{{{#Example}}}}<div class="sentence">{{{{Example}}}}</div>{{{{/Example}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
<hr id=answer>
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence-translation">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
{NOTES_BLOCK}
{{{{/EnableRecognition}}}}
"""

PRODUCTION_FRONT = """\
{{#EnableProduction}}
<div class="definition">{{Eng_trans}}</div>
{{#ExampleTranslation}}<div class="sentence">{{ExampleTranslation}}</div>{{/ExampleTranslation}}
{{#Image}}<div class="image">{{Image}}</div>{{/Image}}
<div class="audio-row">&nbsp;</div>
{{/EnableProduction}}
"""

PRODUCTION_BACK = f"""\
{{{{#EnableProduction}}}}
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
<hr id=answer>
<div class="headword">{{{{Bangla}}}}</div>
{{{{#Example}}}}<div class="sentence">{{{{Example}}}}</div>{{{{/Example}}}}
{NOTES_BLOCK}
{{{{/EnableProduction}}}}
"""

LISTENING_FRONT = f"""\
{{{{#EnableListening}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
{{{{#Example}}}}<div class="sentence-hint">{{{{hint:Example}}}}</div>{{{{/Example}}}}
{{{{/EnableListening}}}}
"""

LISTENING_BACK = f"""\
{{{{#EnableListening}}}}
<div class="audio-row">{SENTENCE_AUDIO}{WORD_AUDIO}</div>
{{{{#Example}}}}<div class="sentence-hint">{{{{Example}}}}</div>{{{{/Example}}}}
<hr id=answer>
<div class="headword">{{{{Bangla}}}}</div>
<div class="definition">{{{{Eng_trans}}}}</div>
{{{{#ExampleTranslation}}}}<div class="sentence-translation">{{{{ExampleTranslation}}}}</div>{{{{/ExampleTranslation}}}}
{{{{#Image}}}}<div class="image">{{{{Image}}}}</div>{{{{/Image}}}}
{NOTES_BLOCK}
{{{{/EnableListening}}}}
"""

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

.sentence {
  font-size: 26px;
  margin: 16px auto;
  max-width: 32em;
  line-height: 1.4;
}
.sentence-translation {
  font-size: 18px;
  color: #6a6a6a;
  margin: 6px auto;
}

.definition { font-size: 22px; margin: 10px 0; }
.image img { max-height: 240px; max-width: 90%; }

.audio-row {
  min-height: 36px;
  margin: 10px 0;
}

.sentence-hint {
  margin: 16px auto;
  max-width: 32em;
  font-size: 22px;
}
.sentence-hint a { color: #5586cd; text-decoration: none; }

.notes {
  font-size: 15px;
  color: #777;
  font-style: italic;
  margin: 10px auto;
  max-width: 32em;
  text-align: center;
}

hr#answer { margin: 18px 0; }
"""

NEW_TEMPLATE_HTML: dict[str, dict[str, str]] = {
    "Recognition": {"Front": RECOGNITION_FRONT, "Back": RECOGNITION_BACK},
    "Production": {"Front": PRODUCTION_FRONT, "Back": PRODUCTION_BACK},
    "Listening": {"Front": LISTENING_FRONT, "Back": LISTENING_BACK},
}


# ---------- Helpers --------------------------------------------------------

def snapshot_model(apply: bool) -> Path | None:
    """Write current model state to backups/. Returns the path."""
    state = {
        "model": MODEL,
        "fields": ac("modelFieldNames", modelName=MODEL),
        "templates": ac("modelTemplates", modelName=MODEL),
        "css": ac("modelStyling", modelName=MODEL)["css"],
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
    }
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = BACKUP_DIR / f"model-bangla-and-reversed-{ts}.json"
    if apply:
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        print(f"  snapshot → {path}")
    else:
        print(f"  snapshot would be written → {path}")
    return path


def step_rename_fields(apply: bool) -> None:
    current = ac("modelFieldNames", modelName=MODEL)
    print("=> Field renames")
    for old, new in FIELD_RENAMES:
        if old in current and new not in current:
            print(f"  rename {old!r} → {new!r}")
            if apply:
                ac("modelFieldRename", modelName=MODEL, oldFieldName=old, newFieldName=new)
        elif new in current and old not in current:
            print(f"  skip   {old!r} → {new!r}  (already renamed)")
        elif old in current and new in current:
            print(f"  WARN   both {old!r} and {new!r} exist — manual merge needed")
        else:
            print(f"  skip   {old!r} → {new!r}  (neither field present?)")


def step_add_fields(apply: bool) -> None:
    current = ac("modelFieldNames", modelName=MODEL)
    print("=> New fields")
    for f in NEW_FIELDS:
        if f in current:
            print(f"  skip   add {f!r}  (already present)")
            continue
        print(f"  add    {f!r}")
        if apply:
            ac("modelFieldAdd", modelName=MODEL, fieldName=f, index=len(current))
            current = current + [f]


def step_rename_templates(apply: bool) -> None:
    current = ac("modelTemplates", modelName=MODEL)
    print("=> Template renames")
    for old, new in TEMPLATE_RENAMES:
        if old in current and new not in current:
            print(f"  rename {old!r} → {new!r}")
            if apply:
                ac(
                    "modelTemplateRename",
                    modelName=MODEL,
                    oldTemplateName=old,
                    newTemplateName=new,
                )
                current = ac("modelTemplates", modelName=MODEL)
        elif new in current:
            pass  # already renamed by an earlier alias
    final = ac("modelTemplates", modelName=MODEL) if apply else current
    print(f"  templates now: {list(final.keys())}")


def step_update_templates(apply: bool) -> None:
    print("=> Template HTML")
    current = ac("modelTemplates", modelName=MODEL)
    missing = [n for n in NEW_TEMPLATE_HTML if n not in current]
    if apply and missing:
        raise SystemExit(
            f"ABORT: expected templates {list(NEW_TEMPLATE_HTML)} missing: {missing}.\n"
            f"Current: {list(current)}"
        )
    if apply:
        ac(
            "updateModelTemplates",
            model={"name": MODEL, "templates": NEW_TEMPLATE_HTML},
        )
        print("  updated 3 templates")
    else:
        if missing:
            print(f"  (after renames) would update 3 templates: {list(NEW_TEMPLATE_HTML)}")
        else:
            print("  would update 3 templates (Recognition / Production / Listening)")


def step_update_css(apply: bool) -> None:
    print("=> CSS")
    if apply:
        ac("updateModelStyling", model={"name": MODEL, "css": CSS})
        print(f"  updated CSS ({len(CSS)} chars)")
    else:
        print(f"  would update CSS ({len(CSS)} chars)")


def step_strip_bidi(apply: bool) -> None:
    """Remove invisible bidi isolate / zero-width chars from all field values."""
    print("=> Strip bidi / zero-width chars from note fields")
    nids = ac("findNotes", query=f'"note:{MODEL}"')
    changes: list[tuple[int, dict[str, str]]] = []
    for i in range(0, len(nids), 500):
        for n in ac("notesInfo", notes=nids[i : i + 500]):
            cleaned: dict[str, str] = {}
            for fname, fval in n["fields"].items():
                v = fval["value"]
                if BIDI_RE.search(v):
                    cleaned[fname] = BIDI_RE.sub("", v)
            if cleaned:
                changes.append((n["noteId"], cleaned))
    print(f"  {len(changes)} notes affected")
    if apply:
        for nid, cleaned in changes:
            ac("updateNoteFields", note={"id": nid, "fields": cleaned})
        print(f"  cleaned {len(changes)} notes")


def step_bulk_update_notes(apply: bool) -> None:
    """Set EnableX=1 on every note; copy `explanation` → `Notes` where applicable."""
    print("=> Bulk note updates")
    nids = ac("findNotes", query=f'"note:{MODEL}"')
    print(f"  {len(nids)} notes")
    if not nids:
        return

    fields = ac("modelFieldNames", modelName=MODEL)
    has_explanation = "explanation" in fields
    has_notes = "Notes" in fields

    # Fetch in chunks to avoid huge payloads.
    enabled_payload = {
        "EnableRecognition": "1",
        "EnableProduction": "1",
        "EnableListening": "1",
    }
    explanation_copies = 0
    chunk = 500
    for i in range(0, len(nids), chunk):
        batch = nids[i : i + chunk]
        infos = ac("notesInfo", notes=batch)
        for n in infos:
            new_fields = dict(enabled_payload)
            if has_explanation and has_notes:
                expl = n["fields"]["explanation"]["value"].strip()
                notes_val = n["fields"]["Notes"]["value"].strip()
                if expl and not notes_val:
                    new_fields["Notes"] = expl
                    explanation_copies += 1
            if apply:
                ac(
                    "updateNoteFields",
                    note={"id": n["noteId"], "fields": new_fields},
                )
        print(f"  processed {min(i + chunk, len(nids))}/{len(nids)}")
    print(
        f"  EnableX set on {len(nids)} notes; "
        f"explanation → Notes copied for {explanation_copies}"
    )


def preflight() -> None:
    print("=> Pre-flight checks")
    if MODEL not in ac("modelNames"):
        raise SystemExit(f"ABORT: model {MODEL!r} not found.")
    note_count = len(ac("findNotes", query=f'"note:{MODEL}"'))
    print(f"  model exists, {note_count} notes")
    cur_fields = ac("modelFieldNames", modelName=MODEL)
    print(f"  current fields ({len(cur_fields)}): {cur_fields}")
    cur_tmpls = list(ac("modelTemplates", modelName=MODEL).keys())
    print(f"  current templates ({len(cur_tmpls)}): {cur_tmpls}")
    backups = sorted(BACKUP_DIR.glob("collection-pre-bangla-migration-*.anki2"))
    if not backups:
        raise SystemExit(
            "ABORT: no collection backup in backups/. Create one before migrating."
        )
    print(f"  collection backup present: {backups[-1].name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Execute (default: dry-run).")
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge schema-bumping and one-way-sync warning.",
    )
    args = ap.parse_args()

    if args.apply and not args.yes:
        raise SystemExit(
            "Refusing to --apply without --yes. This migration bumps the\n"
            "collection schema (one-way sync) and modifies a note type used\n"
            "by 2279 notes. Re-run with --apply --yes to proceed."
        )

    preflight()
    snapshot_model(args.apply)
    step_rename_fields(args.apply)
    step_add_fields(args.apply)
    step_rename_templates(args.apply)
    step_update_templates(args.apply)
    step_update_css(args.apply)
    step_strip_bidi(args.apply)
    step_bulk_update_notes(args.apply)

    if not args.apply:
        print("\nDRY RUN — pass --apply --yes to execute.")
    else:
        print("\nDONE.")


if __name__ == "__main__":
    main()
