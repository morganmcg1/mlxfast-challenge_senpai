#!/usr/bin/env python3
"""R89-A in-situ arm sweep: run the real decode path under the GPUPROF hook.

The five prefetch arms live in ONE worker binary behind
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, so every arm here executes the identical
executable and metallib; only the selected pipeline differs. That removes the
build-to-build confound that a source-swap A/B carries.

Arms are visited in a forward order on even reps and the reversed order on odd
reps, so an arm is never pinned to the same position in the drift sequence
(rule 36).

Usage: maple_r89_insitu.py OUTDIR [REPS] [STEPS] [SPLIT]
  SPLIT=1 gives per-dispatch kernel attribution but inflates absolute GPU time;
  it is only ever used for arm-vs-arm relative comparison, never as a headline.
"""
import json
import os
import re
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = [0, 1, 2, 4, 5]
ARM_LABEL = {
    0: "A0 depth0 (baseline)",
    1: "A1 depth1 hoisted",
    2: "A2 depth2 hoisted",
    4: "A3 depth4 hoisted (full)",
    5: "A4 depth1 control (below barriers)",
}
ROUTER_RE = re.compile(r"laguna_residual_rms_router\S*")


def run(arm, steps, split, out, tag):
    env = dict(os.environ)
    env["DARKBLOOM_ROUTER_WEIGHT_PREFETCH"] = str(arm)
    env["DARKBLOOM_GPU_PROFILE"] = "1"
    env["DARKBLOOM_GPU_PROFILE_SPLIT"] = str(split)
    err = os.path.join(out, f"{tag}.stderr")
    cmd = [sys.executable, os.path.join(REPO, "research", "decode_probe.py"),
           "--steps", str(steps), "--profile", "--profile-top", "40",
           "--stderr", err]
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    txt = p.stdout
    with open(os.path.join(out, f"{tag}.txt"), "w") as fh:
        fh.write(txt)
        fh.write("\n=== STDERR TAIL ===\n")
        fh.write(p.stderr[-4000:])
    if p.returncode != 0:
        print(f"  !! arm {arm} rc={p.returncode}", flush=True)
        print(p.stderr[-2000:], flush=True)
        return None

    rec = {"arm": arm, "tag": tag, "rc": p.returncode}
    m = re.search(r"decode steps=\d+ mean=([\d.]+) ms median=([\d.]+) ms", txt)
    if m:
        rec["mean_ms"] = float(m.group(1))
        rec["median_ms"] = float(m.group(2))
    m = re.search(r"teacher-forced greedy tokens: (\d+) divergences", txt)
    if m:
        rec["divergences"] = int(m.group(1))
    m = re.search(r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
                  r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms", txt)
    if m:
        rec["wall_ms"] = float(m.group(1))
        rec["busy_sum_ms"] = float(m.group(2))
        rec["busy_union_ms"] = float(m.group(3))
        rec["gap_ms"] = float(m.group(4))
    # per-kernel rows: "  us/step  share%  n/step  us/call  kernel"
    for line in txt.splitlines():
        mm = re.match(r"\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(.*)$",
                      line)
        if mm and ROUTER_RE.search(mm.group(5)):
            rec["router_us_step"] = float(mm.group(1))
            rec["router_n_step"] = float(mm.group(3))
            rec["router_us_call"] = float(mm.group(4))
            rec["router_kernel"] = ROUTER_RE.search(mm.group(5)).group(0)
            break
    return rec


def summarise(recs, key, label, out):
    print(f"\n=== {label} ===", flush=True)
    print(f"{'arm':>4}  {'n':>2}  {'mean':>10}  {'sd':>8}  "
          f"{'vs A0':>9}  kernel / label", flush=True)
    by_arm = {}
    for r in recs:
        if key in r:
            by_arm.setdefault(r["arm"], []).append(r[key])
    if 0 not in by_arm:
        return
    base = statistics.mean(by_arm[0])
    for arm in ARMS:
        xs = by_arm.get(arm)
        if not xs:
            continue
        m = statistics.mean(xs)
        sd = statistics.stdev(xs) if len(xs) > 1 else float("nan")
        kern = next((r.get("router_kernel", "") for r in recs
                     if r["arm"] == arm and r.get("router_kernel")), "")
        print(f"{arm:>4}  {len(xs):>2}  {m:10.4f}  {sd:8.4f}  "
              f"{m - base:+9.4f}  {kern or ARM_LABEL[arm]}", flush=True)


def main():
    out = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    split = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    os.makedirs(out, exist_ok=True)
    print(f"R89-A in-situ sweep  reps={reps} steps={steps} split={split}",
          flush=True)

    recs = []
    for rep in range(reps):
        order = ARMS if rep % 2 == 0 else list(reversed(ARMS))
        for arm in order:
            tag = f"rep{rep}_arm{arm}"
            print(f"[{tag}] {ARM_LABEL[arm]}", flush=True)
            r = run(arm, steps, split, out, tag)
            if r:
                recs.append(r)
                print(f"  median={r.get('median_ms')} ms  "
                      f"busy_sum={r.get('busy_sum_ms')} "
                      f"union={r.get('busy_union_ms')}  "
                      f"router={r.get('router_us_call')} us/call "
                      f"x{r.get('router_n_step')}  "
                      f"div={r.get('divergences')}", flush=True)
            with open(os.path.join(out, "records.json"), "w") as fh:
                json.dump(recs, fh, indent=1)

    summarise(recs, "router_us_call", "router kernel us/call (SPLIT-inflated, "
              "relative only)", out)
    summarise(recs, "router_us_step", "router kernel us/step", out)
    summarise(recs, "busy_sum_ms", "gpu_busy_sum ms/step", out)
    summarise(recs, "busy_union_ms", "gpu_busy_union ms/step", out)
    summarise(recs, "median_ms", "end-to-end median ms/step", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
