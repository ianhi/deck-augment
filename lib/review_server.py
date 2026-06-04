"""Tiny localhost review server used by fix_*.py scripts.

Serves a directory of static files (manifest.json + a review HTML page +
before/after media) and accepts JSON POSTs that get written to disk
verbatim. The review HTML drives the interaction; the server only
persists what the page sends. Keeps each fix workflow's logic in its
own script while sharing this boilerplate.
"""
from __future__ import annotations

import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve_review(directory: Path, port: int, post_endpoint: str, out_filename: str, open_page: str | None = None) -> None:
    """Serve `directory` on 127.0.0.1:port.

    POSTs to `post_endpoint` (e.g. "/verdicts") have their body written to
    `directory / out_filename` and a 200 OK returned. Everything else
    behaves like SimpleHTTPRequestHandler.
    """
    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)
    os.chdir(directory)
    target_path = directory / out_filename

    class _Handler(SimpleHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != post_endpoint:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            target_path.write_bytes(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, fmt, *a):
            sys.stderr.write("  " + (fmt % a) + "\n")

    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"Serving {directory} on http://127.0.0.1:{port}/  (Ctrl-C to stop)")
    if open_page:
        webbrowser.open(f"http://127.0.0.1:{port}/{open_page}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
