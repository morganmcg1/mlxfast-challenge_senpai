#!/usr/bin/env python3
"""Negative-control kernel labels and consistency sum for the R89-A sweep.

Re-analysis only: reads the per-run GPUPROF kernel tables that
`maple_r89_router_insitu` already wrote to OUTDIR/rep{R}_slot{S}.txt. No GPU
time is spent.

Three checks the router-only summary cannot make:

  1. Negative controls. Paired within-rep deltas for kernels the arm provably
     does not touch. A clock/DVFS/process artifact would move them together
     with the router; a real kernel-local effect must leave them null.
  2. Consistency sum. The paired delta of the summed per-kernel us/step should
     equal the router delta, with the non-router remainder at zero.
  3. Per-rep sign count for the router delta (exact binomial).

Usage: python3 research/maple_r89_kernel_controls.py OUTDIR [REF_SLOT]
"""
import math
import os
import re
import statistics
import sys

# The depth is encoded in the kernel name (MLX JIT caches by name), so the
# treated label differs per arm and must be matched by prefix.
ROUTER = "residual_rms_router_bf16_2048_rpg8_keys_v1"


def router_us(t):
    v = [x for k, x in t.items() if k.startswith(ROUTER)]
    return sum(v) if v else None


def is_router(k):
    return k.startswith(ROUTER)

ARM_LABEL = {
    "0": "A0 depth0 baseline",
    "0b": "A0 null control (re-run)",
    "1": "A1 depth1",
    "2": "A2 depth2",
    "3": "A5 depth3",
    "4": "A3 depth4/full",
    "5": "A4 depth1 control (below barriers)",
}

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086}

ROW = re.compile(
    r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s+(\S.*?)\s*$")
NAME = re.compile(r"^rep(\d+)_slot(\S+)\.txt$")


def t95(df):
    return T95.get(df, 1.96 if df > 20 else float("nan"))


def parse(path):
    """kernel -> us/step for one run's steady-state GPUPROF table."""
    out = {}
    in_table = False
    for line in open(path):
        if "us/step" in line and "kernel" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("==="):
            break
        m = ROW.match(line)
        if m:
            out[m.group(5)] = float(m.group(1))
    return out


def load(outdir):
    """(rep, slot) -> {kernel: us/step}"""
    tables = {}
    for fn in sorted(os.listdir(outdir)):
        m = NAME.match(fn)
        if not m:
            continue
        t = parse(os.path.join(outdir, fn))
        if t:
            tables[(int(m.group(1)), m.group(2))] = t
    return tables


def paired(tables, pick, ref):
    """Paired within-rep deltas of `pick(table)`, keyed by slot."""
    by_rep = {}
    for (rep, slot), t in tables.items():
        v = pick(t)
        if v is not None:
            by_rep.setdefault(rep, {})[slot] = v
    out = {}
    for slot in {s for d in by_rep.values() for s in d}:
        diffs = [d[slot] - d[ref] for d in by_rep.values()
                 if slot in d and ref in d]
        levels = [d[slot] for d in by_rep.values() if slot in d]
        if len(diffs) > 1:
            sd = statistics.stdev(diffs)
            out[slot] = (statistics.mean(levels), statistics.mean(diffs),
                         t95(len(diffs) - 1) * sd / math.sqrt(len(diffs)),
                         diffs)
    return out


def table(tables, name, pick, ref, slots):
    print(f"\n=== {name}   [us/step, paired vs slot {ref}] ===", flush=True)
    print(f"{'slot':>5}  {'level':>10}  {'paired d':>10}  {'95% CI':>22}  "
          f"sig  label", flush=True)
    res = paired(tables, pick, ref)
    for slot in slots:
        if slot not in res:
            continue
        lvl, d, hw, _ = res[slot]
        sig = "*" if abs(d) > hw else "."
        print(f"{slot:>5}  {lvl:10.2f}  {d:+10.3f}  "
              f"[{d - hw:+8.3f},{d + hw:+8.3f}]   {sig}   "
              f"{ARM_LABEL.get(slot, slot)}", flush=True)
    return res


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r89insitu"
    ref = sys.argv[2] if len(sys.argv) > 2 else "0"
    tables = load(outdir)
    if not tables:
        sys.exit(f"no rep*_slot*.txt tables under {outdir}")

    slots = sorted({s for _r, s in tables},
                   key=lambda s: (len(s), s))
    reps = sorted({r for r, _s in tables})
    print(f"{outdir}: {len(tables)} runs, {len(reps)} reps, slots {slots}",
          flush=True)

    # Kernels present in every run, ranked by baseline cost. The arm edits one
    # generator, so everything else here is a negative control.
    common = set.intersection(*(set(t) for t in tables.values()))
    base = [t for (r, s), t in tables.items() if s == ref]
    rank = sorted(common, key=lambda k: -statistics.mean(
        t.get(k, 0.0) for t in base))

    table(tables, f"ROUTER (treated): {ROUTER}*",
          router_us, ref, slots)

    controls = [k for k in rank if not is_router(k)]
    print(f"\n--- negative controls: {len(controls)} untreated kernel labels; "
          f"'*' = 95% CI excludes zero ---", flush=True)
    print(f"{'us/step':>9}  " + "  ".join(f"{s:>9}" for s in slots) +
          "  kernel", flush=True)
    worst = None
    nsig = {s: 0 for s in slots}
    for k in controls:
        res = paired(tables, lambda t, k=k: t.get(k), ref)
        cells = []
        for s in slots:
            if s not in res:
                cells.append(f"{'-':>9}")
                continue
            _l, d, hw, _dd = res[s]
            sig = abs(d) > hw
            if sig and s != ref:
                nsig[s] += 1
                if worst is None or abs(d) > abs(worst[2]):
                    worst = (k, s, d, hw)
            cells.append(f"{d:+8.2f}{'*' if sig else ' '}")
        lvl = statistics.mean(t[k] for (r, s), t in tables.items()
                              if s == ref and k in t)
        print(f"{lvl:9.1f}  " + "  ".join(cells) + f"  {k}", flush=True)
    print(f"{'#sig':>9}  " + "  ".join(f"{nsig[s]:>9}" for s in slots) +
          f"  of {len(controls)} untreated labels", flush=True)

    table(tables, "CONSISTENCY SUM: all kernel labels",
          lambda t: sum(t.values()), ref, slots)
    table(tables, "REMAINDER: all labels except the router",
          lambda t: sum(v for k, v in t.items() if not is_router(k)), ref,
          slots)

    print("\n=== per-rep sign count, router delta ===", flush=True)
    res = paired(tables, router_us, ref)
    for slot in slots:
        if slot not in res or slot == ref:
            continue
        _l, d, _hw, diffs = res[slot]
        n = len(diffs)
        neg = sum(1 for x in diffs if x < 0)
        p = sum(math.comb(n, k) for k in range(neg, n + 1)) / 2 ** n
        print(f"slot {slot:>3}: {neg}/{n} reps negative  "
              f"one-sided binomial p={p:.4f}  mean d={d:+.4f}  "
              f"{ARM_LABEL.get(slot, slot)}", flush=True)

    print("\n=== verdict ===", flush=True)
    if worst is None:
        print(f"all {len(controls)} negative controls null for every treated "
              f"slot: no clock/DVFS/process-wide artifact", flush=True)
    else:
        print(f"NON-NULL CONTROL: {worst[0]} slot {worst[1]} "
              f"d={worst[2]:+.3f} hw={worst[3]:.3f}", flush=True)


if __name__ == "__main__":
    main()
