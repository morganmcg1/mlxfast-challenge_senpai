#!/usr/bin/env python3
"""PR #27 hardware-constant fit.

Turns receipt observables into the four constants using exactly the algebra the
assignment fixes:

    S = 512000 * prefill_seconds_per_token            (ms, one 512-token forward)
    T = 1000 * decode_seconds_per_token - S/128       (ms, one steady 1-token step)

    DRAM GB/s     = d(bytes per step)    / d(T)
    matrix FLOP/s = d(FLOP per forward)  / d(S)
    c_dispatch    = d(T or S)            / d(dispatch count)

Injection magnitudes (LagunaRuntimeModel.swift, instrument block):
    sweep pass  = 2**24 uint4 = 268_435_456 B read per pass per dispatch
    matmul      = 2*512*2048*8192 = 17_179_869_184 FLOP per dispatch
"""

SWEEP_PASS_BYTES = (1 << 24) * 16
MATMUL_FLOPS = 2 * 512 * 2048 * 8192

# name -> (prefill_seconds_per_token, decode_seconds_per_token,
#          sweep_passes, matmuls, decode_empties, prefill_empties)
RUNS = {
    # ---- M4 Pro (Mac16,11, applegpu_g16s, 20 cores, 48 GB) local-iterate ----
    "m4-zero": (0.00113928271484375, 0.013563942703125, 0, 0, 0, 0),
    "m4-L1": (0.001578521484375, 0.01646667578125, 1, 100, 40, 40),
    # ---- M5 Max official receipts ----
}


def obs(run):
    p, d = run[0], run[1]
    s = 512_000.0 * p
    t = 1000.0 * d - s / 128.0
    return s, t


def show(name):
    s, t = obs(RUNS[name])
    r = RUNS[name]
    print(
        f"{name:10s} S={s:9.3f} ms  T={t:8.4f} ms   "
        f"passes={r[2]} mm={r[3]} empty={r[4]}/{r[5]}"
    )


def bandwidth(a, b, c_dispatch_us=None):
    """GB/s from two runs that differ only in sweep passes."""
    ra, rb = RUNS[a], RUNS[b]
    _, ta = obs(ra)
    _, tb = obs(rb)
    dbytes = (rb[2] - ra[2]) * SWEEP_PASS_BYTES
    dt = tb - ta
    if c_dispatch_us is not None:
        dt -= (rb[4] - ra[4]) * c_dispatch_us / 1000.0
    return dbytes / (dt * 1e-3) / 1e9, dt


def flop_rate(a, b, c_dispatch_us=None):
    """TFLOP/s from two runs that differ only in matmul count."""
    ra, rb = RUNS[a], RUNS[b]
    sa, _ = obs(ra)
    sb, _ = obs(rb)
    dflop = (rb[3] - ra[3]) * MATMUL_FLOPS
    ds = sb - sa
    if c_dispatch_us is not None:
        ds -= (rb[3] - ra[3] + rb[5] - ra[5]) * c_dispatch_us / 1000.0
    return dflop / (ds * 1e-3) / 1e12, ds


def dispatch_cost(a, c):
    """us per injected empty dispatch, on each axis independently."""
    ra, rc = RUNS[a], RUNS[c]
    sa, ta = obs(ra)
    sc, tc = obs(rc)
    out = {}
    if rc[4] != ra[4]:
        out["decode"] = (tc - ta) * 1000.0 / (rc[4] - ra[4])
    if rc[5] != ra[5]:
        out["prefill"] = (sc - sa) * 1000.0 / (rc[5] - ra[5])
    return out


if __name__ == "__main__":
    for name in RUNS:
        show(name)
    print()
    print(
        f"sweep pass = {SWEEP_PASS_BYTES/1e6:.3f} MB   "
        f"matmul = {MATMUL_FLOPS/1e9:.3f} GFLOP"
    )
