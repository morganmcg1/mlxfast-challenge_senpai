#!/usr/bin/env python3
"""Emit `decode prefill passed max_abs_diff golden_hash16` from a
score.local-iterate.json, or five nans if it cannot be read."""
import json
import sys

try:
    doc = json.load(open(sys.argv[1]))
except Exception:
    print("nan nan nan nan nan")
    raise SystemExit

flat = {}


def walk(node, key=""):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, k)
    else:
        flat.setdefault(key, node)


walk(doc)
print(
    flat.get("decode_seconds_per_token", "nan"),
    flat.get("prefill_seconds_per_token", "nan"),
    flat.get("passed", "nan"),
    flat.get("max_abs_diff", "nan"),
    str(flat.get("golden_hash", "nan"))[:16],
)
