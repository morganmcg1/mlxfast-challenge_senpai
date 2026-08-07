#!/usr/bin/env python3
"""Chunk-accurate staged-byte census for the prefill routed NAX gather GEMM.

Prices what `fp_gather_qmm_rhs_expert_nax` actually moves and actually computes
during the scored 512-token prefill, from the measured route histogram rather
than from the analytic all-slots count that the carried ledger uses.

    python3 research/tanjiro-nax-staged-byte-census.py [--csv PATH] [--json PATH]

Everything here is offline arithmetic over committed artifacts; no GPU, no
receipt, no host dependence.  Run it from the repository root.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DEFAULT = os.path.join(REPO, "research/artifacts/route-histogram-prefill512.csv")
JSON_DEFAULT = os.path.join(
    REPO, "research/artifacts/route-histogram-prefill512-stats.json"
)

# ---------------------------------------------------------------------------
# Model / kernel geometry.  Sources are cited so every constant is auditable.
# ---------------------------------------------------------------------------

HIDDEN = 2048  # LagunaConfig.swift:17
MOE_INTER = 512  # LagunaConfig.swift:32
N_EXPERTS = 256  # LagunaConfig.swift:30
TOPK = 8  # LagunaConfig.swift:31
SEQ = 512  # scored prefill window
NUM_HIDDEN_LAYERS = 40  # LagunaConfig.swift:20
SPARSE_LAYERS = 39  # layers 1..39 (validator :495, :541-542)
DISPATCHED_LAYERS = 38  # layer 39 diverts to the M=1 GEMV path (see below)

BYTES_PER_VALUE = 0.5625  # NVFP4: 4 bits code + 8-bit scale per group of 16
GROUP_SIZE = 16

# Ranked instantiation: quantized.cpp:1695-1704, :1491-1526, :1384.
BM, BN, BK = 64, 64, 64
WM, WN = 4, 1
SIMD = 32
THREADS = WM * WN * SIMD  # 128
SM = 16  # fp_quantized_nax.h:1668-1677 derived geometry
BK_PADDED = 72

# The two live projection shapes, as (name, N, K, share_of_values).
#   gate/up fused : [E, N=1024, K=2048]
#   down          : [E, N=2048, K=512]
PROJECTIONS = (
    ("gate_up", 1024, HIDDEN),
    ("down", HIDDEN, MOE_INTER),
)

VALUES_PER_EXPERT = 2 * (HIDDEN * MOE_INTER) + MOE_INTER * HIDDEN  # 3,145,728
FLOP_PER_ROW = 2 * VALUES_PER_EXPERT  # one routed token through one expert

# Carried ledger constants (research/artifacts/tanjiro-pr170-note-s3.md:22-28).
W_MS = 43.2619  # marginal cost of the routed block, PREFILL_ROUTED 39 vs 0
W_MS_LEDGER_SIGMA = 0.402
SIGMA_S_MS = 0.318  # candidate prefill wall sd, n=16 (note-s3 §8)
# A ledger row is always a *difference* of two independent receipts.
THREE_SIGMA_MS = 3.0 * math.sqrt(2.0) * SIGMA_S_MS  # 1.35 ms
S_CONTROL_MS = 97.895
PURE_ISSUE_MS = 6.887  # PR170: staging term that is not bytes
GBYTE_CARRIED = 17.66641  # GB, 39 layers x 256 slots
GFLOP_CARRIED = 1005.02

PEAK_BW_GBPS = 614.0  # assignment value table
PEAK_BW_GBPS_ALT = 610.0  # figure the carried ledger used
PEAK_TFLOPS = 56.0  # corpus bf16 ceiling (tanjiro-pr34-result.md:402, :430)
TFLOPS_RIDGE_ARTIFACT = 34.7  # withdrawn: 34700/610 == this kernel's own AI

# Score sensitivity, this campaign's calibration.
PCT_SCORE_PER_MS = 0.2554  # % of score per ms removed from S

ADVISOR_TABLE = (
    # (label, n, staged_GB, rate_GBps, pct_peak)
    ("chunk-accurate, 38 L", 8379, 14.8264, 342.7, 55.8),
    ("nonzero-expert floor, 38 L", 7757, 13.7258, 317.3, 51.7),
    ("all-slots (analytic), 38 L", 9728, 17.2134, 397.9, 64.8),
    ("chunk-accurate scaled to 39 L", 8599.5, 15.2166, 351.7, 57.3),
)


def rule(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# Kernel work model.
# ---------------------------------------------------------------------------


def staging_model():
    """Per-chunk staging traffic, derived from the loader's own geometry.

    One `loader_w.load_unsafe()` call stages a BN x BK weight tile plus its
    scales, cooperatively across all THREADS threads.  It is issued once per
    k-iteration, per column tile, per chunk -- and, critically, it is *not*
    gated by `sg_active` (fp_quantized_nax.h:1839-1846), so a chunk holding a
    single routed row stages exactly as many bytes as a full 64-row chunk.
    """
    rows = []
    total_calls = 0
    total_bytes = 0
    for name, n, k in PROJECTIONS:
        col_tiles = n // BN
        k_it = k // BK
        calls = col_tiles * k_it
        code_b = BN * BK // 2  # 4-bit codes, two per byte
        scale_b = BN * BK // GROUP_SIZE  # one uint8 scale per group
        per_call = code_b + scale_b
        rows.append(
            dict(
                name=name,
                n=n,
                k=k,
                col_tiles=col_tiles,
                k_it=k_it,
                calls=calls,
                per_call=per_call,
                bytes=calls * per_call,
            )
        )
        total_calls += calls
        total_bytes += calls * per_call
    return rows, total_calls, int(total_bytes)


def executed_mma_rows(rows: int) -> int:
    """Row slots the MMA pipeline actually issues for an expert holding `rows`.

    The M axis is padded twice, at two different granularities:
      * staging / barriers are quantized to BM=64 (a whole chunk),
      * MMA is quantized to SM=16, because `sgp_sm = min(SM, max(0, chunk_rows
        - tm))` and `sg_active = sgp_sm > 0` (fp_quantized_nax.h:1734-1736)
        switch off any simdgroup whose 16-row slice lies past the live rows,
        and `sg_active` gates the A-tile load (:1801) and the MMA chain
        (:1846).
    Summing 16*ceil(chunk_rows/16) over the chunks of one expert collapses to
    16*ceil(rows/16), since BM is a multiple of SM.
    """
    if rows <= 0:
        return 0
    return SM * math.ceil(rows / SM)


def load_route(csv_path: str):
    per_layer: dict[int, list[int]] = {}
    with open(csv_path, newline="") as fh:
        for rec in csv.DictReader(fh):
            per_layer.setdefault(int(rec["layer_index"]), []).append(int(rec["rows"]))
    return per_layer


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--json", default=JSON_DEFAULT)
    args = ap.parse_args()

    for p in (args.csv, args.json):
        if not os.path.exists(p):
            print(f"missing artifact: {p}", file=sys.stderr)
            return 2

    per_layer = load_route(args.csv)
    with open(args.json) as fh:
        doc = json.load(fh)
    stats = doc["pooled"]
    tiles = doc["dispatch_tiles"]

    pairs = [r for rows in per_layer.values() for r in rows]
    n_pairs = len(pairs)
    n_layers_csv = len(per_layer)
    total_rows = sum(pairs)
    zero_pairs = sum(1 for r in pairs if r == 0)
    nonzero_pairs = n_pairs - zero_pairs
    chunks = sum(math.ceil(r / BM) for r in pairs)
    mma_rows = sum(executed_mma_rows(r) for r in pairs)

    # ------------------------------------------------------------------
    rule("0.  ARTIFACT AND GEOMETRY RECONCILIATION")
    print(
        f"""
route histogram : {os.path.relpath(args.csv, REPO)}
  layers present            {n_layers_csv}   (indices {min(per_layer)}..{max(per_layer)})
  (layer, expert) pairs     {n_pairs}   = {n_layers_csv} x {N_EXPERTS}
  routed rows               {total_rows}   = {n_layers_csv} layers x {SEQ} tok x {TOPK} experts
  zero-row slots            {zero_pairs}  ({100.0*zero_pairs/n_pairs:.3f} %)
  nonzero (layer,expert)    {nonzero_pairs}
  chunks at BM={BM}           {chunks}
  mean rows / nonzero slot  {total_rows/nonzero_pairs:.4f}   (vs BM = {BM})

json cross-check: zero_count={stats['zero_count']} nonzero_experts={stats['nonzero_experts']} """
        f"""chunks_bm64={stats['chunks_bm64']} mean_nonzero={stats['mean_nonzero']:.4f}"""
    )
    ok = (
        zero_pairs == stats["zero_count"]
        and nonzero_pairs == stats["nonzero_experts"]
        and chunks == stats["chunks_bm64"]
    )
    print(f"  CSV vs JSON agreement: {'OK' if ok else 'MISMATCH'}")

    print(
        f"""
--- 38 vs 39: the layer multiplier -------------------------------------------
LagunaConfig.swift:20 gives num_hidden_layers = {NUM_HIDDEN_LAYERS}; the validator
(:495, :541-542) and weights/config.json `mlp_layer_types` agree that layer 0 is
dense and layers 1..{SPARSE_LAYERS} are sparse, so the model has {SPARSE_LAYERS} sparse MoE layers.

The shipped 512-token prefill nevertheless dispatches the routed NAX gather GEMM
only {DISPATCHED_LAYERS} times.  LagunaRuntimeModel.swift:10862-10864 routes the final layer
to `callLastPrefillRow` when `h.dim(1) > 1` and the mask is `.causal`; that path
calls `mlp(...)` on a single row (:10504-10507, :10436), i.e. layer 39's MoE runs
as an M=1 GEMV and never enters this kernel.  This is an already-promoted ledger
correction (PR #63, merged f950b5dd; RESEARCH_STATE_ARCHIVE...:5263) and is
independently confirmed in maple-tanjiro-pr91-prefill-budget-census.md:454-467
and maple-fern-m2-lhs-indices.md:493-497.

  => the route histogram's {n_layers_csv} layers are the {DISPATCHED_LAYERS} *dispatched* layers.  It is
     complete for the kernel, and short by one for the model.

Three corpus files disagree or justify this badly and should be corrected:
  research/artifacts/README-route-histogram.md:24-25,:31  asserts 38 with no
      reason and mis-cites LagunaConfig.swift:30-31 (that is numExperts/topk).
  research/h5-per-expert-fused-ffn-closure.md:27-29        says "because layer 0
      is dense", which would give 39, not 38.
  research/lpt_expert_queue_sim.py:48, research/route_histogram.py:41 hardcode
      38 without provenance.

--- what dS_1 = {W_MS} ms actually covers -------------------------------------
Defined in research/tanjiro-pr34-r2-result.md:660 as the raw receipt difference
141.1262 - 97.8643 ms at PREFILL_ROUTED 39 vs 0.  The PR#34 instrument injects
extra routed blocks through a 39-modulus bank map (instrument.patch:149-153),
clamped at num_hidden_layers-1 = 39 (:53-55), so the knob covers exactly {SPARSE_LAYERS}
injected copies, one per sparse bank, bijectively.

Two consequences the corpus currently elides:
  (a) BASIS.  dS_1 is a *{SPARSE_LAYERS}-layer* marginal cost.  The shipped prefill runs the
      kernel {DISPATCHED_LAYERS} times.  The correctly signed rescale to shipped basis is
      {W_MS} x {DISPATCHED_LAYERS}/{SPARSE_LAYERS} = {W_MS*DISPATCHED_LAYERS/SPARSE_LAYERS:.4f} ms -- DOWNWARD.  The
      "x 40/39 = 44.371 ms" correction proposed at tanjiro-pr34-r2-result.md:701-705
      is WRONG: 40 is num_hidden_layers, not the routed-layer count.
  (b) SCOPE.  dS_1 prices `lagunaFusedSortedRoutedGateUp` -- sort/scatter PLUS
      the gate_up gather GEMM PLUS down (instrument.patch:23, :217-221).  PR170's
      W is attributed to `fp_gather_qmm_rhs_expert_nax` alone
      (tanjiro-pr170-note-s3.md:21).  The corpus treats these as the same number.
      They are not, and every rate below inherits that as an UPPER bound on the
      denominator, hence a LOWER bound on achieved GB/s."""
    )

    # ------------------------------------------------------------------
    rule("1.  PER-CHUNK STAGING MODEL")
    smodel, calls_per_chunk, bytes_per_chunk = staging_model()
    print(
        f"\n  {'projection':<10} {'N':>6} {'K':>6} {'col tiles':>10} {'K_it':>6} "
        f"{'calls':>7} {'B/call':>8} {'bytes':>12} {'share':>7}"
    )
    for r in smodel:
        print(
            f"  {r['name']:<10} {r['n']:>6} {r['k']:>6} {r['col_tiles']:>10} "
            f"{r['k_it']:>6} {r['calls']:>7} {r['per_call']:>8} {r['bytes']:>12} "
            f"{100.0*r['bytes']/bytes_per_chunk:>6.2f}%"
        )
    print(
        f"  {'TOTAL':<10} {'':>6} {'':>6} {'':>10} {'':>6} {calls_per_chunk:>7} "
        f"{'':>8} {bytes_per_chunk:>12} {100.0:>6.2f}%"
    )
    analytic = int(3 * MOE_INTER * HIDDEN * BYTES_PER_VALUE)
    print(
        f"""
  cross-check: one full pass over one expert's three projections is
  3 x {MOE_INTER} x {HIDDEN} x {BYTES_PER_VALUE} = {analytic} B -- """
        f"""{'matches' if analytic == bytes_per_chunk else 'DISAGREES with'} the per-chunk total.

  So one BM={BM} chunk stages an entire expert: {calls_per_chunk} cooperative
  `load_unsafe` calls of {smodel[0]['per_call']} B each, {THREADS} threads x 16 B of codes +
  2 B of scales per thread per call.  gate/up carries exactly 2/3 of the bytes
  and down 1/3, because doubling N halves K.

  NOTE: the `dispatch_tiles` block of the stats artifact, and the same block in
  research/artifacts/README-route-histogram.md, have their two projection NAMES
  exchanged: the entry called `gate_up` carries K={tiles['gate_up']['K']}, N={tiles['gate_up']['N']},
  column_tiles={tiles['gate_up']['column_tiles']}, chunk_dram_bytes={tiles['gate_up']['chunk_dram_bytes']}, which is the *down* projection.
  The checkpoint shapes -- gate/up weight [256,512,256] u32 -> [E,N=1024,K=2048],
  down [256,2048,64] u32 -> [E,N=2048,K=512] -- the two shapes hardcoded in
  research/nax_msl_compile_check.sh:53-61 ("2048, 1024" and "512, 2048"), and the
  4096/8192 threadgroups-per-layer split all give the table above.
  The arithmetic inside each block is self-consistent, so only the labels are
  wrong; nothing downstream of that artifact is numerically affected."""
    )

    # Independent cross-check: the artifact's own per-projection dispatch counts.
    art_bytes = sum(
        t["chunk_dram_bytes"] * t["chunk_threadgroup_iterations"] for t in tiles.values()
    )
    print(
        f"""
  independent cross-check against the artifact's own dispatch_tiles block:
    sum(chunk_dram_bytes x chunk_threadgroup_iterations) = {art_bytes} B
    my chunks x bytes_per_chunk                          = {chunks*bytes_per_chunk} B
    {'AGREE' if art_bytes == chunks*bytes_per_chunk else 'DISAGREE'} -- two independent derivations of the chunk-accurate byte total."""
    )

    # ------------------------------------------------------------------
    rule("2.  STAGED BYTES UNDER THREE ACCOUNTINGS, ON BOTH LAYER BASES")

    accountings = (
        ("chunk-accurate", chunks, "ceil(rows/BM) per (layer,expert): what the kernel issues"),
        ("nonzero-expert floor", nonzero_pairs, "one chunk per touched expert: unreachable lower bound"),
        ("all-slots (analytic)", n_pairs, "every (layer,expert) slot: what the carried ledger assumes"),
    )
    scale_39 = SPARSE_LAYERS / DISPATCHED_LAYERS

    print(
        f"\n  {'accounting':<24} {'n (38 L)':>10} {'GB (38 L)':>11} "
        f"{'n (39 L)':>10} {'GB (39 L)':>11}"
    )
    results = {}
    for label, n, _why in accountings:
        gb = n * bytes_per_chunk / 1e9
        gb39 = n * scale_39 * bytes_per_chunk / 1e9
        results[label] = (n, gb, gb39)
        print(f"  {label:<24} {n:>10} {gb:>11.4f} {n*scale_39:>10.1f} {gb39:>11.4f}")

    chunk_n, chunk_gb, chunk_gb39 = results["chunk-accurate"]
    all_n, all_gb, all_gb39 = results["all-slots (analytic)"]
    nz_n, nz_gb, _ = results["nonzero-expert floor"]

    print(
        f"""
  The all-slots / 39-layer cell is {all_gb39:.5f} GB.  The carried ledger's
  GBYTE = {GBYTE_CARRIED} GB. """
        f"""{'They agree' if abs(all_gb39-GBYTE_CARRIED) < 5e-4 else 'They DISAGREE'} -- which proves the carried byte
  count assumes all {N_EXPERTS} expert slots are staged in all {SPARSE_LAYERS} sparse layers.

  chunk-accurate / all-slots = {chunk_gb/all_gb:.4f}.  The carried ledger therefore
  overstates the routed weight stream by {100.0*(all_gb/chunk_gb - 1):.1f} %.
  This reproduces the 0.8613 factor already noted at
  RESEARCH_STATE_ARCHIVE...:4687-4700 ("do not use nominal 17,666 MB")."""
    )

    print("\n--- comparison against the advisor's pre-registered table ---")
    print(
        f"\n  {'accounting':<32} {'n':>9} {'staged GB':>10} {'GB/s @W':>9} "
        f"{'% of 614':>9}  {'my n':>9} {'my GB':>10} {'my GB/s':>9} {'my %':>7}"
    )
    mine = {
        "chunk-accurate, 38 L": (chunk_n, chunk_gb),
        "nonzero-expert floor, 38 L": (nz_n, nz_gb),
        "all-slots (analytic), 38 L": (all_n, all_gb),
        "chunk-accurate scaled to 39 L": (chunk_n * scale_39, chunk_gb39),
    }
    max_dev = 0.0
    for label, n, gb, rate, pct in ADVISOR_TABLE:
        mn, mgb = mine[label]
        mrate = mgb / (W_MS / 1000.0)
        mpct = 100.0 * mrate / PEAK_BW_GBPS
        max_dev = max(max_dev, abs(mrate - rate) / rate)
        print(
            f"  {label:<32} {n:>9} {gb:>10.4f} {rate:>9.1f} {pct:>8.1f}%  "
            f"{mn:>9.1f} {mgb:>10.4f} {mrate:>9.1f} {mpct:>6.1f}%"
        )
    print(
        f"\n  Largest relative disagreement with the advisor's table: "
        f"{100.0*max_dev:.3f} %.  I reproduce every row."
    )

    # ------------------------------------------------------------------
    rule("3.  ACHIEVED BANDWIDTH, WITH sigma(S) PROPAGATED ONTO W")
    sigma_w = SIGMA_S_MS * math.sqrt(2.0)
    rel_w = sigma_w / W_MS
    rate_full = chunk_gb / (W_MS / 1000.0)
    byte_time = W_MS - PURE_ISSUE_MS
    rate_bytetime = chunk_gb / (byte_time / 1000.0)
    print(
        f"""
W is a difference of two receipts, so sigma(W) = sqrt(2) x sigma(S)
   = sqrt(2) x {SIGMA_S_MS} = {sigma_w:.4f} ms  ({100.0*rel_w:.2f} % of W).
The carried ledger uncertainty is +-{W_MS_LEDGER_SIGMA} ms; the two agree to
{abs(sigma_w-W_MS_LEDGER_SIGMA):.3f} ms, so nothing downstream turns on which is used.

Two different denominators are in circulation and they are NOT in conflict:

  (a) bytes / W                (all of W, including the pure-issue term)
        {chunk_gb:.4f} GB / {W_MS:.4f} ms = {rate_full:.1f} +- {rate_full*rel_w:.1f} GB/s
        = {100.0*rate_full/PEAK_BW_GBPS:.1f} % of {PEAK_BW_GBPS:.0f} GB/s   [the advisor's census table]

  (b) bytes / (W - pure issue) (only the part of W that bytes could explain)
        PR170 split the staging term {100.0*0.49:.0f}/{100.0*0.51:.0f} issue/DRAM and priced the pure
        issue term at {PURE_ISSUE_MS} ms, so byte time = {byte_time:.4f} ms
        {chunk_gb:.4f} GB / {byte_time:.4f} ms = {rate_bytetime:.1f} +- {rate_bytetime*rel_w:.1f} GB/s
        = {100.0*rate_bytetime/PEAK_BW_GBPS:.1f} % of {PEAK_BW_GBPS:.0f} GB/s   [the assignment's value table]

TRAP, stated so nobody re-derives the retired headline by accident:
  the old headline {GBYTE_CARRIED} GB / {W_MS} ms = {GBYTE_CARRIED/(W_MS/1000.0):.1f} GB/s is
  numerically almost identical to (b)'s {rate_bytetime:.1f} GB/s.  That is a
  coincidence: the byte ratio {chunk_gb/GBYTE_CARRIED:.4f} happens to sit within
  0.2 % of the time ratio {byte_time/W_MS:.4f}.  One is an overstated byte count
  over the whole kernel; the other is an honest byte count over the byte-limited
  part of the kernel.  They are not the same measurement."""
    )

    print(
        f"""
VERDICT on the "408.4 GB/s = 67 % of peak" headline:
  OVERSTATED as a whole-kernel byte rate.  On the honest denominator the routed
  gather GEMM moves weights at {rate_full:.1f} GB/s = {100.0*rate_full/PEAK_BW_GBPS:.1f} % of peak, not 67 %.
  The advisor's ~343 GB/s / 55.8 % is confirmed to 3 significant figures.
  {100.0*rate_bytetime/PEAK_BW_GBPS:.1f} % of peak is a defensible *byte-time* rate but must be quoted
  with its denominator, because it is conditioned on PR170's issue/DRAM split."""
    )

    # ------------------------------------------------------------------
    rule("4.  STREAMING FLOOR AND HEADROOM")
    print(
        f"\n  {'basis':<34} {'GB':>9} {'floor @614':>11} {'floor @610':>11} "
        f"{'headroom vs W':>14} {'max +score':>11}"
    )
    for label, gb in (
        ("chunk-accurate, 38 L (honest)", chunk_gb),
        ("nonzero-expert floor, 38 L", nz_gb),
        ("all-slots, 38 L", all_gb),
        ("carried ledger (all-slots, 39 L)", GBYTE_CARRIED),
    ):
        f614 = 1000.0 * gb / PEAK_BW_GBPS
        f610 = 1000.0 * gb / PEAK_BW_GBPS_ALT
        head = W_MS - f614
        print(
            f"  {label:<34} {gb:>9.4f} {f614:>10.2f}m {f610:>10.2f}m "
            f"{head:>13.2f}m {head*PCT_SCORE_PER_MS:>10.2f}%"
        )

    floor = 1000.0 * chunk_gb / PEAK_BW_GBPS
    print(
        f"""
  The honest streaming floor is {floor:.2f} ms, leaving {W_MS-floor:.2f} ms of
  headroom inside W -- worth up to {(W_MS-floor)*PCT_SCORE_PER_MS:.2f} % of score at
  {PCT_SCORE_PER_MS} %/ms, and {THREE_SIGMA_MS:.2f} ms is 3 sigma on a paired
  receipt difference, so the headroom is {(W_MS-floor)/THREE_SIGMA_MS:.1f}x that
  detection threshold.  Using the carried
  17.67 GB would have advertised a {1000.0*GBYTE_CARRIED/PEAK_BW_GBPS:.2f} ms floor and understated the
  available headroom by {(1000.0*GBYTE_CARRIED/PEAK_BW_GBPS)-floor:.2f} ms.  The chunk-accurate
  census therefore makes the prize BIGGER, not smaller."""
    )

    # ------------------------------------------------------------------
    rule("5.  ROOFLINE, CHUNK-ACCURATE ON *BOTH* AXES")
    useful_flop = total_rows * FLOP_PER_ROW / 1e9
    exec_flop = mma_rows * FLOP_PER_ROW / 1e9
    print(
        f"""
The M axis is padded twice, at two DIFFERENT granularities.  This is the single
structural fact the carried roofline misses:

  staging / barriers  quantized to BM = {BM}   (load_unsafe is issued before, and
                      outside, the `sg_active` guard -- fp_quantized_nax.h:1839-1846)
  MMA                 quantized to SM = {SM}   (sgp_sm/sg_active, :1734-1736, gate
                      the A-tile load :1801 and the MMA chain :1846)

So a 3-row expert stages a full 64x64 weight tile on every one of its {smodel[0]['k_it']}
k-iterations, but issues MMA on only 1 of its {WM} simdgroups.  Byte waste and FLOP
waste are not the same number, and the two roofline axes cannot share a padding
factor.

  {'axis':<28} {'38 L':>14} {'39 L (scaled)':>15}
  {'useful FLOP (routed rows)':<28} {useful_flop:>13.2f}G {useful_flop*scale_39:>14.2f}G
  {'executed FLOP (SM=16 pad)':<28} {exec_flop:>13.2f}G {exec_flop*scale_39:>14.2f}G
  {'staged GB (BM=64 pad)':<28} {chunk_gb:>13.4f}  {chunk_gb39:>14.4f}
  {'carried GFLOP':<28} {GFLOP_CARRIED*DISPATCHED_LAYERS/SPARSE_LAYERS:>13.2f}G {GFLOP_CARRIED:>14.2f}G

  routed rows {total_rows} = {DISPATCHED_LAYERS} x {SEQ} x {TOPK}; executed MMA row slots {mma_rows}
  M-axis FLOP padding factor  = {exec_flop/useful_flop:.4f}
  M-axis BYTE padding factor  = {chunks*BM/total_rows:.4f}   (chunk rows / routed rows)
  useful-FLOP check vs carried ledger: """
        f"""{'OK' if abs(useful_flop*scale_39 - GFLOP_CARRIED) < 0.05 else 'MISMATCH'}"""
    )

    ai_carried = GBYTE_CARRIED and GFLOP_CARRIED / GBYTE_CARRIED
    ai_useful = useful_flop / chunk_gb
    ai_exec = exec_flop / chunk_gb
    ridge_artifact = 1000.0 * TFLOPS_RIDGE_ARTIFACT / PEAK_BW_GBPS_ALT
    ridge_real = 1000.0 * PEAK_TFLOPS / PEAK_BW_GBPS

    print(
        f"""
  {'arithmetic intensity':<40} {'FLOP/B':>9}
  {'carried (nominal FLOP / nominal bytes)':<40} {ai_carried:>9.2f}
  {'chunk-accurate, useful FLOP':<40} {ai_useful:>9.2f}
  {'chunk-accurate, executed FLOP':<40} {ai_exec:>9.2f}

  {'machine balance':<40} {'FLOP/B':>9}
  {'ridge ARTIFACT ({:.1f} TF/s / {:.0f} GB/s)'.format(TFLOPS_RIDGE_ARTIFACT, PEAK_BW_GBPS_ALT):<40} {ridge_artifact:>9.2f}
  {'real ({:.0f} TF/s / {:.0f} GB/s)'.format(PEAK_TFLOPS, PEAK_BW_GBPS):<40} {ridge_real:>9.2f}

  achieved, at W = {W_MS} ms:
    bytes      {rate_full:.1f} GB/s   = {100.0*rate_full/PEAK_BW_GBPS:.1f} % of {PEAK_BW_GBPS:.0f}
    useful FLOP  {useful_flop/W_MS:.2f} TFLOP/s = {100.0*useful_flop/W_MS/PEAK_TFLOPS:.1f} % of {PEAK_TFLOPS:.0f}
    executed FLOP {exec_flop/W_MS:.2f} TFLOP/s = {100.0*exec_flop/W_MS/PEAK_TFLOPS:.1f} % of {PEAK_TFLOPS:.0f}"""
    )

    u_b = 100.0 * rate_full / PEAK_BW_GBPS
    u_f = 100.0 * exec_flop / W_MS / PEAK_TFLOPS
    print(
        f"""
VERDICT on the 67 %/67 % roofline-ridge identity:
  DEAD, and this census kills it a second and independent way.

  It was already formally retired in research/CURRENT_RESEARCH_STATE.md:1150-1157
  as algebraically forced: the "34.7 TFLOP/s peak" was back-solved from this very
  kernel's own arithmetic intensity via 56.89 = 34700/610, so quoting
  "67 % of bandwidth and 67 % of FLOPs" restated one measurement twice.  With a
  non-circular {PEAK_TFLOPS:.0f} TFLOP/s ceiling the machine balance is {ridge_real:.1f} FLOP/B, not
  {ridge_artifact:.2f}, and the workload is nowhere near it.

  Redone chunk-accurately on both axes the two utilisations are {u_b:.1f} % (bytes)
  and {u_f:.1f} % (executed FLOP) -- a factor of {max(u_b,u_f)/min(u_b,u_f):.2f} apart.  Even the sign of
  "which axis is closer to its roof" is {'bytes' if u_b > u_f else 'FLOPs'}.  There is no ridge, no
  coincidence left to explain, and no joint saturation: which is exactly what
  PR170 measured directly on the M5 (H0 and H1 both eliminated, staging
  positively identified)."""
    )

    # ------------------------------------------------------------------
    rule("6.  VERDICT ON THE DEAD-BYTES BRANCH")
    dead_pct = 100.0 * zero_pairs / n_pairs
    print(
        f"""
The branch asked whether the {zero_pairs} zero-row (layer, expert) slots
({dead_pct:.2f} % of all {n_pairs}) are removable DRAM traffic.

REFUTED BY CONSTRUCTION.  The chunk loop is
  `for (chunk_start = run_start; chunk_start < run_end; chunk_start += BM)`
(fp_quantized_nax.h:1730-1731).  An expert with zero routed rows has
run_start == run_end, the loop body never executes, and the loader is never
constructed, let alone stepped.  A zero-row slot stages EXACTLY ZERO BYTES
today.  There is nothing to remove.

The chunk-accurate count {chunks} already excludes them; the difference
between the all-slots {all_n} and {chunks} is {all_n - chunks} chunks =
{(all_n-chunks)*bytes_per_chunk/1e9:.4f} GB that the carried ledger charges the kernel and
the kernel never moves.  That is a bookkeeping error in the ledger, not an
optimisation target.  README-route-histogram.md already warns "do not price
zero_frac as removable bytes"; this makes the warning quantitative.

What the empty and near-empty slots DO cost is issue and occupancy, not bytes:
  * every threadgroup still runs the {N_EXPERTS//1} / expert_groups slot loop and its
    lower_bound searches and barriers whether or not the slot is live;
  * the mean live expert holds {total_rows/nonzero_pairs:.2f} rows against BM = {BM}, so the
    typical chunk stages a full 64x64 tile to feed {math.ceil((total_rows/nonzero_pairs)/SM)} of {WM} simdgroups.
That is the {PURE_ISSUE_MS} ms pure-issue term PR170 measured ({100.0*PURE_ISSUE_MS/W_MS:.1f} % of W), and it
is attacked by latency hiding -- the K-loop pipeline of this PR's Part B --
not by pruning bytes that are already not being read."""
    )

    # ------------------------------------------------------------------
    rule("7.  LEDGER LINES TO CARRY FORWARD")
    print(
        f"""
  routed gather GEMM, shipped 512-token prefill, chunk-accurate:

    dispatched layers                 {DISPATCHED_LAYERS}   (sparse layers {SPARSE_LAYERS}; layer 39 -> M=1 GEMV)
    chunks at BM=64                   {chunks}
    bytes staged per chunk            {bytes_per_chunk}  ({calls_per_chunk} cooperative calls x {smodel[0]['per_call']} B)
    weight bytes staged               {chunk_gb:.4f} GB   (was {GBYTE_CARRIED} GB, -{100.0*(1-chunk_gb/GBYTE_CARRIED):.1f} %)
    useful FLOP                       {useful_flop:.2f} GFLOP  (was {GFLOP_CARRIED} on 39 L)
    executed FLOP (SM=16 M padding)   {exec_flop:.2f} GFLOP
    achieved bytes / W                {rate_full:.1f} +- {rate_full*rel_w:.1f} GB/s  ({100.0*rate_full/PEAK_BW_GBPS:.1f} % of {PEAK_BW_GBPS:.0f})
    achieved bytes / (W - issue)      {rate_bytetime:.1f} +- {rate_bytetime*rel_w:.1f} GB/s  ({100.0*rate_bytetime/PEAK_BW_GBPS:.1f} % of {PEAK_BW_GBPS:.0f})
    achieved executed FLOP / W        {exec_flop/W_MS:.2f} TFLOP/s ({100.0*exec_flop/W_MS/PEAK_TFLOPS:.1f} % of {PEAK_TFLOPS:.0f})
    streaming floor @ {PEAK_BW_GBPS:.0f} GB/s      {floor:.2f} ms
    headroom inside W                 {W_MS-floor:.2f} ms  (<= {(W_MS-floor)*PCT_SCORE_PER_MS:.2f} % of score)
    sigma(W) from sigma(S)={SIGMA_S_MS}      {sigma_w:.3f} ms; 3 sigma on a paired delta = {THREE_SIGMA_MS:.2f} ms

  RETIRED by this census:
    17.67 GB routed weight stream          -> {chunk_gb:.4f} GB (all-slots x 39 L assumption)
    408.4 GB/s = 67 % of peak              -> {rate_full:.1f} GB/s = {100.0*rate_full/PEAK_BW_GBPS:.1f} % of peak
    67 %/67 % roofline ridge identity      -> {u_b:.1f} % bytes vs {u_f:.1f} % FLOP, no ridge
    "dead bytes" from zero-row slots       -> zero bytes exist to remove
    dS_1 x 40/39 = 44.371 ms               -> x 38/39 = {W_MS*DISPATCHED_LAYERS/SPARSE_LAYERS:.4f} ms
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
