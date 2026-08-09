#!/usr/bin/env python3
"""Print full submissionCommitSha for the six ranked receipts from the provenance artifact."""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROV = os.path.join(REPO, "research", "artifacts", "advisor-r103",
                    "our-receipts-provenance.json")

WANT = ["25e1f18e", "7ce1262d", "83fd2642", "05dd8bbf", "e08d759f", "59bd72a3"]

rows = json.load(open(PROV))
by = {}
for r in rows:
    by[str(r.get("id8", ""))[:8]] = r

for w in WANT:
    r = by.get(w)
    if not r:
        print(f"{w}: NOT FOUND")
        continue
    print(f"{w}  cs={r.get('cs')}  status={r.get('status')} promoted={r.get('promoted')}")
    print(f"    sub_sha={r.get('sub_sha')}")
    print(f"    met_commit={r.get('met_commit')}")

print("\n--- most recent 30 receipts ---")
rows_sorted = sorted(rows, key=lambda r: r.get("ts") or "", reverse=True)
for r in rows_sorted[:30]:
    print(f"{r.get('ts')}  {r.get('id8')}  cs={r.get('cs')}  {r.get('sub_sha')}")
