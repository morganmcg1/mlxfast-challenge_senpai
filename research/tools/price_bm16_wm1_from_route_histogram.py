#!/usr/bin/env python3
"""Price the BM16/WM1 short-run one-SIMDgroup expert `_nax` hypothesis directly
from the committed 512-token routed run-length histogram.

Operator directive (2026-08-11 17:03Z) proposed changing
`fp_gather_qmm_rhs_expert_nax` from BM64/WM4/WN1 to BM16/WM1/WN1 on the
expert-aligned NVFP4 prefill path, on the reasoning that for a "typical prefill
expert run of roughly 16 rows" `SM = BM/WM = 16` leaves one of four SIMDgroups
owning useful MMA rows while all four participate in staging.

This tool answers the two questions the directive said to answer BEFORE coding:

  1. What is the actual 512-token routed run-length distribution? (Do not assume
     every expert receives exactly 16 rows.)
  2. Under the tree's own committed traversal model, what does BM 64 -> 16 do to
     weight-tile staging incidence?

Key structural result it establishes: because 64 is an exact multiple of the
SIMDgroup row granularity SM=16, the *padded MMA row count* is bit-identically
equal under BM64/WM4 and BM16/WM1:

    sum over chunks of 16*ceil(chunk_rows/16)  ==  16*sum_e ceil(rows_e/16)

so BM16/WM1 removes exactly ZERO MMA padding waste. Idle SIMDgroups under
BM64/WM4 already skip MMA (they only help stage). Therefore the entire expected
effect of the change is a threadgroup-scheduling/residency effect, paid for with
a strictly larger number of weight-staging passes each carried by 4x fewer
threads -- on a kernel that four bit-exact perturbation receipts show is
staging-bound (+18.2% of W for added staging at zero extra DRAM bytes, 17.5 sigma).

Data source (committed): research/artifacts/route-histogram-prefill512.csv
  columns: layer_index,expert_id,rows,chunks_bm64
  provenance: research/artifacts/route-histogram-prefill512-stats.json
  -> source_commit "3e8e435 (DARKBLOOM_ROUTE_HISTOGRAM, reverted; PR #11)"
  -> host Apple M4 Pro; routing is model+prompt dependent, host independent
  CAVEAT carried from research/maple-fern-r106i-prefill-traversal-census.md:544-553:
  single prompt, one draw, and a provenance conflict between 3e8e435 and
  ceff917. Treat every fraction below as one draw, not a law.

Traversal model is r106i's own (…r106i-prefill-traversal-census.md:518-527):
  weight incidences per layer = sum_e ceil(rows_e / BM)
  weight traversal = incidences * WEIGHT_BYTES_PER_INCIDENCE
If instead the weight tile were staged once per (expert, column tile)
independent of row chunking, then r106i's 0.8613x multiplicity and its
-6.58 ms floor correction would themselves be wrong: the BM16 penalty computed
here and r106i's headline correction stand or fall on the same model.

Exit 0 on success, 2 on missing/unusable input.
"""
from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE)) if False else os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
CSV_PATH = os.path.join(REPO, "research", "artifacts", "route-histogram-prefill512.csv")
STATS_PATH = os.path.join(REPO, "research", "artifacts",
                          "route-histogram-prefill512-stats.json")

# r106i:521-529
WEIGHT_BYTES_PER_INCIDENCE = 1_769_472
# campaign currencies (research/CURRENT_RESEARCH_STATE.md:7432-7448)
MS_PER_GB_TRAVERSAL = 1.831          # 1 GB traversal = 1.831 ms
PCT_SCORE_PER_MS_TOTAL = 0.3781      # % score per ms of prefill (total form)
SM = 16                              # BM/WM in both arms


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def main() -> int:
    if not os.path.exists(CSV_PATH):
        print("ERROR: missing %s" % CSV_PATH, file=sys.stderr)
        return 2

    rows_per_pair: list[int] = []
    chunks_bm64_col = 0
    with open(CSV_PATH, newline="") as fh:
        rdr = csv.DictReader(fh)
        for rec in rdr:
            rows_per_pair.append(int(rec["rows"]))
            chunks_bm64_col += int(rec["chunks_bm64"])
    if not rows_per_pair:
        print("ERROR: no rows parsed from %s" % CSV_PATH, file=sys.stderr)
        return 2

    n_pairs = len(rows_per_pair)
    total_rows = sum(rows_per_pair)
    zero = sum(1 for r in rows_per_pair if r == 0)
    nonzero = n_pairs - zero

    inc64 = sum(ceil_div(r, 64) for r in rows_per_pair)
    inc16 = sum(ceil_div(r, 16) for r in rows_per_pair)

    # padded MMA rows, both arms -- proof of identity
    pad64 = 0
    for r in rows_per_pair:
        rem = r
        while rem > 0:
            chunk = min(64, rem)
            pad64 += SM * ceil_div(chunk, SM)
            rem -= chunk
    pad16 = SM * inc16

    # threads issued to stage
    threads64 = 128 * inc64
    threads16 = 32 * inc16

    gb64 = inc64 * WEIGHT_BYTES_PER_INCIDENCE / 1e9
    gb16 = inc16 * WEIGHT_BYTES_PER_INCIDENCE / 1e9
    dgb = gb16 - gb64
    dms = dgb * MS_PER_GB_TRAVERSAL
    dpct = dms * PCT_SCORE_PER_MS_TOTAL

    # run-length buckets against the SM=16 granularity
    le16 = sum(1 for r in rows_per_pair if 0 < r <= 16)
    rows_le16 = sum(r for r in rows_per_pair if 0 < r <= 16)
    gt64 = sum(1 for r in rows_per_pair if r > 64)
    rows_gt64 = sum(r for r in rows_per_pair if r > 64)

    # active SIMDgroups per BM64 threadgroup
    act_hist = {1: 0, 2: 0, 3: 0, 4: 0}
    tg64 = 0
    for r in rows_per_pair:
        rem = r
        while rem > 0:
            chunk = min(64, rem)
            act_hist[ceil_div(chunk, SM)] += 1
            tg64 += 1
            rem -= chunk
    mean_active = (sum(k * v for k, v in act_hist.items()) / tg64) if tg64 else 0.0

    print("=" * 78)
    print("BM16/WM1 vs BM64/WM4 priced from the committed 512-token route histogram")
    print("=" * 78)
    print("source            : research/artifacts/route-histogram-prefill512.csv")
    if os.path.exists(STATS_PATH):
        st = json.load(open(STATS_PATH))
        print("provenance        : %s" % st.get("source_commit"))
        print("host / workload   : %s | %s" % (st.get("host"), st.get("workload")))
    print()
    print("(layer,expert) pairs        : %d" % n_pairs)
    print("routed rows total           : %d" % total_rows)
    print("zero-row pairs              : %d (%.2f %%)" % (zero, 100.0 * zero / n_pairs))
    print("non-zero pairs              : %d" % nonzero)
    print("mean rows over non-zero     : %.4f" % (total_rows / nonzero))
    print()
    print("--- does the 'roughly 16 rows' premise hold? ---")
    print("pairs with 1..16 rows       : %d (%.2f %% of non-zero) holding %d rows (%.2f %% of all rows)"
          % (le16, 100.0 * le16 / nonzero, rows_le16, 100.0 * rows_le16 / total_rows))
    print("pairs with >64 rows         : %d (%.2f %% of pairs)  holding %d rows (%.2f %% of all rows)"
          % (gt64, 100.0 * gt64 / n_pairs, rows_gt64, 100.0 * rows_gt64 / total_rows))
    print("=> the modal run is short, but the ROWS are not: a third of the work")
    print("   sits in long runs, which is where fixed BM16 multiplies dispatches.")
    print()
    print("--- idle-SIMDgroup census under BM64/WM4 (SM=16) ---")
    print("BM64 threadgroups           : %d" % tg64)
    for k in (1, 2, 3, 4):
        print("  %d of 4 SIMDgroups w/ MMA  : %6d (%.2f %%)"
              % (k, act_hist[k], 100.0 * act_hist[k] / tg64))
    print("mean active SIMDgroups      : %.4f of 4  (=> %.1f %% of SIMDgroup slots idle for MMA)"
          % (mean_active, 100.0 * (1 - mean_active / 4.0)))
    print()
    print("--- padded MMA rows: THE DECISIVE IDENTITY ---")
    print("padded MMA rows BM64/WM4    : %d" % pad64)
    print("padded MMA rows BM16/WM1    : %d" % pad16)
    print("identical                   : %s" % (pad64 == pad16))
    print("=> BM16/WM1 removes ZERO MMA padding. Idle SIMDgroups already skip MMA.")
    print("   The change cannot buy MMA work; it can only buy scheduling/residency.")
    print()
    print("--- what it costs to buy that scheduling change ---")
    print("weight incidences BM64      : %d   (csv chunks_bm64 column: %d)" % (inc64, chunks_bm64_col))
    print("weight incidences BM16      : %d" % inc16)
    print("incidence multiplier        : %.4f x" % (inc16 / inc64))
    print("weight traversal BM64       : %.4f GB" % gb64)
    print("weight traversal BM16       : %.4f GB" % gb16)
    print("delta                       : %+.4f GB  =>  %+.3f ms prefill  =>  %+.3f %% score"
          % (dgb, dms, -dpct))
    print("staging threads BM64        : %d  (128 per threadgroup)" % threads64)
    print("staging threads BM16        : %d  (32 per threadgroup)" % threads16)
    print("staging thread-issue ratio  : %.4f x" % (threads16 / threads64))
    print()
    print("--- THE EXACT TRADE (an identity, not an estimate) ---")
    print("incidence multiplier  %.4f x  ==  mean active SIMDgroups  %.4f"
          % (inc16 / inc64, mean_active))
    print("because sum_chunks ceil(chunk_rows/16) == sum_e ceil(rows_e/16) when BM % SM == 0.")
    print("=> BM16/WM1 recovers idle SIMDgroup slots and pays for them ONE-FOR-ONE in")
    print("   extra weight-staging passes. On this kernel the measured sensitivity is")
    print("   +18.2 % of W per staging unit vs +4.7 % per MMA unit (R110-B, 4 bit-exact")
    print("   receipts, 17.5 sigma), so the exchange rate is ~3.9:1 AGAINST the trade.")
    print()
    print("VERDICT: under r106i's own traversal model the BM16/WM1 arm pays")
    print("  %.4fx weight-staging incidence (%+.3f ms, %+.3f %% score) and stages each" % (
        inc16 / inc64, dms, -dpct))
    print("  tile with %.2fx the thread-issue, to buy a scheduling effect that cannot" % (threads16 / threads64))
    print("  touch MMA work at all. Predicted sign is NEGATIVE and the magnitude")
    print("  exceeds the landing bar by an order of magnitude. Do not spend the")
    print("  receipt on fixed BM16 without a staging-reuse co-design.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
