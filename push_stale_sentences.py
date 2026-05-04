"""Push only the re-rendered sentence audio files to Anki via storeMediaFile.

Filenames stay the same (conj_<nid>_sentence.mp3) so existing field references
remain valid — this is a pure media overwrite.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request
from pathlib import Path

ANKICONNECT = "http://localhost:8765"
HERE = Path(__file__).parent
AUDIO_DIR = HERE / "out" / "conjugation_audio"
CHANGED = HERE / "out" / "quality_review" / "sent_changed_ids.json"
BATCH = 25


def call(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKICONNECT, data=payload,
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("error"):
        raise RuntimeError(f"{action}: {resp['error']}")
    return resp["result"]


def main():
    nids = json.loads(CHANGED.read_text())
    print(f"{len(nids)} sentence audio files to push")
    missing = [n for n in nids if not (AUDIO_DIR / f"{n}_sentence.mp3").exists()]
    if missing:
        print(f"WARN: {len(missing)} missing local files; skipping them")
    nids = [n for n in nids if (AUDIO_DIR / f"{n}_sentence.mp3").exists()]

    t0 = time.time()
    done = 0
    for i in range(0, len(nids), BATCH):
        batch = nids[i:i+BATCH]
        actions = []
        for n in batch:
            p = AUDIO_DIR / f"{n}_sentence.mp3"
            actions.append({
                "action": "storeMediaFile",
                "params": {
                    "filename": f"conj_{n}_sentence.mp3",
                    "data": base64.b64encode(p.read_bytes()).decode(),
                },
            })
        call("multi", actions=actions)
        done += len(batch)
        if done % 200 == 0 or done == len(nids):
            rate = done / (time.time() - t0)
            print(f"  [{done}/{len(nids)}] {rate:.1f}/s")
    print(f"Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
