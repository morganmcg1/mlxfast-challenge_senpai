#!/usr/bin/env python3
"""Freeze the ranked-receipt corpus with `submissionCommitSha` retained.

WHY A NEW PULLER
----------------
`advisor_r103_freeze_corpus.py` drops `submissionCommitSha` from its frozen
records.  r106-B's whole variance argument is keyed on that field: a *replicate
group* is defined as the set of receipts sharing one identical submission sha,
because identical sha means identical submitted bytes, so all spread inside the
group is measurement noise.  Attributing by `solverUsername` is explicitly wrong
(advisor-r105 standing correction), so the sha is the only usable identity and it
has to survive the freeze.

Everything else follows `advisor_r105_ladder_monitor.py`: same benchmark ref,
same auth, same metric keys, same timestamp fallback order.

READ-ONLY.  Two GETs, no POST/PUT/PATCH, no submission path.

Usage:
    python3 research/nezuko_r106b_pull_corpus.py --out research/artifacts/...json
"""
import argparse
import hashlib
import json
import os
import pathlib
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")

KEEP = (
    "id",
    "submissionCommitSha",
    "solverUsername",
    "solverModel",
    "note",
    "status",
    "createdAt",
    "updatedAt",
)


def token():
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    raise SystemExit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")


def get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    rows = []
    for s in subs:
        r = {k: s.get(k) for k in KEEP}
        m = s.get("officialMetrics")
        r["officialMetrics"] = m if isinstance(m, dict) else None
        rows.append(r)
    rows.sort(key=lambda r: str(r.get("createdAt") or ""))

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmarkId": bid,
        "benchmarkRef": BENCHMARK,
        "count": len(rows),
        "withSha": sum(1 for r in rows if r["submissionCommitSha"]),
        "withMetrics": sum(1 for r in rows if r["officialMetrics"]),
        "submissions": rows,
    }
    blob = json.dumps(payload, indent=1, sort_keys=True).encode()
    out.write_bytes(blob)
    print(f"benchmark {bid}")
    print(f"wrote {out}  {len(blob)} bytes  sha256={hashlib.sha256(blob).hexdigest()}")
    print(f"records={payload['count']}  withSha={payload['withSha']}  "
          f"withMetrics={payload['withMetrics']}")


if __name__ == "__main__":
    main()
