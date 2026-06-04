# ruff: noqa: E501  -- embedded HTML/CSS strings are naturally long
"""Generate out/mx_preview.html — a static page to browse all MX survival
cards with audio playback, for sanity-checking before importing the apkg.

Filter by category and card_type via dropdowns. Open with a browser:
  xdg-open out/mx_preview.html  (or just double-click)
"""
from __future__ import annotations

import html
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"
DATA = OUT / "mx_survival_source.json"
AUDIO_DIR_REL = "mx_audio"  # relative path from the html file


def esc(s: str) -> str:
    return html.escape(s or "")


def card_html(idx: int, e: dict) -> str:
    prompt_src = ""
    answer_src = ""
    if e.get("spanish_prompt"):
        p = OUT / AUDIO_DIR_REL / f"{idx:04d}_prompt.mp3"
        if p.exists():
            prompt_src = f"{AUDIO_DIR_REL}/{idx:04d}_prompt.mp3"
    a = OUT / AUDIO_DIR_REL / f"{idx:04d}_answer.mp3"
    if a.exists():
        answer_src = f"{AUDIO_DIR_REL}/{idx:04d}_answer.mp3"

    prompt_audio = (
        f'<audio class="js-prompt" controls preload="none" src="{prompt_src}"></audio>'
        if prompt_src else '<span class="muted">— none —</span>'
    )
    answer_audio = (
        f'<audio class="js-answer" controls preload="none" src="{answer_src}"></audio>'
        if answer_src else '<span class="muted">—</span>'
    )

    eng_prompt = e.get("english_prompt") or ""
    eng_answer = e.get("english_answer") or ""

    priority = e.get("priority", "")
    return f"""
<div class="card" data-cat="{esc(e['category'])}" data-type="{esc(e['card_type'])}" data-priority="{esc(priority)}">
  <div class="meta">
    <span class="idx">#{idx}</span>
    {f'<span class="tag pri pri-{esc(priority)}">{esc(priority)}</span>' if priority else ''}
    <span class="tag type">{esc(e['card_type'])}</span>
    <span class="tag cat">{esc(e['category'])}</span>
  </div>
  <div class="row">
    <div class="label">prompt</div>
    <div class="value">{prompt_audio}</div>
  </div>
  <div class="row">
    <div class="label">prompt es</div>
    <div class="value es">{esc(e.get('spanish_prompt') or '') or '<span class="muted">—</span>'}</div>
  </div>
  <div class="row">
    <div class="label">prompt en</div>
    <div class="value en">{esc(eng_prompt) or '<span class="muted">—</span>'}</div>
  </div>
  <div class="row">
    <div class="label">scene cue</div>
    <div class="value es">{esc(e.get('spanish_cue', '')) or '<span class="muted">—</span>'}</div>
  </div>
  <div class="row answer-row">
    <div class="label">answer</div>
    <div class="value answer">{esc(e['spanish'])}</div>
  </div>
  <div class="row">
    <div class="label">answer en</div>
    <div class="value en strong">{esc(eng_answer) or '<span class="muted">—</span>'}</div>
  </div>
  <div class="row">
    <div class="label">answer audio</div>
    <div class="value">{answer_audio}</div>
  </div>
  <div class="row">
    <div class="label">context</div>
    <div class="value en">{esc(e['english_context'])}</div>
  </div>
  <div class="row">
    <div class="label">note</div>
    <div class="value note">{esc(e.get('note', '')) or '<span class="muted">—</span>'}</div>
  </div>
</div>
"""


def main() -> None:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    # Render in priority order so scrolling top-to-bottom prioritizes day-1
    # must-knows. Stable within priority by original index → preserves the
    # category-grouped curation order inside each tier.
    pri_rank = {"essential": 0, "likely": 1, "useful": 2, "": 3}
    indexed = list(enumerate(raw))
    indexed.sort(key=lambda x: (pri_rank.get(x[1].get("priority", ""), 4), x[0]))

    data = [e for _, e in indexed]
    orig_idxs = [i for i, _ in indexed]

    cats = sorted({e["category"] for e in data})
    types = sorted({e["card_type"] for e in data})
    priorities = ["essential", "likely", "useful"]

    cards_html = "\n".join(card_html(orig_idxs[i], e) for i, e in enumerate(data))
    cat_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in cats)
    type_opts = "".join(f'<option value="{esc(t)}">{esc(t)}</option>' for t in types)
    pri_opts = "".join(f'<option value="{esc(p)}">{esc(p)}</option>' for p in priorities)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MX Survival Pack — Preview ({len(data)} cards)</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; color: #222; background: #f6f6f6; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .controls {{ position: sticky; top: 0; background: #f6f6f6; padding: 12px 0; border-bottom: 1px solid #ddd; margin-bottom: 16px; }}
  .controls select, .controls input {{ font-size: 14px; padding: 4px 8px; margin-right: 8px; }}
  .count {{ color: #888; font-size: 14px; margin-left: 12px; }}
  .card {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px; padding: 14px 18px; margin-bottom: 14px; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 10px; }}
  .meta .idx {{ font-family: ui-monospace, Consolas, monospace; margin-right: 10px; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; margin-right: 6px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .tag.type {{ background: #e3f2fd; color: #1565c0; }}
  .tag.cat {{ background: #f3e5f5; color: #6a1b9a; }}
  .tag.pri-essential {{ background: #ffebee; color: #c62828; }}
  .tag.pri-likely {{ background: #fff8e1; color: #ef6c00; }}
  .tag.pri-useful {{ background: #f1f8e9; color: #558b2f; }}
  .row {{ display: grid; grid-template-columns: 110px 1fr; gap: 10px; padding: 4px 0; align-items: center; }}
  .label {{ color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; }}
  .value {{ font-size: 15px; }}
  .value.es {{ font-style: italic; color: #444; }}
  .value.en {{ color: #666; font-size: 13px; }}
  .value.answer {{ font-size: 18px; font-weight: 600; color: #1565c0; }}
  .value.note {{ color: #555; font-size: 13px; }}
  .answer-row {{ background: #f9fbff; border-left: 3px solid #1565c0; padding-left: 12px; margin: 6px -12px; }}
  .muted {{ color: #bbb; }}
  audio {{ height: 26px; vertical-align: middle; }}
  .value.en.strong {{ color: #333; font-size: 15px; font-weight: 500; }}
</style>
</head>
<body>
<h1>MX Survival Pack — Preview</h1>
<p style="color:#888;font-size:13px;margin-top:0">{len(data)} cards. Filter to focus on a slice.</p>

<div class="controls">
  <label>Priority:
    <select id="priFilter"><option value="">— all —</option>{pri_opts}</select>
  </label>
  <label>Category:
    <select id="catFilter"><option value="">— all —</option>{cat_opts}</select>
  </label>
  <label>Card type:
    <select id="typeFilter"><option value="">— all —</option>{type_opts}</select>
  </label>
  <input id="searchBox" placeholder="search Spanish/English…" size="28">
  <span class="count" id="count"></span>
</div>

<div id="cards">
{cards_html}
</div>

<script>
const cards = Array.from(document.querySelectorAll('.card'));
const catSel = document.getElementById('catFilter');
const typeSel = document.getElementById('typeFilter');
const priSel = document.getElementById('priFilter');
const search = document.getElementById('searchBox');
const countEl = document.getElementById('count');

function apply() {{
  const cat = catSel.value;
  const type = typeSel.value;
  const pri = priSel.value;
  const q = search.value.toLowerCase().trim();
  let n = 0;
  cards.forEach(c => {{
    const okCat = !cat || c.dataset.cat === cat;
    const okType = !type || c.dataset.type === type;
    const okPri = !pri || c.dataset.priority === pri;
    const okQ = !q || c.textContent.toLowerCase().includes(q);
    const visible = okCat && okType && okPri && okQ;
    c.style.display = visible ? '' : 'none';
    if (visible) n++;
  }});
  countEl.textContent = `showing ${{n}} of ${{cards.length}}`;
}}
catSel.onchange = apply;
typeSel.onchange = apply;
priSel.onchange = apply;
search.oninput = apply;
apply();

</script>
</body>
</html>
"""

    out_path = OUT / "mx_preview.html"
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Open: file://{out_path.absolute()}")


if __name__ == "__main__":
    main()
