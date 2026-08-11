#!/usr/bin/env python3
"""Paired layer-2 ABBA analysis for R119-A.

Reads the TSV written by maple-alphonse-r119-gridappend-bench-abba.sh and
reports, per arm, the delta against the C reference on both axes, plus the
two mirrored halves separately and the run-position listing that exposes any
within-session drift.
"""
import math
import statistics as st
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r119-gridappend-bench.tsv"


def sem(v):
    return st.stdev(v) / math.sqrt(len(v)) if len(v) > 1 else float("nan")


def main():
    rows = [l.split("\t") for l in open(PATH).read().strip().split("\n")[1:]]
    seq = [(int(r[0]), r[1], float(r[4]) * 1e6, float(r[5]) * 1e6, r[6]) for r in rows]

    print(f"runs={len(seq)}  passed_correctness all true: {all(s[4] == 'true' for s in seq)}")
    for name, col in (("DECODE", 2), ("PREFILL", 3)):
        print(f"== {name} us/token")
        by = {}
        for s in seq:
            by.setdefault(s[1], []).append(s[col])
        c = by["C"]
        cm = st.mean(c)
        print(f"  C n={len(c)} mean={cm:9.3f} sd={st.stdev(c):7.3f} se={sem(c):7.3f} "
              f"vals={[round(x, 1) for x in c]}")
        # With n=2 per candidate arm a per-arm sd is worthless: two adjacent
        # draws can land arbitrarily close and manufacture a tight interval.
        # Pool the within-arm variation across every arm instead.
        ss = sum((len(v) - 1) * st.variance(v) for v in by.values() if len(v) > 1)
        dof = sum(len(v) - 1 for v in by.values() if len(v) > 1)
        pooled = math.sqrt(ss / dof)
        print(f"  pooled within-arm sd={pooled:7.3f} (dof={dof})")
        for a in sorted(k for k in by if k != "C"):
            v = by[a]
            m = st.mean(v)
            s = math.sqrt(sem(v) ** 2 + sem(c) ** 2)
            sp = pooled * math.sqrt(1 / len(v) + 1 / len(c))
            print(f"  {a} n={len(v)} mean={m:9.3f} delta={m - cm:+8.3f} "
                  f"rel={100 * (m - cm) / cm:+.3f}% vals={[round(x, 1) for x in v]}")
            print(f"      per-arm se={s:6.3f} 95%CI=[{m - cm - 1.96 * s:+8.3f},"
                  f"{m - cm + 1.96 * s:+8.3f}]")
            print(f"      pooled   se={sp:6.3f} 95%CI=[{m - cm - 1.96 * sp:+8.3f},"
                  f"{m - cm + 1.96 * sp:+8.3f}]")
        half = len(seq) // 2
        for label, idxs in (("forward", range(1, half + 1)), ("mirror", range(half + 1, len(seq) + 1))):
            sub = [s for s in seq if s[0] in idxs]
            cref = st.mean([s[col] for s in sub if s[1] == "C"])
            out = ", ".join(f"{s[1]}={s[col] - cref:+7.3f}" for s in sub if s[1] != "C")
            print(f"    {label}: localC={cref:9.3f}  {out}")
    print("\nposition order (idx: arm decode prefill):")
    for i, a, d, p, _ in seq:
        print(f"  {i}: {a} {d:9.3f} {p:9.3f}")


main()
