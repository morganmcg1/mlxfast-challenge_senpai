#!/usr/bin/env python3
"""R118-A step 5: split the in-situ per-call cost into a fixed part and a
byte-proportional part, and measure tau for this kernel family.

Input: the log directory written by qmv-dose-profile.sh (SPLIT=1, attribution
only, never a ranking).  For each arm we read the profiler's own per-kernel row
for the kernel that was dosed.

The model is the simplest one that can be wrong:

    busy_per_call(nblocks) = c + nblocks * m

`m` is the marginal cost of one 512-wide K block of weight traffic; `c` is
everything that does not scale with the K loop - dispatch/encode latency,
launch ramp, the tail where only a few threadgroups are still alive, the
prologue and epilogue.  Two arms (4 blocks and 1 block) determine both:

    m = (busy(4) - busy(1)) / 3        c = busy(1) - m

This is the "fixed-overhead correction" the assignment asks for, and it decides
the whole question.  The 68 us/step I was sent to chase is the gap between the
7.39 us/call this kernel costs in situ and the 5.637 us/call the same kernel
text costs on a standalone Metal rig (R110 F1).  If `c` is of order that gap,
the gap is per-dispatch overhead: no rewrite of the kernel body can touch it,
only removing dispatches can, and the target is STRUCTURAL.  If `c` is small
and `4m` alone already exceeds the standalone number, the gap is in the memory
system and the target is at least in principle ADDRESSABLE.

The routed kernel is measured the same way from the same binary.  It is 5.3x
bigger per call, so if the two kernels report the same `c` within noise, `c` is
a genuine per-dispatch constant of this machine and not a fitting artefact.
That cross-check is the sensitivity analysis.

usage: analyze-profile.py <PROFILE_DIR> [--wall-shared US] [--wall-routed US]
"""
import argparse
import glob
import json
import os
import re
import statistics as st

SHARED = "shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1"
ROUTED = "routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"
STEP_RE = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms")
ROW_RE = re.compile(
    r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(\S+)\s*$")


def parse(path):
    out = {"kernels": {}}
    with open(path) as fh:
        for line in fh:
            m = STEP_RE.search(line)
            if m:
                out["wall_ms"] = float(m.group(1))
                out["busy_ms"] = float(m.group(2))
                out["gap_ms"] = float(m.group(4))
                continue
            m = ROW_RE.match(line)
            if m:
                name = m.group(5)
                base = re.sub(r"_r118\w+$", "", name)
                out["kernels"][base] = {
                    "us_step": float(m.group(1)), "n_step": float(m.group(3)),
                    "us_call": float(m.group(4)), "raw_name": name}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--wall-shared", type=float, default=None,
                    help="campaign SPLIT=0 wall saving for d1, us/step")
    ap.add_argument("--wall-routed", type=float, default=None,
                    help="campaign SPLIT=0 wall saving for rd1, us/step")
    ap.add_argument("--json", default=None,
                    help="also write the derived quantities here, so that the "
                         "W&B run and this log cannot disagree")
    a = ap.parse_args()
    out = {"dir": a.dir, "wall_shared_us_step": a.wall_shared,
           "wall_routed_us_step": a.wall_routed, "families": {},
           "whole_step_busy_us": {}}

    caps = {}
    for path in sorted(glob.glob(os.path.join(a.dir, "p*_*.log"))):
        m = re.search(r"p(\d+)_(\w+)\.log$", os.path.basename(path))
        arm = m.group(2)
        d = parse(path)
        if "busy_ms" not in d:
            print(f"!! {path}: no steady-step line, skipped")
            continue
        caps.setdefault(arm, []).append((int(m.group(1)), d))

    print("### R118-A profiled dose (SPLIT=1, ATTRIBUTION ONLY, never a ranking)\n")
    print("cap arm    wall_ms  busy_ms   gap_ms   shared us/call  routed us/call")
    for arm in sorted(caps):
        for idx, d in caps[arm]:
            s = d["kernels"].get(SHARED, {})
            r = d["kernels"].get(ROUTED, {})
            print(f"{idx:3d} {arm:<5s} {d['wall_ms']:8.3f} {d['busy_ms']:8.3f} "
                  f"{d['gap_ms']:8.3f} {s.get('us_call', float('nan')):15.3f} "
                  f"{r.get('us_call', float('nan')):15.3f}")
    print()

    def call_us(arm, kern):
        v = [d["kernels"][kern]["us_call"] for _, d in caps.get(arm, [])
             if kern in d["kernels"]]
        return st.mean(v) if v else None

    def n_step(arm, kern):
        v = [d["kernels"][kern]["n_step"] for _, d in caps.get(arm, [])
             if kern in d["kernels"]]
        return st.mean(v) if v else 39.0

    def busy_step(arm):
        v = [d["busy_ms"] for _, d in caps.get(arm, [])]
        return st.mean(v) if v else None

    for kern, dose_arm, label, mb_blk, standalone in (
            (SHARED, "d1", "shared gate+up QMV", 10.86, 5.637),
            (ROUTED, "rd1", "routed gate+up QMV", 86.9, None)):
        b4, b1 = call_us("ship", kern), call_us(dose_arm, kern)
        if b4 is None or b1 is None:
            print(f"-- {label}: missing arm (ship={b4}, {dose_arm}={b1})\n")
            continue
        m = (b4 - b1) / 3.0
        c = b1 - m
        n = n_step("ship", kern)
        print(f"== {label}  ({kern})")
        print(f"   busy/call  4 blocks (ship) = {b4:7.3f} us")
        print(f"   busy/call  1 block  ({dose_arm:>4s}) = {b1:7.3f} us")
        if abs(m) < 1e-6:
            print(f"   marginal   m = {m:7.3f} us per K block "
                  f"({mb_blk / n:.4f} MB/call -> marginal rate undefined: the "
                  f"profiler reports NO busy response to a 3-block dose)")
        else:
            print(f"   marginal   m = {m:7.3f} us per K block "
                  f"({mb_blk / n:.4f} MB/call -> "
                  f"{mb_blk / n / (m * 1e-6) / 1e3:6.1f} GB/s marginal)")
        print(f"   FIXED      c = {c:7.3f} us per call "
              f"({100.0 * c / b4:.1f} % of the shipped per-call cost)")
        print(f"   4m + c     = {4 * m + c:7.3f} us  (identity check vs {b4:.3f})")
        print(f"   per step   fixed part = {c * n:7.1f} us/step, "
              f"byte part = {4 * m * n:7.1f} us/step")
        if standalone is not None:
            print(f"   standalone-cold rig for the same kernel text: "
                  f"{standalone:.3f} us/call (R110 F1)")
            print(f"   in-situ excess over the rig = {b4 - standalone:.3f} "
                  f"us/call = {(b4 - standalone) * n:.1f} us/step")
            print(f"   of which the fixed part c accounts for "
                  f"{100.0 * c / max(1e-9, b4 - standalone):.0f} %")
        dbusy = (b4 - b1) * n
        print(f"   delta busy for this dose = {dbusy:8.1f} us/step")
        wall = a.wall_shared if kern == SHARED else a.wall_routed
        rec = {
            "kernel": kern, "dose_arm": dose_arm, "calls_per_step": n,
            "busy_us_call_4blocks_ship": b4, "busy_us_call_1block": b1,
            "marginal_us_per_k_block": m, "mb_per_call": mb_blk / n,
            "marginal_gbps": (mb_blk / n / (m * 1e-6) / 1e3)
            if abs(m) > 1e-6 else None,
            "fixed_us_call": c, "fixed_pct_of_shipped_call": 100.0 * c / b4,
            "fixed_us_step": c * n, "byte_us_step": 4 * m * n,
            "standalone_cold_us_call": standalone,
            "in_situ_excess_us_call": (b4 - standalone)
            if standalone is not None else None,
            "in_situ_excess_us_step_busy": (b4 - standalone) * n
            if standalone is not None else None,
            "delta_busy_us_step": dbusy,
            "delta_wall_us_step": wall,
            "tau": (wall / dbusy) if (wall and abs(dbusy) > 1e-6) else None,
        }
        if rec["tau"] and rec["in_situ_excess_us_step_busy"] is not None:
            rec["in_situ_excess_us_step_wall_at_tau"] = \
                rec["in_situ_excess_us_step_busy"] * rec["tau"]
        out["families"][label] = rec
        if wall:
            print(f"   delta wall  for this dose = {wall:8.1f} us/step "
                  f"(SPLIT=0 campaign)")
            if abs(dbusy) < 1e-6:
                print(f"   ==> tau({label}) undefined: the profiler saw no "
                      f"busy change for a dose that moved {wall:.1f} us of "
                      f"wall.  That is a statement about the profiler, and it "
                      f"is reported rather than divided by.")
            else:
                print(f"   ==> tau({label}) = {wall / dbusy:.3f}")
        print()

    for arm in sorted(caps):
        bs = busy_step(arm)
        if bs:
            print(f"whole-step busy, arm {arm}: {bs * 1e3:.1f} us/step")
            out["whole_step_busy_us"][arm] = bs * 1e3

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
