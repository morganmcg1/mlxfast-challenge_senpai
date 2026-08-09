#!/usr/bin/env python3
"""Fetch one full MLXFast submission receipt as JSON."""

import json
import pathlib
import sys
import urllib.parse
import urllib.request

cfg = json.loads(pathlib.Path.home().joinpath(".config/mlxfast/config.json").read_text())
base = cfg.get("apiBaseUrl", "https://api.mlx.fast").rstrip("/")
token = cfg["token"]
submission_id = sys.argv[1]
request = urllib.request.Request(
    f"{base}/api/submissions/{urllib.parse.quote(submission_id, safe='')}",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    row = json.load(response)
out = pathlib.Path(sys.argv[2])
out.write_text(json.dumps(row, indent=2, sort_keys=True))
print(f"wrote {out} ({out.stat().st_size} bytes)")
