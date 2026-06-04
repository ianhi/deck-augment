"""Delete orphan conj_<nid>_word.mp3 files from Anki collection.media.

The cloze layout never plays per-word audio — only sentence audio is wired up.
The word mp3s were uploaded by the original push script and are now dead weight.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ANKICONNECT = "http://localhost:8765"
HERE = Path(__file__).resolve().parents[1]
NOTES = HERE / "out" / "conjugation_notes.json"
BATCH = 50


def call(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKICONNECT, data=payload,
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("error"):
        raise RuntimeError(f"{action}: {resp['error']}")
    return resp["result"]


def main():
    notes = json.loads(NOTES.read_text())
    nids = [n["note_id"] for n in notes]
    print(f"{len(nids)} candidate orphan word files to delete")

    # Confirm presence via getMediaFilesNames
    existing = set(call("getMediaFilesNames", pattern="conj_*_word.mp3"))
    print(f"  {len(existing)} actually present in collection.media")

    targets = [f"conj_{n}_word.mp3" for n in nids if f"conj_{n}_word.mp3" in existing]
    print(f"  {len(targets)} to delete")

    t0 = time.time()
    done = 0
    for i in range(0, len(targets), BATCH):
        batch = targets[i:i+BATCH]
        actions = [{"action": "deleteMediaFile", "params": {"filename": fn}} for fn in batch]
        call("multi", actions=actions)
        done += len(batch)
        if done % 500 == 0 or done == len(targets):
            rate = done / (time.time() - t0)
            print(f"  [{done}/{len(targets)}] {rate:.1f}/s")
    print(f"Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
