# PR #34 — What rate do the four largest real kernels actually reach on the ranked M5?

DRAFT — official receipts in flight. Numbers marked `TBD` land when the receipt
feed publishes them.

- Student / PR: maple-tanjiro / #34 (`maple-tanjiro/m5-block-rates`)
- Hypothesis and target cost: the 1.38 ms decode and 47 ms prefill residuals are
  unexplained because nobody has measured the achieved rate of the four blocks
  that dominate them. Measure each block's rate in the real timed window by
  scaling that block's own work over cold data.
- `BASE_SHA`: `eaedee8430f1e2779b235a7fbc296ee20ef3e44b`

## The instrument

One knob per block adds extra copies of that block's real Swift entry point, at
most one copy per layer, each copy binding the weight bank of the layer 20
positions away. At its maximum every knob adds **exactly one extra full copy of
the block's real per-pass work**, independently verified against the model's
published shapes:

| knob | max | added work per pass | share of that axis |
| --- | ---: | ---: | --- |
| `DECODE_ATTN` | 40 | 802.16 MB | 45% of a decode step's weight bytes |
| `DECODE_ROUTED` | 39 | 552.08 MB | 31% of a decode step's weight bytes |
| `PREFILL_ROUTED` | 39 | 17,666.41 MB / 1,005.02 GFLOP | whole routed bank per layer |
| `PREFILL_ATTN` | 40 | 2,852.13 MB / 1,460.29 GFLOP | 52% of a prefill forward's FLOP |

Cold-data property: the copy issued at layer `i` binds bank `(i+20) % 40`, so
about 20 layers of unrelated traffic (~0.9 GB in a decode step, ~8 GB in a
prefill forward) separate the injected read from that bank's own scored read, and
no bank is bound twice in a pass. Rotation 20 preserves the layer's head count
because the sliding/full period 4 divides 20. Magnitudes are ordinary runtime
integers, never Metal function constants. Every injected result is discarded.

## Receipt series (official M5)

| receipt | config `da,dr,pr,pa` | purpose | id | S (ms) | T (ms) |
| --- | --- | --- | --- | ---: | ---: |
| R1 | 0,0,0,0 | anchor | `b6032aeb` | TBD | TBD |
| R2 | 40,0,39,0 | rate 2 (decode attn QMV), rate 1 (prefill routed gather-GEMM) | TBD | TBD | TBD |
| R3 | 0,39,0,40 | rate 4 (decode routed QMV), rate 3 (prefill attn dense GEMM) | TBD | TBD | TBD |
| R4 | arch probe only | Metal architecture character + prefill replicate | TBD | TBD | TBD |

`S = 512000 × prefill_seconds_per_token`, `T = 1000 × decode_seconds_per_token − S/128`.

R2 and R3 are each differenced against the same anchor rather than against each
other, so all four rates are measured against the unperturbed tree.

## Local gate (mandatory, M4 Pro)

Three matched `--local-iterate` receipts on the same quiet host behind the 40 C
gate, all `passed_correctness = true`, peak RAM 21 GB throughout:

| run | config `da,dr,pr,pa` | how set | S (ms) | T (ms) |
| --- | --- | --- | ---: | ---: |
| L0 | 0,0,0,0 | env | 577.201 | 8.8161 |
| L1 | 39,0,20,0 | env | 665.291 | 11.6401 |
| L2 | 39,39,20,20 | env | 767.954 | 13.7371 |
| L3 | 40,0,39,0 | **source defaults, no env** | 735.884 | 11.6572 |

L3 is the receipt-R2 configuration run with **no environment variables set for any
injection knob**, which is how the official runner invokes the binary. Its stderr
inventory reports `prefill_routed_block: 39` and `decode_attn_qmv: 80` (40 copies
x 2 dispatches), so the source defaults do reach the scored path.

Marginal rates:

| block | pair | added work | Δ | marginal rate | @maple-nezuko #9 isolated | ratio |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| decode attention QMV (39 copies) | L1−L0 | 785.65 MB | 2.824 ms | **278.2 GB/s** | 252.6 GB/s | **+10.1%** |
| decode attention QMV (40 copies) | L3−L0 | 802.16 MB | 2.841 ms | **282.4 GB/s** | 252.5 GB/s | **+11.8%** |
| decode routed QMV (39 copies) | L2−L1 | 552.08 MB | 2.097 ms | **263.3 GB/s** | 242.9 GB/s | **+8.4%** |
| prefill routed gather-GEMM (20 copies) | L1−L0 | 9059.70 MB / 515.40 GFLOP | 88.090 ms | 102.8 GB/s / **5.85 TFLOP/s** | — | 79% of M4 dense GEMM |
| prefill routed gather-GEMM (39 copies) | L3−L0 | 17,666.41 MB / 1005.02 GFLOP | 158.683 ms | 111.3 GB/s / **6.33 TFLOP/s** | — | 86% of M4 dense GEMM |
| prefill routed gather-GEMM (20→39 incremental) | L3−L1 | 8606.71 MB / 489.62 GFLOP | 70.593 ms | 121.9 GB/s / **6.94 TFLOP/s** | — | **94% of M4 dense GEMM** |
| prefill attention dense GEMM | L2−L1 | 1509.95 MB / 773.09 GFLOP | 102.663 ms | 14.7 GB/s / **7.53 TFLOP/s** | 7.40–7.46 TFLOP/s (#27 dense probe) | **+1.4%** |

**Gate verdict: PASS.** All three decode readings land inside the mandated 15%
band of @maple-nezuko's isolated per-call rates. The nezuko reference is her
per-call composite reweighted to the exact bank mix each knob touches: 9
full-attention (48-head) banks and 30 sliding (64-head) banks for
`DECODE_ATTN=39`, 10 and 30 for `DECODE_ATTN=40`, and her routed gate/up plus
routed-share-of-down figures for `DECODE_ROUTED=39`.

**Linearity.** The prefill routed block has three points (0, 20, 39 copies) and is
mildly *sub*-linear: 4.405 ms per copy at 20, 4.069 ms per copy at 39, and
3.715 ms per copy for the 20→39 increment. Sub-linear is the absorption
signature, not the thrashing signature — more injected work keeps finding idle
cycles rather than colliding for a scarce resource. The decode axis is
reproducible to 0.15%: L1 and L3 differ by only one attention copy (16.5 MB,
predicted +0.06 ms) and their T differ by +0.017 ms.

**Is the marginal rate systematically below hers? No — it is systematically
above, by +8.4%, +10.1% and +11.8%.** Two independent blocks agreeing in sign and
magnitude points at one mechanism: the injected copies are not chained to the
model's dataflow, so they are free to fill memory cycles the scored step already
leaves idle. M4's scored decode step moves 1794 MB in 8.816 ms = 203.5 GB/s
against a 256 GB/s achievable rate, so roughly 50 GB/s of the memory system is
idle in the unperturbed step; adding 786 MB costs 2.824 ms rather than the
786/256 = 3.07 ms a saturated machine would charge. So there is **no
co-residency penalty** on this instrument; if anything it flatters the kernel by
up to ~10%, which makes every rate below an *upper bound* on the block's
standalone efficiency and a *lower bound* on the slack available to a scheduler.

The prefill attention arm is an unplanned validation of the whole method: the
same real `att.wq/wk/wv/wo` BF16 GEMM measured through the instrument reaches
7.53 TFLOP/s against the 7.40–7.46 TFLOP/s that #27's *synthetic* dense-GEMM
probe measured at the same shape. Within 1.4%. The instrument reproduces a
known kernel rate from inside the scored path.

## Re-pricing the ranked noise floor

The brief propagates `sd(S) = 1.93%` and `sd(T) = 0.34%`. Those are the spread of
the **pinned baseline pass** across all accounts. What a marginal difference needs
is the spread of the **candidate axes** for trees whose scored behaviour is
unchanged. Mined from this account's 11 clean official receipts of 2026-08-04
(`senpai/tools/pr34_replicate_noise.py`):

| quantity | mean | sd | rel sd |
| --- | ---: | ---: | ---: |
| candidate S | 97.9196 ms | 0.2402 ms | **0.245%** |
| candidate T | 4.3516 ms | 0.0191 ms | **0.440%** |
| pinned baseline S | 192.4458 ms | 3.9801 ms | 2.068% |
| pinned baseline T | 13.8648 ms | 0.0343 ms | 0.247% |

Correlation between candidate and baseline within that cluster is `r = +0.143`
on the prefill axis and `r = +0.446` on the decode axis. Propagating:

- prefill: normalising gives `sqrt(0.245² + 2.068² − 2·0.143·0.245·2.068) =
  2.05%` versus **0.245%** raw. Session normalisation inflates prefill
  uncertainty **8.4x**.
- decode: normalising gives `sqrt(0.440² + 0.247² − 2·0.446·0.440·0.247) =
  0.397%` versus 0.440% raw — a 10% improvement, inside its own error.

**Raw is the correct primary estimator, and this supersedes the both-readings
presentation in my #27 report.** The pinned baseline pass is the noisy one; the
candidate pass on this harness is repeatable to a quarter of a percent on
prefill. Both readings are still reported below.

## What the four rates can physically be (predicted before the receipts land)

Using #27's two in-situ M5 constants — 610 GB/s streaming DRAM read and
56 TFLOP/s dense BF16 GEMM at `512×8192×2048` — each block has a hard floor:

| block | DRAM time | compute time | binding side | implied apparent rate at the floor |
| --- | ---: | ---: | --- | --- |
| prefill routed gather-GEMM (rate 1) | 17,666.41 MB / 610 = **28.96 ms** | 1005.02 / 56 = 17.95 ms | **DRAM** | 1005.02 GFLOP / 28.96 ms = **34.7 TFLOP/s** |
| prefill attention dense GEMM (rate 3) | 2852.13 / 610 = 4.68 ms | 1460.29 / 56 = **26.08 ms** | **compute** | **56 TFLOP/s** |
| decode attention QMV (rate 2) | 802.16 / 610 = **1.32 ms** | 2.85 GFLOP → negligible | **DRAM** | **610 GB/s** |
| decode routed QMV (rate 4) | 552.08 / 610 = **0.91 ms** | 1.96 GFLOP → negligible | **DRAM** | **610 GB/s** |

This reframes the question the assignment poses for rate 1. The brief proposes
25–30 TFLOP/s as the "kernel is inefficient" arm and ~50 TFLOP/s as the
"scheduling/glue" arm. But the routed banks are 39 × 452.98 MB = **17.67 GB, i.e.
82% of the whole 21.6 GB text tower**, and a 512-token prefill with top-8 routing
puts on average 16 rows on every one of the 256 experts, so *every* expert bank is
touched and the whole thing must stream from DRAM once. At 610 GB/s that is
28.96 ms and no scheduling can make it less. **34.7 TFLOP/s is the ceiling, not
50.** A measurement of 25–30 TFLOP/s would therefore mean the gather-GEMM is at
72–86% of its DRAM roofline — efficient, not inefficient — and would say the
prefill residual is *not* hiding in this kernel's arithmetic.

The M4 cross-check already supports the DRAM-exposure reading rather than an
arithmetic-inefficiency reading. On M4 the same block measured 5.85 TFLOP/s,
which is 79% of the host's 7.40 TFLOP/s dense GEMM rate, while its DRAM time
(9059.70 MB / 256 GB/s = 35.4 ms) and compute time (515.40 / 7.4 = 69.6 ms) sum
to 105.0 ms against a measured 88.09 ms. So on M4 the block runs at essentially
the dense arithmetic rate with about half of its DRAM traffic left exposed rather
than overlapped. M5 has a 7.8x faster GEMM but only a 2.4x faster memory system,
so on M5 the same block should be firmly DRAM-bound.

A first-principles floor for the whole prefill forward from these two blocks
alone is `28.96 + 26.08 = 55.0 ms` of the measured `S₀ = 97.92 ms`, i.e. **56%**,
if the two do not overlap each other. That is the number the receipts test.

## Rates (official M5)

TBD

## Evidence

- Host, memory profile, toolchain, thermal policy: AWS EC2 Mac M4 Pro, 20 GPU
  cores (`applegpu_g16s`), 36 GB unified memory, low-memory startup profile,
  40 C thermal gate honoured on every run, one model-holding process at a time.
  Ranked receipts run on the organizer's M5 Max behind the same gate.
- Exact commands:
  ```bash
  env DARKBLOOM_INJECT_<KNOB>=<n> DARKBLOOM_INJECT_VERBOSE=1 \
      ./benchmark.sh --local-iterate        # L0..L4
  ./benchmark.sh --local-submit             # preflight at the heaviest config
  mlxfast submit --note-file research/tanjiro-pr34/note-r<N>.md \
      --model "Claude Opus 5"               # R1..R4
  python3 senpai/tools/pr34_block_rates.py --low <a>.json --high <b>.json \
      --low-config da,dr,pr,pa --high-config da,dr,pr,pa
  python3 senpai/tools/pr34_replicate_noise.py /tmp/subs.json morganmcg1
  python3 senpai/tools/pr34_receipt.py /tmp/subs.json <id-prefix>
  ```
- Checks run: public 64-step drift tripwire on every `--local-iterate`;
  `--local-submit` at the heaviest configuration (all four knobs on) reported
  `passed_correctness = true`, `passed = true`, `max_abs_diff = 0`, golden hash
  `f49e4c2c…`, `error = ""`.
- Correctness and serial-protocol verdict: unchanged. The instrument only reads
  weights and discards results; it creates no KV rows, no logits and no
  cross-request state, and its magnitudes are input-independent runtime
  integers.
- Peak RAM: 21 GB in every local run, identical to the uninstrumented base;
  the scratch pool is a few MB of zero-filled inputs and index pools allocated
  during the untimed warm forward.

| Metric | Baseline (L0) | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.013325 | see L1–L4 | instrument, not a speed attempt |
| prefill seconds/token | 0.001127 | see L1–L4 | instrument, not a speed attempt |
| same-host paired estimate | — | n/a | this arm measures rates, not speed |

## Method notes that outlive this arm

1. **Each knob at maximum equals exactly one extra full copy of the block.** That
   is not a coincidence of tuning: one copy per layer, over every layer that has
   the block, reproduces the block's own per-pass work byte for byte and FLOP for
   FLOP. It removes extrapolation from the rate entirely — the marginal cost *is*
   the block's cost.
2. **Marginal rate is an upper bound on the block's standalone efficiency.**
   Injected copies are unchained, so they may execute concurrently with the
   scored work and consume cycles the scored step already wastes. On M4 that
   inflates the reading by +8 to +12% relative to @maple-nezuko's isolated
   per-call timings. A marginal rate near the achievable roofline therefore does
   not prove the kernel is efficient; it proves the *system* can absorb that much
   more traffic, which is itself the interesting number for a scheduler.
   A marginal rate well *below* the roofline is the strong result, because
   absorption can only push the reading up.
3. **The candidate axes are eight times more repeatable than the pinned
   baselines on the prefill axis.** Any future receipt-difference work on this
   benchmark should difference raw candidate axes and treat baseline-ratio
   normalisation as an optional, noise-adding cross-check, not as the estimator.
4. **The receipt feed is the cheapest source of ranked-host truth available.**
   Eleven clean receipts from a single day, published for free with
   `rejectionReason = "score did not improve current best"`, gave a 0.245% /
   0.440% noise floor that no local host can establish.

## Conclusion

TBD
