"""Build out/opus_test.apkg — a 1-card test deck to verify .opus playback on AnkiDroid.

The card plays a single .opus file on the front. If AnkiDroid plays it, .opus
is supported and we can use it for the full deck; otherwise fall back to MP3.

Reads:
  source.apkg               — the full deck (provides model/note structure)
  out/audio_opus_renamed/   — renamed opus files keyed by note id

Writes:
  out/opus_test.apkg        — minimal single-card deck

The script picks rank-19 ("tener") by default because it is a short, familiar
word with guaranteed audio in the source deck.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"


def build(source_apkg: Path, opus_dir: Path, out_apkg: Path) -> int:
    workdir = OUT / "_opus_test_workdir"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    with zipfile.ZipFile(source_apkg) as z:
        z.extractall(workdir)

    col_path = workdir / "collection.anki21"
    con = sqlite3.connect(col_path)
    cur = con.cursor()

    # Prefer rank-19 card ("tener"); fall back to the first available note.
    row: tuple[int, str] | None = cur.execute(
        "SELECT id, flds FROM notes WHERE flds LIKE '19\x1f%' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        row = cur.execute("SELECT id, flds FROM notes LIMIT 1").fetchone()
    if not row:
        print("ERROR: no notes found in source deck", file=sys.stderr)
        con.close()
        return 1

    note_id, _flds = row
    print(f"Using note_id={note_id}")

    # Keep only this note and its cards.
    cur.execute("DELETE FROM notes WHERE id != ?", (note_id,))
    cur.execute("DELETE FROM cards WHERE nid != ?", (note_id,))

    # Replace model fields/templates with a minimal Audio-only layout.
    (models_str,) = cur.execute("SELECT models FROM col").fetchone()
    models: dict[str, dict[str, object]] = json.loads(models_str)
    for m in models.values():
        m["flds"] = [{
            "name": "Audio", "ord": 0, "sticky": False, "rtl": False,
            "font": "Arial", "size": 20, "description": "",
            "plainText": False, "collapsed": False, "excludeFromSearch": False,
            "id": 1, "tag": None, "preventDeletion": False,
        }]
        templates = list(m["tmpls"])  # type: ignore[arg-type]
        m["tmpls"] = [{
            **templates[0],
            "qfmt": (
                "<h1>Opus playback test</h1>\n{{Audio}}\n"
                "<p>If you hear audio when this card shows, .opus works.</p>"
            ),
            "afmt": "{{FrontSide}}\n<hr>\n<p>Flip to replay:</p>\n{{Audio}}",
        }]
    cur.execute("UPDATE col SET models = ?", (json.dumps(models, ensure_ascii=False),))

    audio_filename = f"{note_id}_word.opus"
    cur.execute(
        "UPDATE notes SET flds = ?, tags = ? WHERE id = ?",
        (f"[sound:{audio_filename}]", " opus-test ", note_id),
    )
    con.commit()
    con.close()

    # Copy the single opus file into the archive as media entry "0".
    src = opus_dir / audio_filename
    if not src.exists():
        print(f"ERROR: source audio missing: {src}", file=sys.stderr)
        return 1
    shutil.copy2(src, workdir / "0")
    (workdir / "media").write_text(
        json.dumps({"0": audio_filename}), encoding="utf-8"
    )

    # Pack everything into the output .apkg.
    if out_apkg.exists():
        out_apkg.unlink()
    with zipfile.ZipFile(out_apkg, "w", zipfile.ZIP_DEFLATED) as z:
        for f in workdir.iterdir():
            if f.is_file():
                z.write(f, arcname=f.name)

    print(f"Wrote {out_apkg} ({out_apkg.stat().st_size:,} bytes)")
    print(f"Contains 1 card with [sound:{audio_filename}]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        metavar="APKG",
        type=Path,
        default=HERE / "source.apkg",
        help="Source .apkg to extract note structure from (default: source.apkg).",
    )
    parser.add_argument(
        "--opus-dir",
        metavar="DIR",
        type=Path,
        default=OUT / "audio_opus_renamed",
        help="Directory of renamed .opus files (default: out/audio_opus_renamed/).",
    )
    parser.add_argument(
        "--output",
        metavar="APKG",
        type=Path,
        default=OUT / "opus_test.apkg",
        help="Output .apkg path (default: out/opus_test.apkg).",
    )
    args = parser.parse_args()

    source: Path = args.source
    if not source.exists():
        print(f"ERROR: source apkg not found: {source}", file=sys.stderr)
        return 1

    opus_dir: Path = args.opus_dir
    if not opus_dir.is_dir():
        print(f"ERROR: opus directory not found: {opus_dir}", file=sys.stderr)
        return 1

    return build(source, opus_dir, args.output)


if __name__ == "__main__":
    sys.exit(main())
