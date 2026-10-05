#!/usr/bin/env python3
"""Local preview of public/ that mimics Vercel cleanUrls (/news/D/ID -> ID.html). Usage: preview_server.py [port]"""
import http.server, os, sys
from pathlib import Path
PUB = Path(__file__).resolve().parent.parent / "public"
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(PUB), **k)
    def translate_path(s, path):
        p = super().translate_path(path)
        if not os.path.exists(p) and os.path.exists(p + ".html"): return p + ".html"
        return p
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
