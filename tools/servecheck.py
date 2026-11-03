#!/usr/bin/env python3
"""Verify every asset the app will request is present and served.

Two layers:
  1. On-disk check. Always runs. Every file named in the manifest must exist
     and be non-empty. This is the substantive check and it gates the exit code.
  2. HTTP check. Serves dist/ on an ephemeral port and fetches each asset.
     Some sandboxes forbid binding a socket; when that happens the layer is
     reported as skipped rather than failing, because an environment
     restriction is not a defect in the site.
"""
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

manifest_path = DIST / "data" / "manifest.json"
if not manifest_path.is_file():
    print("dist/data/manifest.json is missing", file=sys.stderr)
    sys.exit(1)

listed = json.loads(manifest_path.read_text(encoding="utf-8"))["tests"]

assets = ["index.html", "app.js", "style.css", "data/manifest.json"]
for entry in listed:
    assets.append("data/%s.json" % entry["id"])
    if entry.get("paper"):
        assets.append(entry["paper"])

# ── layer 1: on disk ───────────────────────────────────────────────
print("on disk")
missing = 0
for rel in assets:
    path = DIST / rel
    if not path.is_file():
        print("  MISSING          %s" % rel)
        missing += 1
    elif path.stat().st_size == 0:
        print("  EMPTY            %s" % rel)
        missing += 1
    else:
        print("  ok   %9d B  %s" % (path.stat().st_size, rel))

if missing:
    print("\n%d asset(s) missing or empty" % missing, file=sys.stderr)
    sys.exit(1)

# ── layer 2: over HTTP ─────────────────────────────────────────────
print("\nover HTTP")


class Quiet(socketserver.TCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass


handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=str(DIST))
try:
    srv = Quiet(("127.0.0.1", 0), handler)
except (PermissionError, OSError) as exc:
    print("  skipped: this environment does not permit binding a local "
          "socket (%s)." % exc)
    print("  The on-disk check above already confirmed every asset.")
    sys.exit(0)

port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d/" % port

bad = 0
try:
    for rel in assets:
        try:
            with urllib.request.urlopen(base + rel, timeout=10) as r:
                print("  %d  %9d B  %s" % (r.status, len(r.read()), rel))
        except Exception as exc:
            print("  ERR              %s  %s" % (rel, exc))
            bad += 1
finally:
    srv.shutdown()
    srv.server_close()

print("\n%d test(s) published:" % len(listed))
for t in listed:
    print("  %s  %d questions, %d min, pass %d%%"
          % (t["title"], t["questionCount"],
             t["recommendedMinutes"], t["passPercent"]))

sys.exit(1 if bad else 0)
