#!/usr/bin/env python3
"""Stage 3: recover the known-magnitude dispatch ladder from decode step times.

The unit of analysis is a BLOCK: a short window of consecutive decode steps in
which every rung of the ladder appears the same number of times. Contrasts are
formed inside a block, so process, run and slow within-run drift cancel before
any averaging happens.

Estimators, in the order they are reported:

  paired rung delta   mean over blocks of mean(rung j) - mean(rung 0)
  slope               block-level OLS through the origin, us per dispatch
  per-rung ratio      delta_j / K_j, the honest linearity check
  quadratic           delta ~ b1*K + b2*K^2, to bound curvature
  carryover           us ~ K + K_prev with block fixed effects absorbed
  placebo             the same machinery on blocks whose rungs are all K=0

All confidence intervals come from a nested process -> run -> block bootstrap,
so process-level and run-level dispersion both propagate into the interval.
Outliers are handled by per-rung median + n*MAD flagging that censors the WHOLE
block, which keeps the design balanced and cannot bias a contrast as long as
spikes are arm-independent (the censored fraction per rung is reported so that
assumption is checkable).
"""
import argparse
import glob
import json
import math
import random
import statistics
import sys


def pct(xs, q):
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return ys[i]


def ci(xs):
    return pct(xs, 0.025), pct(xs, 0.975)


def mad(xs):
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def load(files, drop_steps, keep_warmup_runs, block_len, want_placebo=False):
    """-> (processes, hashes, mismatches) where processes is
    list[process] of list[run] of list[block]; a block is a list of step dicts
    with keys slot, k, us, k_prev."""
    procs, hashes, mism = [], set(), 0
    for path in sorted(files):
        with open(path) as fh:
            doc = json.load(fh)
        hashes.update(doc.get("token_stream_hashes", []))
        mism += doc.get("teacher_forced_mismatches", 0)
        by_run = {}
        for rec in doc["records"]:
            if not keep_warmup_runs and rec.get("warmup_run"):
                continue
            by_run.setdefault(rec["run"], []).append(rec)
        runs = []
        for key in sorted(by_run):
            steps = sorted(by_run[key], key=lambda r: r["step"])
            for i, r in enumerate(steps):
                r["k_prev"] = steps[i - 1]["k"] if i else None
            steps = [r for r in steps if r["step"] >= drop_steps
                     and r["k_prev"] is not None]
            groups = {}
            for r in steps:
                b = r.get("block")
                if b is None:
                    b = r["step"] // block_len
                groups.setdefault(b, []).append(r)
            blocks = [v for _, v in sorted(groups.items())
                      if len(v) == block_len
                      and all(bool(x.get("placebo")) == want_placebo
                              for x in v)]
            if blocks:
                runs.append(blocks)
        if runs:
            procs.append(runs)
    return procs, hashes, mism


def assign_slots(procs, block_len, rng):
    """Overwrite slot/k/k_prev with the randomised within-block order Stage 3
    will emit: each of the 4 rungs twice per 8-step block, freshly permuted.
    Applied to null data this preregisters sigma for the exact estimator,
    including the k_prev carryover term, without any real dispatch delta."""
    nrung = 4
    reps = block_len // nrung
    for runs in procs:
        for blocks in runs:
            carry = None
            for blk in blocks:
                order = [s for s in range(nrung) for _ in range(reps)]
                rng.shuffle(order)
                for rec, slot in zip(blk, order):
                    rec["slot"] = slot
                    rec["k"] = slot
                    rec["k_prev"] = carry
                    carry = slot


def slot_of(rec, rungs):
    """Rung identity of a step. Placebo blocks carry their intended slot so the
    same contrast can be formed on data whose true delta is exactly zero."""
    s = rec.get("slot")
    return rungs[s] if s is not None and s < len(rungs) else rec["k"]


def censor(procs, rungs, mad_mult):
    """Drop whole blocks containing a step beyond per-rung median + n*MAD.
    Thresholds are per rung so a longer arm is not clipped more often."""
    per_rung = {}
    for runs in procs:
        for blocks in runs:
            for blk in blocks:
                for r in blk:
                    per_rung.setdefault(slot_of(r, rungs), []).append(r["us"])
    thr = {k: statistics.median(v) + mad_mult * mad(v) * 1.4826
           for k, v in per_rung.items()}
    flagged = {k: 0 for k in thr}
    kept, dropped = [], 0
    for runs in procs:
        kruns = []
        for blocks in runs:
            kb = []
            for blk in blocks:
                bad = [r for r in blk if r["us"] > thr[slot_of(r, rungs)]]
                if bad:
                    dropped += 1
                    for r in bad:
                        flagged[slot_of(r, rungs)] += 1
                else:
                    kb.append(blk)
            if kb:
                kruns.append(kb)
        if kruns:
            kept.append(kruns)
    return kept, dropped, flagged, per_rung


def block_deltas(blocks, rungs):
    """Per block: {rung: mean(rung) - mean(rung0)}."""
    out = []
    base = rungs[0]
    for blk in blocks:
        by = {}
        for r in blk:
            by.setdefault(slot_of(r, rungs), []).append(r["us"])
        if base not in by or len(by) < 2:
            continue
        b0 = statistics.fmean(by[base])
        out.append({k: statistics.fmean(v) - b0 for k, v in by.items()})
    return out


def flatten(procs, rungs):
    return [d for runs in procs for blocks in runs
            for d in block_deltas(blocks, rungs)]


def nested_resample(procs, rng):
    """Resample processes, then runs inside each drawn process, then blocks
    inside each drawn run, so every level contributes to the interval."""
    out = []
    P = len(procs)
    for _ in range(P):
        runs = procs[rng.randrange(P)]
        rr = []
        for _ in range(len(runs)):
            blocks = runs[rng.randrange(len(runs))]
            rr.append([blocks[rng.randrange(len(blocks))]
                       for _ in range(len(blocks))])
        out.append(rr)
    return out


def slope_through_origin(deltas, rungs):
    base = rungs[0]
    num = den = 0.0
    for d in deltas:
        for k, v in d.items():
            if k == base:
                continue
            num += (k - base) * v
            den += (k - base) ** 2
    return num / den if den else float("nan")


def quadratic(deltas, rungs):
    """delta ~ b1*K + b2*K^2 through the origin."""
    base = rungs[0]
    s11 = s12 = s22 = t1 = t2 = 0.0
    for d in deltas:
        for k, v in d.items():
            if k == base:
                continue
            x1, x2 = float(k - base), float((k - base) ** 2)
            s11 += x1 * x1
            s12 += x1 * x2
            s22 += x2 * x2
            t1 += x1 * v
            t2 += x2 * v
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-12:
        return float("nan"), float("nan")
    return (s22 * t1 - s12 * t2) / det, (s11 * t2 - s12 * t1) / det


def hodges_lehmann(xs, rng):
    if len(xs) > 400:
        xs = [xs[rng.randrange(len(xs))] for _ in range(400)]
    pw = [(xs[i] + xs[j]) / 2
          for i in range(len(xs)) for j in range(i, len(xs))]
    return statistics.median(pw) if pw else float("nan")


def carryover(procs, rungs):
    """us ~ K + K_prev with block fixed effects absorbed by within-block
    demeaning. Returns (beta_own, beta_prev, design correlation)."""
    s11 = s12 = s22 = t1 = t2 = 0.0
    for runs in procs:
        for blocks in runs:
            for blk in blocks:
                rows = [r for r in blk if r.get("k_prev") is not None]
                if len(rows) < 3:
                    continue
                mk = statistics.fmean([r["k"] for r in rows])
                mp = statistics.fmean([r["k_prev"] for r in rows])
                my = statistics.fmean([r["us"] for r in rows])
                for r in rows:
                    x1 = r["k"] - mk
                    x2 = r["k_prev"] - mp
                    y = r["us"] - my
                    s11 += x1 * x1
                    s12 += x1 * x2
                    s22 += x2 * x2
                    t1 += x1 * y
                    t2 += x2 * y
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-9 or s11 <= 0 or s22 <= 0:
        return float("nan"), float("nan"), float("nan")
    b1 = (s22 * t1 - s12 * t2) / det
    b2 = (s11 * t2 - s12 * t1) / det
    return b1, b2, s12 / math.sqrt(s11 * s22)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--block", type=int, default=8,
                    help="steps per block when records carry no block index")
    ap.add_argument("--drop-steps", type=int, default=24)
    ap.add_argument("--keep-warmup-runs", action="store_true")
    ap.add_argument("--rungs", default=None,
                    help="comma-separated K values; inferred when omitted")
    ap.add_argument("--mad-mult", type=float, default=8.0)
    ap.add_argument("--no-censor", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--placebo-assign", action="store_true",
                    help="impose the randomised Stage-3 slot order on null "
                         "K=0 data to preregister sigma for this estimator")
    ap.add_argument("--placebo", action="store_true",
                    help="input is null data; the truth for every delta is 0")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    files = []
    for f in args.files:
        files.extend(glob.glob(f))
    procs, hashes, mism = load(files, args.drop_steps, args.keep_warmup_runs,
                               args.block,
                               want_placebo=args.placebo
                               and not args.placebo_assign)
    if not procs:
        raise SystemExit("no complete blocks found")

    if args.placebo_assign:
        assign_slots(procs, args.block, random.Random(args.seed))
        args.placebo = True

    seen = {r["k"] for runs in procs for blocks in runs
            for blk in blocks for r in blk}
    if args.rungs:
        rungs = sorted(int(x) for x in args.rungs.split(","))
    elif args.placebo and seen == {0}:
        nslots = max((r.get("slot") or 0) for runs in procs
                     for blocks in runs for blk in blocks for r in blk) + 1
        rungs = list(range(nslots))
    else:
        rungs = sorted(seen)

    print(f"token_stream_hashes={sorted(hashes)} "
          f"teacher_forced_mismatches={mism}")
    if len(hashes) != 1:
        print("WARNING: token stream is not identical across all processes")
    nb0 = sum(len(b) for runs in procs for b in runs)
    print(f"processes={len(procs)} runs={[len(r) for r in procs]} "
          f"blocks={nb0} rungs K={rungs}"
          + ("  [PLACEBO: every true delta is 0]" if args.placebo else ""))

    dropped, flagged = 0, {}
    if not args.no_censor:
        procs, dropped, flagged, per_rung = censor(procs, rungs, args.mad_mult)
        tot = {k: len(v) for k, v in per_rung.items()}
        print(f"censoring: dropped {dropped}/{nb0} blocks "
              f"({100.0 * dropped / nb0:.1f}%) at median+{args.mad_mult}*MAD; "
              "flagged steps per rung "
              + ", ".join(f"K={k}:{flagged[k]}/{tot[k]}"
                          for k in sorted(flagged)))

    deltas = flatten(procs, rungs)
    n = len(deltas)
    if n < 8:
        raise SystemExit("too few usable blocks")
    rng = random.Random(args.seed)
    boots = [flatten(nested_resample(procs, rng), rungs)
             for _ in range(args.bootstrap)]

    base = rungs[0]
    print(f"\npaired delta vs K={base} (block-paired, us/step), "
          f"n={n} blocks:")
    out_rungs = {}
    for k in rungs[1:]:
        d = [x[k] for x in deltas if k in x]
        est = statistics.fmean(d)
        bs = [statistics.fmean([x[k] for x in b if k in x])
              for b in boots if any(k in x for x in b)]
        lo, hi = ci(bs)
        se = statistics.pstdev(bs)
        hl = hodges_lehmann(d, rng)
        res = "RESOLVED" if lo * hi > 0 else "not resolved"
        print(f"  K={k:<4} delta={est:+8.2f}  95% CI [{lo:+7.2f},{hi:+7.2f}]"
              f"  SE={se:6.2f}  HL={hl:+7.2f}"
              f"  block sd={statistics.pstdev(d):6.2f}  {res}")
        out_rungs[k] = {"delta": est, "ci": [lo, hi], "se": se, "hl": hl,
                        "block_sd": statistics.pstdev(d),
                        "resolved": lo * hi > 0}

    b = slope_through_origin(deltas, rungs)
    bs = [slope_through_origin(x, rungs) for x in boots]
    slo, shi = ci(bs)
    print(f"\nslope (block OLS through origin): {b:.4f} us/dispatch  "
          f"95% CI [{slo:.4f}, {shi:.4f}]  SE={statistics.pstdev(bs):.4f}")

    print("\nlinearity: implied us/dispatch at each rung "
          "(flat across rungs == linear):")
    ratios = {}
    for k in rungs[1:]:
        div = k - base
        r_est = out_rungs[k]["delta"] / div
        rl = out_rungs[k]["ci"][0] / div
        rh = out_rungs[k]["ci"][1] / div
        ratios[k] = {"per_dispatch": r_est, "ci": [rl, rh]}
        print(f"  K={k:<4} {r_est:+.4f} us/dispatch  "
              f"95% CI [{rl:+.4f}, {rh:+.4f}]")
    _, b2 = quadratic(deltas, rungs)
    qlo, qhi = ci([quadratic(x, rungs)[1] for x in boots])
    span = max(rungs) - base
    print(f"  quadratic term b2={b2:+.3e} us/dispatch^2  95% CI "
          f"[{qlo:+.3e}, {qhi:+.3e}]  (curvature contribution at K="
          f"{max(rungs)} = {b2 * span * span:+.2f} us)")

    c1, c2, cr = carryover(procs, rungs)
    cb = [carryover(nested_resample(procs, rng), rungs)
          for _ in range(min(args.bootstrap, 400))]
    c1lo, c1hi = ci([x[0] for x in cb])
    c2lo, c2hi = ci([x[1] for x in cb])
    vif = 1 / (1 - cr * cr) if cr == cr and abs(cr) < 1 else float("inf")
    print("\ncarryover regression us ~ K + K_prev, block FE absorbed:")
    print(f"  own K      {c1:+.4f} us/dispatch  "
          f"95% CI [{c1lo:+.4f}, {c1hi:+.4f}]")
    print(f"  previous K {c2:+.4f} us/dispatch  "
          f"95% CI [{c2lo:+.4f}, {c2hi:+.4f}]")
    print(f"  design correlation r(K,K_prev)={cr:+.3f}  VIF={vif:.2f}")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({
                "rungs": rungs, "n_blocks": n, "blocks_before_censor": nb0,
                "blocks_dropped": dropped,
                "flagged_steps_per_rung": {str(k): v
                                           for k, v in flagged.items()},
                "delta": {str(k): v for k, v in out_rungs.items()},
                "slope_us_per_dispatch": b, "slope_ci": [slo, shi],
                "slope_se": statistics.pstdev(bs),
                "slope_bootstrap": bs,
                "per_rung_us_per_dispatch": {str(k): v
                                             for k, v in ratios.items()},
                "quadratic_b2": b2, "quadratic_b2_ci": [qlo, qhi],
                "carryover_own": c1, "carryover_own_ci": [c1lo, c1hi],
                "carryover_prev": c2, "carryover_prev_ci": [c2lo, c2hi],
                "design_corr_k_kprev": cr,
                "placebo": bool(args.placebo),
                "token_stream_hashes": sorted(hashes),
            }, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
