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
  it is only ever used for arm-vs-arm relative comparison, never as a headline
  (rule 43). SPLIT=0 is the shipped `nat` regime and is the only source of an
  end-to-end wall or absolute-busy magnitude.

`R89_SLOTS` (comma-separated slot names) restricts the sweep to a subset, so a
`nat` census can spend its duplexes on the contrasts that decide the merge.
"""
import json
import math
import os
import re
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (slot, env value). Slot "0b" repeats the baseline so every rep carries its own
# null control; the null half-width is the resolvable floor for this rig.
ALL_SLOTS = [("0", 0), ("0b", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4),
             ("5", 5)]
_want = os.environ.get("R89_SLOTS")
SLOTS = ([s for s in ALL_SLOTS if s[0] in _want.split(",")] if _want
         else ALL_SLOTS)
ARM_LABEL = {
    "0": "A0 depth0 (baseline)",
    "0b": "A0' depth0 (null control)",
    "1": "A1 depth1 hoisted",
    "2": "A2 depth2 hoisted",
    "3": "A5 depth3 hoisted",
    "4": "A3 depth4 hoisted (full)",
    "5": "A4 depth1 control (below barriers)",
}
ROUTER_RE = re.compile(r"(?:laguna_)?residual_rms_router\S*")
# two-sided 95% t quantiles indexed by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086}


def t95(df):
    return T95.get(df, 1.96 if df > 20 else float("nan"))


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

    rec = {"env": arm, "tag": tag, "rc": p.returncode}
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
        # Under SPLIT=0 a command buffer holds many dispatches and is labelled
        # "[n] a|b|c"; such a row carries no per-kernel attribution.
        if mm and ROUTER_RE.search(mm.group(5)) and not mm.group(5).startswith("["):
            rec["router_us_step"] = float(mm.group(1))
            rec["router_n_step"] = float(mm.group(3))
            rec["router_us_call"] = float(mm.group(4))
            rec["router_kernel"] = ROUTER_RE.search(mm.group(5)).group(0)
            break
    return rec


def summarise(recs, key, label, scale=1.0, unit="", ref="0"):
    """Paired within-rep contrast against a reference slot.

    Every arm is differenced against the reference measured in the SAME rep, so
    rep-level drift (thermal, process placement, page mapping) cancels instead
    of entering the variance. `ref="5"` gives the A4 placement control, which is
    the contrast that isolates cross-barrier overlap from mere loop peeling.
    """
    print(f"\n=== {label}  [ref=slot {ref}] ===", flush=True)
    by_rep = {}
    for r in recs:
        if key in r:
            by_rep.setdefault(r["rep"], {})[r["slot"]] = r[key]
    print(f"{'slot':>5}  {'n':>2}  {'level':>10}  {'paired d':>10}  "
          f"{'95% CI':>22}  {'per-step ' + unit:>16}  label", flush=True)
    for slot, _env in SLOTS:
        levels, diffs = [], []
        for _rep, byslot in sorted(by_rep.items()):
            if slot in byslot:
                levels.append(byslot[slot])
            if slot in byslot and ref in byslot:
                diffs.append(byslot[slot] - byslot[ref])
        if not levels:
            continue
        lvl = statistics.mean(levels)
        if len(diffs) > 1:
            d = statistics.mean(diffs)
            sd = statistics.stdev(diffs)
            hw = t95(len(diffs) - 1) * sd / math.sqrt(len(diffs))
            ci = f"[{d - hw:+.4f},{d + hw:+.4f}]"
            step = f"{d * scale:+.2f} [{(d - hw) * scale:+.2f},{(d + hw) * scale:+.2f}]" if scale != 1.0 else ""
        else:
            d, ci, step = float("nan"), "", ""
        print(f"{slot:>5}  {len(levels):>2}  {lvl:10.4f}  {d:+10.4f}  "
              f"{ci:>22}  {step:>16}  {ARM_LABEL[slot]}", flush=True)


def main():
    out = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    split = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    os.makedirs(out, exist_ok=True)

    recs = []
    if os.environ.get("R89_REPORT_ONLY") == "1":
        # The CLI reps/steps/split args describe a sweep, not a stored one, so
        # re-analysis must read the run shape back out of the records.
        with open(os.path.join(out, "records.json")) as fh:
            recs = json.load(fh)
        print(f"R89-A in-situ re-analysis  {out}  records={len(recs)} "
              f"reps={max(r['rep'] for r in recs) + 1}", flush=True)
        return report(recs)
    print(f"R89-A in-situ sweep  reps={reps} steps={steps} split={split}",
          flush=True)
    for rep in range(reps):
        order = SLOTS if rep % 2 == 0 else list(reversed(SLOTS))
        for slot, env in order:
            tag = f"rep{rep}_slot{slot}"
            print(f"[{tag}] {ARM_LABEL[slot]}", flush=True)
            r = run(env, steps, split, out, tag)
            if r:
                r["rep"], r["slot"] = rep, slot
                recs.append(r)
                print(f"  median={r.get('median_ms')} ms  "
                      f"busy_sum={r.get('busy_sum_ms')} "
                      f"union={r.get('busy_union_ms')}  "
                      f"router={r.get('router_us_call')} us/call "
                      f"x{r.get('router_n_step')}  "
                      f"div={r.get('divergences')}  "
                      f"{r.get('router_kernel','')}", flush=True)
            with open(os.path.join(out, "records.json"), "w") as fh:
                json.dump(recs, fh, indent=1)

    return report(recs)


def report(recs):
    n = max((r.get("router_n_step") or 0) for r in recs) or 39.0
    summarise(recs, "router_us_call",
              "router kernel us/call (SPLIT-inflated, relative only)",
              scale=n, unit="us")
    summarise(recs, "router_us_call",
              "router kernel us/call vs the A4 placement control",
              scale=n, unit="us", ref="5")
    summarise(recs, "router_us_step", "router kernel us/step")
    summarise(recs, "busy_sum_ms", "census absolute busy ms/step (gpu_busy_sum)",
              scale=1000.0, unit="us")
    summarise(recs, "busy_union_ms", "gpu_busy_union ms/step", scale=1000.0,
              unit="us")
    summarise(recs, "wall_ms", "census wall ms/step", scale=1000.0, unit="us")
    summarise(recs, "median_ms", "end-to-end median ms/step", scale=1000.0,
              unit="us")
    ratios = [r["busy_sum_ms"] / r["busy_union_ms"] for r in recs
              if r.get("busy_union_ms")]
    if ratios:
        sd = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
        print(f"\ngpu_busy_sum / gpu_busy_union: mean={statistics.mean(ratios):.4f}"
              f" sd={sd:.4f} n={len(ratios)}", flush=True)
    divs = sorted({(r["slot"], r.get("divergences")) for r in recs})
    print(f"\ndivergences by slot: {divs}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
