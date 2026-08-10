#!/usr/bin/env python3
"""Is `cs` or `officialScore` the lower-variance receipt instrument?

WHY THIS EXISTS
---------------
The campaign has spent six rounds ranking trees by `cs`, a renormalisation of
each receipt's candidate timings against FIXED constants MB_D / MB_P.  The
leaderboard, however, ranks by `officialScore`, which the harness computes
against a baseline it MEASURES IN THE SAME SESSION as the candidate:

    officialScore = (bdec/dec)^0.75 * (bpre/pre)^0.25
    cs            = (MB_D/dec)^0.75 * (MB_P/pre)^0.25

The campaign adopted `cs` on the reasoning that dividing by a noisy measured
baseline injects that baseline's noise, and it explained the leaderboard record
(officialScore 2.61650, cs only 2.574594) as a "+3.03 sigma lucky baseline".

That reasoning is only correct if the session-to-session baseline wobble is
INDEPENDENT of the candidate's own wobble.  If instead both are driven by a
common session/thermal state, the same-session baseline is a CONTROL, the
official ratio removes the drift, and `cs` is the inferior instrument -- in
which case there was no luck, the record is real, and six rounds of merit
ranking have been done with a noisier yardstick than the one already printed
on every receipt.

The discriminator needs no new receipts.  Writing

    ln officialScore = ln cs + f,      f := 0.75 ln(bdec/MB_D) + 0.25 ln(bpre/MB_P)

we have var(ln official) = var(ln cs) + var(f) + 2 cov(ln cs, f).
  * independent baseline  =>  cov = 0  =>  official is strictly NOISIER.
  * common-mode session   =>  cov < 0  =>  official can be QUIETER.
So the sign of cov(ln cs, f) -- equivalently corr(ln dec, ln bdec) -- decides
it, and both are computable from the 84 scored receipts already in hand.

READ-ONLY.  Usage:
    python3 research/advisor_r106_baseline_pairing_test.py
"""
import collections
import json
import math
import os
import pathlib
import statistics
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


def corr(x, y):
    n = len(x)
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def fisher_ci(r, n, z=1.96):
    if n < 4 or not (-1 < r < 1):
        return (float("nan"), float("nan"))
    zr = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    return tuple(math.tanh(zr + s * z * se) for s in (-1, 1))


def main():
    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    R = []
    for s in subs:
        if s.get("solverUsername") != "morganmcg1":
            continue
        m = s.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp):
            continue
        R.append(dict(
            ts=str(m.get("timestamp")), sha=(s.get("submissionCommitSha") or "")[:12],
            d=d, p=p, bd=bd, bp=bp,
            official=s.get("officialScore"),
            note=(s.get("note") or ""),
        ))
    R.sort(key=lambda r: r["ts"])
    n = len(R)
    print(f"{n} scored morganmcg1 receipts with a same-session paired baseline\n")

    ld = [math.log(r["d"]) for r in R]
    lp = [math.log(r["p"]) for r in R]
    lbd = [math.log(r["bd"]) for r in R]
    lbp = [math.log(r["bp"]) for r in R]
    lcs = [0.75 * (math.log(MB_D) - a) + 0.25 * (math.log(MB_P) - c)
           for a, c in zip(ld, lp)]
    f = [0.75 * (a - math.log(MB_D)) + 0.25 * (c - math.log(MB_P))
         for a, c in zip(lbd, lbp)]
    loff = [a + b for a, b in zip(lcs, f)]
    # sanity: reconstructed official score must match the API's officialScore
    err = [abs(math.exp(a) - r["official"]) / r["official"]
           for a, r in zip(loff, R) if r["official"]]
    print(f"reconstruction check vs API officialScore: max rel err "
          f"{max(err):.3e} over n={len(err)}\n")

    print("--- 1. is the session baseline common-mode with the candidate? ---")
    for nm, a, bb in (("decode   ln(cand) vs ln(baseline)", ld, lbd),
                      ("prefill  ln(cand) vs ln(baseline)", lp, lbp)):
        r = corr(a, bb)
        lo, hi = fisher_ci(r, n)
        print(f"    {nm}: r = {r:+.4f}   95% CI [{lo:+.4f}, {hi:+.4f}]")
    r = corr(lcs, f)
    lo, hi = fisher_ci(r, n)
    print(f"    corr(ln cs, f)                  : r = {r:+.4f}   "
          f"95% CI [{lo:+.4f}, {hi:+.4f}]")
    print("      (cov<0 favours officialScore; cov=0 favours cs)\n")

    print("--- 2. spread of the two instruments over the same 84 receipts ---")
    for nm, v in (("ln cs           ", lcs), ("ln officialScore", loff),
                  ("f (baseline fac)", f)):
        print(f"    sd({nm}) = {100*statistics.pstdev(v):.4f} %")
    vc, vo = statistics.pvariance(lcs), statistics.pvariance(loff)
    print(f"    var ratio official/cs = {vo/vc:.4f}   "
          f"({'official QUIETER' if vo < vc else 'official NOISIER'})\n")

    print("--- 3. same-tree replicates (identical submissionCommitSha) ---")
    g = collections.defaultdict(list)
    for i, r in enumerate(R):
        if r["sha"]:
            g[r["sha"]].append(i)
    reps = {k: v for k, v in g.items() if len(v) > 1}
    if not reps:
        print("    none: every scored receipt has a distinct submission commit\n")
    for k, idx in reps.items():
        print(f"    {k} n={len(idx)}  "
              f"sd(ln cs)={100*statistics.pstdev([lcs[i] for i in idx]):.4f} %  "
              f"sd(ln off)={100*statistics.pstdev([loff[i] for i in idx]):.4f} %")
    print()

    print("--- 4. the leaderboard record, re-read ---")
    best = max(R, key=lambda r: r["official"] or 0)
    print(f"    our best officialScore receipt: {best['sha']} {best['ts']} "
          f"official={best['official']:.6f}")
    print(f"    record to beat = 2.61650354381456")
    print(f"    gap in ln(officialScore) = "
          f"{100*(math.log(2.61650354381456) - math.log(best['official'])):.4f} %")
    bestcs = max(range(n), key=lambda i: lcs[i])
    print(f"    our best cs receipt           : {R[bestcs]['sha']} "
          f"{R[bestcs]['ts']} cs={math.exp(lcs[bestcs]):.6f} "
          f"official={R[bestcs]['official']:.6f}")
    print()

    print("--- 5. ledger, both instruments ---")
    print(f"{'ts':<22}{'sha':<14}{'cs':<11}{'official':<11}{'f %':<10}launch")
    for i, r in enumerate(R):
        lz = "maple" if "maple-" in r["note"] else (
             "cedar" if "cedar-" in r["note"] else (
             "birch" if "birch-" in r["note"] else "?"))
        print(f"{r['ts']:<22}{r['sha']:<14}{math.exp(lcs[i]):<11.6f}"
              f"{(r['official'] or 0):<11.6f}{100*f[i]:<10.4f}{lz}")


if __name__ == "__main__":
    main()
