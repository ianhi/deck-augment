"""Generate TTS audio for `Bangla (and reversed)` notes via tts-tools.

Synthesizes per note:
  out/audio_bn/<note_id>_word.mp3      — the Bangla headword
  out/audio_bn/<note_id>_sentence.mp3  — the Example sentence (bold tags stripped)

Voice is assigned deterministically by hashing the note id, from the
six-voice Spanish-set (Kore/Aoede/Sulafat + Charon/Fenrir/Orus). Sentence
and word audio for one note always share the same voice.

Idempotent: notes whose both files already exist on disk are skipped.

The `--apply` step uploads MP3s into Anki's collection.media folder via
AnkiConnect and sets `WordAudio` + `ExampleAudio` field values to
`[sound:...]` references. Sentence sound is referenced before word in the
field-value layout, matching the user's "sentence audio first" preference.

Usage:
  uv run tts_run_bangla.py --limit 20           # small test batch
  uv run tts_run_bangla.py                      # generate for all eligible notes
  uv run tts_run_bangla.py --apply              # push generated MP3s to Anki
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import asyncio
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tts_tools import synthesize_async

from lib.ankiconnect import ac

HERE = Path(__file__).resolve().parents[1]
OUT_DIR = HERE / "out"

LANGUAGE = "bn-IN"
ALL_VOICES = ["Kore", "Aoede", "Sulafat", "Charon", "Fenrir", "Orus"]


@dataclass(frozen=True)
class Profile:
    """Per-deck TTS config. Add an entry to PROFILES to support another note type."""
    name: str
    model: str
    headword_field: str        # "" disables word-audio synthesis
    sentence_field: str
    word_audio_field: str      # ignored if headword_field is ""
    sentence_audio_field: str
    media_prefix: str
    audio_dirname: str
    index_filename: str


PROFILES: dict[str, Profile] = {
    "bangla-vocab": Profile(
        name="bangla-vocab",
        model="Bangla (and reversed)",
        headword_field="Bangla",
        sentence_field="Example",
        word_audio_field="WordAudio",
        sentence_audio_field="ExampleAudio",
        media_prefix="bn_",
        audio_dirname="audio_bn",
        index_filename="audio_bn_index.jsonl",
    ),
    "bangla-numbers": Profile(
        name="bangla-numbers",
        model="Bangla Number",
        headword_field="bengali_word",
        sentence_field="example_bangla",
        word_audio_field="word_audio",
        sentence_audio_field="sentence_audio",
        media_prefix="bn_num_",
        audio_dirname="audio_bn_numbers",
        index_filename="audio_bn_numbers_index.jsonl",
    ),
    "bangla-defs": Profile(
        name="bangla-defs",
        model="anki-defs-bn-IN",
        headword_field="Word",
        sentence_field="Example",
        word_audio_field="WordAudio",
        sentence_audio_field="ExampleAudio",
        media_prefix="bn_defs_",
        audio_dirname="audio_bn_defs",
        index_filename="audio_bn_defs_index.jsonl",
    ),
    "bangla-conjugation": Profile(
        name="bangla-conjugation",
        model="Bangla Conjugation",
        headword_field="",  # cloze-only, no separate word audio
        sentence_field="Text",
        word_audio_field="",
        sentence_audio_field="SentenceAudio",
        media_prefix="bn_conj_",
        audio_dirname="audio_bn_conjugation",
        index_filename="audio_bn_conjugation_index.jsonl",
    ),
}

# Set in main() before any deck I/O runs.
PROFILE: Profile = PROFILES["bangla-vocab"]


def _audio_dir() -> Path:
    return OUT_DIR / PROFILE.audio_dirname


def _index_path() -> Path:
    return OUT_DIR / PROFILE.index_filename

BOLD_RE = re.compile(r"</?b\b[^>]*>", re.IGNORECASE)
CLOZE_RE = re.compile(r"\{\{c\d+::([^:}]+)(?:::[^}]+)?\}\}")


def voice_for_note(note_id: int, voices: list[str]) -> str:
    """Deterministic voice for a note id (SHA-1 → modulo)."""
    digest = hashlib.sha1(str(note_id).encode()).digest()
    return voices[digest[0] % len(voices)]


def plain_text(value: str) -> str:
    """Strip <b>...</b> markup and {{c1::form::hint}} cloze syntax before TTS."""
    no_bold = BOLD_RE.sub("", value)
    no_cloze = CLOZE_RE.sub(r"\1", no_bold)
    return no_cloze.strip()


def filename_safe_word(note_id: int) -> str:
    return f"{PROFILE.media_prefix}{note_id}_word.mp3"


def filename_safe_sentence(note_id: int) -> str:
    return f"{PROFILE.media_prefix}{note_id}_sentence.mp3"


def raw_path(trimmed_path: Path) -> Path:
    """Sibling path for the un-trimmed source audio."""
    return trimmed_path.with_name(trimmed_path.stem + "_raw" + trimmed_path.suffix)


_vad_model = None  # lazy-loaded Silero VAD model


def _get_vad_model():
    """Load Silero VAD on first call. Returns None if unavailable so
    callers can fall back to the ffmpeg silenceremove path."""
    global _vad_model
    if _vad_model is False:
        return None
    if _vad_model is not None:
        return _vad_model
    try:
        from silero_vad import load_silero_vad
        _vad_model = load_silero_vad()
    except Exception:  # noqa: BLE001
        _vad_model = False
        return None
    return _vad_model


def _file_duration_seconds(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path),
            ],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        return float(out) if out else None
    except (subprocess.CalledProcessError, ValueError):
        return None


# Chirp3 occasionally returns near-silent audio for very short inputs
# (observed on bare Bangla monosyllables like ভাই). Anything quieter
# than this we treat as broken and refuse to upload.
SILENCE_PEAK_DB_THRESHOLD = -30.0


def _peak_volume_db(path: Path) -> float | None:
    """Return the peak volume in dB (e.g. -2.0 for loud, -50.0 for near-silent)."""
    try:
        out = subprocess.run(
            [
                "ffmpeg", "-v", "info", "-i", str(path),
                "-af", "volumedetect", "-f", "null", "-",
            ],
            check=True, capture_output=True, text=True,
        ).stderr
    except subprocess.CalledProcessError:
        return None
    for line in out.splitlines():
        if "max_volume" in line:
            try:
                return float(line.rsplit("max_volume:", 1)[1].split("dB")[0])
            except (IndexError, ValueError):
                return None
    return None


def _vad_trim(raw_path: Path, out_path: Path, padding_s: float = 0.12) -> bool:
    """Trim using Silero VAD on a 16 kHz mono mixdown.

    Returns True on success. Returns False (caller should fall back) when:
      - the VAD model can't be loaded
      - no speech is detected
      - the trim would yield a clip shorter than 100 ms
    """
    model = _get_vad_model()
    if model is None or not shutil.which("ffmpeg"):
        return False
    # Decode raw → 16 kHz mono PCM via ffmpeg (Silero expects this).
    try:
        import numpy as np
        import torch
        from silero_vad import get_speech_timestamps
    except Exception:  # noqa: BLE001
        return False
    try:
        pcm = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", str(raw_path),
                "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
            ],
            check=True, capture_output=True,
        ).stdout
    except subprocess.CalledProcessError:
        return False
    if not pcm:
        return False
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        return False
    wav = torch.from_numpy(samples)
    timestamps = get_speech_timestamps(
        wav, model, sampling_rate=16000, return_seconds=True,
    )
    if not timestamps:
        return False
    total_duration = samples.size / 16000.0
    start = max(0.0, timestamps[0]["start"] - padding_s)
    end = min(total_duration, timestamps[-1]["end"] + padding_s)
    if end - start < 0.1:
        return False
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(raw_path),
                "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                "-codec:a", "libmp3lame", "-qscale:a", "4",
                str(out_path),
            ],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    duration = _file_duration_seconds(out_path)
    if duration is None or duration < 0.1:
        return False
    return True


def _silence_threshold_trim(raw_path: Path, out_path: Path) -> bool:
    """Fallback trim: ffmpeg silenceremove with conservative thresholds.

    Threshold -55 dB, minimum 200 ms of contiguous silence before cutting.
    Returns True on success, False when ffmpeg fails or produces an
    unreadable / too-short file."""
    if not shutil.which("ffmpeg"):
        return False
    silenceremove = (
        "silenceremove=start_periods=1:start_duration=0.2:"
        "start_threshold=-55dB:detection=peak"
    )
    af = f"{silenceremove},areverse,{silenceremove},areverse"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(raw_path),
                "-af", af,
                "-codec:a", "libmp3lame", "-qscale:a", "4",
                str(out_path),
            ],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    duration = _file_duration_seconds(out_path)
    return duration is not None and duration >= 0.1


def light_trim(raw_path: Path, out_path: Path) -> None:
    """Produce a lightly-trimmed copy. Prefers Silero VAD when available
    (most accurate); falls back to ffmpeg silenceremove; if both fail,
    copies the raw file as-is so callers always end up with a playable
    out_path."""
    if _vad_trim(raw_path, out_path):
        return
    if _silence_threshold_trim(raw_path, out_path):
        return
    shutil.copyfile(raw_path, out_path)


_progress_lock = asyncio.Lock()
_done_count = 0


async def _record(entry: dict, total: int) -> None:
    global _done_count
    async with _progress_lock:
        with _index_path().open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _done_count += 1
        if _done_count % 25 == 0 or _done_count == total:
            print(f"  [{_done_count:>4}/{total}] synthesized", flush=True)


async def _synth_with_silence_retry(
    text: str,
    primary_voice: str,
    all_voices: list[str],
    raw_out: Path,
    trimmed_out: Path,
) -> tuple[bool, str, list[str]]:
    """Synthesize `text`, retrying with different voices if Chirp3
    returns a near-silent clip. Saves the LAST attempted raw to raw_out
    (whether silent or not) and the trimmed output to trimmed_out
    (deleted when all attempts come back silent).

    Returns (audible, winning_voice, attempted_voice_log).
    `audible=False` means every voice produced a silent clip — caller
    treats it as a known-broken card and lets the template TTS fallback
    kick in.
    """
    # Try the deterministic primary voice first, then up to 2 alternates.
    ordered = [primary_voice] + [v for v in all_voices if v != primary_voice]
    ordered = ordered[:3]  # cap retries to keep cost bounded
    attempts: list[str] = []
    for voice in ordered:
        voice_name = f"{LANGUAGE}-Chirp3-HD-{voice}"
        result = await synthesize_async(
            text, language=LANGUAGE, voice=voice_name,
            trim=False, max_retries=6,
        )
        result.save(str(raw_out))
        light_trim(raw_out, trimmed_out)
        peak = _peak_volume_db(trimmed_out)
        attempts.append(f"{voice}:{peak:.1f}dB" if peak is not None else f"{voice}:?")
        if peak is None or peak >= SILENCE_PEAK_DB_THRESHOLD:
            return True, voice, attempts
        # silent — delete trimmed and try next voice
        trimmed_out.unlink(missing_ok=True)
    return False, ordered[-1], attempts


async def synth_one_note(
    voice: str,
    note_id: int,
    headword: str,
    sentence: str,
    total: int,
    all_voices: list[str],
) -> None:
    """Synthesize word + sentence audio for one note. Each clip retries
    with alternate voices on near-silence (Chirp3 quirk on short inputs)
    before giving up. Failures log but don't abort siblings — re-run
    picks up missing files. Concurrency is now controlled by the
    worker-pool in run_generation; this coroutine is fully serial."""
    word_path = _audio_dir() / filename_safe_word(note_id)
    sent_path = _audio_dir() / filename_safe_sentence(note_id)
    try:
        jobs: list[tuple[str, str, Path]] = []
        if headword and not (word_path.exists() or raw_path(word_path).exists()):
            jobs.append(("word", headword, word_path))
        if sentence and not (sent_path.exists() or raw_path(sent_path).exists()):
            jobs.append(("sentence", sentence, sent_path))
        if not jobs:
            return
        results = await asyncio.gather(*[
            _synth_with_silence_retry(
                text, voice, all_voices, raw_path(out_path), out_path,
            )
            for _, text, out_path in jobs
        ])
        silent_flags: list[str] = []
        winning_voices: dict[str, str] = {}
        for (label, _text, _out_path), (audible, win_voice, attempts) in zip(
            jobs, results, strict=True,
        ):
            winning_voices[label] = win_voice
            if not audible:
                silent_flags.append(f"{label}:silent_all[{','.join(attempts)}]")
        if silent_flags:
            print(
                f"  SILENT note_id={note_id} ({headword!r}): "
                f"{'; '.join(silent_flags)}",
                flush=True,
            )
        await _record(
            {
                "note_id": note_id,
                "voice": voice,
                "winning_voices": winning_voices or None,
                "word_path": (
                    f"{PROFILE.audio_dirname}/{word_path.name}"
                    if word_path.exists() else None
                ),
                "sentence_path": (
                    f"{PROFILE.audio_dirname}/{sent_path.name}"
                    if sent_path.exists() else None
                ),
                "silent_flags": silent_flags or None,
            },
            total,
        )
    except Exception as exc:  # noqa: BLE001 — never kill the run
        print(
            f"  FAILED note_id={note_id} voice={voice}: {type(exc).__name__}: {exc}",
            flush=True,
        )


def discover_eligible_notes(limit: int | None) -> list[tuple[int, str, str]]:
    """Return (note_id, headword, plain_sentence) for every eligible note.

    Eligibility: profile has either a non-empty headword OR a non-empty
    sentence field. Profiles with `headword_field=""` are sentence-only
    (e.g. the conjugation profile — cloze-only, no word audio)."""
    if PROFILE.headword_field:
        query = f'"note:{PROFILE.model}" {PROFILE.headword_field}:_*'
    else:
        query = f'"note:{PROFILE.model}" {PROFILE.sentence_field}:_*'
    nids = ac("findNotes", query=query)
    nids.sort()
    if limit:
        nids = nids[:limit]
    notes: list[dict] = []
    for i in range(0, len(nids), 200):
        notes.extend(ac("notesInfo", notes=nids[i : i + 200]))
    out: list[tuple[int, str, str]] = []
    for n in notes:
        if PROFILE.headword_field:
            hw = (n["fields"].get(PROFILE.headword_field, {}).get("value") or "").strip()
            if not hw:
                continue
        else:
            hw = ""
        sent_raw = n["fields"].get(PROFILE.sentence_field, {}).get("value", "")
        sent = plain_text(sent_raw)
        if not hw and not sent:
            continue
        out.append((n["noteId"], hw, sent))
    return out



def apply_audio_to_anki(only: int | None) -> None:
    """Push generated MP3s into Anki and set the audio field values.

    Batches storeMediaFile + updateNoteFields via AnkiConnect's `multi`
    action so each HTTP round-trip covers many cards. ~10× faster than
    one-call-per-action.
    """
    if not _index_path().exists():
        print("No audio index yet — run generation first.")
        return
    entries: list[dict] = []
    for line in _index_path().read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    by_note: dict[int, dict] = {}
    for e in entries:
        by_note[e["note_id"]] = e

    nids = sorted(by_note.keys())
    if only:
        nids = nids[:only]
    print(f"{len(nids)} notes to apply.")

    # Fetch current field values to skip notes already up-to-date.
    current: dict[int, dict[str, str]] = {}
    for i in range(0, len(nids), 200):
        for n in ac("notesInfo", notes=nids[i : i + 200]):
            fields = n.get("fields")
            if not fields:
                # Note was deleted from Anki — skip; the audio-index entry is stale.
                continue
            cur: dict[str, str] = {}
            if PROFILE.word_audio_field:
                cur[PROFILE.word_audio_field] = (
                    fields.get(PROFILE.word_audio_field, {}).get("value", "")
                )
            cur[PROFILE.sentence_audio_field] = (
                fields.get(PROFILE.sentence_audio_field, {}).get("value", "")
            )
            current[n["noteId"]] = cur

    # Build a flat list of actions, batched into multi-calls.
    BATCH_SIZE = 25  # ~75 actions/HTTP call — well under AnkiConnect limits
    actions: list[dict] = []
    updated = 0
    unchanged = 0

    def flush() -> None:
        if not actions:
            return
        ac("multi", actions=list(actions))
        actions.clear()

    for nid in nids:
        word_local = _audio_dir() / filename_safe_word(nid)
        sent_local = _audio_dir() / filename_safe_sentence(nid)
        desired: dict[str, str] = {}
        media_actions: list[dict] = []
        if PROFILE.word_audio_field and word_local.exists():
            media_actions.append({
                "action": "storeMediaFile",
                "params": {
                    "filename": word_local.name,
                    "data": base64.b64encode(word_local.read_bytes()).decode(),
                },
            })
            desired[PROFILE.word_audio_field] = f"[sound:{word_local.name}]"
        if sent_local.exists():
            media_actions.append({
                "action": "storeMediaFile",
                "params": {
                    "filename": sent_local.name,
                    "data": base64.b64encode(sent_local.read_bytes()).decode(),
                },
            })
            desired[PROFILE.sentence_audio_field] = f"[sound:{sent_local.name}]"
        if not desired:
            continue
        cur = current.get(nid, {})
        if all(cur.get(k, "") == v for k, v in desired.items()):
            unchanged += 1
            continue
        actions.extend(media_actions)
        actions.append({
            "action": "updateNoteFields",
            "params": {"note": {"id": nid, "fields": desired}},
        })
        updated += 1
        # Each card contributes 2-3 actions; flush by note count, not action count.
        if updated % BATCH_SIZE == 0:
            flush()
            print(f"  pushed {updated} so far …", flush=True)
    flush()
    print(f"Pushed {updated}; {unchanged} already up-to-date.")


async def run_generation(
    work: list[tuple[str, int, str, str]],
    concurrency: int,
    all_voices: list[str],
) -> None:
    """Worker-pool over an asyncio.Queue.

    N persistent workers each pull from the queue and process one card
    at a time. Workers desync naturally — when one finishes a fast card
    and another is mid-flight on a slow card, the queue keeps the fast
    worker fed instead of waiting for a synchronised "wave" of N tasks
    to finish (which is what happens with `Semaphore + gather`).
    """
    queue: asyncio.Queue[tuple[str, int, str, str]] = asyncio.Queue()
    for item in work:
        queue.put_nowait(item)
    total = len(work)

    async def worker() -> None:
        while True:
            try:
                voice, nid, hw, sent = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await synth_one_note(voice, nid, hw, sent, total, all_voices)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default="bangla-vocab",
        help="Which deck/note-type to target. Each profile sets the Anki "
             "model name, source fields, audio fields, and file layout.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only process the first N notes."
    )
    parser.add_argument(
        "--concurrency", type=int, default=4,
        help="Concurrent note slots (each slot fires up to 2 TTS calls).",
    )
    parser.add_argument(
        "--voices", default=",".join(ALL_VOICES),
        help="Comma-separated voice-name subset (default: all 6).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Push generated MP3s into Anki + set audio fields (no synthesis).",
    )
    args = parser.parse_args()

    global PROFILE
    PROFILE = PROFILES[args.profile]
    print(f"Profile: {PROFILE.name}  (model={PROFILE.model!r})")

    if args.apply:
        apply_audio_to_anki(args.limit)
        return

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    _audio_dir().mkdir(parents=True, exist_ok=True)

    eligible = discover_eligible_notes(args.limit)
    work: list[tuple[str, int, str, str]] = []
    skipped_existing = 0
    for nid, hw, sent in eligible:
        word_path = _audio_dir() / filename_safe_word(nid)
        sent_path = _audio_dir() / filename_safe_sentence(nid)
        # "Raw exists" means a prior run already attempted this clip;
        # even if the trimmed file is gone (silence-flagged → deleted),
        # don't retry — Chirp3 is deterministic enough that a retry on
        # the same input gives the same silent result.
        word_attempted = word_path.exists() or raw_path(word_path).exists()
        sent_attempted = sent_path.exists() or raw_path(sent_path).exists()
        need_word = bool(hw) and not word_attempted
        need_sent = bool(sent) and not sent_attempted
        if not (need_word or need_sent):
            skipped_existing += 1
            continue
        voice = voice_for_note(nid, voices)
        work.append((voice, nid, hw, sent))

    buckets = {v: 0 for v in voices}
    char_total = 0
    for v, _, hw, sent in work:
        buckets[v] += 1
        char_total += len(hw) + len(sent)
    print(f"To process: {len(work)} notes  (~{char_total:,} chars)")
    print(f"Skipped (already on disk): {skipped_existing}")
    print("Per-voice distribution:")
    for v in voices:
        print(f"  {v:<10} {buckets[v]}")
    print()

    if not work:
        print("Nothing to synthesize. Use --apply to push generated audio to Anki.")
        return

    try:
        asyncio.run(run_generation(work, args.concurrency, voices))
    except KeyboardInterrupt:
        print("\nInterrupted. Partial state in", _audio_dir())
        sys.exit(130)


if __name__ == "__main__":
    main()
