#!/usr/bin/env python3
"""Serve dist/ on a free port and fetch every asset the app requests."""
import functools
import http.server
import json
import socketserver
import sys
import threading
import urllib.request
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"
if not DIST.is_dir():
    print("dist/ not built yet; run tools/build.py first", file=sys.stderr)
    sys.exit(1)

handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=str(DIST))


class Quiet(socketserver.TCPServer):
    allow_reuse_address = True


srv = Quiet(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d/" % port

assets = ["index.html", "app.js", "style.css",
          "data/manifest.json", "data/secplus-sy0701-1-1.json"]
bad = 0
for path in assets:
    try:
        with urllib.request.urlopen(base + path) as r:
            print("  %d  %8d B  %s" % (r.status, len(r.read()), path))
    except Exception as exc:
        print("  ERR            %s  %s" % (path, exc))
        bad += 1

with urllib.request.urlopen(base + "data/manifest.json") as r:
    m = json.load(r)
t = m["tests"][0]
print("\nmanifest entry -> %s" % t["title"])
print("  %s | %d questions | %d min | pass %d%%"
      % (t["objective"], t["questionCount"],
         t["recommendedMinutes"], t["passPercent"]))
print("  sections: %s" % " / ".join(t["sections"]))

srv.shutdown()
sys.exit(1 if bad else 0)
