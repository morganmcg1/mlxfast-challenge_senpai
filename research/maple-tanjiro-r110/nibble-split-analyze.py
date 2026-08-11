#!/usr/bin/env python3
"""Paired intervals for the R116-B DARKBLOOM_NVFP4_NIBBLE_SPLIT contrast.

Reads the TSV from nibble-split-abba.sh and reports, for each ordered arm pair,
the per-step wall difference with a 95% interval under two estimators:

  unpaired  Welch t on the two arm samples, with the true Welch-Satterthwaite
            df.  Stage 0 used the conservative df = min(n)-1 and I flagged that
            as a shortcut; this is the honest version.  Correct only if the
            session has no drift.
  blocked   ORDER is 12 consecutive blocks of 3, each a permutation of {0,1,2},
            so every block contributes exactly one (arm A - arm B) contrast with
            both arms measured inside the same short window.  Any drift that is
            locally linear cancels; the block-to-block t interval is the honest
            one and is what the verdict is read from.

Decision bar (advisor Rule 105.12): a decode win under +30 us/step on the
ranked M5 does not justify shipping.  The M4 bytes-bound equivalent is
+68.7 us/step, i.e. this host has to show 2.29x the M5 delta for the same
physical saving because its DRAM is roughly half as wide.  The verdict is read
on the M4 number against 68.7; the M5 translation is printed alongside so the
advisor can price it directly.

  research/maple-tanjiro-r110/nibble-split-analyze.py TSV [BLOCK_LEN]
"""
import itertools
import statistics
import sys

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}

BAR_M4_US = 68.7          # Rule 105.12, M4 bytes-bound
M4_TO_M5 = 30.0 / 68.7    # 0.4367
M5_DECODE_US = 8972.0     # ranked M5 decode wall per step
TAU = 1.06                # real DRAM/work removal converts ~1:1 into wall


def t95(df: float) -> float:
    return T95.get(int(round(df)), 1.960 if df > 200 else 2.021)


def welch_df(sa, na, sb, nb):
    va, vb = sa * sa / na, sb * sb / nb
    num = (va + vb) ** 2
    den = va * va / (na - 1) + vb * vb / (nb - 1)
    return num / den if den else 1.0


def pct_of_score(d_m4_us: float) -> float:
    return 0.75 * TAU * (d_m4_us * M4_TO_M5) / M5_DECODE_US * 100.0


# Offline ISA proof (nibble-split-isa.sh, evidence in nibble-evidence/): arms 0
# and 2 compile to a BYTE-IDENTICAL metallib, differing only in module ID and
# source filename.  Two consequences the analysis must respect:
#   * [0 - 2] is a NEGATIVE CONTROL.  It compares a program with itself, so its
#     interval must contain zero.  If it does not, the rig is mis-stating its
#     own resolution and no other interval here can be believed.
#   * arms 0 and 2 may be POOLED into one arm P, which is the honest treatment
#     contrast (P vs 1) at 2x the samples.
CONTROL_PAIR = ("0", "2")
POOL = {"0": "P", "2": "P", "1": "1"}


def pair_report(rows, a, b, col, block_len, control=False):
    xa = [r[col] * 1e3 for r in rows if r[1] == a]
    xb = [r[col] * 1e3 for r in rows if r[1] == b]
    if len(xa) < 2 or len(xb) < 2:
        return
    ma, mb = statistics.mean(xa), statistics.mean(xb)
    sa, sb = statistics.stdev(xa), statistics.stdev(xb)
    se = (sa * sa / len(xa) + sb * sb / len(xb)) ** 0.5
    df = welch_df(sa, len(xa), sb, len(xb))
    h = t95(df) * se
    d = ma - mb
    tag = "  <== NEGATIVE CONTROL (same machine code)" if control else ""
    print(f"\n  [{a} - {b}]{tag}")
    print(f"    unpaired {d:+7.1f} us/step "
          f"[{d - h:+7.1f}, {d + h:+7.1f}] (Welch, df={df:.1f})")

    blocks = []
    for start in range(0, len(rows), block_len):
        chunk = rows[start:start + block_len]
        ca = [r[col] * 1e3 for r in chunk if r[1] == a]
        cb = [r[col] * 1e3 for r in chunk if r[1] == b]
        if ca and cb:
            blocks.append(statistics.mean(ca) - statistics.mean(cb))
    if len(blocks) < 2:
        return
    md = statistics.mean(blocks)
    sd = statistics.stdev(blocks)
    hb = t95(len(blocks) - 1) * sd / len(blocks) ** 0.5
    print(f"    blocked  {md:+7.1f} us/step "
          f"[{md - hb:+7.1f}, {md + hb:+7.1f}] "
          f"(k={len(blocks)} blocks of {block_len}, sd={sd:.1f})")
    if control:
        ok = (md - hb) <= 0.0 <= (md + hb)
        print(f"    -> control interval {'CONTAINS' if ok else 'EXCLUDES'} zero"
              f" -- rig {'validated' if ok else 'NOT TRUSTWORTHY'};"
              f" measured half-width {hb:.1f} us/step is this rig's true"
              f" resolution on a known-null contrast")
        return
    win = -md   # positive when arm b is faster than arm a
    print(f"    -> switching {a} -> {b} saves {win:+7.1f} us/step "
          f"= {pct_of_score(win):+.3f} % of score; "
          f"bar {BAR_M4_US:.1f}; "
          f"{'CLEARS' if win - hb > BAR_M4_US else 'below bar'}")


def main() -> int:
    tsv = sys.argv[1]
    block_len = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    rows = []
    with open(tsv) as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 7 or f[2] == "NA":
                continue
            rows.append((int(f[0]), f[1], float(f[2]), float(f[3]), f[6]))

    arms = sorted({r[1] for r in rows})
    bad = [r for r in rows if r[4] not in ("0", "NA")]
    print(f"n={len(rows)} rows; arms={arms}; divergent runs: {len(bad)}"
          + (f" -> {bad}" if bad else " (all teacher-forced tokens match)"))
    print(f"bar: {BAR_M4_US:.1f} us/step on this M4 "
          f"(= +{BAR_M4_US * M4_TO_M5:.1f} us/step M5 = "
          f"+{pct_of_score(BAR_M4_US):.2f} % of score at tau={TAU})")

    for col, name in ((2, "mean"), (3, "median")):
        print(f"\n================ {name} per-step wall ================")
        for arm in arms:
            x = [r[col] * 1e3 for r in rows if r[1] == arm]
            print(f"  arm {arm}: n={len(x)} {statistics.mean(x):8.1f} us/step"
                  f"  sd={statistics.stdev(x):6.1f}"
                  f"  min={min(x):8.1f}  max={max(x):8.1f}")

        for a, b in itertools.combinations(arms, 2):
            pair_report(rows, a, b, col, block_len,
                        control=(a, b) == CONTROL_PAIR)

        if set(arms) == set(POOL):
            pooled = [(r[0], POOL[r[1]], r[2], r[3], r[4]) for r in rows]
            print("\n  ---- arms 0 and 2 pooled as P (byte-identical metallib);"
                  " P vs 1 is the treatment contrast ----")
            for arm in ("P", "1"):
                x = [r[col] * 1e3 for r in pooled if r[1] == arm]
                print(f"  arm {arm}: n={len(x)} {statistics.mean(x):8.1f}"
                      f" us/step  sd={statistics.stdev(x):6.1f}")
            pair_report(pooled, "P", "1", col, block_len)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
