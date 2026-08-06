#!/usr/bin/env python3
"""Fetch PR170 discriminator receipts and apply the pre-registered verdict.

The `mlxfast submissions` CLI truncates `details` and has no `--json`, so the
full metric set comes from the submissions endpoint:

    curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
      "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
      -o /tmp/subs.json

Usage: tanjiro-pr170-receipts.py <subs.json> [arm=id-prefix ...]
"""

import json
import sys

# Renormalisation constants (advisor's frozen §9.1 contract).
ND_NUM = 0.013890
NPF_NUM = 0.0003845

# Promoted control 97a5090 / commit 3e165fa.
CTRL = {
    "prefill_s_per_tok": 0.00019120068359375,
    "decode_s_per_tok": 0.0049083720703125,
    "officialScore": 2.58882784082067,
    "ns": 2.5982163,
}

# Measured cost of the routed gather GEMM on the control receipt. This is the
# only empirical anchor; everything else below is an exact ledger derivation.
W = 43.2619            # ms, measured prefill gather-GEMM wall
W_SD = 0.402           # ms

# Exact per-window work, derived from weights/config.json:
#   hidden=2048, moe_intermediate=512, experts=256, top_k=8, blocks=40 with
#   L_moe=39 MoE blocks (one block is a dense MLP), NVFP4 4.5 bit = 0.5625 B.
#   values/expert = 2*(2048*512) + 512*2048            = 3,145,728
#   FLOP  = 512*8 * values * 2 * 39                    = 1005.022 GFLOP
#   bytes = 256  * values * 0.5625  * 39               = 17,666.41 MB
# Both reproduce the ledger exactly, which shows the ledger byte figure is
# WEIGHTS ONLY: activations/outputs (~42 MB/layer vs ~453 MB of weights) are
# not counted, so real DRAM traffic is ~9% higher than GBYTE.
GFLOP = 1005.02
GBYTE = 17.66641       # GB of expert weights read per prefill window
AI = GFLOP / GBYTE     # 56.89 FLOP/B -- equals the 34700/610 ridge exactly

TFLOPS_PEAK = 34.7     # M5 Max GPU fp16/bf16 matmul peak
GBPS = {"546.2": 546.2, "610": 610.0, "651.8": 651.8}

# Peak-rate lower bounds on the marginal cost of one added stream. A peak rate
# can only OVERSTATE the machine, so these are floors on an honest measurement:
# an arm below its floor means the injected work did not execute as intended.
M_PEAK = GFLOP / TFLOPS_PEAK                        # 28.96 ms at 34.7 TFLOP/s
D_PEAK = {k: GBYTE / v * 1000.0 for k, v in GBPS.items()}  # 32.3 / 29.0 / 27.1

# Instrument-failure gates (see report section 4.1). Half the peak-derived
# floor is the void threshold; a 2.3x-of-floor cap flags a runaway arm.
FLOOR_M2 = 13.0        # dM2 below this -> R0a, arm void
FLOOR_S2 = 9.5         # dS2 below this -> R0a, arm void
CAP_M2 = 33.3          # dM2 above this -> R0b, flag
CAP_S2 = 37.2          # dS2 above this -> R0b, flag

MU = 0.10 * W          # 4.326 ms, minimum separation for a directional claim
R1_WIN = 0.25 * W      # 10.82 ms, dB2 at or above this makes H3 the headline
R1_MAT = 0.10 * W      # 4.326 ms, dB2 at or above this is material
R5_SUM = W - MU        # 38.94 ms, both streams fitting under this implies H3


def S_ms(prefill_s_per_tok):
    """Prefill wall for the frozen 512-token window, in ms."""
    return 512000.0 * prefill_s_per_tok


def T_ms(decode_s_per_tok, prefill_s_per_tok):
    """Per-step decode wall with the amortised seed prefill removed, in ms."""
    return 1000.0 * decode_s_per_tok - S_ms(prefill_s_per_tok) / 128.0


def ns_of(decode_s_per_tok, prefill_s_per_tok):
    nd = ND_NUM / decode_s_per_tok
    npf = NPF_NUM / prefill_s_per_tok
    return nd ** 0.75 * npf ** 0.25


def load(path):
    d = json.load(open(path))
    if isinstance(d, list):
        return d
    for key in ("submissions", "items", "data", "results"):
        if isinstance(d.get(key), list):
            return d[key]
    raise SystemExit(f"no submission list in {path}: keys={list(d)}")


def verdict(dM2, dS2, dB2):
    """Pre-registered decision rules R0-R5 from report section 4.2.

    Deltas are ms of added prefill wall. dS2 is the RAW S2 delta; the pure
    load cost dS2p is only bracketed, not known, because S2 also adds one
    barrier and B2 adds two whose costs may coalesce:
        dS2p in [dS2 - dB2, dS2 - dB2/2]
    """
    out = []

    # R0: instrument-failure gates. An arm below its peak-derived floor did
    # not execute the work it claims to have added, so it measures nothing.
    void = []
    if dM2 is not None and dM2 < FLOOR_M2:
        void.append(f"dM2={dM2:+.3f} < {FLOOR_M2}")
    if dS2 is not None and dS2 < FLOOR_S2:
        void.append(f"dS2={dS2:+.3f} < {FLOOR_S2}")
    if void:
        out.append("R0a ARM VOID: " + "; ".join(void) + ". Below the peak-rate "
                   "floor, so the injected stream did not run as intended "
                   "(dead-code elimination, wrong probe compiled in, or the "
                   "kernel was not selected). Do not interpret as a regime.")
        return out
    if dM2 is not None and dM2 > CAP_M2:
        out.append(f"R0b FLAG: dM2={dM2:+.3f} > {CAP_M2}; the arm cost far more "
                   "than a peak-rate second stream. Suspect occupancy loss "
                   "(register pressure) rather than pure arithmetic.")
    if dS2 is not None and dS2 > CAP_S2:
        out.append(f"R0b FLAG: dS2={dS2:+.3f} > {CAP_S2}; suspect threadgroup-"
                   "memory or occupancy loss rather than pure load bandwidth.")

    # R1: barriers first, because a large dB2 contaminates dS2's bracket.
    if dB2 is not None:
        if dB2 >= R1_WIN:
            out.append(f"R1 H3 HEADLINE: dB2={dB2:+.3f} >= {R1_WIN:.2f} "
                       "(0.25W). Synchronisation latency dominates; the next "
                       "mechanism is removing barriers / raising occupancy, "
                       "not fewer FLOPs or bytes. dS2's bracket is wide here, "
                       "so treat R2/R3 below as provisional.")
        elif dB2 >= R1_MAT:
            out.append(f"R1' H3 MATERIAL: {R1_MAT:.2f} <= dB2={dB2:+.3f} < "
                       f"{R1_WIN:.2f}. Barriers cost real time but are not the "
                       "binding constraint on their own.")
        else:
            out.append(f"R1'' H3 MINOR: dB2={dB2:+.3f} < {R1_MAT:.2f}. "
                       "Synchronisation is not the constraint; dS2p is tightly "
                       "bracketed.")

    if dM2 is None or dS2 is None or dB2 is None:
        out.append("R2-R5 need all three arms; not all receipts are in.")
        return out

    lo, hi = dS2 - dB2, dS2 - dB2 / 2.0

    # R5 is checked before R2/R3: if both injected streams are largely
    # absorbed, neither is the constraint regardless of which is larger.
    if dM2 + hi <= R5_SUM:
        out.append(f"R5 H3 BY ELIMINATION: dM2+dS2p_hi={dM2 + hi:.3f} <= "
                   f"{R5_SUM:.2f} (W-mu). The kernel absorbed a full extra "
                   "compute stream AND a full extra load stream without "
                   "paying for them, so neither arithmetic nor bandwidth is "
                   "binding. The remaining cost is latency/schedule.")
    elif dM2 - hi >= MU:
        out.append(f"R2 H1 WINS: dM2={dM2:+.3f} exceeds dS2p_hi={hi:+.3f} by "
                   f">= mu={MU:.2f}. MMA-limited: reduce arithmetic.")
    elif lo - dM2 >= MU:
        out.append(f"R3 H2 WINS: dS2p_lo={lo:+.3f} exceeds dM2={dM2:+.3f} by "
                   f">= mu={MU:.2f}. Load+dequant-limited: move fewer bytes or "
                   "make dequant cheaper.")
    else:
        out.append(f"R4 H0 JOINTLY SATURATED: dM2={dM2:+.3f} and dS2p in "
                   f"[{lo:+.3f}, {hi:+.3f}] are within mu={MU:.2f} of each "
                   "other and neither is absorbed. Both streams are already "
                   "overlapped about as well as the hardware allows; only a "
                   "change that shrinks both helps.")
    return out


def main():
    feed = sys.argv[1]
    arms = {}
    for a in sys.argv[2:]:
        name, _, pref = a.partition("=")
        arms[name] = pref

    rows = load(feed)
    ctrl_S = S_ms(CTRL["prefill_s_per_tok"])
    ctrl_T = T_ms(CTRL["decode_s_per_tok"], CTRL["prefill_s_per_tok"])
    print(f"control 97a5090  S={ctrl_S:8.3f} ms  T={ctrl_T:7.5f} ms  "
          f"ns={CTRL['ns']:.6f}")
    print(f"gather GEMM W={W:.4f}+-{W_SD:.3f} ms   {GFLOP:.2f} GFLOP  "
          f"{GBYTE:.4f} GB (weights only)  AI={AI:.2f} FLOP/B")
    dp = "  ".join(f"{k}GB/s:{v:.1f}" for k, v in sorted(D_PEAK.items()))
    print(f"peak-rate stream cost   compute {M_PEAK:.1f} ms   dram {dp}  (ms)")
    print(f"gates  dM2 void<{FLOOR_M2}  flag>{CAP_M2}   dS2 void<{FLOOR_S2}  "
          f"flag>{CAP_S2}   mu={MU:.3f}  R1_win={R1_WIN:.2f}  "
          f"R5_sum={R5_SUM:.2f}")
    print()

    got = {}
    for name, pref in arms.items():
        hit = next((s for s in rows if (s.get("id") or "").startswith(pref)), None)
        if hit is None:
            print(f"{name:4s} {pref}: NOT FOUND in feed")
            continue
        m = hit.get("officialMetrics") or {}
        print(f"=== {name}  {hit.get('id')}  status={hit.get('status')} "
              f"score={hit.get('score')}")
        if not m:
            print("     officialMetrics: (none published)")
            print(f"     error: {hit.get('failureReason') or hit.get('error')}")
            continue
        p = m.get("prefill_seconds_per_token")
        dsec = m.get("decode_seconds_per_token")
        S = S_ms(p)
        T = T_ms(dsec, p)
        got[name] = {"S": S, "T": T, "dS": S - ctrl_S, "dT": T - ctrl_T,
                     "ns": ns_of(dsec, p), "id": hit.get("id")}
        for k in ("passed_correctness", "max_abs_diff",
                  "passed_prefill_speedup_floor", "passed_decode_speedup_floor",
                  "prefill_speedup", "decode_speedup", "gpqa_ttft_passed",
                  "semantic_gpqa_passed", "benchmark_wall_seconds", "commit",
                  "error"):
            if k in m:
                print(f"     {k:32s} {m[k]}")
        print(f"     S                                {S:8.3f} ms "
              f"(dS = {S - ctrl_S:+8.3f})")
        print(f"     T                                {T:8.5f} ms "
              f"(dT = {T - ctrl_T:+8.5f})")
        print()

    dM2 = got.get("m2", {}).get("dS")
    dS2 = got.get("s2", {}).get("dS")
    dB2 = got.get("b2", {}).get("dS")
    span = None if (dS2 is None or dB2 is None) else (dS2 - dB2, dS2 - dB2 / 2.0)
    print("--- decomposition ---")
    print(f"  dM2  (pure MMA doubling)        = "
          f"{'n/a' if dM2 is None else f'{dM2:+.3f} ms'}")
    print(f"  dB2  (pure barrier doubling)    = "
          f"{'n/a' if dB2 is None else f'{dB2:+.3f} ms'}")
    print(f"  dS2  (raw, load+dequant+1 barr) = "
          f"{'n/a' if dS2 is None else f'{dS2:+.3f} ms'}")
    print(f"  dS2p (pure load, interval)      = "
          f"{'n/a' if span is None else f'[{span[0]:+.3f}, {span[1]:+.3f}] ms'}")
    print()
    print("--- verdict ---")
    for line in verdict(dM2, dS2, dB2):
        print(f"  {line}")
    print()
    print("--- decode control (must be unchanged) ---")
    for name, g in got.items():
        flag = "OK" if abs(g["dT"]) < 0.05 else "LEAK?"
        print(f"  {name}: dT = {g['dT']:+.5f} ms  {flag}")


if __name__ == "__main__":
    main()
