#!/usr/bin/env python3
"""Round-105 receipt forensics: provenance, field parity, and note mining.

One corpus pull, three questions.

  Q1  PROVENANCE.  §11.4 of advisor-r104-the-receipt-is-the-instrument.md says
      attribute a receipt by its `submissionCommitSha`, never by
      `solverUsername`.  This script tests that rule against the live corpus:
      for every receipt carrying a given solver name it asks whether the
      commit exists in THIS checkout.  A receipt whose commit is not reachable
      here was not produced by this campaign, whatever name is on it.

  Q2  PARITY.  Refreshes research/advisor_r104_field_parity.py from live data
      instead of a frozen 2026-08-09T23:20Z snapshot, for every solver with
      enough metric-bearing receipts in the trailing window.

  Q3  NOTES.  The `note` field carries the solver's own free-text write-up of
      the mechanism they tried.  It is a rich, previously unexploited
      intelligence channel.  This prints a ranked index and can dump bodies.

Everything here is READ-ONLY: GETs against the MLXFast API, and
`git cat-file` / `git log` against the local checkout.

Operating notes (round 105, learned the hard way):
  * The API base URL is https://api.mlx.fast .  The older
    https://mlxfast.eigenlabs.org host is DEAD -- its name resolves to nothing
    and reaching the apex Cloudflare IP with an SNI override returns HTTP 530
    (Cloudflare error 1016, "Origin DNS error").  Never use it.
  * A submission record has NO top-level `timestamp` field.  Use `createdAt`
    (or `updatedAt`); `officialMetrics.timestamp` also exists on scored
    records.  Filtering on a top-level `timestamp` silently yields zero rows.
  * `GET /api/benchmarks/{urlquoted ref}` returns {"benchmark": {...}} -- the
    id is NESTED.  `GET /api/benchmarks/{id}/submissions` returns
    {"submissions": [...]}.

Usage:
    python3 research/advisor_r105_receipt_forensics.py [--since ISO8601]
                                                       [--who NAME]
                                                       [--notes N]
                                                       [--grep PATTERN]
"""
import argparse
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")

# Round-103 flagship constants.
MB_D = 0.013855009542
MB_P = 0.000372473193
OUR_CS = 2.583111        # honest geometric-mean cs of our tree
SD_LN_CS = 0.001860      # 0.1860 %, trimmed dof-14 identical-code noise floor


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
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


def pull():
    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))
    return bid, subs


def ts_of(s):
    """The only reliable timestamps on a submission record."""
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


# --------------------------------------------------------------------------
# Q1 provenance
# --------------------------------------------------------------------------
def local_commit(sha):
    if not sha:
        return None
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                       capture_output=True)
    if r.returncode != 0:
        return None
    rr = subprocess.run(["git", "log", "-1", "--format=%ad %an %s", "--date=short", sha],
                        capture_output=True, text=True)
    return rr.stdout.strip()


def provenance(subs, who, since):
    rows = [s for s in subs
            if (who is None or s.get("solverUsername") == who)
            and ts_of(s) >= since]
    rows.sort(key=ts_of)
    label = who or "(all solvers)"
    print(f"=== Q1 PROVENANCE: {len(rows)} receipts for {label} since {since} ===")
    n_local = 0
    for s in rows:
        sha = s.get("submissionCommitSha") or ""
        desc = local_commit(sha)
        n_local += desc is not None
        m = s.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        cs = cs_of(s)
        print(f"{ts_of(s)}  {(sha or '(none)')[:12]:12s}  "
              f"{'LOCAL' if desc else 'not-in-this-checkout':20s}  "
              f"dec {d * 1e6 if d else float('nan'):9.3f}  "
              f"pre {p * 1e6 if p else float('nan'):8.4f}  "
              f"cs {cs if cs else float('nan'):.6f}  {s.get('status')}")
        if desc:
            print(f"      -> {desc[:100]}")
    print(f"\n  reachable in THIS checkout: {n_local} / {len(rows)}")
    if rows and n_local == 0:
        print("  VERDICT: none of these receipts came from this checkout.  The "
              "solver account is shared; attribute by commit, not by name "
              "(advisor-r104 §11.4).")
    return rows


# --------------------------------------------------------------------------
# Q2 parity
# --------------------------------------------------------------------------
def geo_mean(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def sd_ln(xs):
    ls = [math.log(x) for x in xs]
    m = sum(ls) / len(ls)
    return (sum((x - m) ** 2 for x in ls) / (len(ls) - 1)) ** 0.5


def chi2_sf(x, dof):
    """P(chi2_dof > x).  Exact closed form for even dof; Wilson-Hilferty else."""
    if dof % 2 == 0:
        k = dof // 2
        term, tot = 1.0, 1.0
        for i in range(1, k):
            term *= (x / 2.0) / i
            tot += term
        return math.exp(-x / 2.0) * tot
    z = ((x / dof) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * dof))) / math.sqrt(2.0 / (9.0 * dof))
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def parity(subs, since, min_n=3):
    by = {}
    for s in subs:
        cs = cs_of(s)
        if cs is None or ts_of(s) < since:
            continue
        by.setdefault(s.get("solverUsername") or "?", []).append((ts_of(s), cs))
    print(f"\n=== Q2 FIELD PARITY vs our honest cs {OUR_CS:.6f}, "
          f"receipts since {since} ===")
    print("  (identical-code floor sd(ln cs) = %.4f %%, dof 14)" % (100 * SD_LN_CS))
    for who, vals in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(vals) < min_n:
            continue
        vals.sort()
        cs_values = [c for _, c in vals]
        n = len(cs_values)
        m = math.log(geo_mean(cs_values))
        sd = sd_ln(cs_values)
        d = m - math.log(OUR_CS)
        se = SD_LN_CS / math.sqrt(n)
        lo, hi = d - 1.96 * se, d + 1.96 * se
        stat = (n - 1) * (sd / SD_LN_CS) ** 2
        pv = chi2_sf(stat, n - 1)
        print(f"\n{who}: n={n}  geo-mean cs {math.exp(m):.6f} "
              f"({100 * (math.exp(m) / OUR_CS - 1):+.4f} % vs ours)  "
              f"best {max(cs_values):.6f}")
        print(f"    their sd(ln cs) = {100 * sd:.4f} %   "
              f"chi2 = {stat:.2f} on {n - 1} dof, p = {pv:.4f}  -> "
              f"{'ONE fixed tree measured n times' if pv > 0.05 else 'MORE THAN ONE TREE (spread exceeds identical-code noise)'}")
        print(f"    z = {d / se:+.2f}   95 % CI [{100 * lo:+.3f} %, {100 * hi:+.3f} %]"
              f"  => {'PARITY' if lo < 0 < hi else 'a real difference'}")
        print(f"    window {vals[0][0]} .. {vals[-1][0]}")


# --------------------------------------------------------------------------
# Q3 notes
# --------------------------------------------------------------------------
FILE_RE = re.compile(r"[A-Za-z0-9_./-]+\.(?:swift|cpp|h|metal|json|py|md)")


def notes(subs, since, top, pattern):
    rows = [s for s in subs if (s.get("note") or "").strip() and ts_of(s) >= since]
    rows.sort(key=ts_of, reverse=True)
    rx = re.compile(pattern, re.I) if pattern else None
    if rx:
        rows = [s for s in rows if rx.search(s["note"])]
    print(f"\n=== Q3 NOTES: {len(rows)} receipts with a non-empty note since {since}"
          + (f", matching /{pattern}/" if pattern else "") + " ===")
    files = {}
    for s in rows:
        for f in FILE_RE.findall(s["note"] or ""):
            files[f] = files.get(f, 0) + 1
    if files:
        print("\n  files named across those notes (top 25):")
        for f, c in sorted(files.items(), key=lambda kv: -kv[1])[:25]:
            print(f"    {c:4d}  {f}")
    print()
    for s in rows[:top]:
        cs = cs_of(s)
        head = (s["note"] or "").strip().splitlines()
        print("-" * 78)
        print(f"{ts_of(s)}  {s.get('solverUsername')}  {s.get('status')}  "
              f"cs {cs if cs else float('nan'):.6f}  "
              f"commit {(s.get('submissionCommitSha') or '')[:12]}")
        for line in head[:14]:
            print(f"  | {line[:110]}")
        if len(head) > 14:
            print(f"  | ... (+{len(head) - 14} more lines)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-09T00:00:00Z")
    ap.add_argument("--who", default="morganmcg1")
    ap.add_argument("--notes", type=int, default=6)
    ap.add_argument("--grep", default=None)
    ap.add_argument("--skip", default="", help="comma list of q1,q2,q3 to skip")
    a = ap.parse_args()
    skip = set(x.strip() for x in a.skip.split(",") if x.strip())

    bid, subs = pull()
    print(f"benchmark {bid}   pulled {len(subs)} raw submission records\n")
    if "q1" not in skip:
        provenance(subs, a.who, a.since)
    if "q2" not in skip:
        parity(subs, a.since)
    if "q3" not in skip:
        notes(subs, a.since, a.notes, a.grep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
