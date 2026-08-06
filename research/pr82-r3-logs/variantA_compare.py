#!/usr/bin/env python3
"""r3 item 2: interleaved BASE/CAND replication of PR #82 Variant A."""
import pathlib
import re
import statistics

LOGS = pathlib.Path(__file__).parent
STEP = re.compile(
    r"per steady step: wall=(?P<wall>[\d.]+) ms gpu_busy_sum=(?P<sum>[\d.]+) ms "
    r"gpu_busy_union=(?P<union>[\d.]+) ms gap=(?P<gap>[\d.]+) ms .* "
    r"cbs=(?P<cbs>[\d.]+) dispatches=(?P<disp>[\d.]+)"
)
GROUP = re.compile(r"^\s*\d+:\s+([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+\[\d+\]\s+(.*)$")
MOE = ("swiglu_qmv", "ordinal_table", "down_residual", "router_bf16")
ARMS = {"BASE": ["base_a", "base_b", "base_c"], "CAND": ["cand_a", "cand_b", "cand_c"]}


def parse(tag):
    path = LOGS / f"{tag}.txt"
    if not path.exists():
        return None
    text = path.read_text()
    m = STEP.search(text)
    if not m:
        return None
    rec = {k: float(v) for k, v in m.groupdict().items()}
    rec["sum_us"] = rec["sum"] * 1000.0
    rec["moe"] = rec["nonmoe"] = 0.0
    kernel_us = {}
    for line in text.splitlines():
        g = GROUP.match(line)
        if not g:
            continue
        us, _, n, _, body = g.groups()
        us, n = float(us), float(n)
        names = body.split("|")
        share = us / max(len(names), 1)
        for name in names:
            kernel_us[name] = kernel_us.get(name, 0.0) + share
            if any(k in name for k in MOE):
                rec["moe"] += share
            else:
                rec["nonmoe"] += share
    rec["kernels"] = kernel_us
    rec["routed_qmv"] = sum(v for k, v in kernel_us.items() if "routed_nvfp4_swiglu_qmv" in k)
    rec["ordinal"] = sum(v for k, v in kernel_us.items() if "ordinal_table" in k)
    rec["variant"] = "idx" if any("top8idx" in k for k in kernel_us) else "keys"
    rec["tokens"] = "0 divergences" in text
    return rec


print(f"{'arm':<6} {'run':<8} {'busy_sum':>9} {'gap':>7} {'cbs':>5} {'disp':>6} "
      f"{'routedQMV':>10} {'ordinal':>8} {'kernel':>7} {'exact':>6}")
cells = {}
for arm, tags in ARMS.items():
    vals = []
    for tag in tags:
        r = parse(tag)
        if r is None:
            print(f"{arm:<6} {tag:<8} MISSING")
            continue
        vals.append(r["sum_us"])
        print(f"{arm:<6} {tag:<8} {r['sum_us']:9.1f} {r['gap']*1000:7.1f} {r['cbs']:5.0f} "
              f"{r['disp']:6.0f} {r['routed_qmv']:10.1f} {r['ordinal']:8.1f} "
              f"{r['variant']:>7} {str(r['tokens']):>6}")
    if vals:
        cells[arm] = (statistics.mean(vals), (max(vals) - min(vals)) / 2, len(vals))

print()
for arm, (mean, hr, n) in cells.items():
    print(f"{arm:<6} n={n} mean={mean:9.1f} us/step  half-range={hr:6.2f}")

if len(cells) == 2:
    b_mean, b_hr, _ = cells["BASE"]
    c_mean, c_hr, _ = cells["CAND"]
    delta = c_mean - b_mean
    noise = b_hr + c_hr
    print(f"\nCAND - BASE = {delta:+.1f} us/step ({delta / b_mean * 100:+.3f} %)"
          f"  pooled half-range noise {noise:.2f}")
    print("r2 reported SPLIT=0 CAND - BASE = +56.5 us/step (+0.698 %)")
    if abs(delta) < noise:
        print("=> NULL: r2 SPLIT=0 regression does NOT replicate at n=3 interleaved")
    elif delta > 0:
        print("=> replicates: Variant A is a real regression")
    else:
        print("=> reverses: Variant A is a real improvement")
