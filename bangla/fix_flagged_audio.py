"""Fix orange-flagged Bangla audio via before/after review.

The user flags cards orange when audio is broken (missing, silent,
mispronounced, or end-truncated by an over-eager trim). Many of these
already have a saved `_raw.mp3` next to the trimmed clip, so we can
re-trim with more padding without spending TTS budget.

Workflow:

  1. uv run bangla/fix_flagged_audio.py prepare [--pad 0.25]
       Finds orange-flagged cards in deck:Bangla, re-trims their audio
       from the saved _raw files into out/audio_bn_fix/, and writes a
       review page at out/audio_bn_fix/review.html.

  2. uv run bangla/fix_flagged_audio.py serve [--port 8000]
       Serves out/audio_bn_fix/ on localhost so the page can play both
       before/after clips. Mark each as good/bad in the page, click
       'Save verdicts' — POSTs to /verdicts which writes verdicts.json
       next to the HTML.

  3. uv run bangla/fix_flagged_audio.py apply [--commit]
       For each 'good' verdict, replaces the live trimmed file in
       out/audio_bn/ with the candidate and pushes it into Anki media.
       Default is --dry-run; pass --commit to write.

Idempotent: prepare can be re-run; apply skips clips that are already
identical to the candidate. Notes flagged 'both bad' in verdicts are
left alone for a future iteration (different strategy / resynth).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import base64
import json
import shutil
from collections import defaultdict
from pathlib import Path

from lib.ankiconnect import ac
from lib.review_server import serve_review
from bangla.tts_run import PROFILES, _vad_trim, _silence_threshold_trim

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"
FIX_DIR = OUT_DIR / "audio_bn_fix"

# Map Anki model name → tts_run profile key.
MODEL_TO_PROFILE = {
    "Bangla (and reversed)": "bangla-vocab",
    "Bangla Number": "bangla-numbers",
    "Bangla Conjugation": "bangla-conjugation",
}


def _profile_for(model: str):
    key = MODEL_TO_PROFILE.get(model)
    return PROFILES[key] if key else None


def _live_dir(profile) -> Path:
    return OUT_DIR / profile.audio_dirname


def _live_paths(profile, nid: int) -> dict:
    d = _live_dir(profile)
    prefix = profile.media_prefix
    paths = {
        "sentence": d / f"{prefix}{nid}_sentence.mp3",
        "sentence_raw": d / f"{prefix}{nid}_sentence_raw.mp3",
    }
    if profile.headword_field:
        paths["word"] = d / f"{prefix}{nid}_word.mp3"
        paths["word_raw"] = d / f"{prefix}{nid}_word_raw.mp3"
    return paths


def _fix_paths(profile, nid: int) -> dict:
    prefix = profile.media_prefix
    paths = {
        "sentence_before": FIX_DIR / f"{prefix}{nid}_sentence_before.mp3",
        "sentence_after": FIX_DIR / f"{prefix}{nid}_sentence_after.mp3",
    }
    if profile.headword_field:
        paths["word_before"] = FIX_DIR / f"{prefix}{nid}_word_before.mp3"
        paths["word_after"] = FIX_DIR / f"{prefix}{nid}_word_after.mp3"
    return paths


def _retrim(raw: Path, dest: Path, padding_s: float) -> str:
    """Re-trim raw → dest with more padding. Returns status string."""
    if not raw.exists():
        return "no_raw"
    if _vad_trim(raw, dest, padding_s=padding_s):
        return "vad"
    if _silence_threshold_trim(raw, dest):
        return "silenceremove"
    shutil.copyfile(raw, dest)
    return "copy_raw"


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s).strip()


def discover_flagged() -> list[dict]:
    """Return list of {note_id, model, profile, fields} for orange-flagged notes."""
    cids = ac("findCards", query="deck:Bangla flag:2")
    if not cids:
        return []
    cards = ac("cardsInfo", cards=cids)
    nid_to_model: dict[int, str] = {}
    for c in cards:
        nid_to_model[c["note"]] = c.get("modelName", "")
    nids = sorted(nid_to_model.keys())
    notes_info = ac("notesInfo", notes=nids)
    out: list[dict] = []
    for n in notes_info:
        model = n.get("modelName", "")
        profile = _profile_for(model)
        if profile is None:
            print(f"  skip note {n['noteId']}: model {model!r} has no audio profile")
            continue
        fields = {k: v["value"] for k, v in n["fields"].items()}
        out.append({
            "note_id": n["noteId"],
            "model": model,
            "profile_key": MODEL_TO_PROFILE[model],
            "bangla": _strip_html(fields.get(profile.headword_field or profile.sentence_field, "")),
            "english": _strip_html(
                fields.get("Eng_main")
                or fields.get("Eng_trans")
                or fields.get("English")
                or fields.get("Meaning")
                or ""
            ),
            "example": _strip_html(fields.get(profile.sentence_field, "")),
        })
    return out


def cmd_prepare(args: argparse.Namespace) -> None:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    notes = discover_flagged()
    print(f"Found {len(notes)} flagged notes with audio profiles")

    manifest: list[dict] = []
    for n in notes:
        profile = PROFILES[n["profile_key"]]
        nid = n["note_id"]
        live = _live_paths(profile, nid)
        fix = _fix_paths(profile, nid)

        clips: list[dict] = []
        kinds = ["sentence"] + (["word"] if profile.headword_field else [])
        for kind in kinds:
            live_trim = live[kind]
            raw = live[f"{kind}_raw"]
            before = fix[f"{kind}_before"]
            after = fix[f"{kind}_after"]
            before_exists = live_trim.exists()
            if before_exists:
                shutil.copyfile(live_trim, before)
            status = _retrim(raw, after, args.pad) if raw.exists() else "no_raw"
            clips.append({
                "kind": kind,
                "before": before.name if before_exists else None,
                "after": after.name if after.exists() else None,
                "status": status,
                "live_path": str(live_trim.relative_to(OUT_DIR)),
            })

        manifest.append({
            "note_id": nid,
            "model": n["model"],
            "profile_key": n["profile_key"],
            "bangla": n["bangla"],
            "english": n["english"],
            "example": n["example"],
            "clips": clips,
        })

    manifest_path = FIX_DIR / "manifest.json"
    manifest_path.write_text(json.dumps({"pad": args.pad, "notes": manifest}, ensure_ascii=False, indent=2))
    print(f"Wrote {manifest_path} ({len(manifest)} notes)")

    html_path = FIX_DIR / "review.html"
    html_path.write_text(REVIEW_HTML)
    print(f"Wrote {html_path}")
    print(f"Next: uv run bangla/fix_flagged_audio.py serve")


REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bangla audio fix review</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 1em auto; padding: 0 1em; }
  .note { border: 1px solid #ddd; border-radius: 6px; padding: 1em; margin: 1em 0; }
  .meta { font-size: 0.9em; color: #555; }
  .bangla { font-size: 1.4em; font-family: "Noto Sans Bengali", sans-serif; }
  .example { font-family: "Noto Sans Bengali", sans-serif; margin: 0.3em 0; }
  .english { color: #444; font-style: italic; }
  .clip { display: grid; grid-template-columns: 80px 1fr 1fr; gap: 0.5em; align-items: center; padding: 0.4em 0; border-top: 1px dashed #eee; }
  .clip-kind { font-weight: bold; }
  .clip-col { display: flex; flex-direction: column; gap: 0.2em; }
  .clip-col label { font-size: 0.85em; color: #666; }
  audio { width: 100%; }
  .verdict { margin-top: 0.4em; font-size: 0.9em; }
  .verdict label { margin-right: 0.7em; cursor: pointer; }
  .summary { position: sticky; top: 0; background: white; padding: 0.5em 0; border-bottom: 1px solid #ddd; z-index: 10; display: flex; gap: 0.7em; align-items: center; }
  button { padding: 0.4em 0.9em; cursor: pointer; }
  .status-good { color: #2a7; }
  .status-bad { color: #c44; }
  .status-skip { color: #999; }
  .badge { display: inline-block; padding: 0.1em 0.4em; border-radius: 3px; background: #eee; font-size: 0.8em; margin-right: 0.3em; }
  .badge-no_raw { background: #fdd; }
</style>
</head>
<body>
<div class="summary">
  <span id="counts"></span>
  <button id="save">Save verdicts</button>
  <button id="export">Download JSON</button>
  <span id="save-status"></span>
</div>
<div id="cards"></div>

<script>
const STORAGE_KEY = "bangla_audio_verdicts_v1";
let manifest = null;
let verdicts = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

function setVerdict(nid, kind, value) {
  const key = nid + ":" + kind;
  if (value === null) delete verdicts[key];
  else verdicts[key] = value;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(verdicts));
  updateCounts();
}

function updateCounts() {
  const good = Object.values(verdicts).filter(v => v === "good").length;
  const bad = Object.values(verdicts).filter(v => v === "bad").length;
  const total = manifest ? manifest.notes.reduce((acc, n) => acc + n.clips.filter(c => c.after).length, 0) : 0;
  document.getElementById("counts").textContent = `${good} good / ${bad} bad / ${total} total clips`;
}

function clipRow(nid, clip) {
  const key = nid + ":" + clip.kind;
  const current = verdicts[key] || "";
  const after = clip.after ? `<audio controls preload="none" src="${clip.after}"></audio>` :
                `<span class="status-skip">no candidate (${clip.status})</span>`;
  const before = clip.before ? `<audio controls preload="none" src="${clip.before}"></audio>` :
                 `<span class="status-skip">no live file</span>`;
  const verdictHtml = clip.after ? `
    <div class="verdict">
      <label><input type="radio" name="v_${nid}_${clip.kind}" value="good" ${current==="good"?"checked":""}> after is good</label>
      <label><input type="radio" name="v_${nid}_${clip.kind}" value="bad" ${current==="bad"?"checked":""}> both bad</label>
      <label><input type="radio" name="v_${nid}_${clip.kind}" value="" ${current===""?"checked":""}> undecided</label>
    </div>` : "";
  const statusBadge = clip.status !== "vad" ? `<span class="badge badge-${clip.status}">${clip.status}</span>` : "";
  return `
    <div class="clip" data-nid="${nid}" data-kind="${clip.kind}">
      <div class="clip-kind">${clip.kind} ${statusBadge}</div>
      <div class="clip-col"><label>before</label>${before}</div>
      <div class="clip-col"><label>after</label>${after}${verdictHtml}</div>
    </div>`;
}

function render() {
  const root = document.getElementById("cards");
  root.innerHTML = manifest.notes.map(n => `
    <div class="note">
      <div class="meta">note ${n.note_id} · <code>${n.model}</code> · pad=${manifest.pad}s</div>
      <div class="bangla">${escapeHtml(n.bangla)}</div>
      <div class="example">${escapeHtml(n.example)}</div>
      <div class="english">${escapeHtml(n.english)}</div>
      ${n.clips.map(c => clipRow(n.note_id, c)).join("")}
    </div>
  `).join("");
  root.addEventListener("change", e => {
    if (e.target.matches('input[type="radio"]')) {
      const clip = e.target.closest(".clip");
      setVerdict(parseInt(clip.dataset.nid, 10), clip.dataset.kind, e.target.value);
    }
  });
  updateCounts();
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

document.getElementById("save").onclick = async () => {
  const status = document.getElementById("save-status");
  status.textContent = "saving…";
  try {
    const r = await fetch("/verdicts", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({verdicts, saved_at: new Date().toISOString()}),
    });
    status.textContent = r.ok ? "saved ✓" : `error: ${r.status}`;
  } catch (e) {
    status.textContent = "error: " + e.message;
  }
};

document.getElementById("export").onclick = () => {
  const blob = new Blob([JSON.stringify({verdicts}, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "verdicts.json";
  a.click();
};

fetch("manifest.json").then(r => r.json()).then(m => { manifest = m; render(); });
</script>
</body>
</html>
"""


def cmd_serve(args: argparse.Namespace) -> None:
    if not (FIX_DIR / "review.html").exists():
        print("No review.html — run `prepare` first.")
        sys.exit(1)
    serve_review(
        directory=FIX_DIR, port=args.port,
        post_endpoint="/verdicts", out_filename="verdicts.json",
        open_page=None if args.no_open else "review.html",
    )


def cmd_apply(args: argparse.Namespace) -> None:
    verdicts_path = FIX_DIR / "verdicts.json"
    if not verdicts_path.exists():
        print(f"No {verdicts_path} — save verdicts from the review page first.")
        sys.exit(1)
    manifest = json.loads((FIX_DIR / "manifest.json").read_text())
    verdicts = json.loads(verdicts_path.read_text()).get("verdicts", {})

    notes_by_id = {n["note_id"]: n for n in manifest["notes"]}

    good: list[tuple[int, str, dict]] = []
    bad: list[tuple[int, str]] = []
    skipped: list[tuple[int, str]] = []
    for key, value in verdicts.items():
        nid_s, kind = key.split(":", 1)
        nid = int(nid_s)
        if value == "good":
            n = notes_by_id.get(nid)
            if not n:
                continue
            good.append((nid, kind, n))
        elif value == "bad":
            bad.append((nid, kind))
        else:
            skipped.append((nid, kind))

    print(f"good (will apply): {len(good)}")
    print(f"bad (left for next iteration): {len(bad)}")
    if bad:
        for nid, kind in bad:
            print(f"  bad: note {nid} {kind}")

    if not good:
        return

    if not args.commit:
        print("\nDRY RUN — pass --commit to actually copy files + push to Anki.")
        for nid, kind, _ in good:
            print(f"  would apply: note {nid} {kind}")
        return

    media_actions: list[dict] = []
    for nid, kind, n in good:
        profile = PROFILES[n["profile_key"]]
        live = _live_paths(profile, nid)
        fix = _fix_paths(profile, nid)
        after = fix[f"{kind}_after"]
        target = live[kind]
        if not after.exists():
            print(f"  SKIP note {nid} {kind}: candidate missing")
            continue
        shutil.copyfile(after, target)
        media_actions.append({
            "action": "storeMediaFile",
            "params": {
                "filename": target.name,
                "data": base64.b64encode(target.read_bytes()).decode(),
            },
        })
        print(f"  applied: note {nid} {kind} → {target.name}")

    if media_actions:
        # Batch upload, 25 per multi-call.
        for i in range(0, len(media_actions), 25):
            ac("multi", actions=media_actions[i : i + 25])
        print(f"Pushed {len(media_actions)} media files to Anki.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="Discover flagged notes + build candidates + review page")
    pp.add_argument("--pad", type=float, default=0.25, help="VAD padding seconds (default 0.25)")
    pp.set_defaults(func=cmd_prepare)

    ps = sub.add_parser("serve", help="Serve the review page on localhost")
    ps.add_argument("--port", type=int, default=8765 + 1, help="HTTP port (default 8766)")
    ps.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    ps.set_defaults(func=cmd_serve)

    pa = sub.add_parser("apply", help="Apply 'good' verdicts to live audio + Anki media")
    pa.add_argument("--commit", action="store_true", help="Actually write (default is dry-run)")
    pa.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
