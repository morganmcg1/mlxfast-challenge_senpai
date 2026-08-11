#!/usr/bin/env python3
"""Fetch one submission receipt and print its raw benchmark legs.

Usage: fetch_receipt.py <submission-id-or-prefix> [...]
Reads MLXFAST_API_TOKEN from the environment.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
TOKEN = os.environ.get("MLXFAST_API_TOKEN", "")


def get(path: str) -> dict:
    req = urllib.request.Request(
        API.rstrip("/") + path,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str]) -> int:
    for sid in argv:
        encoded = urllib.parse.quote(sid, safe="")
        row = get(f"/api/submissions/{encoded}")["submission"]
        print(json.dumps(row, indent=2, sort_keys=True))
        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
