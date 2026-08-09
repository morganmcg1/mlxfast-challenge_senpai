#!/usr/bin/env python3
"""R93-C stall-structure analysis (research-only, not submitted).

Reads `<outdir>/census.jsonl` written by `research/maple_r93_census.py` and
emits (a) the roofline table, (b) per-ladder marginal-cost fits with 95 % CIs,
and (c) the classification evidence per kernel.

  python3 research/maple_r93_analyze.py OUTDIR [OUTDIR ...]

Marginal fits are ordinary least squares of per-kernel us/step against the
ladder level `n`, anchored on that ladder's own level-0 placement control
(Rule 44). The reported CI is the Student-t interval on the slope; with 2-3
replicates per level the interval is wide by construction and is quoted, not
hidden.
"""
import json
import math
import sys
from collections import defaultdict

# --- Static work counts, derived from the kernel sources at base ca920bb. ----
# threads/step: grid threads per dispatch times dispatches per decode step.
#   qkv    h64 (10240/2)*64 = 327680 x30 layers; h48 (8192/2)*64 = 262144 x10
#   oproj  (2048/8)*64 = 16384 x40 layers
#   routed 8*256*64 = 131072 x39 sparse layers
# trips: iterations of the K loop that the ALU ladder sits inside.
#   qkv 2048/512 = 4; oproj in_vec/512 = 16 (h64) / 12 (h48); routed 2048/512 = 4
GEOM = {
    "qkv": {
        "threads": 327680 * 30 + 262144 * 10,
        "alu_ops_per_n": (327680 * 30 * 4 + 262144 * 10 * 4) * 4,
    },
    "oproj": {
        "threads": 16384 * 40,
        "alu_ops_per_n": (16384 * 30 * 16 + 16384 * 10 * 12) * 4,
    },
    "routed": {
        "threads": 131072 * 39,
        "alu_ops_per_n": 131072 * 39 * 4 * 4,
    },
}

# Weight-plane bytes actually read per decode step (codes + packed 4-bit scale
# nibbles + per-row scale base), plus activations. See the report for the
# derivation; NVFP4 group-16 codes are 0.5 B/value and the lane-major `_pw1`
# scale plane is 0.25 B per group of 16, i.e. 1/64 B per value.
BYTES_PER_STEP = {
    "qkv": 30 * 10240 * (1024 + 32 + 1) + 10 * 8192 * (1024 + 32 + 1) + 930_000,
    "oproj": 30 * 2048 * (4096 + 128 + 1) + 10 * 2048 * (3072 + 96 + 1) + 760_000,
    "routed": 39 * 8 * (1024 * 1024 + 65536) + 500_000,
}
# Same-host measured achievable read bandwidth for each kernel's access pattern
# (senpai/tools/bandwidth-pattern-probe, M4 Pro, 2026-08-04).
PATTERN_CEILING_GBPS = {"qkv": 236.6, "oproj": 236.6, "routed": 243.0}

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
       13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120}


def ols(xs, ys):
    """Slope, intercept, and the Student-t 95 % half-width on the slope."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0 or n < 3:
        return float("nan"), float("nan"), float("nan")
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    dof = n - 2
    s2 = sum(r * r for r in resid) / dof
    se = math.sqrt(s2 / sxx)
    return b, a, T95.get(dof, 1.96) * se


def load(paths):
    recs = []
    for p in paths:
        with open(p.rstrip("/") + "/census.jsonl") as f:
            for line in f:
                r = json.loads(line)
                if r["returncode"] == 0:
                    recs.append(r)
    return recs


def main() -> int:
    recs = load(sys.argv[1:])
    bad = [r["arm"] for r in recs if r.get("divergences")]
    print(f"records: {len(recs)}  non-bit-exact arms: {sorted(set(bad)) or 'none'}\n")

    by_arm = defaultdict(list)
    for r in recs:
        by_arm[r["arm"]].append(r)

    # ---- SPLIT tax control ---------------------------------------------
    for arm in ("off", "off@nosplit"):
        rs = by_arm.get(arm, [])
        if rs:
            b = [r["busy_sum_ms"] for r in rs]
            w = [r["wall_ms"] for r in rs]
            print(f"{arm:>14}: n={len(rs)} busy_sum={sum(b)/len(b):.3f} ms "
                  f"wall={sum(w)/len(w):.3f} ms")
    print()

    # ---- Roofline -------------------------------------------------------
    base = by_arm.get("off", [])
    print(f"{'kernel':>8} {'us/step':>9} {'MB/step':>9} {'GB/s':>8} "
          f"{'ceil GB/s':>10} {'% ceil':>8}")
    base_us = {}
    for tag in GEOM:
        vals = [r["rows"][tag]["us_per_step"] for r in base if tag in r["rows"]]
        if not vals:
            continue
        us = sum(vals) / len(vals)
        base_us[tag] = us
        mb = BYTES_PER_STEP[tag] / 1e6
        gbps = BYTES_PER_STEP[tag] / (us * 1e-6) / 1e9
        ceil = PATTERN_CEILING_GBPS[tag]
        print(f"{tag:>8} {us:9.1f} {mb:9.1f} {gbps:8.1f} {ceil:10.1f} "
              f"{gbps/ceil*100:7.1f}%")
    print()

    # ---- Ladder fits ----------------------------------------------------
    ladders = defaultdict(lambda: defaultdict(list))
    for arm, rs in by_arm.items():
        if ":" not in arm or "@" in arm:
            continue
        tgt, kind, n = arm.split(":")
        for r in rs:
            if tgt in r["rows"]:
                ladders[(tgt, kind)][int(n)].append(r["rows"][tgt]["us_per_step"])

    print(f"{'kernel':>8} {'kind':>5} {'levels':>28} "
          f"{'us/step per n':>26} {'unit cost':>26}")
    for (tgt, kind) in sorted(ladders):
        lv = ladders[(tgt, kind)]
        xs, ys = [], []
        for n, vals in sorted(lv.items()):
            for v in vals:
                xs.append(n)
                ys.append(v)
        slope, _, half = ols(xs, ys)
        shown = " ".join(
            f"{n}:{sum(v)/len(v):.0f}" for n, v in sorted(lv.items()))
        if kind in ("fma", "imad"):
            ops = GEOM[tgt]["alu_ops_per_n"]
            # picoseconds of kernel time per added ALU op
            unit = f"{slope*1e-6/ops*1e12:.3f} ps/op" if slope == slope else "n/a"
            eff = f" ({ops/1e6:.1f} Mop/n)"
        else:
            w = 8 if kind == "ld8" else 16
            thr = GEOM[tgt]["threads"]
            unit = (f"{slope*1e-6/(thr*w)*1e9*1e9:.3f} ps/B"
                    if slope == slope else "n/a")
            eff = f" ({thr*w/1e6:.1f} MB/n, {thr/1e6:.2f} Mld/n)"
        print(f"{tgt:>8} {kind:>5} {shown:>28} "
              f"{slope:9.1f} +/- {half:7.1f}  {unit:>14}{eff}")
    print()

    # ---- ld8:2 vs ld16:1 discriminator ----------------------------------
    print("byte-vs-load discriminator (equal bytes, 2x vs 1x load count):")
    for tgt, a, b in (("qkv", "ld8:2", "ld16:1"),
                      ("routed", "ld8:2", "ld16:1"),
                      ("oproj", "ld8:8", "ld16:4")):
        ctl8 = ladders[(tgt, "ld8")].get(0, [])
        va = ladders[(tgt, "ld8")].get(int(a.split(":")[1]), [])
        vb = ladders[(tgt, "ld16")].get(int(b.split(":")[1]), [])
        if not (ctl8 and va and vb):
            continue
        m0 = sum(ctl8) / len(ctl8)
        da = sum(va) / len(va) - m0
        db = sum(vb) / len(vb) - m0
        print(f"  {tgt:>8} {a}: +{da:7.1f} us/step   {b}: +{db:7.1f} us/step"
              f"   ratio {db/da if da else float('nan'):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
