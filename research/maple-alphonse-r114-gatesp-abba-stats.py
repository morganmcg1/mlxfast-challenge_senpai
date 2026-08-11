#!/usr/bin/env python3
"""Paired block statistics for the R114-E gate_sp fusion ABBA.

The driver emits a palindromic CFFC-block order, so each consecutive CFFC
block is a self-contained pair whose mean cancels any monotone drift in host
state.  We report the per-block delta (F mean - C mean), its mean, and a
Student-t interval over the blocks, plus the pooled two-sample view as a
sanity check.  Research instrumentation only; not part of the runtime.
"""
import statistics
import sys

BAR_US = 36.0  # 0.25 % of a 14.4 ms M4 decode step, per the assignment


def read(path):
    rows = []
    with open(path) as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 5 or f[2] == "NA":
                continue
            rows.append((f[1], float(f[2]), float(f[3]), f[4]))
    return rows


def t_crit(df):
    return {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
            6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}.get(df, 1.96)


def main(path):
    rows = read(path)
    bad = [r for r in rows if r[3] != "true"]
    if bad:
        print(f"!! {len(bad)} run(s) failed correctness -- results are void")
    print(f"n = {len(rows)} runs\n")

    blocks, cur = [], []
    for r in rows:
        cur.append(r)
        if len(cur) == 4:
            blocks.append(cur)
            cur = []
    if cur:
        print(f"(dropping {len(cur)} trailing runs outside a complete block)\n")

    deltas = []
    print("block   C mean (s/tok)   F mean (s/tok)   delta us/step   delta %")
    for i, b in enumerate(blocks, 1):
        c = statistics.mean(x[1] for x in b if x[0] == "C")
        f = statistics.mean(x[1] for x in b if x[0] == "F")
        d = (f - c) * 1e6
        deltas.append(d)
        print(f"  {i}     {c:.9f}      {f:.9f}     {d:+8.1f}      {100*(f-c)/c:+.3f}")

    if len(deltas) < 2:
        return
    m = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    se = sd / len(deltas) ** 0.5
    h = t_crit(len(deltas) - 1) * se
    print(f"\npaired block delta  {m:+.1f} us/step   95% CI [{m-h:+.1f}, {m+h:+.1f}]")
    print(f"excludes zero: {'YES' if abs(m) > h else 'NO'}")
    print(f"clears the {BAR_US:.0f} us bar: "
          f"{'YES' if (m + h) < -BAR_US else 'NO'}  (needs the whole CI below -{BAR_US:.0f})")

    allc = [x[1] for x in rows if x[0] == "C"]
    allf = [x[1] for x in rows if x[0] == "F"]
    print(f"\npooled  C {statistics.mean(allc):.9f} (sd {statistics.stdev(allc)*1e6:.1f} us)"
          f"  F {statistics.mean(allf):.9f} (sd {statistics.stdev(allf)*1e6:.1f} us)"
          f"  delta {(statistics.mean(allf)-statistics.mean(allc))*1e6:+.1f} us")

    pc = [x[2] for x in rows if x[0] == "C"]
    pf = [x[2] for x in rows if x[0] == "F"]
    print(f"prefill C {statistics.mean(pc):.9f}  F {statistics.mean(pf):.9f}"
          f"  delta {(statistics.mean(pf)-statistics.mean(pc))*1e6:+.1f} us/token")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/r114-gatesp-fusion.tsv")
