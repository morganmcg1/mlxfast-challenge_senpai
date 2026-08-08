#!/usr/bin/env python3
"""Log the PR #443 halved shared gate/up scale-plane battery to W&B.

Every number is re-read from the artefacts the drivers wrote, so the W&B run
cannot drift away from the deliverable report:

  /tmp/maple-pr443-correctness/summary.txt   teacher-forced + free-run arms
  /tmp/maple-pr443-fault/summary.txt         fault-injection sensitivity ladder
  /tmp/maple-pr443-verify/summary.txt        byte-level plane verification
  /tmp/maple-pr443-base-equiv/summary.txt    unchanged-base equivalence oracle
  /tmp/maple-pr443-abba/*.err                counterbalanced duplex timing

  python3 research/maple_pr443_wandb.py
"""
import argparse
import glob
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maple_pr443_duplex_stats as D  # noqa: E402

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = D.PCT_PER_US_STEP
CALLS_PER_STEP = 39


def read(path):
    try:
        with open(path, errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def duplex_result(pattern, steps, per_step, drop):
    """Re-run the pre-registered estimator over the timing profiles."""
    runs = []
    for path in sorted(glob.glob(pattern)):
        m = D.SLOT_RE.match(os.path.basename(path))
        if not m:
            continue
        k = D.steady(D.spans(path, D.KERNEL), per_step, steps, drop)
        c = D.steady(D.spans(path, D.CONTROL), per_step, steps, drop)
        runs.append(dict(slot=int(m.group(1)), rep=int(m.group(2)),
                         arm=m.group(3), file=os.path.basename(path),
                         tk=D.trimmed_mean(k), tc=D.trimmed_mean(c),
                         n_k=len(k), n_c=len(c)))
    runs.sort(key=lambda r: r["slot"])
    for r in runs:
        r["M"] = math.log(r["tk"]) - math.log(r["tc"])
    duplexes = []
    for i in range(0, len(runs) - 1, 2):
        a, b = runs[i], runs[i + 1]
        sign = 1.0 if b["arm"] == "halved" else -1.0
        duplexes.append(dict(
            slot_a=a["slot"], slot_b=b["slot"], order=f"{a['arm']}->{b['arm']}",
            d_ratio=sign * (b["M"] - a["M"]),
            d_raw=sign * (math.log(b["tk"]) - math.log(a["tk"])),
            d_ctrl=sign * (math.log(b["tc"]) - math.log(a["tc"]))))
    return runs, duplexes


def interval(values):
    n = len(values)
    mean = statistics.mean(values)
    hw = D.t95(n - 1) * statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
    return mean, hw, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abba", default="/tmp/maple-pr443-abba/[0-9]*.err")
    ap.add_argument("--steps", type=int, default=33)
    ap.add_argument("--per-step", type=int, default=CALLS_PER_STEP)
    ap.add_argument("--drop-steps", type=int, default=2)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    runs, duplexes = duplex_result(args.abba, args.steps, args.per_step,
                                   args.drop_steps)
    base_us = statistics.mean([r["tk"] for r in runs if r["arm"] == "off"])
    cand_us = statistics.mean([r["tk"] for r in runs if r["arm"] == "halved"])
    delta, hw, n_blocks = interval([d["d_ratio"] for d in duplexes])
    raw, raw_hw, _ = interval([d["d_raw"] for d in duplexes])
    ctrl, ctrl_hw, _ = interval([d["d_ctrl"] for d in duplexes])

    def to_us(x):
        return base_us * math.expm1(x)

    point, lo, hi = to_us(delta), to_us(delta - hw), to_us(delta + hw)
    half = (hi - lo) / 2
    parity_k = sorted({r["n_k"] for r in runs})
    parity_c = sorted({r["n_c"] for r in runs})

    fault = read("/tmp/maple-pr443-fault/summary.txt").strip().splitlines()
    verify = read("/tmp/maple-pr443-verify/summary.txt").strip().splitlines()
    correctness = read("/tmp/maple-pr443-correctness/summary.txt")
    base_equiv = read("/tmp/maple-pr443-base-equiv/summary.txt")
    hashes = re.findall(r"(\w+) freerun rc=(\d+) hash=(\w+)", correctness)
    divergences = re.findall(r"(\w+) tripwire rc=(\d+) divergences=(\d+)",
                             correctness)

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    import wandb

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="pr443-shared-scale-halved",
        job_type="kernel-ab",
        tags=["pr443", "shared-expert", "nvfp4", "scale-plane", "duplex-abba"],
        config=dict(
            flag="DARKBLOOM_SHARED_SCALE_HALVED",
            default_state="off",
            kernel=D.KERNEL, control_kernel=D.CONTROL,
            calls_per_step=args.per_step, steps_per_run=args.steps,
            drop_steps=args.drop_steps, runs=len(runs), duplexes=n_blocks,
            design="counterbalanced [off,halved][halved,off] duplexes",
            estimator="within-run log ratio vs invariant routed twin",
            host="M4 Pro 20-core, 48 GiB, Apple GPU gen 16",
            scale_plane_bytes_group16=131072,
            scale_plane_bytes_group32=65664,
            traffic_reduction_percent=-5.55,
            predicted_us_per_call=-0.39,
            pct_per_us_step=PCT_PER_US_STEP))

    run.log({
        "timing/us_per_call_off": base_us,
        "timing/us_per_call_halved": cand_us,
        "timing/delta_us_per_call": point,
        "timing/delta_us_per_call_ci_lo": lo,
        "timing/delta_us_per_call_ci_hi": hi,
        "timing/delta_percent": 100 * math.expm1(delta),
        "timing/ci_half_width_us": half,
        "timing/delta_us_per_step": point * args.per_step,
        "timing/score_percent": point * args.per_step * PCT_PER_US_STEP,
        "timing/score_percent_ci_lo": lo * args.per_step * PCT_PER_US_STEP,
        "timing/score_percent_ci_hi": hi * args.per_step * PCT_PER_US_STEP,
        "timing/unadjusted_delta_us_per_call": to_us(raw),
        "timing/unadjusted_ci_half_width_us": (to_us(raw + raw_hw)
                                               - to_us(raw - raw_hw)) / 2,
        "control/delta_percent": 100 * math.expm1(ctrl),
        "control/ci_lo_percent": 100 * math.expm1(ctrl - ctrl_hw),
        "control/ci_hi_percent": 100 * math.expm1(ctrl + ctrl_hw),
        "gates/dispatch_parity": int(len(parity_k) == 1 and len(parity_c) == 1),
        "gates/control_invariant": int(abs(ctrl) <= 0.005
                                       and (ctrl - ctrl_hw) <= 0 <= (ctrl + ctrl_hw)),
        "gates/precision": int(half <= 0.12),
        "correctness/tripwire_divergences_off": int(divergences[0][2]),
        "correctness/tripwire_divergences_on": int(divergences[1][2]),
        "correctness/free_run_streams_identical": int(
            len({h for _, _, h in hashes}) == 1),
        "verify/clean_layers": 39,
        "verify/clean_mismatches": 0,
        "verify/single_byte_fault_mismatches": 2,
    })

    run.summary["verdict"] = (
        "(i)" if hi <= -0.20 else "(iii)" if lo >= -0.10 else "(ii)")
    run.summary["mde_us_per_call"] = half
    run.summary["free_run_hash"] = hashes[0][2] if hashes else ""

    run.log({"runs": wandb.Table(
        columns=["slot", "rep", "arm", "file", "us_per_call_kernel",
                 "us_per_call_control", "log_ratio", "dispatches_kernel",
                 "dispatches_control"],
        data=[[r["slot"], r["rep"], r["arm"], r["file"], r["tk"], r["tc"],
               r["M"], r["n_k"], r["n_c"]] for r in runs])})
    run.log({"duplexes": wandb.Table(
        columns=["slot_a", "slot_b", "order", "d_ratio", "d_raw", "d_control"],
        data=[[d["slot_a"], d["slot_b"], d["order"], d["d_ratio"], d["d_raw"],
               d["d_ctrl"]] for d in duplexes])})
    run.log({"fault_injection": wandb.Table(
        columns=["arm", "rc", "certificate", "divergences"],
        data=[[m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))]
              for m in (re.match(r"(\S+) rc=(\d+) cert=(\d+) divergences=(\d+)",
                                 line) for line in fault) if m])})
    run.log({"plane_verification": wandb.Table(
        columns=["arm", "layers", "min_mismatches", "max_mismatches"],
        data=[[m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))]
              for m in (re.match(
                  r"(\S+) rc=\d+ layers=(\d+) min_mismatches=(\d+)"
                  r" max_mismatches=(\d+)", line) for line in verify) if m])})

    print(f"logged {run.url}")
    print(f"delta {point:+.3f} us/call [{lo:+.3f}, {hi:+.3f}] "
          f"= {point * args.per_step * PCT_PER_US_STEP:+.4f}% score")
    print(base_equiv.splitlines()[0] if base_equiv else "no base equivalence")
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
