#!/usr/bin/env python3
"""Paired interval for the R110-A rev4 Stage 0 norm+QKV fusion contrast.

Reads the TSV written by stage0-norm-qkv-abba.sh and reports, per arm pair, the
mean per-step wall difference with a 95% interval.  Two estimators are printed
because they fail differently:

  unpaired  Welch t on the two arm samples.  Correct if the session has no
            drift; inflated by any monotone session trend.
  blocked   the ORDER is a repeated balanced block, so each block contributes
            one (mean F - mean U) contrast and the block-to-block t interval
            absorbs any drift that is constant within a block.

The decision bar is stated in per-step microseconds: the campaign pricing
constant is 0.0070 % of score per M4 steady-state wall microsecond, so the
Stage 1 gate of +0.25 % score is 35.7 us/step.

  research/maple-tanjiro-r110/stage0-analyze.py TSV [BLOCK_LEN] [A] [B]
"""
import statistics
import sys

# Student t, two-sided 95%, indexed by degrees of freedom (1..30), then a tail
# value good enough for anything larger.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}
BAR_US = 0.25 / 0.0070  # 35.7 us/step buys +0.25 % of score


def t95(df: int) -> float:
    return T95.get(df, 1.960 if df > 200 else 2.021)


def main() -> int:
    tsv, block_len = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8
    a = sys.argv[3] if len(sys.argv) > 3 else "F"
    b = sys.argv[4] if len(sys.argv) > 4 else "U"

    rows = []
    with open(tsv) as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 7 or f[2] == "NA":
                continue
            rows.append((int(f[0]), f[1], float(f[2]), float(f[3]), f[6]))

    bad = [r for r in rows if r[4] not in ("0", "NA")]
    print(f"n={len(rows)} rows; divergent runs: {len(bad)}"
          + (f" -> {bad}" if bad else " (all teacher-forced tokens match)"))

    for col, name in ((2, "mean"), (3, "median")):
        xa = [r[col] * 1e3 for r in rows if r[1] == a]
        xb = [r[col] * 1e3 for r in rows if r[1] == b]
        if len(xa) < 2 or len(xb) < 2:
            continue
        ma, mb = statistics.mean(xa), statistics.mean(xb)
        sa, sb = statistics.stdev(xa), statistics.stdev(xb)
        se = (sa * sa / len(xa) + sb * sb / len(xb)) ** 0.5
        df = min(len(xa), len(xb)) - 1
        h = t95(df) * se
        print(f"\n[{name}] {a} n={len(xa)} {ma:8.1f} us/step sd={sa:6.1f}"
              f"   {b} n={len(xb)} {mb:8.1f} us/step sd={sb:6.1f}")
        print(f"  unpaired  {a}-{b} = {ma - mb:+7.1f} us/step "
              f"[{ma - mb - h:+7.1f}, {ma - mb + h:+7.1f}] (Welch, df={df})")

        blocks = []
        for start in range(0, len(rows), block_len):
            chunk = rows[start:start + block_len]
            ca = [r[col] * 1e3 for r in chunk if r[1] == a]
            cb = [r[col] * 1e3 for r in chunk if r[1] == b]
            if ca and cb:
                blocks.append(statistics.mean(ca) - statistics.mean(cb))
        if len(blocks) >= 2:
            mdiff = statistics.mean(blocks)
            sd = statistics.stdev(blocks)
            hb = t95(len(blocks) - 1) * sd / len(blocks) ** 0.5
            print(f"  blocked   {a}-{b} = {mdiff:+7.1f} us/step "
                  f"[{mdiff - hb:+7.1f}, {mdiff + hb:+7.1f}] "
                  f"(k={len(blocks)} blocks of {block_len}, sd={sd:.1f})")
        print(f"  fusion saving = {mb - ma:+7.1f} us/step "
              f"= {(mb - ma) * 0.0070:+.3f} % of score; "
              f"Stage 1 bar is {BAR_US:.1f} us/step")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
