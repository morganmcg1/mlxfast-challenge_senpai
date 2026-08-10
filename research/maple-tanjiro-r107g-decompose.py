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

# ================================================================ CROSS-FAMILY AUDIT
# Measured host constants (this report):
FMA_CEILING = 3.4453e12        # stage1-ALU-ceiling-s1-tgs2048-tpt64, sustained
STREAM_BEST = 262.96e9         # stage1-BW-geometry-s1, best geometry (8 TG/core x 64 thr)
EXPOSURE_AT_BASE = 0.087       # measured on family D; transferred, flagged in the report

MACHINE_BALANCE = DRAM_PEAK / FMA_CEILING      # bytes per fma at which the host is balanced

# family, calls/step, HEAD MB/step (fern r101 audit), M4 us/step (B.0.3),
# threads, total fma/dispatch, streaming GB/s achievable at that geometry (measured)
FAMILIES = [
    ("D  T2c routed gate+up",   39, 347.60, 1497.7, 131_072,  8 * 2 * 512 * 2048, 256.4e9),
    ("A  T3b oproj h64",        30, 259.58, 1117.7,  16_384,      2048 * 8192,    254.4e9),
    ("C  T0b(a) qkv h64",       30, 324.71, 1340.1,  81_920,     10240 * 2048,    254.4e9),
    ("B  T2d down+residual",    39, 195.53,  858.9, 147_456,  9 * 2048 * 512,     252.3e9),
    ("E  T2b gate_sp h64",      30,   7.86,  248.0,   1_920,        64 * 2048,    219.3e9),
]

print("\n\n================ CROSS-FAMILY BYTE / ISSUE AUDIT ================")
print(f"  measured DRAM peak              {DRAM_PEAK/1e9:.1f} GB/s")
print(f"  measured best streaming rate    {STREAM_BEST/1e9:.2f} GB/s "
      f"= {STREAM_BEST/DRAM_PEAK*100:.1f} % of peak")
print(f"  measured sustained fma ceiling  {FMA_CEILING/1e12:.4f}e12 fma/s")
print(f"  ==> MACHINE BALANCE POINT       {MACHINE_BALANCE:.5f} bytes per fma")
print("\n  family                       disp_us   B/dispatch   GB/s   %peak  %geom   "
      "B/fma  x_bal  nom_ALU%  exp_ALU%  lat%")
rows = []
for name, calls, headMB, m4, threads, fma, geom in FAMILIES:
    dus = m4 / calls
    b = headMB * 1e6 / calls
    ach = b / (dus * 1e-6)
    issue_nom = fma / FMA_CEILING * 1e6
    issue_exp = issue_nom * EXPOSURE_AT_BASE
    byte_term = b / DRAM_PEAK * 1e6
    lat = dus - byte_term - issue_exp
    intensity = b / fma
    rows.append((name, dus, ach, issue_nom, issue_exp, byte_term, lat))
    print(f"  {name:26s} {dus:7.2f} {b:11,.0f} {ach/1e9:6.1f} {ach/DRAM_PEAK*100:7.1f}"
          f" {ach/geom*100:6.1f} {intensity:7.3f} {intensity/MACHINE_BALANCE:6.1f}"
          f" {issue_nom/dus*100:9.1f} {issue_exp/dus*100:9.2f} {lat/dus*100:6.1f}")

print("\n  regime call: BYTES when %geom >= 85 and exp_ALU% < 5 and lat% < 25")
for name, dus, ach, inom, iexp, bt, lat in rows:
    if ach / DRAM_PEAK > 0.5 and iexp / dus < 0.05 and lat / dus < 0.25:
        verdict, k = "BYTES", ALPHA
    elif iexp / dus > 0.30:
        verdict, k = "ISSUE", None
    else:
        verdict, k = "LATENCY", BETA
    kd = "no valid k - ISSUE-bound" if k is None else f"k = {k}"
    print(f"  {name:26s} -> {verdict:8s}  {kd}")

# ---------------------------------------------------------------- alpha/beta adjudication
print("\n\n================ 3.5  ALPHA / BETA ADJUDICATION ================")
# alpha-free measured M5 achieved rates and M4 efficiencies (B.0.6 + this report)
POOLS = [("routed", 515.9, 0.864), ("qkvo", 597.9, 0.883)]
print("  pool     M5 achieved   M4 efficiency   ceiling M5 needs for efficiency-invariance"
      "   implied alpha")
for pool, m5_ach, m4_eff in POOLS:
    need = m5_ach / m4_eff
    print(f"  {pool:8s} {m5_ach:9.1f}    {m4_eff*100:9.1f} %      {need:14.1f} GB/s"
          f"            {DRAM_PEAK/1e9/need:8.4f}")
for label, ceil in (("alpha=0.4369 -> 610.6", 610.6), ("alpha=0.389  -> 686.0", 686.0)):
    devs = [(m5 / ceil - eff) * 100 for _, m5, eff in POOLS]
    print(f"  {label}:  routed {devs[0]:+.1f} pp   qkvo {devs[1]:+.1f} pp"
          f"   SSE {devs[0]**2 + devs[1]**2:7.1f} pp^2")
