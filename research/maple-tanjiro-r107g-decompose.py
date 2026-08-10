#!/usr/bin/env python3
"""R107-G: H-REGIME decomposition arithmetic for the decode-family regime census.

Every input is a measured number carried in from a named artifact log; nothing
here is fitted.  Run with no arguments; it prints the per-family publish block
in the exact shape the assignment asks for.
"""
from __future__ import annotations

# ---------------------------------------------------------------- campaign constants
PRICE_PER_US_STEP = 0.015228   # % of cs per M4 us/step, at k = 1  (rule 105)
ALPHA = 0.4369                 # bytes-regime exchange constant
ALPHA_ALT = 0.389
BETA = 0.5
BYTES_1PCT = 16_714_024        # 1 % of B, in bytes/step
BYTES_1PCT_CS = 0.4223         # ... which is worth this much % of cs
DRAM_PEAK = 266.3e9            # B/s, measured, rule 55
DRAM_INTERCEPT_US = 3.97       # rule 55 fixed term


def bar_us_step(k: float) -> float:
    return 0.4 / (k * PRICE_PER_US_STEP)


def pct_cs(delta_us_step_m4: float, k: float = ALPHA) -> float:
    return delta_us_step_m4 * k * PRICE_PER_US_STEP


def report(
    tag: str,
    dispatches_per_step: int,
    dispatch_us: float,
    bytes_per_dispatch: int,
    threads: int,
    base_fma_per_thread: float,
    us_per_slot_pure: float,       # pure-ALU ceiling probe, matched geometry
    us_per_slot_exposed: float,    # low-dose marginal slope on the real kernel
    m4_family_us_step: float,
    k: float,
) -> None:
    byte_term = bytes_per_dispatch / DRAM_PEAK * 1e6
    issue_nominal = base_fma_per_thread * us_per_slot_pure
    issue_exposed = base_fma_per_thread * us_per_slot_exposed
    residual = dispatch_us - byte_term - issue_exposed
    unexplained = residual - DRAM_INTERCEPT_US
    achieved = bytes_per_dispatch / (dispatch_us * 1e-6)

    print(f"\n================ {tag} ================")
    print(f"  dispatches/step                {dispatches_per_step}")
    print(f"  dispatch_us (M4, defeated)     {dispatch_us:.3f}")
    print(f"  reach: dispatch x count        {dispatch_us * dispatches_per_step:.1f} us/step"
          f"   vs charge {m4_family_us_step:.1f}"
          f"   ({(dispatch_us * dispatches_per_step / m4_family_us_step - 1) * 100:+.2f} %)")
    print(f"  unique bytes / dispatch        {bytes_per_dispatch:,} B")
    print(f"  achieved                       {achieved / 1e9:.1f} GB/s"
          f"  = {achieved / DRAM_PEAK * 100:.1f} % of measured DRAM peak")
    print("  --- H-REGIME terms -------------------------------------------")
    print(f"  byte_term_us  (bytes / 266.3)  {byte_term:.3f}   ({byte_term / dispatch_us * 100:.1f} %)")
    print(f"  issue_term_us  NOMINAL         {issue_nominal:.3f}   ({issue_nominal / dispatch_us * 100:.1f} %)"
          f"   [{base_fma_per_thread:.0f} fma/thr x {us_per_slot_pure:.6f}]")
    print(f"  issue_term_us  EXPOSED         {issue_exposed:.3f}   ({issue_exposed / dispatch_us * 100:.1f} %)"
          f"   [{base_fma_per_thread:.0f} fma/thr x {us_per_slot_exposed:.6f}]")
    print(f"  residual_latency_us            {residual:.3f}   ({residual / dispatch_us * 100:.1f} %)")
    print(f"  ... minus rule-55 intercept    {unexplained:.3f}   ({unexplained / dispatch_us * 100:.1f} %) UNEXPLAINED")
    print(f"  exposure fraction at base      {us_per_slot_exposed / us_per_slot_pure * 100:.1f} %")
    print(f"  ALU headroom (nominal/pure)    {dispatch_us / issue_nominal:.2f}x")
    print("  --- exchange rates ------------------------------------------")
    per_instr_m4 = us_per_slot_exposed * dispatches_per_step
    print(f"  1 instr/thread removed         {per_instr_m4:.5f} us/step M4"
          f"  = {pct_cs(per_instr_m4, k):.6f} % of cs   (k={k})")
    print(f"  BAR: instr/thread for 0.4 %    {0.4 / pct_cs(per_instr_m4, k):.0f}"
          f"   (= {0.4 / pct_cs(per_instr_m4, k) / base_fma_per_thread:.2f}x the entire base ALU load)")
    per_mb = BYTES_1PCT_CS / BYTES_1PCT * 1_048_576
    bar_bytes = 0.4 / BYTES_1PCT_CS * BYTES_1PCT
    fam_bytes = bytes_per_dispatch * dispatches_per_step
    print(f"  1 MiB/step removed             {per_mb:.5f} % of cs")
    print(f"  BAR: MiB/step for 0.4 %        {bar_bytes / 1048576:.2f} MiB/step"
          f"  = {bar_bytes / fam_bytes * 100:.2f} % of this family's own bytes")
    print(f"  family bytes/step              {fam_bytes / 1048576:.1f} MiB"
          f"  = {fam_bytes / (BYTES_1PCT * 100) * 100:.1f} % of B")
    print(f"  0.4 % bar in M4 us/step        {bar_us_step(k):.1f}"
          f"  = {bar_us_step(k) / m4_family_us_step * 100:.1f} % of this family's own M4 cost")
    headroom_us = dispatch_us * (1 - achieved / DRAM_PEAK)
    print(f"  efficiency ceiling (bytes fixed) {headroom_us * dispatches_per_step:.1f} us/step M4"
          f"  = {pct_cs(headroom_us * dispatches_per_step, k):.3f} % of cs  (rule 105-E caps at 1.548 %)")


print("=== bars, all three k values (rule 105) ===")
for name, k in (("alpha=0.4369", ALPHA), ("alpha=0.389", ALPHA_ALT), ("beta=0.5", BETA)):
    print(f"  {name:14s} 0.4 % bar = {bar_us_step(k):6.1f} M4 us/step")

# ---------------------------------------------------------------- FAMILY D  (T2c)
report(
    tag="FAMILY D  T2c routed gate+up QMV  (2048 TG x 64 thr)",
    dispatches_per_step=39,
    dispatch_us=38.80,                    # mean of s1 38.75 / s2 38.85, defeated
    bytes_per_dispatch=8_925_845,
    threads=131_072,
    base_fma_per_thread=128,
    us_per_slot_pure=0.038043721,         # stage1-ALU-ceiling-s1-tgs2048-tpt64
    us_per_slot_exposed=0.003313,         # dose 0->4 marginal, defeated
    m4_family_us_step=1497.7,
    k=ALPHA,
)
