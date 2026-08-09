#!/usr/bin/env python3
"""r97-d: estimate the rule-58 response ratio R = dD/dP from a Stage 1 ladder.

Rule 58 says the harness starts its decode clock BEFORE the 512-token seed
forward, so with S the seed-forward cost and T the 128 single-token steps

    P = S / prompt_tokens          D = (S + T) / decode_steps

Injecting an output-neutral cost `delta` into every multi-token forward moves
both windows, and the ratio of the two movements is pure harness arithmetic:

    dP = delta / prompt_tokens     dD = delta / decode_steps
    R  = dD / dP = prompt_tokens / decode_steps = 512 / 128 = 4

H0 (seed forward is NOT charged to decode) predicts R = 0. A leak of the
injected work into the single-token steps themselves would predict R ~ 512.
The assignment brief's R = 16 applies the 512/128 factor twice.

The estimator never regresses D on P directly: both share a large common-mode
thermal component and D/P is itself ~26 at this operating point, so a naive
regression is biased upward by construction. It works only on within-block
paired differences against that block's rung-0 run.

    python3 research/frieren_r97_analyze.py research/r97-runs/stage1
"""
import argparse
import glob
import json
import os
import random
import re
import statistics
import sys

TAG_RE = re.compile(r"^(\d+)-b(\d+)-n(\d+)\.score\.json$")


def load_runs(outdir):
    runs = []
    for path in sorted(glob.glob(os.path.join(outdir, "*.score.json"))):
        m = TAG_RE.match(os.path.basename(path))
        if not m:
            continue
        idx, block, rung = (int(g) for g in m.groups())
        with open(path) as fh:
            doc = json.load(fh)
        metrics = doc.get("metrics", doc)
        log = os.path.join(outdir, os.path.basename(path).replace(".score.json", ".log"))
        prompt_tokens, decode_steps, seed_s, mean_step_s = harness_shape(log)
        run = {
            "idx": idx,
            "block": block,
            "rung": rung,
            # seconds -> microseconds; D is us/step, P is us/token
            "D": metrics["decode_seconds_per_token"] * 1e6,
            "P": metrics["prefill_seconds_per_token"] * 1e6,
            "passed": bool(metrics.get("passed_correctness")),
            "prompt_tokens": prompt_tokens,
            "decode_steps": decode_steps,
            "seed_ms": seed_s * 1e3 if seed_s else None,
            "mean_step_ms": mean_step_s * 1e3 if mean_step_s else None,
        }
        if seed_s and mean_step_s and decode_steps and prompt_tokens:
            # What the decode metric would be if the seed forward were NOT
            # inside the decode timer.
            run["D_if_steps_only"] = mean_step_s * 1e6
            # Seed cost implied by the published metric, and the same forward
            # as seen by the prefill timer.
            run["seed_implied_ms"] = (
                run["D"] * decode_steps / 1e3 - mean_step_s * decode_steps * 1e3)
            run["prefill_total_ms"] = run["P"] * prompt_tokens / 1e3
        runs.append(run)
    return runs


NUM = r"([0-9]+\.?[0-9]*(?:[eE][-+]?[0-9]+)?)"
SEED_RE = re.compile(r"decode seed prefill complete seconds=" + NUM)
MEANSTEP_RE = re.compile(r"mean_step_seconds=" + NUM)


def harness_shape(logpath):
    """Read the run's own timer topology out of its progress log.

    Returns prompt_tokens, decode_steps, the seed-forward seconds the harness
    itself reports as "(charged to decode)", and the final step-only mean. The
    prediction is `prompt_tokens / decode_steps`; reading it from the run
    rather than hardcoding 4 keeps the test honest if the local case differs.
    The seed and step-only figures give a within-run decomposition of D that
    needs no cross-run differencing at all.
    """
    prompt_tokens = decode_steps = seed_seconds = mean_step_seconds = None
    if not os.path.exists(logpath):
        return prompt_tokens, decode_steps, seed_seconds, mean_step_seconds
    with open(logpath, errors="replace") as fh:
        for line in fh:
            if prompt_tokens is None and "prefill measured start prompt_tokens=" in line:
                prompt_tokens = int(line.split("prompt_tokens=")[1].split()[0])
            if decode_steps is None and "decode measured start tokens=" in line:
                decode_steps = int(line.split("decode measured start tokens=")[1].split()[0])
            if seed_seconds is None:
                m = SEED_RE.search(line)
                if m:
                    seed_seconds = float(m.group(1))
            m = MEANSTEP_RE.search(line)
            if m:
                # keep the last one: it is the mean over every decoded step
                mean_step_seconds = float(m.group(1))
    return prompt_tokens, decode_steps, seed_seconds, mean_step_seconds


def paired_deltas(runs):
    """(block, rung, dP, dD) for every non-zero rung against its block's rung 0."""
    base = {}
    for r in runs:
        if r["rung"] == 0:
            base.setdefault(r["block"], []).append(r)
    out = []
    for r in runs:
        if r["rung"] == 0 or r["block"] not in base:
            continue
        b = base[r["block"]]
        dP = r["P"] - statistics.mean(x["P"] for x in b)
        dD = r["D"] - statistics.mean(x["D"] for x in b)
        out.append((r["block"], r["rung"], dP, dD))
    return out


def slope_through_origin(pairs):
    num = sum(dP * dD for _, _, dP, dD in pairs)
    den = sum(dP * dP for _, _, dP, _ in pairs)
    return num / den if den else float("nan")


def block_bootstrap(pairs, reps=4000, seed=93):
    blocks = sorted({b for b, _, _, _ in pairs})
    by_block = {b: [p for p in pairs if p[0] == b] for b in blocks}
    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        sample = []
        for _ in blocks:
            sample += by_block[rng.choice(blocks)]
        s = slope_through_origin(sample)
        if s == s:
            draws.append(s)
    draws.sort()
    if not draws:
        return float("nan"), float("nan")
    return draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--reps", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--json", help="write the machine-readable summary here")
    args = ap.parse_args()

    runs = load_runs(args.outdir)
    if not runs:
        print(f"no *.score.json under {args.outdir}", file=sys.stderr)
        return 2

    shapes = {(r["prompt_tokens"], r["decode_steps"]) for r in runs}
    prompt_tokens, decode_steps = sorted(shapes)[-1]
    predicted = (prompt_tokens / decode_steps
                 if prompt_tokens and decode_steps else float("nan"))

    print(f"runs={len(runs)} blocks={len({r['block'] for r in runs})} "
          f"shapes={sorted(shapes)} predicted_R={predicted:.3f}")
    failed = [r for r in runs if not r["passed"]]
    print(f"passed_correctness: {len(runs)-len(failed)}/{len(runs)}"
          + (f"  FAILED: {[r['idx'] for r in failed]}" if failed else ""))

    print(f"\n{'idx':>4} {'blk':>4} {'rung':>5} {'D us/step':>11} {'P us/token':>11} {'ok':>3}")
    for r in sorted(runs, key=lambda x: x["idx"]):
        print(f"{r['idx']:4d} {r['block']:4d} {r['rung']:5d} "
              f"{r['D']:11.1f} {r['P']:11.2f} {str(r['passed'])[:3]:>3}")

    # Within-run decomposition. This needs no cross-run differencing, so host
    # drift cancels exactly: every quantity comes from the same timed window.
    decomp = [r for r in runs if r.get("seed_implied_ms")]
    if decomp:
        print(f"\nwithin-run decomposition (D*steps - meanstep*steps vs prefill window)")
        print(f"{'idx':>4} {'rung':>5} {'seed logged':>12} {'seed implied':>13} "
              f"{'prefill win':>12} {'implied/win':>12} {'D_stepsonly':>12} {'D/D_so':>7}")
        for r in sorted(decomp, key=lambda x: x["idx"]):
            print(f"{r['idx']:4d} {r['rung']:5d} {r['seed_ms']:12.1f} "
                  f"{r['seed_implied_ms']:13.1f} {r['prefill_total_ms']:12.1f} "
                  f"{r['seed_implied_ms']/r['prefill_total_ms']:12.3f} "
                  f"{r['D_if_steps_only']:12.1f} "
                  f"{r['D']/r['D_if_steps_only']:7.3f}")
        rat = [r["seed_implied_ms"] / r["prefill_total_ms"] for r in decomp]
        print(f"  implied-seed / prefill-window: mean={statistics.mean(rat):.3f}"
              + (f" sd={statistics.stdev(rat):.3f}" if len(rat) > 1 else ""))

    print(f"\n{'rung':>5} {'n':>3} {'mean D':>10} {'mean P':>10} "
          f"{'dD':>9} {'dP':>8} {'ratio':>7}")
    rung0 = [r for r in runs if r["rung"] == 0]
    d0 = statistics.mean(r["D"] for r in rung0)
    p0 = statistics.mean(r["P"] for r in rung0)
    per_rung = {}
    for rung in sorted({r["rung"] for r in runs}):
        sel = [r for r in runs if r["rung"] == rung]
        dm = statistics.mean(r["D"] for r in sel)
        pm = statistics.mean(r["P"] for r in sel)
        ratio = (dm - d0) / (pm - p0) if rung and (pm - p0) else float("nan")
        per_rung[rung] = {"n": len(sel), "mean_D_us": dm, "mean_P_us": pm,
                          "dD_us": dm - d0, "dP_us": pm - p0, "ratio": ratio}
        print(f"{rung:5d} {len(sel):3d} {dm:10.1f} {pm:10.2f} "
              f"{dm-d0:9.1f} {pm-p0:8.2f} {ratio:7.3f}")

    pairs = paired_deltas(runs)
    R = slope_through_origin(pairs)
    lo, hi = block_bootstrap(pairs, reps=args.reps, seed=args.seed)
    half = (hi - lo) / 2
    print(f"\nprimary: R = {R:.3f}  95% block-bootstrap CI [{lo:.3f}, {hi:.3f}]"
          f"  half-width {half/R*100 if R else float('nan'):.1f}% of R")

    verdict = {
        "contains_prediction": lo <= predicted <= hi,
        "excludes_zero": lo > 0,
        "excludes_16": not (lo <= 16 <= hi),
        "tight_enough": R == R and abs(half) < 0.20 * predicted,
    }
    for k, v in verdict.items():
        print(f"  {k:22s} {v}")
    passed = all(verdict.values())
    print(f"\nVERDICT: {'PASS' if passed else 'FAIL/AMBIGUOUS'} "
          f"(H58 predicts {predicted:.0f}; H0 predicts 0; "
          f"brief predicted 16)")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({
                "runs": runs, "predicted_R": predicted,
                "per_rung": {str(k): v for k, v in per_rung.items()},
                "R": R, "ci_low": lo, "ci_high": hi,
                "verdict": verdict, "pass": passed,
            }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
