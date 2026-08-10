#!/usr/bin/env python3
"""Dump the COMPLETE raw record for named receipts, to settle provenance.

WHY THIS EXISTS
---------------
Round-106.  Two receipts landed on the shared `morganmcg1` solver account at
08:03:15Z and 08:26:50Z on 2026-08-10 carrying NO campaign tag and NO arm
label -- the first untagged receipts of the campaign.  One of them,
`5c542169b5e6`, scores cs 2.590753, which is above our best-ever recorded
2.590559.  Before that number can enter the merit table it has to be
attributed, and before frieren fires her one Rule-88 shot she has to know
whether the validation channel is contested.

The standing attribution rule (advisor_r105_ladder_monitor.py docstring) is:
attribute by `submissionCommitSha` AND `note`; the solver username is neither.
`git cat-file` on a submissionCommitSha is USELESS as a provenance test --
submission commits are never pushed, so even receipts we know are ours are
absent from the local object store.

So this script does the only thing left: prints every field of the raw record,
verbatim, including the full free-text note.  READ-ONLY.

Usage:
    python3 research/advisor_r106_untagged_receipt_provenance.py SHA_PREFIX...
    python3 research/advisor_r106_untagged_receipt_provenance.py --since ISO
"""
import argparse
import json
import os
import pathlib
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
MB_D = 0.013855009542
MB_P = 0.000372473193


def token():
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def ts_of(s):
    m = s.get("officialMetrics")
    if isinstance(m, dict) and m.get("timestamp"):
        return str(m["timestamp"])
    return str(s.get("createdAt") or s.get("updatedAt") or "")


def cs_of(s):
    m = s.get("officialMetrics")
    if not isinstance(m, dict):
        return None
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if not (d and p):
        return None
    return (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25


def redact(v):
    """Never echo anything that smells like a credential."""
    if isinstance(v, str) and len(v) > 24 and any(
            k in v.lower() for k in ("token", "secret", "bearer")):
        return "<redacted>"
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shas", nargs="*", help="submissionCommitSha prefixes")
    ap.add_argument("--since", default=None)
    ap.add_argument("--who", default=None,
                    help="restrict to a solver username (default: all)")
    a = ap.parse_args()

    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    print(f"benchmark {bid}   {len(subs)} raw records")
    solvers = {}
    for s in subs:
        solvers[s.get("solverUsername")] = solvers.get(s.get("solverUsername"), 0) + 1
    print("solver accounts seen: " + ", ".join(
        f"{k}={v}" for k, v in sorted(solvers.items(), key=lambda kv: -kv[1])))
    print()

    def want(s):
        if a.who and s.get("solverUsername") != a.who:
            return False
        if a.since and ts_of(s) < a.since:
            return False
        if a.shas:
            sha = str(s.get("submissionCommitSha") or "")
            if not sha:
                return False
            return any(sha.startswith(p) or p.startswith(sha) for p in a.shas)
        return bool(a.since)

    hits = [s for s in subs if want(s)]
    hits.sort(key=ts_of)
    print(f"=== {len(hits)} matching record(s) ===\n")
    for s in hits:
        cs = cs_of(s)
        print("=" * 78)
        print(f"ts   {ts_of(s)}")
        print(f"sha  {s.get('submissionCommitSha')}")
        print(f"who  {s.get('solverUsername')}")
        print(f"cs   {cs if cs is None else round(cs, 6)}")
        print("-" * 78)
        for k in sorted(s.keys()):
            v = s[k]
            if k == "note":
                continue
            if isinstance(v, (dict, list)):
                print(f"{k}: {json.dumps(v, indent=2, sort_keys=True)[:4000]}")
            else:
                print(f"{k}: {redact(v)!r}")
        note = s.get("note")
        print("-" * 78)
        print("NOTE (verbatim, full):")
        print(note if note else "<empty / absent>")
        print()


if __name__ == "__main__":
    main()
