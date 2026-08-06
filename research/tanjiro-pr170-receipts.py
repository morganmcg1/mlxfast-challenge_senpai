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

# Baseline decomposition of the gather GEMM on the control receipt.
DS1 = 43.2619          # ms, measured gather-GEMM cost
DS1_SD = 0.402         # ms
ROOFLINE_FRAC = 0.67   # of BOTH compute and bandwidth roofline
STREAM = ROOFLINE_FRAC * DS1   # 28.99 ms per stream in isolation
SERIAL = 2 * STREAM            # 57.98 ms if perfectly serial
L_BRACKET = SERIAL - DS1       # +14.72 ms, added work fully absorbed
R_BRACKET = STREAM             # +28.99 ms, added work absorbs nothing
EXCESS = DS1 - STREAM          # +14.27 ms over the higher roofline


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


def verdict(dM2, dS2p, dB2):
    """Pre-registered decision rules R1-R5. Deltas are ms of prefill wall."""
    out = []
    if dB2 is not None:
        if dB2 >= 7:
            out.append("R1 H3 WINS: schedule/barrier latency explains >=half "
                       "the roofline excess; next mechanism is barrier removal "
                       "/ occupancy, not fewer FLOPs or bytes.")
        elif dB2 >= 3:
            out.append("R1 H3 PARTIAL: barriers are a real but minority cost.")
        elif dB2 < 1.5:
            out.append("R1 H3 DEAD: synchronisation is not the constraint.")
        else:
            out.append("R1 H3 WEAK: 1.5 <= dB2 < 3, no claim.")
    if dM2 is not None and dS2p is not None:
        if dM2 >= 24 and dM2 - dS2p >= 6:
            out.append("R2 H1 WINS: MMA-limited. Reduce arithmetic.")
        elif dS2p >= 24 and dS2p - dM2 >= 6:
            out.append("R3 H2 WINS: load+dequant-limited. Reduce bytes moved "
                       "or make dequant cheaper.")
        elif 13 <= dM2 <= 19 and 13 <= dS2p <= 19 and (dB2 or 0) < 1.5:
            out.append("R4 H0: jointly saturated; both streams already overlap "
                       "as well as the hardware allows.")
        if dM2 >= 24 and dS2p >= 24 and (dB2 or 0) < 1.5:
            out.append("R5 NEW REGIME (outside H0-H3): neither stream absorbs "
                       "the other -- they run back to back. Next mechanism is "
                       "OVERLAPPING them (software pipelining / double-buffered "
                       "staging), not shrinking either one.")
    return out or ["no rule fired; report the raw deltas without a claim"]


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
    print(f"gather GEMM dS1={DS1:.4f}+-{DS1_SD:.3f} ms  stream={STREAM:.2f} ms  "
          f"excess={EXCESS:.2f} ms  brackets [+{L_BRACKET:.2f}, +{R_BRACKET:.2f}]")
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
    dS2p = None if (dS2 is None or dB2 is None) else dS2 - dB2 / 2.0
    print("--- decomposition ---")
    print(f"  dM2  (pure MMA doubling)        = "
          f"{'n/a' if dM2 is None else f'{dM2:+.3f} ms'}")
    print(f"  dB2  (pure barrier doubling)    = "
          f"{'n/a' if dB2 is None else f'{dB2:+.3f} ms'}")
    print(f"  dS2  (raw, load+dequant+1 barr) = "
          f"{'n/a' if dS2 is None else f'{dS2:+.3f} ms'}")
    print(f"  dS2p (= dS2 - dB2/2, pure load) = "
          f"{'n/a' if dS2p is None else f'{dS2p:+.3f} ms'}")
    print()
    print("--- verdict ---")
    for line in verdict(dM2, dS2p, dB2):
        print(f"  {line}")
    print()
    print("--- decode control (must be unchanged) ---")
    for name, g in got.items():
        flag = "OK" if abs(g["dT"]) < 0.05 else "LEAK?"
        print(f"  {name}: dT = {g['dT']:+.5f} ms  {flag}")


if __name__ == "__main__":
    main()
