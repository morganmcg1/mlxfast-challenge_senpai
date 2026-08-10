#!/usr/bin/env python3
"""R106-F' Stage 0: paired M4 calibration of the pinned ranked baseline tree.

Inputs are the ABBA-counterbalanced warm medians printed by
research/r106f_calibrate.sh (slots: cand, base, base, cand).
"""
import math

# --- measured, M4 Pro, one session, ABBA counterbalanced -------------------
CAND_DEC = [8.046, 8.202]        # ms/step, median over 40 steps, slots 1 & 4
BASE_DEC = [23.101, 22.967]      # slots 2 & 3
CAND_PRE = [548.673, 544.143]    # ms per 512-token forward, warm median of 5
BASE_PRE = [612.125, 611.593]

# --- the harness/ranked M5 reference the brief supplies --------------------
M5_CAND_DEC = 4.89371            # ms/step
M5_BASE_DEC = 13.855009542       # ms/step  (MB_D)
M5_CAND_PRE = 96.149             # ms / 512 tokens
M5_BASE_PRE = 190.706            # ms / 512 tokens (MB_P * 512 * 1e3)


def mean(v):
    return sum(v) / len(v)


def spread(v):
    return abs(v[0] - v[1]) / mean(v) * 100.0


def main():
    cd, bd = mean(CAND_DEC), mean(BASE_DEC)
    cp, bp = mean(CAND_PRE), mean(BASE_PRE)
    m4_dec, m4_pre = bd / cd, bp / cp
    m5_dec, m5_pre = M5_BASE_DEC / M5_CAND_DEC, M5_BASE_PRE / M5_CAND_PRE

    print("== Stage 0: M4 paired medians (ABBA) ==")
    for n, v in (("cand decode ", CAND_DEC), ("base decode ", BASE_DEC),
                 ("cand prefill", CAND_PRE), ("base prefill", BASE_PRE)):
        print(f"  {n}  mean {mean(v):10.4f} ms   AB spread {spread(v):5.3f}%")

    print("\n== speedups ==")
    print(f"  decode   M4 {m4_dec:7.4f}x   M5 {m5_dec:7.4f}x"
          f"   M4/M5 {m4_dec / m5_dec:7.4f}  ({(m4_dec/m5_dec-1)*100:+.2f}%)")
    print(f"  prefill  M4 {m4_pre:7.4f}x   M5 {m5_pre:7.4f}x"
          f"   M4/M5 {m4_pre / m5_pre:7.4f}  ({(m4_pre/m5_pre-1)*100:+.2f}%)")
    print(f"  share of the M5 log-prefill gain visible on M4: "
          f"{100 * math.log(m4_pre) / math.log(m5_pre):.1f}%")
    print(f"  share of the M5 log-decode  gain visible on M4: "
          f"{100 * math.log(m4_dec) / math.log(m5_dec):.1f}%")

    print("\n== M4 -> M5 hardware factor, per tree ==")
    print(f"  decode   base {bd / M5_BASE_DEC:6.3f}x   cand {cd / M5_CAND_DEC:6.3f}x"
          f"   cand/base {(cd / M5_CAND_DEC) / (bd / M5_BASE_DEC):6.3f}")
    print(f"  prefill  base {bp / M5_BASE_PRE:6.3f}x   cand {cp / M5_CAND_PRE:6.3f}x"
          f"   cand/base {(cp / M5_CAND_PRE) / (bp / M5_BASE_PRE):6.3f}")

    print("\n== scores implied by each host's own paired pair ==")
    for tag, d, p in (("M5 (harness)", m5_dec, m5_pre), ("M4 (measured)", m4_dec, m4_pre)):
        print(f"  {tag:<14} cs = {d ** 0.75 * p ** 0.25:.6f}")

    print("\n== the gap the brief prices ==")
    print(f"  M5: 0.25*ln(dec/pre) = {0.25 * math.log(m5_dec / m5_pre) * 100:+.2f}% of score")
    print(f"  M4: 0.25*ln(dec/pre) = {0.25 * math.log(m4_dec / m4_pre) * 100:+.2f}% of score")


if __name__ == "__main__":
    main()
