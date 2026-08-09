#!/usr/bin/env python3
"""r100-B Part 1 companion: is the session lottery common-mode?

session_factor is exactly the baseline half of the per-draw noise. The
candidate is re-measured in the same session by the same instrument, so the
strategic question is whether the two halves cancel. If the machine is simply
slow that session, bl_* and cand_* both inflate and the published ratio is
protected; if they are independent, the candidate half *adds* variance.

No receipt in the corpus repeats a commit, so this is answered by conditioning
on a narrow merit band where competing candidates are effectively converged,
and by same-solver same-day adjacent pairs.
"""
import json
import math
import statistics as st

CORPUS = "research/r93-runs/receipts-latest.json"
MB_D = 0.013855009542
MB_P = 0.000372473193


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a)
                    * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def rel(v):
    m = st.mean(v)
    return [100.0 * (x / m - 1.0) for x in v]


def main():
    rows = json.load(open(CORPUS))
    print(f"n={len(rows)}  distinct commits="
          f"{len({r['commit'] for r in rows})}  (no candidate is repeated)")

    print("\n[pure re-measurement noise of fixed code: the pinned baseline]")
    for nm, pin in (("bl_dec", MB_D), ("bl_pre", MB_P)):
        v = [100.0 * (r[nm] / pin - 1.0) for r in rows]
        print(f"  {nm}: mean {st.mean(v):+.4f}%  sd {st.stdev(v):.4f}%  "
              f"min {min(v):+.3f}%  max {max(v):+.3f}%")

    for lo, hi in ((2.40, 2.70), (2.50, 2.62), (2.54, 2.60)):
        band = [r for r in rows if lo <= r["cs"] <= hi]
        if len(band) < 30:
            continue
        cs = rel([r["cs"] for r in band])
        sc = rel([r["score"] for r in band])
        sf = rel([r["score"] / r["cs"] for r in band])
        s_cs, s_sc, s_sf = st.stdev(cs), st.stdev(sc), st.stdev(sf)
        indep = math.sqrt(s_cs ** 2 + s_sf ** 2)
        print(f"\n[merit band cs in [{lo},{hi}]]  n={len(band)}")
        print(f"  sd(cs merit) {s_cs:.4f}%    sd(session_factor) {s_sf:.4f}%")
        print(f"  sd(officialScore) observed {s_sc:.4f}%   "
              f"independent prediction {indep:.4f}%   ratio {s_sc/indep:.3f}")
        print(f"  corr(cs, session_factor) = {corr(cs, sf):+.4f}   "
              "(strongly negative => common-mode cancellation)")
        print(f"  corr(bl_dec, cand_dec) = "
              f"{corr([r['bl_dec'] for r in band], [r['cand_dec'] for r in band]):+.4f}"
              f"   corr(bl_pre, cand_pre) = "
              f"{corr([r['bl_pre'] for r in band], [r['cand_pre'] for r in band]):+.4f}")

    rows.sort(key=lambda r: r["ts"])
    pairs = [(a, b) for a, b in zip(rows, rows[1:])
             if a["solver"] == b["solver"] and a["ts"][:10] == b["ts"][:10]]
    if pairs:
        dbl = [100.0 * (b["bl_dec"] / a["bl_dec"] - 1.0) for a, b in pairs]
        dcd = [100.0 * (b["cand_dec"] / a["cand_dec"] - 1.0) for a, b in pairs]
        pbl = [100.0 * (b["bl_pre"] / a["bl_pre"] - 1.0) for a, b in pairs]
        pcd = [100.0 * (b["cand_pre"] / a["cand_pre"] - 1.0) for a, b in pairs]
        print(f"\n[adjacent same-solver same-day pairs] n={len(pairs)}")
        print(f"  corr(d bl_dec, d cand_dec) = {corr(dbl, dcd):+.4f}   "
              f"sd {st.stdev(dbl):.3f}% / {st.stdev(dcd):.3f}%")
        print(f"  corr(d bl_pre, d cand_pre) = {corr(pbl, pcd):+.4f}   "
              f"sd {st.stdev(pbl):.3f}% / {st.stdev(pcd):.3f}%")

    print("\n[our own paired M5 receipts, r91b Arm F vs Arm R, 2026-08-09]")
    print("  Arm R = frontier + r85-C float4 merge epilogue; "
          "Arm F = same frontier without it.")
    arms = {
        "armR 01:07:57Z (epilogue)": dict(
            bl_dec=0.01384702115625, bl_pre=0.00036804638671875,
            cand_dec=0.0048937119140625, cand_pre=0.000188042724609375,
            score=2.5804768841155),
        "armF 01:40:30Z (no epilogue)": dict(
            bl_dec=0.013863095703125, bl_pre=0.0003729877109375,
            cand_dec=0.0048989290390625, cand_pre=0.000187608154296875,
            score=2.5907768487015),
    }
    out = {}
    for nm, v in arms.items():
        cs = (MB_D / v["cand_dec"]) ** 0.75 * (MB_P / v["cand_pre"]) ** 0.25
        sf = v["score"] / cs
        out[nm] = (cs, sf)
        print(f"  {nm}")
        print(f"    baseline vs pinned median: bl_dec "
              f"{100*(v['bl_dec']/MB_D-1):+.4f}%  bl_pre "
              f"{100*(v['bl_pre']/MB_P-1):+.4f}%")
        print(f"    officialScore {v['score']:.10f}   cs {cs:.6f}   "
              f"session_factor {100*(sf-1):+.4f}%")
    (csR, _), (csF, _) = out["armR 01:07:57Z (epilogue)"], \
        out["armF 01:40:30Z (no epilogue)"]
    dR = arms["armR 01:07:57Z (epilogue)"]
    dF = arms["armF 01:40:30Z (no epilogue)"]
    print(f"\n  merit delta R-F: cs {100*(csR/csF-1):+.5f}%   "
          f"raw decode {100*(dR['cand_dec']/dF['cand_dec']-1):+.5f}%   "
          f"raw prefill {100*(dR['cand_pre']/dF['cand_pre']-1):+.5f}%")
    print(f"  published-score delta R-F: "
          f"{100*(dR['score']/dF['score']-1):+.5f}%  "
          "(dominated by the baseline draw, not by merit)")
    print(f"  decode delta in absolute terms: "
          f"{1e6*(dR['cand_dec']-dF['cand_dec']):+.3f} us/token")


if __name__ == "__main__":
    main()
