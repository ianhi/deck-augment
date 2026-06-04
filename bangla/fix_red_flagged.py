"""Fix red-flagged Bangla cards via Gemini-proposed edits + review.

Red flags mark text-quality issues — typos in the headword, full
sentences sitting in the headword field, examples that use a different
form of the word, fragmentary examples, etc. We pull each flagged note,
ask Gemini to diagnose and propose a minimal fix, then present a
side-by-side edit page (current vs. proposed). On apply, accepted edits
are pushed to Anki via updateNoteFields and any change to the audio
source fields (Bangla / Example) invalidates the on-disk audio so the
next `tts_run` regenerates from the fresh text.

Workflow:

  1. uv run bangla/fix_red_flagged.py prepare
       Pulls red-flagged notes, calls Gemini once per note, writes
       out/red_fix/manifest.json + edit.html.

  2. uv run bangla/fix_red_flagged.py serve
       Localhost server. The page lets you edit any suggested field
       before accepting. Save → POSTs verdicts to /edits.

  3. uv run bangla/fix_red_flagged.py apply [--commit]
       For each accepted note, updateNoteFields via AnkiConnect and
       (if Bangla/Example changed) delete the live + raw audio files
       so the next `tts_run` regenerates. Default is dry-run.
       Afterwards: `uv run bangla/tts_run.py --profile bangla-vocab`
       to regenerate audio, then `--apply` to push it.

Scope: handles `Bangla (and reversed)` notes. Cloze-type red flags
(Bangla Conjugation / Bangla Enhanced Cloze) are listed for manual
inspection but skipped by the Gemini pass — their fields are more
complex and warrant a separate prompt.
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
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from lib.ankiconnect import ac
from lib.review_server import serve_review
from bangla.tts_run import PROFILES

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
FIX_DIR = OUT_DIR / "red_fix"

DEFAULT_MODEL = "gemini-2.5-pro"

STRIP = re.compile(r"<[^>]+>")

SUPPORTED_MODEL = "Bangla (and reversed)"

SYSTEM_PROMPT = """\
You are cleaning up a Kolkata Bengali vocabulary deck. Each entry has:
  - Bangla: a headword (should be a single word or short fixed expression)
  - Eng_trans: English gloss of the headword
  - Example: a Bengali example sentence (4–8 words, natural, Kolkata register)
  - ExampleTranslation: English translation of the example

A reviewer flagged the entry as wrong. Diagnose the problem and propose a
MINIMAL fix. Common failure modes:

  1. Bangla field contains a full sentence rather than a single headword.
     -> Pick the headword (the focus word the example illustrates) and use
        that. Adjust Eng_trans if needed.
  2. Bangla has a typo (e.g. জয়ার should be জোয়ার for "tide").
     -> Fix the spelling. Example may already be correct.
  3. Example uses a completely different form / different verb than the
     headword (e.g. headword "ঘুমাক" but example "ঘুমাও").
     -> Rewrite Example so it uses the headword (citation form or a
        natural inflection of it). Keep it 4–8 words, Kolkata register,
        natural, grammatical. Update ExampleTranslation to match.
  4. Example is a fragment, not a complete sentence.
     -> Rewrite into a complete short sentence using the headword.
  5. Example sentence reads like a translated English template, drifts
     off-topic, or references unrelated material (e.g. Mahabharata when
     the headword is a generic adjective).
     -> Rewrite into a natural everyday Kolkata Bengali sentence using
        the headword.

Use Kolkata (West Bengal, India) Bengali, casual everyday register (চলিত
ভাষা). Avoid Bangladeshi-marked vocabulary. The example must be
grammatical and naturally spoken.

Return JSON with this shape:

{
  "diagnosis": "<one short sentence describing what's wrong>",
  "fix": {
    // include ONLY fields you are changing; omit fields that should stay as-is
    "Bangla": "<new headword>",
    "Eng_trans": "<new gloss>",
    "Example": "<new sentence>",
    "ExampleTranslation": "<new translation>"
  },
  "confidence": "high" | "medium" | "low",
  "notes": "<optional short note for the human reviewer>"
}

If you cannot diagnose the problem, set fix={} and confidence="low" with a
notes field explaining what to check.
"""


def discover_red_flagged() -> tuple[list[dict], list[dict]]:
    """Return (supported_notes, skipped_notes). Supported = `Bangla (and reversed)`."""
    cids = ac("findCards", query="deck:Bangla flag:1")
    if not cids:
        return [], []
    cards = ac("cardsInfo", cards=cids)
    nid_to_model: dict[int, str] = {}
    for c in cards:
        nid_to_model[c["note"]] = c.get("modelName", "")
    nids = sorted(nid_to_model.keys())
    notes_info = ac("notesInfo", notes=nids)
    supported, skipped = [], []
    for n in notes_info:
        if n.get("modelName") == SUPPORTED_MODEL:
            supported.append(n)
        else:
            skipped.append(n)
    return supported, skipped


def extract_fields(note: dict) -> dict:
    f = {k: v["value"] for k, v in note["fields"].items()}
    return {
        "Bangla": STRIP.sub("", f.get("Bangla", "")).strip(),
        "Eng_trans": f.get("Eng_trans", "").strip(),
        "Example": STRIP.sub("", f.get("Example", "")).strip(),
        "ExampleTranslation": f.get("ExampleTranslation", "").strip(),
    }


async def diagnose_one(client: genai.Client, model_name: str, note: dict, sem: asyncio.Semaphore) -> dict:
    fields = extract_fields(note)
    user_prompt = (
        f"Note id: {note['noteId']}\n"
        f"Bangla: {fields['Bangla']}\n"
        f"Eng_trans: {fields['Eng_trans']}\n"
        f"Example: {fields['Example']}\n"
        f"ExampleTranslation: {fields['ExampleTranslation']}\n"
    )
    async with sem:
        try:
            r = await client.aio.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )
        except genai_errors.APIError as e:
            return {"note_id": note["noteId"], "error": f"api: {e}", "current": fields}
    try:
        payload = json.JSONDecoder().raw_decode(r.text.lstrip())[0]
    except (ValueError, json.JSONDecodeError) as e:
        return {"note_id": note["noteId"], "error": f"json: {e}", "current": fields, "raw": r.text[:400]}
    return {
        "note_id": note["noteId"],
        "current": fields,
        "diagnosis": payload.get("diagnosis", ""),
        "fix": payload.get("fix", {}) or {},
        "confidence": payload.get("confidence", ""),
        "notes": payload.get("notes", ""),
    }


async def diagnose_all(notes: list[dict], model_name: str, concurrency: int) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    client = genai.Client(api_key=api_key)
    sem = asyncio.Semaphore(concurrency)
    print(f"Calling Gemini ({model_name}) for {len(notes)} notes…")
    tasks = [diagnose_one(client, model_name, n, sem) for n in notes]
    results: list[dict] = []
    for i, fut in enumerate(asyncio.as_completed(tasks), 1):
        r = await fut
        results.append(r)
        nid = r["note_id"]
        if "error" in r:
            print(f"  [{i}/{len(notes)}] {nid}: ERROR {r['error']}")
        else:
            keys = ", ".join(r["fix"].keys()) or "no changes"
            print(f"  [{i}/{len(notes)}] {nid}: {r['confidence']} — {keys}")
    return sorted(results, key=lambda r: r["note_id"])


def cmd_prepare(args: argparse.Namespace) -> None:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    supported, skipped = discover_red_flagged()
    print(f"red-flagged: {len(supported)} supported + {len(skipped)} cloze/other (skipped)")
    for n in skipped:
        print(f"  manual: {n['noteId']} ({n['modelName']})")

    results = asyncio.run(diagnose_all(supported, args.model, args.concurrency))

    manifest = {
        "model": args.model,
        "supported_count": len(supported),
        "skipped": [{"note_id": n["noteId"], "model": n["modelName"]} for n in skipped],
        "items": results,
    }
    (FIX_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    (FIX_DIR / "edit.html").write_text(EDIT_HTML)
    print(f"Wrote {FIX_DIR / 'manifest.json'} + edit.html")
    print(f"Next: uv run bangla/fix_red_flagged.py serve")


EDIT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bangla red-flag fixes</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 1em auto; padding: 0 1em; }
  .summary { position: sticky; top: 0; background: white; padding: 0.6em 0; border-bottom: 1px solid #ddd; z-index: 10; display: flex; gap: 1em; align-items: center; }
  .item { border: 1px solid #ddd; border-radius: 6px; padding: 0.9em; margin: 1em 0; }
  .meta { font-size: 0.85em; color: #555; margin-bottom: 0.4em; }
  .diagnosis { background: #fff7e0; padding: 0.5em 0.7em; border-left: 3px solid #e0a020; border-radius: 3px; margin: 0.4em 0; }
  .notes { color: #555; font-size: 0.9em; margin-top: 0.3em; }
  .fields { display: grid; grid-template-columns: 130px 1fr 1fr; gap: 0.5em; align-items: start; margin: 0.5em 0; }
  .fields .h { font-weight: bold; color: #777; font-size: 0.85em; padding-top: 0.4em; }
  .fields .h2 { font-weight: bold; color: #444; font-size: 0.85em; padding-top: 0.4em; }
  .fields textarea, .fields .cur { font-family: "Noto Sans Bengali", system-ui, sans-serif; font-size: 1em; padding: 0.4em; border: 1px solid #ccc; border-radius: 3px; width: 100%; box-sizing: border-box; resize: vertical; min-height: 2.2em; }
  .fields .cur { background: #fafafa; color: #444; }
  .fields .changed textarea { border-color: #2a7; background: #f3fbf5; }
  .verdict { margin-top: 0.5em; }
  .verdict label { margin-right: 0.8em; cursor: pointer; }
  button { padding: 0.45em 1em; cursor: pointer; }
  .conf-high { color: #2a7; }
  .conf-medium { color: #c70; }
  .conf-low { color: #c44; }
  .skipped { background: #f6f6f6; padding: 0.8em; border-radius: 4px; margin: 1em 0; }
</style>
</head>
<body>
<div class="summary">
  <span id="counts"></span>
  <button id="save">Save edits</button>
  <button id="export">Download JSON</button>
  <span id="save-status"></span>
</div>

<div id="items"></div>
<div id="skipped"></div>

<script>
const STORAGE_KEY = "bangla_red_edits_v1";
let manifest = null;
let edits = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

const FIELD_ORDER = ["Bangla", "Eng_trans", "Example", "ExampleTranslation"];

function setEdit(nid, patch) {
  edits[nid] = { ...(edits[nid] || {}), ...patch };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(edits));
  updateCounts();
}

function updateCounts() {
  const decisions = Object.values(edits);
  const accept = decisions.filter(d => d.verdict === "accept").length;
  const reject = decisions.filter(d => d.verdict === "reject").length;
  const total = manifest ? manifest.items.length : 0;
  document.getElementById("counts").textContent = `${accept} accept / ${reject} reject / ${total} total`;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

function itemRow(item) {
  const nid = item.note_id;
  const cur = item.current || {};
  const fix = item.fix || {};
  const saved = edits[nid] || {};
  const savedValues = saved.values || {};
  const verdict = saved.verdict || "";
  const confClass = `conf-${(item.confidence || "low").toLowerCase()}`;

  const rows = FIELD_ORDER.map(f => {
    const c = cur[f] || "";
    const proposed = (f in fix) ? fix[f] : c;
    const value = (f in savedValues) ? savedValues[f] : proposed;
    const changed = (proposed !== c) ? " changed" : "";
    return `
      <div class="h">${f}</div>
      <div class="cur" data-cur>${escapeHtml(c)}</div>
      <div class="cell${changed}"><textarea data-nid="${nid}" data-field="${f}" rows="1">${escapeHtml(value)}</textarea></div>
    `;
  }).join("");

  const err = item.error ? `<div class="diagnosis">ERROR: ${escapeHtml(item.error)}</div>` : "";

  return `
    <div class="item" data-nid="${nid}">
      <div class="meta">note <a href="anki:note?id=${nid}" target="_blank">${nid}</a> · confidence: <span class="${confClass}">${item.confidence || "?"}</span></div>
      ${err}
      ${item.diagnosis ? `<div class="diagnosis">${escapeHtml(item.diagnosis)}</div>` : ""}
      <div class="fields">
        <div class="h"></div><div class="h2">current</div><div class="h2">edit (proposed pre-filled)</div>
        ${rows}
      </div>
      ${item.notes ? `<div class="notes">${escapeHtml(item.notes)}</div>` : ""}
      <div class="verdict">
        <label><input type="radio" name="v_${nid}" value="accept" ${verdict==="accept"?"checked":""}> accept edits above</label>
        <label><input type="radio" name="v_${nid}" value="reject" ${verdict==="reject"?"checked":""}> reject (leave as-is)</label>
        <label><input type="radio" name="v_${nid}" value="" ${verdict===""?"checked":""}> undecided</label>
      </div>
    </div>`;
}

function render() {
  document.getElementById("items").innerHTML = manifest.items.map(itemRow).join("");

  const skipped = (manifest.skipped || []);
  if (skipped.length) {
    document.getElementById("skipped").innerHTML = `
      <div class="skipped">
        <strong>Cloze-type notes skipped by Gemini pass (fix in Anki by hand):</strong>
        <ul>${skipped.map(s => `<li><a href="anki:note?id=${s.note_id}" target="_blank">${s.note_id}</a> · ${escapeHtml(s.model)}</li>`).join("")}</ul>
      </div>`;
  }

  document.body.addEventListener("change", e => {
    if (e.target.matches('input[type="radio"][name^="v_"]')) {
      const nid = parseInt(e.target.name.slice(2), 10);
      setEdit(nid, {verdict: e.target.value});
    } else if (e.target.matches("textarea[data-nid]")) {
      const nid = parseInt(e.target.dataset.nid, 10);
      const field = e.target.dataset.field;
      const prev = edits[nid] || {};
      const values = { ...(prev.values || {}), [field]: e.target.value };
      setEdit(nid, {values});
    }
  });
  // auto-resize textareas
  document.body.addEventListener("input", e => {
    if (e.target.matches("textarea")) {
      e.target.style.height = "auto";
      e.target.style.height = e.target.scrollHeight + "px";
    }
  });
  document.querySelectorAll("textarea").forEach(t => {
    t.style.height = "auto";
    t.style.height = t.scrollHeight + "px";
  });
  updateCounts();
}

document.getElementById("save").onclick = async () => {
  const status = document.getElementById("save-status");
  status.textContent = "saving…";
  try {
    const r = await fetch("/edits", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({edits, saved_at: new Date().toISOString()}),
    });
    status.textContent = r.ok ? "saved ✓" : `error: ${r.status}`;
  } catch (e) {
    status.textContent = "error: " + e.message;
  }
};

document.getElementById("export").onclick = () => {
  const blob = new Blob([JSON.stringify({edits}, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "edits.json";
  a.click();
};

fetch("manifest.json").then(r => r.json()).then(m => { manifest = m; render(); });
</script>
</body>
</html>
"""


def cmd_serve(args: argparse.Namespace) -> None:
    if not (FIX_DIR / "edit.html").exists():
        print("No edit.html — run `prepare` first.")
        sys.exit(1)
    serve_review(
        directory=FIX_DIR, port=args.port,
        post_endpoint="/edits", out_filename="edits.json",
        open_page=None if args.no_open else "edit.html",
    )


def _invalidate_audio_for(nid: int, profile_name: str = "bangla-vocab") -> list[Path]:
    """Delete trimmed + raw audio files for a note so tts_run regenerates."""
    profile = PROFILES[profile_name]
    audio_dir = OUT_DIR / profile.audio_dirname
    prefix = profile.media_prefix
    targets = [
        audio_dir / f"{prefix}{nid}_word.mp3",
        audio_dir / f"{prefix}{nid}_word_raw.mp3",
        audio_dir / f"{prefix}{nid}_sentence.mp3",
        audio_dir / f"{prefix}{nid}_sentence_raw.mp3",
    ]
    removed = [p for p in targets if p.exists()]
    for p in removed:
        p.unlink()
    return removed


def cmd_apply(args: argparse.Namespace) -> None:
    edits_path = FIX_DIR / "edits.json"
    if not edits_path.exists():
        print(f"No {edits_path} — save edits from the review page first.")
        sys.exit(1)
    manifest = json.loads((FIX_DIR / "manifest.json").read_text())
    saved = json.loads(edits_path.read_text()).get("edits", {})
    items_by_id = {i["note_id"]: i for i in manifest["items"]}

    accepted: list[tuple[int, dict]] = []
    for nid_s, state in saved.items():
        if state.get("verdict") != "accept":
            continue
        nid = int(nid_s)
        item = items_by_id.get(nid)
        if not item:
            continue
        cur = item.get("current", {})
        # Effective edits = textarea values that differ from current.
        values = state.get("values") or {}
        changes = {f: v for f, v in values.items() if v.strip() != cur.get(f, "").strip()}
        if not changes:
            print(f"  note {nid}: accepted but no field changed — skip")
            continue
        accepted.append((nid, changes))

    rejected = sum(1 for s in saved.values() if s.get("verdict") == "reject")
    print(f"accept: {len(accepted)}  reject: {rejected}  total saved: {len(saved)}")

    if not accepted:
        return

    for nid, changes in accepted:
        keys = ", ".join(changes.keys())
        print(f"  note {nid}: change {keys}")

    if not args.commit:
        print("\nDRY RUN — pass --commit to write to Anki + invalidate audio.")
        return

    # Wrap field values back in <b>...</b> for Example only if the original
    # had bolding and the new value contains the headword (best-effort).
    actions: list[dict] = []
    audio_invalidations: list[int] = []
    for nid, changes in accepted:
        item = items_by_id[nid]
        cur = item["current"]
        # Re-wrap headword bolding in Example if the original was bolded.
        final = dict(changes)
        if "Example" in final:
            # Determine headword to bold: the (possibly new) Bangla value.
            hw = final.get("Bangla") or cur.get("Bangla") or ""
            hw = hw.strip()
            if hw and hw in final["Example"]:
                final["Example"] = final["Example"].replace(hw, f"<b>{hw}</b>", 1)
        actions.append({
            "action": "updateNoteFields",
            "params": {"note": {"id": nid, "fields": final}},
        })
        if "Bangla" in changes or "Example" in changes:
            audio_invalidations.append(nid)

    for i in range(0, len(actions), 25):
        ac("multi", actions=actions[i : i + 25])
    print(f"Pushed {len(actions)} updateNoteFields to Anki.")

    if audio_invalidations:
        print(f"Invalidating audio for {len(audio_invalidations)} notes (Bangla/Example changed):")
        total_removed = 0
        for nid in audio_invalidations:
            removed = _invalidate_audio_for(nid)
            total_removed += len(removed)
            print(f"  note {nid}: removed {len(removed)} file(s)")
        print(f"Removed {total_removed} audio files total.")
        print("Now run:")
        print("  uv run bangla/tts_run.py --profile bangla-vocab")
        print("  uv run bangla/tts_run.py --profile bangla-vocab --apply")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="Pull red-flagged + call Gemini + build edit page")
    pp.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default {DEFAULT_MODEL})")
    pp.add_argument("--concurrency", type=int, default=4, help="Concurrent Gemini calls")
    pp.set_defaults(func=cmd_prepare)

    ps = sub.add_parser("serve", help="Serve the edit page on localhost")
    ps.add_argument("--port", type=int, default=8767, help="HTTP port (default 8767)")
    ps.add_argument("--no-open", action="store_true")
    ps.set_defaults(func=cmd_serve)

    pa = sub.add_parser("apply", help="Push accepted edits to Anki + invalidate audio")
    pa.add_argument("--commit", action="store_true", help="Actually write (default dry-run)")
    pa.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
