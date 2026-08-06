#!/usr/bin/env python3
"""Deflate the SPLIT=1 prefill family ledger by measured per-command-buffer overhead.

DARKBLOOM_GPU_PROFILE_SPLIT=1 puts every dispatch in its own command buffer so
each one can be attributed individually.  That isolation is not free: it adds one
command-buffer setup/teardown per dispatch.  This script removes that instrument
tax from every family and checks the deflated total against the *unhooked-batching*
(SPLIT=0) union, which is the serial ground truth for the same work.

Inputs are the medians already emitted by pr91_census.py; nothing is re-measured
here, so this is pure arithmetic over logged values and is exactly reproducible.

Column labels follow the census convention:
  A = algorithmic / analytic (derived from source + geometry, host-independent)
  M = machine-determined (measured on this host, carries this host's noise)
"""

# ---- measured inputs (all M) -------------------------------------------------

# Per-command-buffer overhead, from the SPLIT=1 vs SPLIT=0 command-buffer delta
# (985 extra command buffers).  Three independent estimators:
PER_CB_US = {
    "warm-median delta (headline)": 5.88,
    "wall delta": 6.17,
    "union delta": 7.41,
}
HEADLINE_PER_CB_US = PER_CB_US["warm-median delta (headline)"]

# SPLIT=1 per-family medians: (dispatches per forward, ms per forward).
FAMILIES = [
    ("routed_gather_gemm", 76, 266.605),
    ("steel_gemm_bf16", 392, 219.295),
    ("sort_scatter", 154, 98.394),
    ("attention_core", 40, 28.209),
    ("nvfp4_dense_qmm", 116, 20.135),
    ("elementwise", 235, 4.747),
    ("qk_norm_rope", 41, 4.323),
    ("moe_tail", 38, 2.537),
    ("rms_norm", 82, 1.687),
    ("router", 40, 0.959),
    ("lm_head", 5, 0.668),
    ("other", 3, 0.309),
]

# `arangeuint32` lives in sort_scatter but is fully overlapped: it never appears
# in the union, so it must be removed before any serial-equivalent comparison.
ARANGE_N = 76
ARANGE_MS = 95.762

# SPLIT=0 union == sum (zero dispatch concurrency under shipped batching).
SPLIT0_UNION_MS = 540.699
SPLIT1_UNION_MS = 547.993
SPLIT1_SUM_MS = 648.007


def deflate(per_cb_us: float) -> tuple[list[tuple[str, int, float, float]], float]:
    rows = []
    total = 0.0
    for name, n, ms in FAMILIES:
        n_eff, ms_eff = n, ms
        if name == "sort_scatter":
            # charge only the non-overlapped remainder
            n_eff -= ARANGE_N
            ms_eff -= ARANGE_MS
        deflated = ms_eff - n_eff * per_cb_us / 1000.0
        rows.append((name, n_eff, ms_eff, deflated))
        total += deflated
    return rows, total


def main() -> None:
    print("prefill SPLIT=1 ledger, per-command-buffer overhead removed")
    print(f"  SPLIT=1 sum            {SPLIT1_SUM_MS:9.3f} ms   (M)")
    print(f"  SPLIT=1 union          {SPLIT1_UNION_MS:9.3f} ms   (M)")
    print(f"  arangeuint32 (overlapped, non-additive)  {ARANGE_MS:7.3f} ms over {ARANGE_N} calls   (M)")
    print(f"  SPLIT=0 union == sum   {SPLIT0_UNION_MS:9.3f} ms   (M, serial ground truth)")
    print()

    for label, us in PER_CB_US.items():
        _, total = deflate(us)
        resid = total - SPLIT0_UNION_MS
        print(
            f"  per-cb {us:4.2f} us [{label}]: deflated total {total:8.3f} ms  "
            f"residual {resid:+7.3f} ms  ({100.0 * resid / SPLIT0_UNION_MS:+.2f} %)"
        )
    print()

    rows, total = deflate(HEADLINE_PER_CB_US)
    print(f"per-family detail at the headline {HEADLINE_PER_CB_US} us/cb")
    print(f"{'family':<22} {'n':>5} {'raw ms':>9} {'deflated ms':>12} {'tax ms':>8} {'%serial':>8}")
    for name, n, ms_eff, deflated in rows:
        print(
            f"{name:<22} {n:>5} {ms_eff:>9.3f} {deflated:>12.3f} "
            f"{ms_eff - deflated:>8.3f} {100.0 * deflated / total:>7.2f}%"
        )
    resid = total - SPLIT0_UNION_MS
    print(f"{'TOTAL':<22} {'':>5} {'':>9} {total:>12.3f}")
    print()
    print(
        f"self-consistency: deflated {total:.3f} ms vs SPLIT=0 union {SPLIT0_UNION_MS:.3f} ms "
        f"-> residual {resid:+.3f} ms = {100.0 * resid / SPLIT0_UNION_MS:+.2f} % over-attribution"
    )
    print(
        "A positive residual means the SPLIT=1 ledger over-attributes: the isolated\n"
        "dispatches are individually slower than the same dispatches inside shipped\n"
        "command buffers even after the per-cb tax is removed.  Treat every family\n"
        "figure as an upper bound with this much headroom."
    )


if __name__ == "__main__":
    main()
