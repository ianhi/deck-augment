"""Small helper for talking to a local AnkiConnect server.

Requires Anki Desktop running with the AnkiConnect add-on installed,
listening on the default port 8765.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

ANKICONNECT_URL = "http://localhost:8765"


def ac(action: str, **params: Any) -> Any:
    """Call an AnkiConnect action and return its result.

    Raises RuntimeError if AnkiConnect reports an error, which typically means
    Anki is not running or the add-on is not installed.
    """
    req = json.dumps({"action": action, "version": 6, "params": params}).encode()
    with urllib.request.urlopen(ANKICONNECT_URL, req) as r:
        resp = json.loads(r.read())
    if resp.get("error"):
        raise RuntimeError(f"{action}: {resp['error']}")
    return resp["result"]
