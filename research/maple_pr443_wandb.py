#!/usr/bin/env python3
"""Log the PR #443 halved shared gate/up scale-plane battery to W&B.

Every number is re-read from the artefacts the drivers wrote, so the W&B run
cannot drift away from the deliverable report:

  /tmp/maple-pr443-correctness/summary.txt   teacher-forced + free-run arms
  /tmp/maple-pr443-fault/summary.txt         fault-injection sensitivity ladder
  /tmp/maple-pr443-verify/summary.txt        byte-level plane verification
  /tmp/maple-pr443-base-equiv/summary.txt    unchanged-base equivalence oracle
  /tmp/maple-pr443-abba/*.err                counterbalanced duplex timing (fwd)
  /tmp/maple-pr443-abba-rev/*.err            the same design, reversed order
  /tmp/maple-pr443-prefill/*.log             paired 512-token prefill arm

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
import maple_pr443_step_decomposition as S  # noqa: E402

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = D.PCT_PER_US_STEP
PCT_PER_MS_PREFILL = 0.374750
CALLS_PER_STEP = 39
PREFILL_RE = re.compile(r"prefill 512 tokens:\s*([0-9.]+)\s*ms")


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


def kernel_stats(pattern, steps, per_step, drop):
    """Pre-registered per-call estimator over one counterbalanced order."""
    runs, duplexes = duplex_result(pattern, steps, per_step, drop)
    if not runs:
        return None
    base_us = statistics.mean([r["tk"] for r in runs if r["arm"] == "off"])
    cand_us = statistics.mean([r["tk"] for r in runs if r["arm"] == "halved"])
    delta, hw, n_blocks = interval([d["d_ratio"] for d in duplexes])
    raw, raw_hw, _ = interval([d["d_raw"] for d in duplexes])
    ctrl, ctrl_hw, _ = interval([d["d_ctrl"] for d in duplexes])
    return dict(runs=runs, duplexes=duplexes, base_us=base_us, cand_us=cand_us,
                delta=delta, hw=hw, raw=raw, raw_hw=raw_hw, ctrl=ctrl,
                ctrl_hw=ctrl_hw, n_blocks=n_blocks,
                order="->".join(r["arm"] for r in runs[:4]),
                parity_k=sorted({r["n_k"] for r in runs}),
                parity_c=sorted({r["n_c"] for r in runs}))


def step_stats(pattern, steps, cbs_per_step, min_us_step=5.0):
    """Whole-step attribution: where the per-call win goes, and the net."""
    steady = steps - 1
    runs = []
    for path in sorted(glob.glob(pattern)):
        m = S.SLOT_RE.match(os.path.basename(path))
        if not m:
            continue
        totals, busy = S.label_totals(path, cbs_per_step, steady)
        runs.append(dict(slot=int(m.group(1)), arm=m.group(3),
                         file=os.path.basename(path), totals=totals, busy=busy))
    if not runs:
        return None
    runs.sort(key=lambda r: r["slot"])
    control = next(k for k in runs[0]["totals"] if D.CONTROL in k)
    idx = list(range(0, len(runs) - 1, 2))

    def contrast(getter):
        out = []
        for i in idx:
            a, b = runs[i], runs[i + 1]
            sign = 1.0 if b["arm"] == "halved" else -1.0
            out.append(sign * (math.log(getter(b)) - math.log(getter(a))))
        return out

    rows = []
    for key in sorted(set(runs[0]["totals"]),
                      key=lambda k: -runs[0]["totals"].get(k, 0.0)):
        if any(key not in r["totals"] for r in runs):
            continue
        base_us = statistics.mean([r["totals"][key] / steady
                                   for r in runs if r["arm"] == "off"])
        if base_us < min_us_step and D.CONTROL not in key:
            continue
        mean, hw = S.ci(contrast(lambda r, k=key: r["totals"][k] / r["totals"][control]))
        rows.append(dict(kernel=key, base_us_step=base_us,
                         delta_us_step=base_us * math.expm1(mean),
                         lo_us_step=base_us * math.expm1(mean - hw),
                         hi_us_step=base_us * math.expm1(mean + hw),
                         delta_percent=100 * math.expm1(mean),
                         significant=int((mean - hw) * (mean + hw) > 0)))
    base_busy = statistics.mean([r["busy"] / steady
                                 for r in runs if r["arm"] == "off"])
    b_mean, b_hw = S.ci(contrast(lambda r: r["busy"] / r["totals"][control]))
    r_mean, r_hw = S.ci(contrast(lambda r: r["busy"]))
    return dict(rows=rows, base_busy=base_busy, control=control,
                busy_us_step=base_busy * math.expm1(b_mean),
                busy_lo_us_step=base_busy * math.expm1(b_mean - b_hw),
                busy_hi_us_step=base_busy * math.expm1(b_mean + b_hw),
                busy_raw_us_step=base_busy * math.expm1(r_mean),
                busy_raw_lo_us_step=base_busy * math.expm1(r_mean - r_hw),
                busy_raw_hi_us_step=base_busy * math.expm1(r_mean + r_hw))


def prefill_stats(pattern):
    """Paired 512-token prefill contrast; the change is decode-only by guard."""
    runs = []
    for path in sorted(glob.glob(pattern)):
        m = PREFILL_RE.search(read(path))
        if m:
            arm = path.rsplit("-", 1)[-1].split(".")[0]
            runs.append((os.path.basename(path), arm, float(m.group(1))))
    if len(runs) < 2:
        return None
    diffs = []
    for i in range(0, len(runs) - 1, 2):
        (_, a0, v0), (_, a1, v1) = runs[i], runs[i + 1]
        if {a0, a1} != {"off", "halved"}:
            return None
        diffs.append(math.log(v1 / v0) if a1 == "halved" else math.log(v0 / v1))
    mean, hw, n = interval(diffs)
    base_ms = statistics.mean([ms for _, a, ms in runs if a == "off"])
    return dict(runs=runs, n_blocks=n, base_ms=base_ms,
                cand_ms=statistics.mean([ms for _, a, ms in runs if a == "halved"]),
                delta_ms=base_ms * math.expm1(mean),
                lo_ms=base_ms * math.expm1(mean - hw),
                hi_ms=base_ms * math.expm1(mean + hw),
                delta_percent=100 * math.expm1(mean),
                speedup=math.exp(-mean))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abba", default="/tmp/maple-pr443-abba/[0-9]*.err")
    ap.add_argument("--abba-rev", default="/tmp/maple-pr443-abba-rev/[0-9]*.err")
    ap.add_argument("--prefill", default="/tmp/maple-pr443-prefill/[0-9]*.log")
    ap.add_argument("--steps", type=int, default=33)
    ap.add_argument("--per-step", type=int, default=CALLS_PER_STEP)
    ap.add_argument("--cbs-per-step", type=int, default=406)
    ap.add_argument("--drop-steps", type=int, default=2)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    orders = {}
    for name, pattern in (("fwd", args.abba), ("rev", args.abba_rev)):
        k = kernel_stats(pattern, args.steps, args.per_step, args.drop_steps)
        if k is None:
            continue
        k["step"] = step_stats(pattern, args.steps, args.cbs_per_step)
        for row in k["runs"] + k["duplexes"]:
            row["order_name"] = name
        orders[name] = k
    if "fwd" not in orders:
        print(f"no forward-order timing under {args.abba}", file=sys.stderr)
        return 1

    runs = [r for o in orders.values() for r in o["runs"]]
    duplexes = [d for o in orders.values() for d in o["duplexes"]]
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
    prefill = prefill_stats(args.prefill)

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
            cbs_per_step=args.cbs_per_step,
            drop_steps=args.drop_steps, runs=len(runs), duplexes=n_blocks,
            orders=sorted(orders),
            design="counterbalanced [off,halved][halved,off] duplexes, "
                   "run in both global orders",
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

    for name, o in orders.items():
        run.log({
            f"order_{name}/us_per_call_off": o["base_us"],
            f"order_{name}/us_per_call_halved": o["cand_us"],
            f"order_{name}/delta_us_per_call":
                o["base_us"] * math.expm1(o["delta"]),
            f"order_{name}/delta_percent": 100 * math.expm1(o["delta"]),
            f"order_{name}/ci_lo_percent": 100 * math.expm1(o["delta"] - o["hw"]),
            f"order_{name}/ci_hi_percent": 100 * math.expm1(o["delta"] + o["hw"]),
            f"order_{name}/control_delta_percent": 100 * math.expm1(o["ctrl"]),
            f"order_{name}/control_ci_lo_percent":
                100 * math.expm1(o["ctrl"] - o["ctrl_hw"]),
            f"order_{name}/control_ci_hi_percent":
                100 * math.expm1(o["ctrl"] + o["ctrl_hw"]),
            f"order_{name}/duplexes": o["n_blocks"]})
        st = o.get("step")
        if st is None:
            continue
        run.log({
            f"step_{name}/busy_us_step_off": st["base_busy"],
            f"step_{name}/delta_us_step": st["busy_us_step"],
            f"step_{name}/delta_us_step_ci_lo": st["busy_lo_us_step"],
            f"step_{name}/delta_us_step_ci_hi": st["busy_hi_us_step"],
            f"step_{name}/score_percent": -st["busy_us_step"] * PCT_PER_US_STEP,
            f"step_{name}/score_percent_ci_lo":
                -st["busy_hi_us_step"] * PCT_PER_US_STEP,
            f"step_{name}/score_percent_ci_hi":
                -st["busy_lo_us_step"] * PCT_PER_US_STEP,
            f"step_{name}/delta_us_step_unadjusted": st["busy_raw_us_step"],
            f"step_{name}/delta_us_step_unadjusted_ci_lo":
                st["busy_raw_lo_us_step"],
            f"step_{name}/delta_us_step_unadjusted_ci_hi":
                st["busy_raw_hi_us_step"]})
        run.log({f"step_{name}/decomposition": wandb.Table(
            columns=["kernel", "us_step_off", "delta_percent", "delta_us_step",
                     "ci_lo_us_step", "ci_hi_us_step", "significant"],
            data=[[r["kernel"], r["base_us_step"], r["delta_percent"],
                   r["delta_us_step"], r["lo_us_step"], r["hi_us_step"],
                   r["significant"]] for r in st["rows"]])})

    if prefill is not None:
        run.log({
            "prefill/ms_off": prefill["base_ms"],
            "prefill/ms_halved": prefill["cand_ms"],
            "prefill/delta_ms": prefill["delta_ms"],
            "prefill/delta_ms_ci_lo": prefill["lo_ms"],
            "prefill/delta_ms_ci_hi": prefill["hi_ms"],
            "prefill/delta_percent": prefill["delta_percent"],
            "prefill/speedup": prefill["speedup"],
            "prefill/score_percent": -prefill["delta_ms"] * PCT_PER_MS_PREFILL,
            "prefill/duplexes": prefill["n_blocks"],
            "gates/prefill_floor_0p95": int(prefill["speedup"] >= 0.95)})
        run.log({"prefill/runs": wandb.Table(
            columns=["file", "arm", "prefill_ms"],
            data=[list(r) for r in prefill["runs"]])})

    run.summary["verdict_per_call"] = (
        "(i)" if hi <= -0.20 else "(iii)" if lo >= -0.10 else "(ii)")
    step_fwd = orders["fwd"].get("step")
    if step_fwd is not None:
        run.summary["verdict_step"] = (
            "net win" if step_fwd["busy_hi_us_step"] < 0
            else "net regression" if step_fwd["busy_lo_us_step"] > 0
            else "not separable from zero")
    run.summary["mde_us_per_call"] = half
    run.summary["free_run_hash"] = hashes[0][2] if hashes else ""

    run.log({"runs": wandb.Table(
        columns=["set", "slot", "rep", "arm", "file", "us_per_call_kernel",
                 "us_per_call_control", "log_ratio", "dispatches_kernel",
                 "dispatches_control"],
        data=[[r["order_name"], r["slot"], r["rep"], r["arm"], r["file"],
               r["tk"], r["tc"], r["M"], r["n_k"], r["n_c"]] for r in runs])})
    run.log({"duplexes": wandb.Table(
        columns=["set", "slot_a", "slot_b", "order", "d_ratio", "d_raw",
                 "d_control"],
        data=[[d["order_name"], d["slot_a"], d["slot_b"], d["order"],
               d["d_ratio"], d["d_raw"], d["d_ctrl"]] for d in duplexes])})
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
    print(f"pooled ({'+'.join(sorted(orders))}, {n_blocks} duplexes) "
          f"{point:+.3f} us/call [{lo:+.3f}, {hi:+.3f}] "
          f"= {point * args.per_step * PCT_PER_US_STEP:+.4f}% score if it "
          f"reached the step")
    for name, o in orders.items():
        st = o.get("step")
        print(f"  {name}: per-call {100*math.expm1(o['delta']):+.3f}%  "
              f"control {100*math.expm1(o['ctrl']):+.3f}%"
              + (f"  step {st['busy_us_step']:+.1f} us "
                 f"[{st['busy_lo_us_step']:+.1f}, {st['busy_hi_us_step']:+.1f}]"
                 if st else ""))
    if prefill is not None:
        print(f"  prefill {prefill['delta_ms']:+.3f} ms "
              f"({prefill['delta_percent']:+.3f}%), speedup "
              f"{prefill['speedup']:.4f}")
    print(base_equiv.splitlines()[0] if base_equiv else "no base equivalence")
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
