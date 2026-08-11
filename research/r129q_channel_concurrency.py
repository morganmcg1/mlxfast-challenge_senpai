#!/usr/bin/env python3
"""R129-Q: is the shared submission channel serial or concurrent?

Read-only. One GET against the benchmark's public `submissions` collection,
then pure arithmetic. NO submission is created; the only network call is the
listing GET (plus `--help` text from the CLI, which does not contact the API).

Every printed block carries the wall-clock UTC time of the poll it used.

Usage: research/r129q_channel_concurrency.py <fresh-snapshot-out.json> [old.json]
Reads MLXFAST_API_TOKEN from the environment.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import subprocess
import sys
import urllib.request

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
TOKEN = os.environ.get("MLXFAST_API_TOKEN", "")
BID = os.environ.get("MLXFAST_BENCHMARK_ID", "1854efdf-feba-4773-bae9-b80520881a74")
US = "morganmcg1"
TERMINAL = {"rejected", "failed", "accepted", "promoted"}
CLOSE = dt.datetime(2026, 8, 11, 17, 0, 0, tzinfo=dt.timezone.utc)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def hm(d: dt.datetime) -> str:
    return d.strftime("%H:%M:%SZ")


def get(path: str) -> dict:
    req = urllib.request.Request(
        API.rstrip("/") + path, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)["submissions"]


def sweep_max_concurrent(rows: list[dict], asof: dt.datetime):
    """Max simultaneously-non-terminal rows, from [createdAt, updatedAt]."""
    events = []
    for r in rows:
        a = ts(r["createdAt"])
        b = ts(r["updatedAt"]) if r.get("status") in TERMINAL else asof
        if b < a:
            b = a
        events.append((a, +1, r))
        events.append((b, -1, r))
    events.sort(key=lambda e: (e[0], -e[1]))
    cur = best = 0
    at = None
    witness: list[dict] = []
    live: list[dict] = []
    for t, d, r in events:
        if d > 0:
            live.append(r)
        else:
            live = [x for x in live if x["id"] != r["id"]]
        cur += d
        if cur > best:
            best, at, witness = cur, t, list(live)
    return best, at, witness


def main(argv: list[str]) -> int:
    out = argv[0]
    poll = now()
    print(f"POLL (fresh listing GET) at {poll.isoformat()}")
    rows = get(f"/api/benchmarks/{BID}/submissions")["submissions"]
    with open(out, "w") as f:
        json.dump({"submissions": rows, "polled_at": poll.isoformat()}, f)
    print(f"  fetched {len(rows)} rows -> {out}")

    # ---------------- Q1: scope of this listing ----------------
    print("\n=== Q1  LISTING SCOPE ===")
    owners: dict[str, int] = {}
    for r in rows:
        owners[r.get("solverUsername") or "<none>"] = owners.get(
            r.get("solverUsername") or "<none>", 0) + 1
    print(f"  rows carry owner fields: solverUsername / solverAccountId / "
          f"solverProfileUrl -> present on {sum(1 for r in rows if r.get('solverUsername'))}"
          f"/{len(rows)} rows")
    print(f"  distinct solverUsername values: {len(owners)}  => scope is GLOBAL "
          f"(multi-tenant), not account-scoped")
    for k, v in sorted(owners.items(), key=lambda kv: -kv[1])[:12]:
        print(f"    {v:5d}  {k}")
    ours = [r for r in rows if r.get("solverUsername") == US]
    print(f"  our account ({US}): {len(ours)} of {len(rows)} rows "
          f"({100.0*len(ours)/len(rows):.1f}%)")

    live_now = [r for r in rows if r.get("status") not in TERMINAL]
    print(f"\n  non-terminal rows in the GLOBAL listing at {hm(poll)}: {len(live_now)}")
    for r in sorted(live_now, key=lambda r: r["createdAt"]):
        age = (poll - ts(r["createdAt"])).total_seconds() / 60.0
        print(f"    {r['id'][:8]}  {r.get('solverUsername'):<12} {r.get('status'):<12} "
              f"created {hm(ts(r['createdAt']))}  age {age:6.1f} min"
              f"{'   <== OURS' if r.get('solverUsername') == US else ''}")

    # 12:06Z read reconciliation (the 9 validating rows / head-of-line ggt54)
    if len(argv) > 1 and os.path.exists(argv[1]):
        old = load(argv[1])
        oldlive = [r for r in old if r.get("status") not in TERMINAL]
        print(f"\n  RECONCILE my 12:06Z read, from {argv[1]} ({len(old)} rows):")
        print(f"    non-terminal then: {len(oldlive)}; owners: "
              f"{sorted({r.get('solverUsername') for r in oldlive})}")
        print(f"    ours among them: "
              f"{sum(1 for r in oldlive if r.get('solverUsername') == US)}")
        for r in sorted(oldlive, key=lambda r: r["createdAt"]):
            print(f"      {r['id'][:8]}  {r.get('solverUsername'):<12} "
                  f"{r.get('status'):<12} created {r['createdAt']}")
        for pref in ("ggt54", "ggu77wt"):
            hit = [r for r in old if r["id"].startswith(pref)
                   or (r.get("solverUsername") or "").startswith(pref)]
            print(f"    prefix {pref!r}: {len(hit)} match(es) "
                  f"-> {[(h['id'][:8], h.get('solverUsername')) for h in hit[:3]]}")

    # ---------------- UTC anchor check on createdAt ----------------
    print("\n=== UTC ANCHOR CHECK on createdAt (advisor asked for a 2nd anchor) ===")
    for pref in ("5fae2f13", "4be372f9"):
        hit = [r for r in rows if r["id"].startswith(pref)]
        for h in hit:
            print(f"  {h['id'][:8]}  createdAt {h['createdAt']}  "
                  f"updatedAt {h['updatedAt']}  status {h.get('status')}  "
                  f"score {h.get('officialScore')}")

    # ---------------- Q2: has OUR account ever held 2 in flight? ----------------
    print("\n=== Q2  CONCURRENCY: max simultaneously non-terminal rows ===")
    best_us, at_us, wit_us = sweep_max_concurrent(ours, poll)
    print(f"  our account, all {len(ours)} rows: MAX CONCURRENT = {best_us} "
          f"(first reached {at_us.isoformat() if at_us else 'n/a'})")
    if best_us >= 2:
        for w in wit_us:
            print(f"    witness {w['id'][:8]} created {w['createdAt']} "
                  f"updated {w['updatedAt']} status {w.get('status')}")

    per_owner = {}
    for r in rows:
        per_owner.setdefault(r.get("solverUsername") or "<none>", []).append(r)
    print("\n  same sweep for EVERY account (does the platform permit >=2 in flight?):")
    tbl = []
    for k, rs in per_owner.items():
        b, a, w = sweep_max_concurrent(rs, poll)
        tbl.append((b, len(rs), k, a, w))
    tbl.sort(key=lambda x: -x[0])
    for b, n, k, a, w in tbl[:12]:
        print(f"    max_concurrent {b:3d}  rows {n:5d}  {k:<14} first at "
              f"{a.isoformat() if a else 'n/a'}")
    permits = [t for t in tbl if t[0] >= 2]
    print(f"  accounts ever holding >=2 non-terminal simultaneously: "
          f"{len(permits)} of {len(tbl)}")
    if permits:
        b, n, k, a, w = permits[0]
        print(f"  EXAMPLE ({k}, {b} at once, {a.isoformat() if a else ''}):")
        for x in sorted(w, key=lambda r: r["createdAt"])[:6]:
            print(f"      {x['id'][:8]} created {x['createdAt']} "
                  f"updated {x['updatedAt']} status {x.get('status')}")

    b_all, a_all, _ = sweep_max_concurrent(rows, poll)
    print(f"  GLOBAL max concurrent (all accounts): {b_all} at "
          f"{a_all.isoformat() if a_all else 'n/a'} => the SERVICE is concurrent")

    # ---------------- power of the negative ----------------
    print("\n=== Q2b  POWER OF THE NEGATIVE (would we even see overlap?) ===")
    term = sorted([r for r in ours if r.get("status") in TERMINAL],
                  key=lambda r: r["createdAt"])
    soj = [(ts(r["updatedAt"]) - ts(r["createdAt"])).total_seconds() / 60.0
           for r in term]
    gaps = [(ts(term[i + 1]["createdAt"]) - ts(term[i]["createdAt"])).total_seconds() / 60.0
            for i in range(len(term) - 1)]
    print(f"  our terminal rows n={len(term)}; sojourn (createdAt->updatedAt) min: "
          f"median {statistics.median(soj):.1f}  p90 "
          f"{sorted(soj)[int(0.9*(len(soj)-1))]:.1f}  max {max(soj):.1f}")
    print(f"  our inter-arrival gaps n={len(gaps)}: median "
          f"{statistics.median(gaps):.1f}  p10 {sorted(gaps)[int(0.1*(len(gaps)-1))]:.1f}"
          f"  min {min(gaps):.1f}")
    viol = sum(1 for i in range(len(gaps)) if soj[i] > gaps[i])
    print(f"  rows whose OWN sojourn exceeded the gap to the NEXT fire: "
          f"{viol}/{len(gaps)} = {100.0*viol/max(1,len(gaps)):.1f}%")
    print("  => if admission were capped at 1, those fires could not have been "
          "admitted when they were; each is an overlap receipt.")

    # ---------------- Q4: age-of-queue arithmetic ----------------
    print("\n=== Q4  LAST FIRE FOR A 17:00Z ADJUDICATION (age-of-queue) ===")
    ages = sorted(((poll - ts(r["createdAt"])).total_seconds() / 60.0)
                  for r in live_now)
    print(f"  ages of the {len(ages)} rows resident RIGHT NOW (min): "
          f"{[round(a,1) for a in ages]}")
    if ages:
        print(f"    max resident age {max(ages):.1f} min  (a completed-service "
              f"percentile cannot see this tail)")
    recent = [r for r in term if ts(r["createdAt"]) > poll - dt.timedelta(hours=6)]
    rsoj = sorted((ts(r["updatedAt"]) - ts(r["createdAt"])).total_seconds() / 60.0
                  for r in recent)
    if rsoj:
        p50 = statistics.median(rsoj)
        p90 = rsoj[int(0.9 * (len(rsoj) - 1))]
        print(f"  our last-6h terminal rows n={len(rsoj)}: median {p50:.1f} "
              f"p90 {p90:.1f} max {max(rsoj):.1f} min")
        for label, budget in (("median", p50), ("p90", p90),
                              ("max-resident-age", max(ages) if ages else p90)):
            lf = CLOSE - dt.timedelta(minutes=budget)
            print(f"    budget={label:18s} {budget:6.1f} min -> LAST FIRE "
                  f"{hm(lf)}")
    # censored tail: resident rows are lower bounds on their own sojourn
    allsoj = sorted(soj + ages)
    if allsoj:
        print(f"  age-of-queue pool (terminal sojourns + current ages, "
              f"n={len(allsoj)}): p90 {allsoj[int(0.9*(len(allsoj)-1))]:.1f} "
              f"p95 {allsoj[int(0.95*(len(allsoj)-1))]:.1f} min")

    # ---------------- Q3: documented limits ----------------
    print("\n=== Q3  DOCUMENTED LIMITS (CLI help text; no API call) ===")
    for cmd in (["mlxfast", "--help"], ["mlxfast", "submissions", "--help"],
                ["mlxfast", "submit", "--help"]):
        print(f"\n  $ {' '.join(cmd)}")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            txt = (p.stdout or "") + (p.stderr or "")
            for line in txt.splitlines():
                print("    " + line)
            print(f"    [exit {p.returncode}]")
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED: {exc}")
    print(f"\nDONE at {now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
