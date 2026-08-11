#!/usr/bin/env python3
"""How well can an official receipt measure an arm?

Every official receipt carries four timing legs.  The published score factors
exactly as

    published   = normalized * draw
    normalized  = (REF_D/cand_decode)**0.75 * (REF_P/cand_prefill)**0.25
    draw        = (base_decode/REF_D)**0.75 * (base_prefill/REF_P)**0.25

`normalized` depends only on the candidate legs, so it is a property of the
submitted executable.  `draw` depends only on the baseline legs the harness timed
in the same session, so it is pure session luck: it is what the harness measured
for the *unoptimised reference*, and it is independent of which campaign
submitted.

Grouping receipts by package commit finds no replays -- the submit tool mints a
fresh commit for every archive -- so within-executable reproducibility has to be
established another way.  Two ways are used here.

1. A verified control pair.  Maple receipts `c1c0ba2c` and `88584270` are
   package commits 074f47e8 and 04e8bf3c, which differ by exactly one four-line
   *comment* in Sources/MLXFastModel/DenseTensorStore.swift and nothing else
   (`git diff --stat` = "1 file changed, 4 insertions(+)").  The compiled
   behaviour is therefore identical, so the spread between those two receipts is
   pure harness noise.

2. A population mixture argument.  For consecutive receipts by the same solver,
   |dnormalized| has a sharp mode at zero (the solver resubmitted materially the
   same executable) while |dpublished| for those very same pairs is large.  The
   width of the zero mode bounds the candidate-leg noise without assuming which
   pairs are replays.
"""
import json
import math
import os
import statistics as st
import sys
import urllib.request

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "artifacts", "fern-r109f", "receipts", "submissions.json")
CONTROL = ("c1c0ba2c", "88584270")


def load(argv):
    if len(argv) > 1 and argv[1] == "--fetch":
        tok = os.environ["MLXFAST_API_TOKEN"]
        url = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        return json.load(urllib.request.urlopen(req, timeout=60))
    return json.load(open(argv[1] if len(argv) > 1 else CACHE))


def rowsof(raw):
    if isinstance(raw, dict):
        for k in ("submissions", "data", "items", "results"):
            if isinstance(raw.get(k), list):
                raw = raw[k]
                break
    return [r for r in raw if isinstance(r, dict)]


def axes(r):
    om = r.get("officialMetrics") or {}
    keys = ("decode_seconds_per_token", "prefill_seconds_per_token",
            "baseline_decode_seconds_per_token", "baseline_prefill_seconds_per_token")
    if any(not om.get(k) for k in keys):
        return None
    cd, cp, bd, bp = (om[k] for k in keys)
    return {
        "id": r.get("id", "")[:8],
        "user": r.get("solverUsername"),
        "pkg": (om.get("commit") or r.get("submissionCommitSha") or "")[:8],
        "created": r.get("createdAt") or "",
        "pub": r.get("officialScore") or 0.0,
        "norm": (REF_D / cd) ** 0.75 * (REF_P / cp) ** 0.25,
        "draw": (bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25,
        "cd": cd * 1e6, "cp": cp * 1e6, "bd": bd * 1e6, "bp": bp * 1e6,
    }


def pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def main():
    rows = [a for a in (axes(r) for r in rowsof(load(sys.argv))) if a]
    rows.sort(key=lambda a: a["created"])
    print(f"receipts with full legs: {len(rows)}")

    pkgs = {a["pkg"] for a in rows if a["pkg"]}
    tail = ("no archive is ever replayed under the same commit"
            if len(pkgs) == len(rows) else "some commits repeat")
    print(f"distinct package commits: {len(pkgs)}  -> {tail}")

    # ---- 1. verified control pair -------------------------------------------
    ctrl = [a for a in rows if a["id"] in CONTROL]
    if len(ctrl) == 2:
        a, b = ctrl
        print("\n[1] verified comment-only control pair (identical compiled behaviour)")
        for x in (a, b):
            print(f"    {x['id']} pkg={x['pkg']} pub={x['pub']:.11f} norm={x['norm']:.9f}"
                  f" draw={x['draw']:.6f} candD={x['cd']:.1f}us candP={x['cp']:.2f}us"
                  f" baseD={x['bd']:.1f}us baseP={x['bp']:.2f}us")

        def rel(k):
            return 100 * abs(b[k] - a[k]) / a[k]

        print(f"    spread: published {rel('pub'):.4f} %   normalized {rel('norm'):.4f} %"
              f"   draw {rel('draw'):.4f} %")
        print(f"    legs:   cand decode {rel('cd'):.4f} %  cand prefill {rel('cp'):.4f} %"
              f"  base decode {rel('bd'):.4f} %  base prefill {rel('bp'):.4f} %")
        if rel("norm"):
            print(f"    reading candidate legs instead of the published score is"
                  f" {rel('pub') / rel('norm'):.0f}x more precise on this pair")

    # ---- 2. population mixture ---------------------------------------------
    bysolver = {}
    for a in rows:
        bysolver.setdefault(a["user"], []).append(a)
    dn, dp, pairs = [], [], []
    for user, rs in bysolver.items():
        rs.sort(key=lambda a: a["created"])
        for x, y in zip(rs, rs[1:]):
            rn = 100 * abs(y["norm"] - x["norm"]) / x["norm"]
            rp = 100 * abs(y["pub"] - x["pub"]) / x["pub"] if x["pub"] else 0.0
            dn.append(rn)
            dp.append(rp)
            pairs.append((rn, rp, user, x["id"], y["id"]))
    dn.sort()
    dp.sort()
    print(f"\n[2] consecutive same-solver receipt pairs: n={len(pairs)}")
    print("    quantile |d normalized| vs |d published|  (percent)")
    for q in (0.01, 0.05, 0.10, 0.25, 0.50):
        print(f"      p{int(100 * q):02d}  norm {pct(dn, q):8.4f}   pub {pct(dp, q):8.4f}")

    for thr in (0.01, 0.02, 0.05, 0.10):
        sel = [p for p in pairs if p[0] < thr]
        if not sel:
            continue
        pubs = sorted(p[1] for p in sel)
        print(f"    pairs with |d norm| < {thr:.2f} %: n={len(sel):4d}"
              f"  their |d published|: median {pct(pubs, 0.5):.4f} %"
              f"  p90 {pct(pubs, 0.9):.4f} %  max {pubs[-1]:.4f} %")

    # ---- 3. the draw, i.e. the luck axis -----------------------------------
    draws = sorted(a["draw"] for a in rows)
    dm = st.fmean(draws)
    dsd = st.stdev(draws)
    print(f"\n[3] draw population: n={len(draws)} mean={dm:.6f} sd={dsd:.6f}"
          f" cv={100 * dsd / dm:.4f}% min={draws[0]:.6f} max={draws[-1]:.6f}")
    print("    the draw is the entire reason a fixed executable moves on the"
          " leaderboard; it carries no information about code quality")

    # ---- 4. what this implies for the landing bar ---------------------------
    if len(ctrl) == 2:
        sd_norm = abs(ctrl[1]["norm"] - ctrl[0]["norm"]) / ctrl[0]["norm"] / math.sqrt(2)
        n_norm = max(1, math.ceil(2 * (2 * sd_norm / 0.0007) ** 2))
        n_pub = math.ceil(2 * (2 * (dsd / dm) / 0.0007) ** 2)
        print(f"\n[4] single-pair sd estimate on normalized: {100 * sd_norm:.4f} %"
              f" (1 df, so treat as an order of magnitude)")
        print(f"    receipts needed to resolve a 0.07 % arm at 2 sigma:"
              f" normalized n ~ {n_norm}, published-score n ~ {n_pub}")


if __name__ == "__main__":
    main()
