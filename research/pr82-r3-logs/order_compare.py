#!/usr/bin/env python3
"""PR #82 r3 dispatch-order analysis.

Reads the SPLIT=0 profile logs written by run_arms.sh and reports, per arm:
  * per-steady-step gpu_busy_sum, cb count, dispatch count
  * whether decode_router_top8_ordinal_table_norm_v1 is emitted before or
    after shared_nvfp4_swiglu_qmv_rows1_bf16_v1 inside MoE-containing groups
  * cell means / half-ranges and the O0-vs-Ob contrast
Group name-lists keep emission order, so the relative position of the two
kernel names inside a group is the mechanism check.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTER = "decode_router_top8_ordinal_table_norm_v1"
SHARED = "shared_nvfp4_swiglu_qmv_rows1_bf16_v1"
ROW = re.compile(r"\s+([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(.*)$")
HDR = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms .* cbs=([\d.]+) "
    r"dispatches=([\d.]+)")


def parse(tag):
    path = os.path.join(HERE, tag + ".txt")
    if not os.path.exists(path):
        return None
    out = {"tag": tag, "groups": {}, "divergences": None}
    for line in open(path):
        if "divergences" in line:
            out["divergences"] = line.strip()
        m = HDR.search(line)
        if m:
            out["wall"] = float(m.group(1))
            out["busy_sum"] = float(m.group(2)) * 1000.0
            out["busy_union"] = float(m.group(3)) * 1000.0
            out["gap"] = float(m.group(4)) * 1000.0
            out["cbs"] = float(m.group(5))
            out["dispatches"] = float(m.group(6))
            continue
        m = ROW.match(line.rstrip("\n"))
        if m:
            raw = m.group(5)
            body = raw.split("] ", 1)[1] if raw.startswith("[") else raw
            key = "|".join(sorted(body.split("|")))
            out["groups"][key] = (float(m.group(1)), float(m.group(3)), body)
    return out


def order_flag(run):
    """+1 router-before-shared, -1 shared-before-router, 0 none/mixed."""
    votes = set()
    for _, (_, _, body) in run["groups"].items():
        parts = body.split("|")
        if ROUTER in parts and SHARED in parts:
            votes.add(1 if parts.index(ROUTER) < parts.index(SHARED) else -1)
    if votes == {1}:
        return 1
    if votes == {-1}:
        return -1
    return 0


def moe_split(run):
    """(MoE-group us/step, non-MoE us/step)."""
    moe = non = 0.0
    for _, (us, _, body) in run["groups"].items():
        parts = body.split("|")
        if ROUTER in parts or SHARED in parts:
            moe += us
        else:
            non += us
    return moe, non


ARMS = {
    "O0 shipped": ["o0_a", "o0_b", "o0_c"],
    "Ob routerlate": ["ob_a", "ob_b", "ob_c"],
    "Osf sharedfirst": ["osf_a"],
    "Oc routerearly": ["oc_a"],
    "Od routedlast": ["od_a"],
}
LABEL = {1: "router->shared", -1: "shared->router", 0: "mixed/absent"}

cells = {}
print(f"{'arm':18}{'run':8}{'busy_sum':>10}{'union':>9}{'gap':>8}"
      f"{'cbs':>7}{'disp':>7}{'MoE':>9}{'nonMoE':>9}  emit-order  tokens")
for arm, tags in ARMS.items():
    vals = []
    for tag in tags:
        r = parse(tag)
        if r is None or "busy_sum" not in r:
            print(f"{arm:18}{tag:8}  MISSING")
            continue
        moe, non = moe_split(r)
        vals.append(r["busy_sum"])
        div = (r["divergences"] or "?").replace(
            "teacher-forced greedy tokens: ", "")
        print(f"{arm:18}{tag:8}{r['busy_sum']:10.1f}{r['busy_union']:9.1f}"
              f"{r['gap']:8.1f}{r['cbs']:7.1f}{r['dispatches']:7.1f}"
              f"{moe:9.1f}{non:9.1f}  {LABEL[order_flag(r)]:14}{div}")
    if vals:
        cells[arm] = vals

print()
print(f"{'arm':18}{'n':>3}{'mean':>10}{'half-range':>12}")
for arm, v in cells.items():
    hr = (max(v) - min(v)) / 2
    print(f"{arm:18}{len(v):3d}{sum(v)/len(v):10.1f}{hr:12.2f}")

if "O0 shipped" in cells and "Ob routerlate" in cells:
    b, c = cells["O0 shipped"], cells["Ob routerlate"]
    mb, mc = sum(b)/len(b), sum(c)/len(c)
    noise = (max(b)-min(b))/2 + (max(c)-min(c))/2
    print(f"\nCONTROL  Ob - O0 = {mc - mb:+.1f} us/step "
          f"({100*(mc-mb)/mb:+.3f} %)  pooled half-range noise {noise:.2f}")
    print("pre-registered prediction +54.5 us/step (+0.67 %)")
    if mc - mb >= 40:
        print("=> branch 1: causal claim ESTABLISHED")
    elif abs(mc - mb) < noise:
        print("=> branch 2: NULL, re-attribute and stop")
    elif mc - mb <= -noise:
        print("=> branch 3: control is FASTER, opposite sign")
    else:
        print("=> between branches: report the raw number, no causal claim")
sys.exit(0)
