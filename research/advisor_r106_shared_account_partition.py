#!/usr/bin/env python3
"""Partition the shared `morganmcg1` receipt corpus by owning launch.

WHY THIS EXISTS
---------------
Round-106 discovery.  The fork `morganmcg1/mlxfast-challenge_senpai` hosts at
least three concurrent Senpai launches -- `maple` (ours), `cedar`, `birch` --
and ALL of them submit official receipts through the single `morganmcg1`
solver account.  Every rule in the research state that was estimated over
"the morganmcg1 receipts" therefore rests on a corpus that may be a mixture of
launches with different code, different advisor branches and different trees.

That is not a small worry.  Rule 89.2's channel sigma, the merit table, and
the record-gap VOI table are all pooled statistics over that corpus.  If the
corpus is a mixture, the pooled spread is inflated by BETWEEN-LAUNCH tree
variation that has nothing to do with measurement noise.

This script extracts, for every morganmcg1 receipt, the fields that could act
as a launch fingerprint:

  * `harness_hash`     - hash of the delivered non-editable harness
  * `weights_hash`     - hash of the weight files
  * `golden_hash`      - reference token stream digest
  * baseline decode/prefill seconds-per-token of the SAME-SESSION paired base
  * note-derived markers: "Advisor HEAD is <sha>", `student maple-<name>`,
    `PR #NNN`, and the campaign tag in the title

and reports which of them actually separates launches.  READ-ONLY.

Usage:
    python3 research/advisor_r106_shared_account_partition.py [--who NAME]
"""
import argparse
import collections
import json
import os
import pathlib
import re
import statistics
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
MB_D = 0.013855009542
MB_P = 0.000372473193

HEAD_RE = re.compile(r"Advisor HEAD is[^0-9a-f]*([0-9a-f]{7,40})")
STUDENT_RE = re.compile(r"student[^`\w]*`?(maple|cedar|birch)-([a-z]+)`?", re.I)
BRANCH_RE = re.compile(r"\b(maple|cedar|birch)-(?:frieren|fern|tanjiro|nezuko|"
                       r"alphonse|thorfinn|edward|askeladd)\b", re.I)
PR_RE = re.compile(r"\bPRs?\s*#(\d+)")
TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="morganmcg1")
    a = ap.parse_args()

    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    rows = [s for s in subs if s.get("solverUsername") == a.who]
    rows.sort(key=ts_of)

    recs = []
    for s in rows:
        m = s.get("officialMetrics") or {}
        note = s.get("note") or ""
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        cs = (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25 if (d and p) else None
        mh = HEAD_RE.search(note)
        launch = ""
        ms = STUDENT_RE.search(note) or BRANCH_RE.search(note)
        if ms:
            launch = ms.group(1).lower()
        title = ""
        mt = TITLE_RE.search(note)
        if mt:
            title = mt.group(1).strip()[:64]
        recs.append(dict(
            ts=ts_of(s), sha=(s.get("submissionCommitSha") or "")[:12],
            status=s.get("status"), cs=cs,
            dec=d * 1e6 if d else None, pre=p * 1e6 if p else None,
            bdec=m.get("baseline_decode_seconds_per_token"),
            bpre=m.get("baseline_prefill_seconds_per_token"),
            harness=(m.get("harness_hash") or "")[:12],
            golden=(m.get("golden_hash") or "")[:12],
            weights=(m.get("weights_hash") or "")[:12],
            ahead=(mh.group(1)[:12] if mh else ""),
            launch=launch, title=title, note_len=len(note),
        ))

    scored = [r for r in recs if r["cs"] is not None]
    print(f"benchmark {bid}   {len(rows)} {a.who} records   {len(scored)} scored\n")

    for field in ("harness", "golden", "weights"):
        c = collections.Counter(r[field] for r in scored)
        print(f"--- distinct {field}_hash over {len(scored)} scored receipts: "
              f"{len(c)}")
        for k, v in c.most_common(12):
            print(f"      {k or '(none)'}  n={v}")
        print()

    print("--- launch attribution from note text ---")
    c = collections.Counter(r["launch"] or "(unattributed)" for r in scored)
    for k, v in c.most_common():
        print(f"      {k}  n={v}")
    print()

    print("--- advisor HEAD named in note ---")
    c = collections.Counter(r["ahead"] or "(none)" for r in scored)
    for k, v in c.most_common(20):
        print(f"      {k}  n={v}")
    print()

    print("--- does harness_hash separate launches? ---")
    tab = collections.defaultdict(collections.Counter)
    for r in scored:
        tab[r["harness"]][r["launch"] or "(unattributed)"] += 1
    for h, cc in sorted(tab.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"      {h}: " + ", ".join(f"{k}={v}" for k, v in cc.most_common()))
    print()

    print("--- baseline drift (same-session paired base, seconds/token) ---")
    bd = [r["bdec"] for r in scored if r["bdec"]]
    bp = [r["bpre"] for r in scored if r["bpre"]]
    for nm, v, ref in (("baseline_decode", bd, MB_D), ("baseline_prefill", bp, MB_P)):
        if len(v) > 1:
            print(f"      {nm}: n={len(v)} mean={statistics.mean(v):.12g} "
                  f"sd={statistics.pstdev(v):.4g} "
                  f"cv={100*statistics.pstdev(v)/statistics.mean(v):.4f}% "
                  f"min={min(v):.12g} max={max(v):.12g} "
                  f"(cs constant uses {ref:.12g})")
    print()

    print("=== full scored ledger (chronological) ===")
    print(f"{'ts':<22}{'sha':<14}{'launch':<8}{'harness':<14}"
          f"{'bdec':<16}{'cs':<11}{'status':<10}title")
    for r in scored:
        print(f"{r['ts']:<22}{r['sha']:<14}{(r['launch'] or '?'):<8}"
              f"{r['harness']:<14}{(r['bdec'] or 0):<16.12g}"
              f"{r['cs']:<11.6f}{str(r['status']):<10}{r['title']}")


if __name__ == "__main__":
    main()
