"""Prints whether the local server answers on /api/health."""

import json
import sys
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5) as r:
        body = json.load(r)
    print("Server is running:", body.get("success"))
except Exception as e:  # noqa: BLE001
    print("Server did not answer yet:", e)
    print("Check logs\\server.log")
    sys.exit(1)
