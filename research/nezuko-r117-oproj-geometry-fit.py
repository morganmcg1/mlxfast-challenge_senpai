#!/usr/bin/env python3
"""
R117-C Stage 1 analyser -- the o_proj geometry ladder.

Reads a maple-nezuko-r107j-certify.sh TSV and reports, in this order:

  1. PRIMARY   paired block-wise delta vs the reference arm C, with a t-CI95.
  2. PACKAGING N4 vs C -- same simdgroup count, same activation bytes, HALF the
               threadgroups. The one byte-free contrast in the design.
  3. FIXED-TG  R8 vs N4 -- same threadgroup count, half the simdgroups and half
               the activation bytes.
  4. TWO-FORM  delta(sg) = a*log2(sg/512) + tau_act*US_PER_MB*(act_MB(sg)-314.57)
               fitted on the ns=2 arms, with a block bootstrap CI, PLUS the
               out-of-sample R2 test pre-registered in amendment 12.
  5. RECEIPTS  bit-exactness and pass flags for every run.

Why not just regress delta on bytes?  Because activation bytes are an exact
linear function of the simdgroup count in this kernel
(act = simdgroups * in_vec_size * 2 * calls), so along the ns=2 ladder the byte
dose and the parallelism knob are collinear with correlation 1.0.  A regression
of delta on bytes returns "bytes + parallelism, bundled", not B_act.  See
research/nezuko-r117-stage1-amendment12-identifiability.md, committed before the
first paired observation existed.  The two forms are separable only because a
bandwidth term is linear in bytes while an occupancy term saturates like
log2(simdgroups) -- that is a functional-form assumption, and it is tested
out-of-sample against R2 rather than asserted.

Usage:
  python3 research/nezuko-r117-oproj-geometry-fit.py <certify.tsv> [--csv PATH]
  python3 research/nezuko-r117-oproj-geometry-fit.py --selftest
"""
import sys
import csv
import math
import random
from collections import defaultdict

US_PER_MB = 1e3 / 256.7          # 3.8956 us per MB at the 256.7 GB/s DRAM peak
REF = "C"
GOLDEN = "f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2"

# arm -> (rows_per_simdgroup, simdgroups_per_threadgroup)
GEOM = {"C": (4, 2), "R1": (1, 2), "R2": (2, 2), "R8": (8, 2), "N4": (4, 4)}
OUTVEC = 2048
CALLS = [(64 * 128, 30), (48 * 128, 10)]   # (in_vec_size, calls/step) for h64, h48


def geom(arm):
    rps, ns = GEOM[arm]
    tiles = OUTVEC // (ns * rps)
    sg = tiles * ns
    act_mb = sum(sg * k * 2 * c for k, c in CALLS) / 1e6
    return dict(rps=rps, ns=ns, tiles=tiles, simdgroups=sg, act_mb=act_mb)


BASE = geom(REF)


def tcrit(n):
    # two-sided 95% t critical values, df = n-1
    tab = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
           7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
           13: 2.160, 14: 2.145, 15: 2.131, 19: 2.093, 24: 2.064, 29: 2.045}
    df = max(1, n - 1)
    if df in tab:
        return tab[df]
    return 1.96 + 2.4 / df


def mean_ci(xs):
    n = len(xs)
    if n == 0:
        return (float("nan"),) * 4
    m = sum(xs) / n
    if n == 1:
        return m, float("nan"), float("nan"), float("nan")
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = tcrit(n) * sd / math.sqrt(n)
    return m, m - h, m + h, sd


def load(path):
    rows = []
    with open(path) as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        for r in rd:
            if not r.get("arm"):
                continue
            try:
                us = float(r["decode_s_per_token"]) * 1e6
            except (TypeError, ValueError):
                continue
            rows.append(dict(
                block=int(r["block"]), pos=int(r["pos"]), arm=r["arm"].strip(),
                us=us, passed=(r.get("passed", "").strip() == "true"),
                golden=(r.get("golden") or "").strip(),
                idx=int(r["idx"]),
            ))
    return rows


def paired(rows):
    """block -> arm -> row, keeping only complete blocks that contain REF."""
    by = defaultdict(dict)
    for r in rows:
        by[r["block"]][r["arm"]] = r
    return {b: d for b, d in sorted(by.items()) if REF in d}


def contrast(bl, a, b):
    """block-wise a-minus-b, only where both arms are present."""
    out = []
    for blk, d in sorted(bl.items()):
        if a in d and b in d:
            out.append((blk, d[a]["us"] - d[b]["us"]))
    return out


def fit_two_form(points):
    """points: list of (log2_sg_ratio, dbytes_MB, delta_us). Least squares, 2 params."""
    sxx = sxy = sxz = syy = syz = 0.0
    for x, mb, z in points:
        y = US_PER_MB * mb
        sxx += x * x
        sxy += x * y
        syy += y * y
        sxz += x * z
        syz += y * z
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-12:
        return None, None
    a = (sxz * syy - syz * sxy) / det
    tau = (syz * sxx - sxz * sxy) / det
    return a, tau


def arm_points(bl, arms, blocks=None):
    pts = []
    for blk, d in sorted(bl.items()):
        if blocks is not None and blk not in blocks:
            continue
        if REF not in d:
            continue
        for arm in arms:
            if arm not in d:
                continue
            g = geom(arm)
            pts.append((math.log2(g["simdgroups"] / BASE["simdgroups"]),
                        g["act_mb"] - BASE["act_mb"],
                        d[arm]["us"] - d[REF]["us"]))
    return pts


def main():
    args = [a for a in sys.argv[1:]]
    if "--selftest" in args:
        return selftest()
    csv_out = None
    if "--csv" in args:
        i = args.index("--csv")
        csv_out = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    rows = load(path)
    bl = paired(rows)

    print("=" * 78)
    print("R117-C Stage 1 -- o_proj geometry ladder")
    print("=" * 78)
    print(f"  source        : {path}")
    print(f"  runs          : {len(rows)}")
    print(f"  blocks w/ ref : {len(bl)}")
    print()
    print("  GEOMETRY (derived from source, not from the log)")
    print(f"  {'arm':4s} {'rps':>4s} {'ns':>3s} {'simdgrp':>8s} {'thrgrp':>7s} "
          f"{'act MB/step':>12s} {'d act':>10s} {'pred us @tau=1':>15s}")
    for arm in ["C", "R1", "R2", "R8", "N4"]:
        g = geom(arm)
        d = g["act_mb"] - BASE["act_mb"]
        print(f"  {arm:4s} {g['rps']:4d} {g['ns']:3d} {g['simdgroups']:8d} "
              f"{g['tiles']:7d} {g['act_mb']:12.2f} {d:+10.2f} {d*US_PER_MB:+15.1f}")
    print()

    # ---------------- receipts ----------------
    bad_pass = [r for r in rows if not r["passed"]]
    goldens = sorted({r["golden"] for r in rows if r["golden"]})
    print("-" * 78)
    print("RECEIPTS -- bit exactness")
    print("-" * 78)
    print(f"  runs with passed=true : {len(rows)-len(bad_pass)}/{len(rows)}")
    print(f"  distinct golden hashes: {len(goldens)}")
    for g in goldens:
        n = sum(1 for r in rows if r["golden"] == g)
        flag = "  <-- expected" if g == GOLDEN else "  <-- UNEXPECTED"
        print(f"    {g[:24]}...  n={n}{flag}")
    if bad_pass:
        print(f"  !! {len(bad_pass)} runs did NOT pass: "
              f"{sorted({r['arm'] for r in bad_pass})}")
    print()

    # ---------------- primary ----------------
    print("-" * 78)
    print(f"PRIMARY -- paired block-wise delta vs {REF}   (negative = faster)")
    print("-" * 78)
    results = {}
    for arm in ["R1", "R2", "R8", "N4"]:
        cs = contrast(bl, arm, REF)
        if not cs:
            continue
        vals = [v for _, v in cs]
        m, lo, hi, sd = mean_ci(vals)
        results[arm] = (m, lo, hi, sd, vals)
        g = geom(arm)
        print(f"  {arm:4s} n={len(vals)}  delta = {m:+8.2f} us/step  "
              f"CI95 [{lo:+8.2f}, {hi:+8.2f}]  sd={sd:6.2f}")
        print(f"       per-block: " + " ".join(f"{v:+7.1f}" for v in vals))
        print(f"       byte model at tau=0.780 would predict "
              f"{0.780*US_PER_MB*(g['act_mb']-BASE['act_mb']):+8.1f} us/step")
        print()

    # ---------------- packaging & fixed-TG ----------------
    print("-" * 78)
    print("SECONDARY -- the two attributable contrasts")
    print("-" * 78)
    for a, b, label in [("N4", REF, "packaging, BYTE-FREE (sg 512=512, TG 256->128)"),
                        ("R8", "N4", "fixed threadgroups (TG 128=128, sg 512->256, -157.29 MB)")]:
        cs = contrast(bl, a, b)
        if not cs:
            continue
        vals = [v for _, v in cs]
        m, lo, hi, sd = mean_ci(vals)
        print(f"  {a} vs {b}: {label}")
        print(f"     delta = {m:+8.2f} us/step  CI95 [{lo:+8.2f}, {hi:+8.2f}]  "
              f"sd={sd:6.2f}  n={len(vals)}")
        print()

    # ---------------- two-form fit ----------------
    print("-" * 78)
    print("TWO-FORM FIT (ns=2 arms only):  delta = a*log2(sg/512) + tau_act*us_per_MB*d_bytes")
    print("-" * 78)
    ns2 = ["R1", "R2", "R8"]
    pts = arm_points(bl, ns2)
    a_hat, tau_hat = fit_two_form(pts)
    if a_hat is None:
        print("  fit is singular -- not identifiable on this data")
    else:
        print(f"  a       = {a_hat:+8.2f} us per doubling of the simdgroup count")
        print(f"  tau_act = {tau_hat:+8.3f}   (vs Stage 0b scale-plane tau = +0.780)")
        blocks = sorted(bl)
        boot_a, boot_t = [], []
        rnd = random.Random(20260811)
        for _ in range(20000):
            samp = [rnd.choice(blocks) for _ in blocks]
            p = []
            for b in samp:
                p.extend(arm_points(bl, ns2, blocks={b}))
            aa, tt = fit_two_form(p)
            if aa is not None:
                boot_a.append(aa)
                boot_t.append(tt)
        if boot_a:
            boot_a.sort()
            boot_t.sort()
            q = lambda v, p: v[max(0, min(len(v) - 1, int(p * len(v))))]
            print(f"  block bootstrap CI95 (20000 reps):")
            print(f"     a       [{q(boot_a,0.025):+8.2f}, {q(boot_a,0.975):+8.2f}]")
            print(f"     tau_act [{q(boot_t,0.025):+8.3f}, {q(boot_t,0.975):+8.3f}]")
        print()
        print("  OUT-OF-SAMPLE TEST pre-registered in amendment 12:")
        pts_no_r2 = arm_points(bl, ["R1", "R8"])
        a2, t2 = fit_two_form(pts_no_r2)
        if a2 is not None:
            g = geom("R2")
            pred = (a2 * math.log2(g["simdgroups"] / BASE["simdgroups"])
                    + t2 * US_PER_MB * (g["act_mb"] - BASE["act_mb"]))
            print(f"     fit on R1,R8 only -> a={a2:+.2f}, tau_act={t2:+.3f}")
            print(f"     predicted R2 delta = {pred:+8.2f} us/step")
            if "R2" in results:
                m, lo, hi, sd, _ = results["R2"]
                inside = lo <= pred <= hi
                print(f"     observed  R2 delta = {m:+8.2f} us/step  "
                      f"CI95 [{lo:+8.2f}, {hi:+8.2f}]")
                print(f"     prediction inside the observed CI95? "
                      f"{'YES -- decomposition survives' if inside else 'NO -- decomposition REJECTED'}")
            print(f"     (amendment 12 wrote -66.8 us/step from the pre-flight singles)")
    print()

    # ---------------- csv ----------------
    if csv_out:
        with open(csv_out, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["block", "arm", "pos", "idx", "rps", "ns", "simdgroups",
                        "threadgroups", "act_MB_per_step", "d_act_MB_per_step",
                        "pred_us_at_tau1", "us_per_step", "ref_us_per_step",
                        "delta_us", "passed", "golden", "golden_match"])
            for blk, d in sorted(bl.items()):
                ref = d[REF]["us"]
                for arm, r in sorted(d.items()):
                    g = geom(arm)
                    dmb = g["act_mb"] - BASE["act_mb"]
                    w.writerow([blk, arm, r["pos"], r["idx"], g["rps"], g["ns"],
                                g["simdgroups"], g["tiles"],
                                f"{g['act_mb']:.4f}", f"{dmb:+.4f}",
                                f"{dmb*US_PER_MB:+.4f}", f"{r['us']:.4f}",
                                f"{ref:.4f}", f"{r['us']-ref:+.4f}",
                                str(r["passed"]).lower(), r["golden"],
                                str(r["golden"] == GOLDEN).lower()])
        print(f"  raw array -> {csv_out}")
    print("=" * 78)
    return 0


def selftest():
    """Synthetic data with a KNOWN a and tau_act; check the fit recovers them."""
    print("SELFTEST -- two-form fit recovery")
    a_true, tau_true, c_true = -140.0, 0.06, 8990.0
    rnd = random.Random(7)
    rows = []
    idx = 0
    for blk in range(1, 6):
        drift = rnd.gauss(0, 18)
        for pos, arm in enumerate(["C", "R1", "R2", "R8", "N4"], start=1):
            g = geom(arm)
            eff = 0.0
            if arm != "C":
                eff = (a_true * math.log2(g["simdgroups"] / BASE["simdgroups"])
                       + tau_true * US_PER_MB * (g["act_mb"] - BASE["act_mb"]))
                if arm == "N4":
                    eff = 23.0          # byte-free packaging cost
            idx += 1
            rows.append(dict(block=blk, pos=pos, arm=arm, idx=idx,
                             us=c_true + drift + eff + rnd.gauss(0, 9),
                             passed=True, golden=GOLDEN))
    bl = paired(rows)
    pts = arm_points(bl, ["R1", "R2", "R8"])
    a_hat, tau_hat = fit_two_form(pts)
    print(f"  a_true   = {a_true:+8.2f}   a_hat   = {a_hat:+8.2f}")
    print(f"  tau_true = {tau_true:+8.3f}   tau_hat = {tau_hat:+8.3f}")
    ok = abs(a_hat - a_true) < 25 and abs(tau_hat - tau_true) < 0.05
    print(f"  recovery {'OK' if ok else 'FAILED'}")
    cs = contrast(bl, "N4", "C")
    m, lo, hi, sd = mean_ci([v for _, v in cs])
    print(f"  N4 packaging (true +23.0): {m:+.2f} CI95 [{lo:+.2f}, {hi:+.2f}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
