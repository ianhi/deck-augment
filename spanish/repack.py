"""Build out/enhanced.apkg from source.apkg + all our enhancements.

Steps:
1. Extract source.apkg to a temp dir.
2. Open collection.anki21 (sqlite).
3. Update notes:
   - Replace Spanish field with bolded_sentence from bolded_sentences.json.
   - Append a Notes field with regional_note (if present).
   - Append SentenceAudio / WordAudio fields referencing MP3s (if both exist).
4. Modify note type (col.models):
   - Add Notes, SentenceAudio, WordAudio fields.
   - Update card template to include them on the back.
5. Suspend cards:
   - Dedup matches (already in user's other decks).
   - Empty-sentence cards.
6. Copy audio files into the zip with numeric media names, update media JSON.
7. Write out/enhanced.apkg.

Idempotent: every run produces out/enhanced.apkg from scratch; intermediate
temp files go to out/_repack_workdir/.

Usage::

    python repack.py [--source SOURCE] [--out OUT] [--audio-dir AUDIO_DIR]
                     [--audio-ext EXT] [--no-dedup-suspend]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "out"

TAG_NAMESPACE = "davies-5000"
FLAG_TAG_MAP = {
    "REGIONAL": f"{TAG_NAMESPACE}::regional",
    "TYPO": f"{TAG_NAMESPACE}::typo",
    "UNGRAMMATICAL": f"{TAG_NAMESPACE}::ungrammatical",
    "AWKWARD": f"{TAG_NAMESPACE}::awkward",
    "ARCHAIC": f"{TAG_NAMESPACE}::archaic",
    "NO_MATCH": f"{TAG_NAMESPACE}::no-match",
}


# ---------------------------------------------------------------------------
# Input loaders
# ---------------------------------------------------------------------------


def load_bolded(bolded_path: Path) -> dict[int, dict]:
    data = json.loads(bolded_path.read_text())
    return {e["note_id"]: e for e in data}


def load_dedup_note_ids(dedup_path: Path, bolded_path: Path) -> set[int]:
    """Return note_ids that already exist in the user's other decks."""
    if not dedup_path.exists():
        return set()
    matches = json.loads(dedup_path.read_text())
    bolded = json.loads(bolded_path.read_text())
    rank_to_nid = {e["rank"]: e["note_id"] for e in bolded}
    return {rank_to_nid[m["rank"]] for m in matches if m["rank"] in rank_to_nid}


def load_flags_per_note(batch_dir: Path, output_dir: Path) -> dict[int, set[str]]:
    """Parse batch outputs + manifests to map note_id → {flag categories}."""
    tag_re = re.compile(r"\[(NO_MATCH|REGIONAL|UNGRAMMATICAL|ARCHAIC|AWKWARD|TYPO)")
    line_re = re.compile(r"^\s*(\d+)\.\s*(.*)$")
    result: dict[int, set[str]] = {}
    if not output_dir.exists():
        return result
    for batch_num in range(50):
        out_file = output_dir / f"batch_{batch_num:02d}_output.md"
        manifest_file = batch_dir / f"batch_{batch_num:02d}_manifest.json"
        if not (out_file.exists() and manifest_file.exists()):
            continue
        manifest = {m["line"]: m["note_id"] for m in json.loads(manifest_file.read_text())}
        for raw in out_file.read_text().splitlines():
            m = line_re.match(raw)
            if not m:
                continue
            lineno = int(m.group(1))
            body = m.group(2)
            note_id = manifest.get(lineno)
            if note_id is None:
                continue
            for match in tag_re.finditer(body):
                result.setdefault(note_id, set()).add(match.group(1))
    return result


def load_audio_index(audio_index_path: Path, audio_dir: Path, audio_ext: str) -> dict[int, dict]:
    """Return {note_id: entry} for cards where both audio files exist on disk."""
    index: dict[int, dict] = {}
    if not audio_index_path.exists():
        return index
    for line in audio_index_path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        word = audio_dir / f"{entry['note_id']}_word{audio_ext}"
        sent = audio_dir / f"{entry['note_id']}_sentence{audio_ext}"
        if word.exists() and sent.exists():
            index[entry["note_id"]] = entry
    return index


def load_inputs(
    source_apkg: Path,
    out_dir: Path,
    audio_dir: Path,
    audio_ext: str,
) -> tuple[dict[int, dict], set[int], dict[int, dict], dict[int, set[str]]]:
    """Load all input data and return (bolded, dedup_ids, audio_index, flags_per_note)."""
    bolded_path = out_dir / "bolded_sentences.json"
    dedup_path = out_dir / "dedup_matches.json"
    audio_index_path = out_dir / "audio_index.jsonl"
    batch_dir = out_dir / "bold_batches"
    output_dir = out_dir / "bold_outputs"

    print(f"Loading bolded sentences from {bolded_path}...")
    bolded = load_bolded(bolded_path)
    print(f"  {len(bolded)} entries")

    print(f"Loading dedup matches from {dedup_path}...")
    dedup_ids = load_dedup_note_ids(dedup_path, bolded_path)
    print(f"  {len(dedup_ids)} cards to suspend (dedup)")

    print(f"Loading audio index from {audio_index_path}...")
    audio_index = load_audio_index(audio_index_path, audio_dir, audio_ext)
    print(f"  {len(audio_index)} cards with audio ready")

    print("Loading flags from batch outputs for tagging...")
    flags_per_note = load_flags_per_note(batch_dir, output_dir)
    print(f"  flags for {len(flags_per_note)} notes")

    return bolded, dedup_ids, audio_index, flags_per_note


# ---------------------------------------------------------------------------
# Model modification
# ---------------------------------------------------------------------------


def modify_models(con: sqlite3.Connection, new_field_names: list[str]) -> int:
    """Add new fields and rewrite card templates; return original field count."""
    cur = con.cursor()
    (models_json_str,) = cur.execute("SELECT models FROM col").fetchone()
    models: dict = json.loads(models_json_str)

    base_field_counts = {len(m["flds"]) for m in models.values()}
    assert len(base_field_counts) == 1, f"Mixed field counts: {base_field_counts}"
    n_existing: int = next(iter(base_field_counts))
    print(f"\nExisting fields per note: {n_existing}")

    for model in models.values():
        existing_names = {f["name"] for f in model["flds"]}
        next_ord = max((f["ord"] for f in model["flds"]), default=-1) + 1
        for name in new_field_names:
            if name in existing_names:
                continue
            model["flds"].append({
                "name": name,
                "ord": next_ord,
                "sticky": False,
                "rtl": False,
                "font": "Arial",
                "size": 14,
                "description": "",
                "plainText": False,
                "collapsed": False,
                "excludeFromSearch": False,
                "id": next_ord + 1000,
                "tag": None,
                "preventDeletion": False,
            })
            next_ord += 1
        for tmpl in model["tmpls"]:
            tmpl["qfmt"] = (
                '{{SentenceAudio}}\n'
                '{{WordAudio}}\n'
                '<div class="hint-row">{{hint:Spanish}}</div>\n'
            )
            tmpl["afmt"] = (
                '<div class="word">{{Word}} '
                '<span class="part-of-speech">{{Part-of-Speech}}</span></div>\n'
                '<div class="spanish">{{Spanish}}</div>\n'
                '{{SentenceAudio}}\n'
                '{{WordAudio}}\n'
                '<hr id=answer>\n'
                '<div class="definition">{{Definition}}</div>\n'
                '<div class="english">{{English}}</div>\n'
                '{{#Notes}}<hr><div class="notes">⚠ {{Notes}}</div>{{/Notes}}\n'
            )

    cur.execute("UPDATE col SET models = ?", (json.dumps(models, ensure_ascii=False),))
    con.commit()
    print(f"Added fields: {', '.join(new_field_names)}")
    return n_existing


# ---------------------------------------------------------------------------
# Note rewriting
# ---------------------------------------------------------------------------


def rewrite_notes(
    con: sqlite3.Connection,
    bolded: dict[int, dict],
    audio_index: dict[int, dict],
    flags_per_note: dict[int, set[str]],
    dedup_ids: set[int],
    empty_ids: set[int],
    n_existing_fields: int,
) -> int:
    """Rewrite each note's flds with bolded sentence + new Notes + Audio fields."""
    cur = con.cursor()
    updated = 0
    rows = cur.execute("SELECT id, flds FROM notes").fetchall()
    for note_id, flds in rows:
        parts = flds.split("\x1f")
        if len(parts) < n_existing_fields:
            parts.extend([""] * (n_existing_fields - len(parts)))

        bold_entry = bolded.get(note_id)
        if bold_entry and not bold_entry["no_match"]:
            parts[4] = bold_entry["bolded_sentence"]

        notes_value = ""
        if bold_entry and bold_entry.get("regional_note"):
            notes_value = bold_entry["regional_note"]

        audio_entry = audio_index.get(note_id)
        sentence_audio = f"[sound:{note_id}_sentence.mp3]" if audio_entry else ""
        word_audio = f"[sound:{note_id}_word.mp3]" if audio_entry else ""

        tags: list[str] = [TAG_NAMESPACE]
        for flag in flags_per_note.get(note_id, set()):
            tag = FLAG_TAG_MAP.get(flag)
            if tag:
                tags.append(tag)
        if note_id in dedup_ids:
            tags.append(f"{TAG_NAMESPACE}::dedup-existing")
        if note_id in empty_ids:
            tags.append(f"{TAG_NAMESPACE}::empty-sentence")
        tags_str = " " + " ".join(sorted(set(tags))) + " "

        new_flds = parts + [notes_value, sentence_audio, word_audio]
        cur.execute(
            "UPDATE notes SET flds = ?, tags = ? WHERE id = ?",
            ("\x1f".join(new_flds), tags_str, note_id),
        )
        updated += 1
    con.commit()
    return updated


# ---------------------------------------------------------------------------
# Ordering and suspension
# ---------------------------------------------------------------------------


def set_ordering(con: sqlite3.Connection, bolded: dict[int, dict]) -> int:
    """Set each card's due field to its note's rank for frequency-order delivery."""
    cur = con.cursor()
    for note_id, entry in bolded.items():
        cur.execute(
            "UPDATE cards SET due = ? WHERE nid = ?",
            (entry["rank"], note_id),
        )
    con.commit()
    return len(bolded)


def suspend_cards(con: sqlite3.Connection, note_ids: set[int]) -> int:
    """Set queue = -1 (suspended) for all cards belonging to given notes."""
    if not note_ids:
        return 0
    cur = con.cursor()
    placeholders = ",".join("?" * len(note_ids))
    cur.execute(
        f"UPDATE cards SET queue = -1 WHERE nid IN ({placeholders})",
        tuple(note_ids),
    )
    con.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Media packing
# ---------------------------------------------------------------------------


def copy_media(
    workdir: Path,
    audio_index: dict[int, dict],
    audio_dir: Path,
    audio_ext: str,
) -> dict[str, str]:
    """Copy MP3s into workdir with numeric filenames, update media JSON.

    Returns updated media mapping {numeric_str: original_filename}.
    """
    media_path = workdir / "media"
    existing_media: dict[str, str] = {}
    if media_path.exists():
        content = media_path.read_text()
        if content.strip():
            existing_media = json.loads(content)

    next_idx = max((int(k) for k in existing_media.keys()), default=-1) + 1
    for note_id in audio_index:
        for suffix in ("word", "sentence"):
            src = audio_dir / f"{note_id}_{suffix}{audio_ext}"
            if not src.exists():
                continue
            media_name = f"{note_id}_{suffix}{audio_ext}"
            if media_name in existing_media.values():
                continue
            dst = workdir / str(next_idx)
            shutil.copy2(src, dst)
            existing_media[str(next_idx)] = media_name
            next_idx += 1

    media_path.write_text(json.dumps(existing_media, ensure_ascii=False))
    return existing_media


# ---------------------------------------------------------------------------
# Output packaging
# ---------------------------------------------------------------------------


def write_apkg(workdir: Path, enhanced_apkg: Path) -> float:
    """Package workdir contents into enhanced_apkg; return file size in MB."""
    if enhanced_apkg.exists():
        enhanced_apkg.unlink()
    with zipfile.ZipFile(enhanced_apkg, "w", zipfile.ZIP_DEFLATED) as z:
        for f in workdir.iterdir():
            if f.is_file():
                z.write(f, arcname=f.name)
    return enhanced_apkg.stat().st_size / 1_000_000


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build out/enhanced.apkg from source.apkg + enhancements.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=HERE / "source.apkg",
        help="Path to source .apkg (default: source.apkg)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT,
        help="Output directory (default: out/)",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=OUT / "audio_mp3_64k",
        help="Directory containing audio files (default: out/audio_mp3_64k)",
    )
    parser.add_argument(
        "--audio-ext",
        default=".mp3",
        help="Audio file extension including dot (default: .mp3)",
    )
    parser.add_argument(
        "--no-dedup-suspend",
        action="store_true",
        help="Skip suspending cards matched by dedup",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    source_apkg: Path = args.source
    out_dir: Path = args.out
    audio_dir: Path = args.audio_dir
    audio_ext: str = args.audio_ext
    enhanced_apkg = out_dir / "enhanced.apkg"
    workdir = out_dir / "_repack_workdir"

    bolded, dedup_ids, audio_index, flags_per_note = load_inputs(
        source_apkg, out_dir, audio_dir, audio_ext,
    )

    if args.no_dedup_suspend:
        dedup_ids = set()

    empty_ids: set[int] = {
        e["note_id"] for e in bolded.values()
        if not e["bolded_sentence"].strip()
    }
    print(f"  {len(empty_ids)} cards to suspend (empty sentence)")

    print("\nExtracting source.apkg...")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    with zipfile.ZipFile(source_apkg) as z:
        z.extractall(workdir)

    col_path = workdir / "collection.anki21"
    con = sqlite3.connect(col_path)

    n_existing = modify_models(con, ["Notes", "SentenceAudio", "WordAudio"])

    print("\nUpdating notes (content + tags)...")
    n_updated = rewrite_notes(
        con, bolded, audio_index, flags_per_note, dedup_ids, empty_ids, n_existing,
    )
    print(f"  updated {n_updated} notes")

    print("\nSetting card due=rank for frequency-order delivery...")
    n_due = set_ordering(con, bolded)
    print(f"  set due on {n_due} cards")

    print("\nSuspending cards...")
    suspended_dedup = suspend_cards(con, dedup_ids)
    suspended_empty = suspend_cards(con, empty_ids)
    print(f"  suspended {suspended_dedup} (dedup) + {suspended_empty} (empty)")

    con.close()

    print("\nCopying audio files...")
    media = copy_media(workdir, audio_index, audio_dir, audio_ext)
    print(f"  media entries: {len(media)}")

    print(f"\nPackaging {enhanced_apkg}...")
    size_mb = write_apkg(workdir, enhanced_apkg)
    print(f"  wrote {enhanced_apkg} ({size_mb:.1f} MB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
