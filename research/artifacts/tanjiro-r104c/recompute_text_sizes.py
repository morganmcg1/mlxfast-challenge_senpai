#!/usr/bin/env python3
"""Post-hoc __text accounting for the R104-C host-side channel gate.

`size -m` on a relocatable .o reports an unnamed segment, so the gate script's
`/Segment __TEXT/` filter matched nothing and wrote textsum=0.  This recomputes
the aggregate from the surviving pass-2 objects without another build.
"""
import json
import os
import re
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OBJREL = ".build-worker/arm64-apple-macosx/release/MLXFastModel.build"
OUT = os.path.join(ROOT, "research/artifacts/tanjiro-r104c/hostgate/text_recomputed.json")

res = {}
for rev in ("old", "mid", "new"):
    d = os.path.join(ROOT, ".mlxfast-private", "r103b-" + rev, OBJREL)
    total = 0
    rows = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".o"):
            continue
        out = subprocess.run(["size", "-m", os.path.join(d, f)],
                             capture_output=True, text=True).stdout
        t = sum(int(m) for m in re.findall(r"Section \(__TEXT, __text\): (\d+)", out))
        total += t
        rows.append({"name": f, "text": t,
                     "file_bytes": os.path.getsize(os.path.join(d, f))})
    res[rev] = {"objects": len(rows), "total_text": total, "detail": rows}
    print("== %s: objects=%d TOTAL __text=%d" % (rev, len(rows), total))
    for r in rows:
        print("     %-40s __text=%9d  file=%d" % (r["name"], r["text"], r["file_bytes"]))

print()
for a, b in (("old", "mid"), ("mid", "new"), ("old", "new")):
    print("%s->%s: __text %d -> %d  delta=%+d"
          % (a, b, res[a]["total_text"], res[b]["total_text"],
             res[b]["total_text"] - res[a]["total_text"]))

with open(OUT, "w") as fh:
    json.dump(res, fh, indent=1)
print("\nwrote", OUT)
