# lib — Notes

Shared infrastructure imported by `bangla/`, `mx/`, `spanish/`, `archive/`.

- `paths.py` — `REPO_ROOT` and `OUT_DIR`. Use these instead of computing
  `Path(__file__).parent` from inside a subdir script.
- `ankiconnect.py` — thin `ac(action, **params)` wrapper around AnkiConnect's
  HTTP JSON-RPC. Raises on `error` field. Default port 8765.
- `gemini_prompts.py` — all system + user prompt strings. One module per
  pass: `BANGLA_SENTENCE_*`, `BANGLA_TRANSLATION_*`, `BANGLA_NATURALNESS_*`,
  `BANGLA_NUMBER_FILL_*`, `NOTES_FILTER_SYSTEM`. Add new passes here so the
  prompts stay grep-able from one place.
- `sentence_sampling.py` — deterministic per-note sampling of form
  constraints (tense, register, person, sentence type, polarity). Distributions
  sourced from the Dash 5M-token corpus for Bangla. Seeded by SHA-1(note_id)
  so re-runs are stable.
- `numbers_seed.py` — pure data for the Bangla Number deck (~125 notes). No
  I/O. The fused 21–99 cardinals are seeded as `bengali_word=None` and
  filled by Gemini at build time — don't seed those from memory.

## Subdir scripts that import from here

Each one needs a 3-line bootstrap so `from lib.X import Y` resolves under
`uv run`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

If you move a script in or out of a subdir, update its bootstrap (or remove
it) accordingly.
