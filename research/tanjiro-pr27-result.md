# PR #27 result — M5 Max hardware constants read out of official receipts

- **Student / PR:** maple-tanjiro / #27 `maple-tanjiro/m5-constants`,
  assignment `maple-2026-08-04f-m5-constants`, revision `r1`
- **Hypothesis:** an output-neutral work injection in the scored forward pass
  turns the two published benchmark numbers into a measuring instrument, so the
  hardware constants the programme divides by can be measured *on the ranked
  M5 Max, through the ranked harness*, instead of estimated from marketing peaks.
- **Decision:** green on the instrument and on the rate constants; the
  per-dispatch constant is fully resolved on the development host and reduced to
  a bound on the ranked host, for a reason that is itself the most actionable
  result here.
- **`BASE_SHA`:** `768bb9d4adfc2baac7d74c0008afc92d010329da`
- **Submitted candidate files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  — one delimited instrument block at the end of the file plus a single call site
  inside the 40-layer loop. Nothing else on the scored path is touched.
- **Supporting research files (never on the scored path):**
  `research/tanjiro-pr27-interim.md` (full log, 9 sections),
  `research/tanjiro-pr27-result.md`, `research/tanjiro-pr27-submission-note.md`,
  `research/host_device_arch.swift`, `research/tanjiro-receipt-mine.py`,
  `research/tanjiro-receipt-fetch.py`, `research/tanjiro-pr27-fit.py`,
  `research/tanjiro-knee-fit.py`, `research/tanjiro-mb-fit.py`

## Headline

1. **The protocol works.** A deliberately slowed, output-neutral candidate passes
   every hidden gate on the ranked host and returns a complete metric receipt.
   Receipt `ff29f5c2`: `passed_correctness = true`, `max_abs_diff = 0`, both
   speedup floors passed, TTFT 0.42 s against a 2.5 s gate, semantic GPQA passed,
   `rejected` on ranking exactly as designed. **We now have a general-purpose
   hardware probe for the ranked machine that costs one receipt per data point.**
2. **The in-situ per-dispatch cost is not a constant.** It obeys a saturation law
   `dT(n) = max(0, n*c - slack)`, fitted independently at two threadgroup widths
   20x apart, with one confirmed out-of-sample null prediction. On the development
   host `c = 2.64-2.80 us` and `slack = 4.17-4.78 ms` per decode step, i.e. a knee
   at **~1600 extra dispatches**. The scored decode path issues ~406 ops, so it is
   4x below saturation.
3. **What the slack absorbs is host time, not GPU time.** One injected dispatch
   carrying 1.048 ms of real DRAM traffic appeared at **106%** of its cost; 600
   dispatches carrying 1.68 ms of pure launch overhead appeared at **1%**. So:
   *GPU-work reduction pays in full with no launch discount; MLX-op-count
   reduction on the decode path is worth zero until the count roughly quadruples.*
   The 0.884 ms launch-ramp line in the decode budget is not a recoverable term.
4. **The cache-resident question kills the head-packing arm** (advisor comment
   `#issuecomment-5181161230`). The fused-attention kernel at 375 GB/s on issued
   bytes is at **34%** of the cache-resident aggregate ceiling *at its own working
   set*, not at it. Packing 4 or 8 query heads per threadgroup removes bytes the
   kernel is not bound by.
5. **The official receipt feed is public and mineable with our own token**, which
   re-prices the ranked noise floor from 929 pinned baselines: `sd(S) = 1.93%`,
   `sd(T) = 0.34%` — the brief assumed 0.497% on both. All 789 `rejected`
   submissions publish full metrics; only the 467 `failed` ones publish none.

## The constants

### Ranked host (M5 Max, official receipts)

| constant | value | source |
| --- | ---: | --- |
| achievable DRAM read GB/s | _pending B_ | `1610.612736 MB / (T_B - T_A)` |
| bf16 GEMM TFLOP/s at `512x8192x2048` | _pending B_ | `1717.986918 GFLOP / (S_B - S_A)` |
| decode dispatch absorption | _pending D_ | `T_D - T_A` at 1800 extra dispatches |
| prefill overlap / glue | see below | not separable within the floors |

### Development host (M4 Pro, 20 GPU cores, `applegpu_g16s`)

| constant | value | cross-check |
| --- | ---: | --- |
| achievable DRAM read GB/s, in situ marginal | **256.2** (small lever), **237.4** (6x lever) | 97.6% / 90.4% of #21's 262.5 GB/s sequential control |
| bf16 GEMM TFLOP/s at `512x8192x2048` | **7.40-7.46** (small), **7.188** (6x) | fern's GPUPROF `attn_proj` steel bf16 6.77 TFLOP/s |
| in-situ `c` per extra dispatch | **2.64-2.80 us**, flat from tg=8 to tg=160, +11 ns/TG above | isolated same-day probe at tg=160: 2.788 us |
| decode `slack` per step | **4.17-4.78 ms** (knee ~1600 dispatches) | out-of-sample null at 600 dispatches: +0.019 ms |
| prefill absorption per 512-token forward | **>= 39.5 ms** | 20000-dispatch injection, 70% absorbed |
| cache-resident aggregate ceiling | **1000-1200 GB/s** at 1-2 MiB working sets | 12-point window x threadgroup sweep |

## Evidence

- **Host / toolchain / thermal policy:** development host Apple M4 Pro
  (`Mac16,11`), 20 GPU cores, 48 GB unified memory, low-memory startup profile,
  `./benchmark.sh --local-iterate` with its thermal gate honoured on every run.
  Ranked host: self-hosted M5 Max, 128 GB, official paired session.
- **Exact commands:**

```bash
# every local point (knobs default to the shipped configuration)
env MLXFAST_LOCAL_FAN_PROMPT=0 \
    DARKBLOOM_INJECT_SWEEP_PASSES=<p> DARKBLOOM_INJECT_PREFILL_MATMULS=<m> \
    DARKBLOOM_INJECT_DECODE_EMPTY=<nd> DARKBLOOM_INJECT_PREFILL_EMPTY=<np> \
    DARKBLOOM_INJECT_EMPTY_TG=<tg> ./benchmark.sh --local-iterate
# standalone Metal probe
xcrun swiftc -O research/host_device_arch.swift -o /tmp/devarch && /tmp/devarch
# official
export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --note-file research/tanjiro-pr27-submission-note.md \
               --model "Claude Opus 5"
```

- **Correctness and serial-protocol verdict:** every local receipt and every
  official receipt reports `passed_correctness = true` and `max_abs_diff = 0`.
  The instrument adds no cache state, no cross-request state, and no token-keyed
  memo: it reads a private 256 MiB pool and two private GEMM operands, and writes
  only a sink tensor that no model tensor reads. Logical and physical KV
  advancement is untouched, so the serial non-speculative rule is unaffected.
- **Peak RAM:** 21 GB on every configuration, including 120 injected GEMMs and
  100000 injected dispatches — injected operands are allocated once and reused.

### Local measurement table (M4 Pro)

`S = 512000 * prefill_seconds_per_token` ms;
`T = 1000 * decode_seconds_per_token - S/128` ms.

| run | sweep passes | GEMMs | decode empties | prefill empties | tg | S (ms) | T (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| zero | 0 | 0 | 0 | 0 | — | 583.311 | 9.00680 |
| LA3 (= A) | 1 | 20 | 0 | 0 | — | 614.827 | 10.11366 |
| LB3 | 3 | 20 | 0 | 0 | — | 621.122 | 12.20914 |
| LC3 | 1 | 20 | 600 | 1000 | 160 | 619.864 | 10.13248 |
| LE | 1 | 20 | 2000 | 0 | 160 | 575.182 | 10.93761 |
| LD | 1 | 20 | 4000 | 20000 | 160 | 588.450 | 16.54604 |
| LH | 1 | 20 | 2000 | 0 | 8 | 562.166 | 11.22364 |
| LF | 1 | 20 | 8000 | 0 | 8 | 576.764 | 27.05580 |
| LG | 1 | 20 | 4000 | 0 | 512 | 573.317 | 31.99681 |
| LJ | 1 | 20 | 0 | 50000 | 160 | 873.950 | — |
| LI | 1 | 20 | 0 | 100000 | 160 | 922.739 | — |
| MB (= B) | 7 | 120 | 0 | 0 | — | 853.829 | 16.89766 |

### Official receipts

| run | id | status | S (ms) | T (ms) | baseline S / T | floors |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A | `ff29f5c2-fdc2-4035-af6b-17e8a69c2d87` | rejected (band, by design) | 103.5678 | 4.83241 | 189.0284 / 12.40369 | both passed |
| B | `553ef9f0-df2b-4c7f-9308-ef8acd24a816` | _pending_ | | | | |

## Conclusion

_Pending B and D._

## Suggested follow-ups (not implemented)

1. **Re-price every op-count-reduction arm.** If D shows the ranked decode path is
   also below its knee, arms whose only mechanism is "issue fewer MLX ops" should
   be closed unqualified, and the review bar for new ones raised to "removes GPU
   work or removes bytes".
2. **A second receipt pair on the decode compute axis.** The same instrument with
   a GEMV-shaped injection would give the decode-shape matrix rate, which is the
   denominator for the routed-expert and shared-expert projections. That is a
   different constant from the prefill-shape rate measured here and the two are
   not interchangeable.
3. **Keep the instrument as a maintained tool.** It is one delimited block behind
   defaults that cost nothing when disabled. Any future "is this arm worth a
   submission" question can be answered for one receipt instead of a week of
   guessing.
4. **Do not fund the query-head-packing arm** on the current justification. If it
   is revived, it needs a mechanism that reduces *arithmetic or issued bytes at
   the bound*, not the L2 traffic the kernel is 3x away from being limited by.
