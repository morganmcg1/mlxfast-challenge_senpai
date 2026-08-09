#!/usr/bin/env python3
"""Stage 2: turn the Stage-1 variance decomposition into a sharper protocol.

Two independent answers are produced.

1. Analytic: given the nested variance components and the measured cost model
   (per-process load, per-run seed forward, per-step decode), the SE of a paired
   A-B contrast is minimised over (P, R, S) subject to a wall-clock budget, at
   each level the arm is allowed to switch (step / run / process).

2. Placebo: the *exact* Stage-3 estimator is applied to Stage-1 null data
   (every step is K=0), so its dispersion is a direct end-to-end measurement of
   the protocol's sigma including drift, autocorrelation and scheduler noise.
   This is the number to preregister; the analytic model is only a sanity check.

Usage:
  fern_r93_alloc.py /tmp/r93/stage1/p*.json --pattern 0,1,2,3,3,2,1,0
"""
import argparse
import glob
import json
import math
import random
import statistics
import sys

# Measured on this host by research/fern_r93_nested_session.sh (round 93 smoke).
COST_PROCESS_S = 37.8   # worker spawn + 21.6 GB text tower load
COST_RUN_S = 0.545      # decode_begin: fresh cache + 512-token seed forward
COST_STEP_S = 0.00815   # one teacher-forced decode step at base

# Hard ceiling: the public golden case supplies 256 expected tokens, so a run
# can teacher-force at most 255 steps.
MAX_STEPS_PER_RUN = 255


def sd(v):
    return math.sqrt(v) if v > 0 else -math.sqrt(-v)


def pct(xs, q):
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round(q * (len(ys) - 1)))))
    return ys[i]


def load(paths, drop_steps, keep_warmup_runs):
    """-> list over processes of list over runs of step-time lists (us)."""
    cells = []
    hashes = set()
    for path in sorted(paths):
        with open(path) as fh:
            doc = json.load(fh)
        for h in doc.get("token_stream_hashes", []):
            hashes.add(h)
        by_run = {}
        for rec in doc["steps"]:
            if not keep_warmup_runs and rec.get("warmup_run"):
                continue
            if rec["step"] < drop_steps:
                continue
            by_run.setdefault(rec["run"], []).append(rec["us"])
        if by_run:
            cells.append([by_run[k] for k in sorted(by_run)])
    return cells, hashes


# --------------------------------------------------------------------------
# 1. analytic allocation
# --------------------------------------------------------------------------

def wall_seconds(P, R, S):
    return P * (COST_PROCESS_S + R * (COST_RUN_S + S * COST_STEP_S))


def se_contrast(level, comp, P, R, S):
    """SE of a paired A-B mean difference for a design that spends P*R*S steps
    *in total across both arms*."""
    vp, vr, vs = comp["vp"], comp["vr"], comp["vs_eff"]
    vp, vr, vs = max(vp, 0.0), max(vr, 0.0), max(vs, 0.0)
    if level == "step":
        # both arms live inside every run; process and run effects cancel.
        n_pairs = P * R * S / 2.0
        return math.sqrt(2 * vs / n_pairs)
    if level == "run":
        # arms alternate whole runs inside a process; process effect cancels.
        n_pairs = P * (R / 2.0)
        return math.sqrt(2 * (vr + vs / S) / n_pairs)
    if level == "process":
        n_pairs = P / 2.0
        return math.sqrt(2 * (vp + vr / R + vs / (R * S)) / n_pairs)
    raise ValueError(level)


def sweep(comp, budgets, min_P, max_P, min_R, max_R, S):
    rows = []
    for level in ("step", "run", "process"):
        for T in budgets:
            best = None
            for P in range(min_P, max_P + 1):
                for R in range(min_R, max_R + 1):
                    if level == "process" and P % 2:
                        continue
                    if level == "run" and R % 2:
                        continue
                    t = wall_seconds(P, R, S)
                    if t > T:
                        continue
                    se = se_contrast(level, comp, P, R, S)
                    if best is None or se < best[0]:
                        best = (se, P, R, t)
            if best:
                rows.append((level, T, best[0], best[1], best[2], best[3]))
    return rows


# --------------------------------------------------------------------------
# 2. placebo estimator on null data
# --------------------------------------------------------------------------

def block_contrasts(cells, pattern):
    """Chop every run into consecutive blocks of len(pattern) and, inside each
    block, compute mean(slot j) - mean(slot 0) for every distinct slot j.

    Returns list over processes of list over runs of list over blocks of
    {slot: delta}.  Under Stage-1 null data every delta has expectation 0, so
    the observed spread is the protocol's noise floor."""
    slots = sorted(set(pattern))
    B = len(pattern)
    out = []
    for runs in cells:
        pruns = []
        for steps in runs:
            blocks = []
            for i in range(0, len(steps) - B + 1, B):
                chunk = steps[i:i + B]
                by_slot = {s: [] for s in slots}
                for k, s in enumerate(pattern):
                    by_slot[s].append(chunk[k])
                m = {s: statistics.fmean(v) for s, v in by_slot.items()}
                base = m[slots[0]]
                blocks.append({s: m[s] - base for s in slots[1:]})
            if blocks:
                pruns.append(blocks)
        if pruns:
            out.append(pruns)
    return out, slots


def flatten(bc):
    return [b for runs in bc for blocks in runs for b in blocks]


def placebo_sigma(bc, slot, n_blocks):
    """SE of the pooled slot-vs-slot0 delta when n_blocks blocks are averaged."""
    ds = [b[slot] for b in flatten(bc)]
    if len(ds) < 2:
        return float("nan"), float("nan"), 0
    s = statistics.stdev(ds)
    return s / math.sqrt(n_blocks), s, len(ds)


def nested_boot_sigma(bc, slot, n_blocks, iters, rng):
    """Bootstrap the block-level sd respecting the process/run nesting."""
    out = []
    P = len(bc)
    for _ in range(iters):
        ds = []
        for _ in range(P):
            runs = bc[rng.randrange(P)]
            for _ in range(len(runs)):
                blocks = runs[rng.randrange(len(runs))]
                for _ in range(len(blocks)):
                    ds.append(blocks[rng.randrange(len(blocks))][slot])
        if len(ds) > 1:
            out.append(statistics.stdev(ds) / math.sqrt(n_blocks))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--pattern", default="0,1,2,3,3,2,1,0",
                    help="mirrored slot pattern of the Stage-3 ladder block")
    ap.add_argument("--drop-steps", type=int, default=8)
    ap.add_argument("--keep-warmup-runs", action="store_true")
    ap.add_argument("--label-contains", default=None)
    ap.add_argument("--steps-per-run", type=int, default=248)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--variance-json", default=None,
                    help="fern_r93_variance.py --json-out, for the analytic model")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    paths = []
    for p in args.paths:
        paths.extend(glob.glob(p))
    if args.label_contains:
        keep = []
        for path in paths:
            with open(path) as fh:
                doc = json.load(fh)
            if args.label_contains in (doc.get("label") or ""):
                keep.append(path)
        paths = keep
    if not paths:
        raise SystemExit("no input files")

    cells, hashes = load(paths, args.drop_steps, args.keep_warmup_runs)
    if not cells:
        raise SystemExit("no usable steps")
    print(f"inputs={len(paths)} processes={len(cells)} "
          f"runs/process={[len(c) for c in cells]}")
    print(f"token_stream_hashes={sorted(hashes)}")

    pattern = [int(x) for x in args.pattern.split(",")]
    B = len(pattern)
    S = min(args.steps_per_run, MAX_STEPS_PER_RUN)
    S = (S // B) * B
    blocks_per_run = S // B
    print(f"\nladder block = {pattern} ({B} steps); usable S={S} "
          f"-> {blocks_per_run} blocks/run (cap {MAX_STEPS_PER_RUN} steps)")

    bc, slots = block_contrasts(cells, pattern)
    n_obs = len(flatten(bc))
    print(f"placebo blocks available in Stage-1 null data: {n_obs}")

    rng = random.Random(args.seed)
    print("\nPLACEBO sigma of the mirrored block estimator on K=0 data")
    print("(slot j minus slot 0; truth is exactly 0 us)")
    placebo = {}
    for slot in slots[1:]:
        _, s_block, n = placebo_sigma(bc, slot, 1)
        line = [f"  slot{slot}: block sd={s_block:7.2f} us  (n={n})"]
        row = {"block_sd": s_block, "n_blocks_observed": n, "se": {}}
        for nb in (31, 62, 124, 248, 496, 992, 1984):
            se = s_block / math.sqrt(nb)
            row["se"][nb] = se
            line.append(f"nb={nb}:{se:6.2f}")
        placebo[slot] = row
        print("  ".join(line))

    # CI on the headline slot (the smallest rung, hardest to resolve)
    head = slots[1]
    for nb in (248, 496, 992):
        bs = nested_boot_sigma(bc, head, nb, args.bootstrap, rng)
        print(f"  slot{head} sigma at nb={nb}: {placebo[head]['se'][nb]:.2f} us"
              f"  95% CI [{pct(bs, 0.025):.2f}, {pct(bs, 0.975):.2f}]")
        placebo[head].setdefault("ci", {})[nb] = [pct(bs, 0.025), pct(bs, 0.975)]

    print("\nwall-clock cost of a mirrored-ladder design (all 4 rungs at once):")
    for R in (4, 8, 16, 32, 64):
        for P in (2, 4, 6, 8):
            nb = P * R * blocks_per_run
            t = wall_seconds(P, R, S)
            se = placebo[head]["block_sd"] / math.sqrt(nb)
            flag = "  <= 12us" if se <= 12 else ("  <= 25us" if se <= 25 else "")
            print(f"  P={P:<2} R={R:<3} S={S}  blocks={nb:<5} "
                  f"wall={t/60:6.1f} min  sigma(slot{head})={se:7.2f} us{flag}")

    out = {"pattern": pattern, "S": S, "blocks_per_run": blocks_per_run,
           "placebo": {str(k): v for k, v in placebo.items()},
           "cost_model": {"process_s": COST_PROCESS_S, "run_s": COST_RUN_S,
                          "step_s": COST_STEP_S}}

    if args.variance_json:
        with open(args.variance_json) as fh:
            vj = json.load(fh)
        comp = {"vp": vj["sd_process"] * abs(vj["sd_process"]),
                "vr": vj["sd_run"] * abs(vj["sd_run"]),
                "vs_eff": vj["sd_step_eff"] ** 2}
        print("\nANALYTIC optimum from the variance components "
              "(sd_p=%.1f sd_r=%.1f sd_step_eff=%.1f):"
              % (vj["sd_process"], vj["sd_run"], vj["sd_step_eff"]))
        budgets = [600, 1200, 1800, 3600, 7200]
        rows = sweep(comp, budgets, 2, 12, 2, 64, S)
        print(f"  {'level':<9}{'budget':>8}{'sigma_us':>10}{'P':>4}{'R':>4}"
              f"{'wall_min':>10}")
        for level, T, se, P, R, t in rows:
            print(f"  {level:<9}{T/60:7.0f}m{se:10.2f}{P:4d}{R:4d}{t/60:10.1f}")
        out["analytic"] = [
            {"level": l, "budget_s": T, "sigma_us": se, "P": P, "R": R,
             "wall_s": t} for l, T, se, P, R, t in rows]

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
