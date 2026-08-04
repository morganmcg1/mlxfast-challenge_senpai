#!/usr/bin/env python3
"""Fit hardware constants from work-injection receipts (PR #27).

Every run reports two observables. With the injected work known exactly, two
runs give one rate per axis:

    S = 512000 * prefill_seconds_per_token          (ms, 512-token forward)
    T = 1000 * decode_seconds_per_token - S/128     (ms, steady 1-token step)

    DRAM GB/s     = d(bytes per decode step) / d(T)
    matrix FLOP/s = d(FLOP per forward)     / d(S)
    per-dispatch  = d(T or S) / d(dispatch count)

Usage: python3 research/tanjiro-pr27-fit.py
Edit RUNS below; each entry is one receipt.
"""

SWEEP_BYTES = (1 << 24) * 16  # 268,435,456 B per injected DRAM sweep
MATMUL_FLOPS = 2 * 512 * 2048 * 8192  # 17,179,869,184 FLOP per injected matmul

# Identical-code noise floors from the 3-receipt control family (PR #13).
FLOOR_T = 0.00475
FLOOR_S = 0.00497


class Run:
    def __init__(self, label, host, prefill_s_per_tok, decode_s_per_tok,
                 sweeps, matmuls, decode_empty, prefill_empty):
        self.label = label
        self.host = host
        self.P = prefill_s_per_tok
        self.D = decode_s_per_tok
        self.S = 512000.0 * self.P
        self.T = 1000.0 * self.D - self.S / 128.0
        self.sweeps = sweeps
        self.matmuls = matmuls
        # Injected dispatches per single-token decode step and per forward.
        self.decode_dispatches = sweeps + decode_empty
        self.prefill_dispatches = matmuls + prefill_empty
        self.decode_bytes = sweeps * SWEEP_BYTES
        self.prefill_flops = matmuls * MATMUL_FLOPS


# ---------------------------------------------------------------------------
# Receipts. Local M4 --local-iterate first, then official M5 submissions.
# ---------------------------------------------------------------------------
RUNS = [
    # Run("m4-0", "M4", 0.0, 0.0, 0, 0, 0, 0),
    # Run("m4-A", "M4", 0.0, 0.0, 1, 40, 40, 40),
    # Run("m4-B", "M4", 0.0, 0.0, 3, 100, 40, 40),
    # Run("m4-C", "M4", 0.0, 0.0, 1, 40, 1000, 4000),
]


def rel(a, b):
    return (b - a) / a * 100.0


def bandwidth(r0, r1):
    """GB/s from the decode-byte difference."""
    dbytes = r1.decode_bytes - r0.decode_bytes
    dt_ms = r1.T - r0.T
    if dbytes == 0 or dt_ms == 0:
        return None
    return (dbytes / 1e9) / (dt_ms / 1e3)


def flop_rate(r0, r1):
    """TFLOP/s from the prefill-FLOP difference."""
    dflop = r1.prefill_flops - r0.prefill_flops
    ds_ms = r1.S - r0.S
    if dflop == 0 or ds_ms == 0:
        return None
    return (dflop / 1e12) / (ds_ms / 1e3)


def dispatch_us(r0, r1, axis):
    if axis == "decode":
        dn = r1.decode_dispatches - r0.decode_dispatches
        dv_ms = r1.T - r0.T
    else:
        dn = r1.prefill_dispatches - r0.prefill_dispatches
        dv_ms = r1.S - r0.S
    if dn == 0:
        return None
    return dv_ms * 1000.0 / dn


def err_pct(v0, v1, floor):
    """Relative 1-sigma error on a difference of two noisy observables."""
    sigma = ((v0 * floor) ** 2 + (v1 * floor) ** 2) ** 0.5
    return abs(sigma / (v1 - v0)) * 100.0 if v1 != v0 else float("nan")


def report(runs):
    print(f"{'run':>8} {'host':>4} {'S ms':>10} {'T ms':>9} "
          f"{'MB/step':>9} {'GFLOP/fwd':>10} {'disp d/p':>10}")
    for r in runs:
        print(f"{r.label:>8} {r.host:>4} {r.S:10.3f} {r.T:9.4f} "
              f"{r.decode_bytes/1e6:9.1f} {r.prefill_flops/1e9:10.1f} "
              f"{r.decode_dispatches:5d}/{r.prefill_dispatches:<5d}")
    print()
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            a, b = runs[i], runs[j]
            if a.host != b.host:
                continue
            print(f"--- {a.label} -> {b.label} "
                  f"(dS {b.S - a.S:+.3f} ms, dT {b.T - a.T:+.4f} ms)")
            bw = bandwidth(a, b)
            if bw:
                print(f"    DRAM            {bw:8.1f} GB/s "
                      f"+/- {err_pct(a.T, b.T, FLOOR_T):.1f}%")
            fr = flop_rate(a, b)
            if fr:
                print(f"    matrix          {fr:8.2f} TFLOP/s "
                      f"+/- {err_pct(a.S, b.S, FLOOR_S):.1f}%")
            cd = dispatch_us(a, b, "decode")
            if cd is not None and b.decode_dispatches != a.decode_dispatches:
                print(f"    c_decode        {cd:8.3f} us/dispatch")
            cp = dispatch_us(a, b, "prefill")
            if cp is not None and b.prefill_dispatches != a.prefill_dispatches:
                print(f"    c_prefill       {cp:8.3f} us/dispatch")
            print()


if __name__ == "__main__":
    if not RUNS:
        print("no receipts recorded yet")
    else:
        report(RUNS)
