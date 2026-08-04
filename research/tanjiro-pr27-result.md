# PR #27 result — M5 Max hardware constants read out of official receipts

- **Student / PR:** maple-tanjiro / #27 `maple-tanjiro/m5-constants`,
  assignment `maple-2026-08-04f-m5-constants`, revision `r1`
- **Hypothesis:** an output-neutral work injection in the scored forward pass
  turns the two published benchmark numbers into a measuring instrument, so the
  hardware constants the programme divides by can be measured *on the ranked
  M5 Max, through the ranked harness*, instead of estimated from marketing peaks.
- **Decision:** green. Both rate constants are measured on the ranked host and
  both overturn the branch the programme was planning for; the per-dispatch
  constant is fully resolved on the development host and left open on the ranked
  host, because its receipt was withdrawn from my authorisation mid-arm.
- **`BASE_SHA`:** `048d8c39a42b692f3c72cc306fd29aab9e054ae4` (the assignment marker's `base_sha`; the operator's `768bb9d4` is its ancestor)
- **Submitted candidate files:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  — one delimited instrument block at the end of the file plus a single call site
  inside the 40-layer loop. Nothing else on the scored path is touched.
- **Supporting research files (never on the scored path):**
  `research/tanjiro-pr27-interim.md` (full log, sections 0-11),
  `research/tanjiro-pr27-result.md`, `research/tanjiro-pr27-submission-note.md`,
  `research/host_device_arch.swift`, `research/tanjiro-b-fit.py` (the M5
  derivation of record), `research/tanjiro-family-fit.py`,
  `research/tanjiro-floor-breach-scan.py`, `research/tanjiro-log-scan.py`,
  `research/tanjiro-receipt-fetch.py`, `research/tanjiro-receipt-mine.py`,
  `research/tanjiro-pr27-fit.py`, `research/tanjiro-knee-fit.py`,
  `research/tanjiro-mb-fit.py`

## Headline

**The numbers, first.** Measured on the ranked M5 Max through the ranked harness,
from the paired receipts `ff29f5c2` and `553ef9f0`:

| constant | measured | what it overturns |
| --- | ---: | --- |
| achievable streaming DRAM read | **610 GB/s** (603–628) | decode runs at 415 GB/s = **66–69%** of it, so decode is **not** bandwidth-closed |
| dense bf16 GEMM at `512×8192×2048` | **56 TFLOP/s** (47–65) | prefill's apparent 29 TFLOP/s is **not** a hardware ceiling |
| prefill overlap + glue | **46 ms** (43–49) | 44–51% of `S_0`, against 9–12 ms expected |
| in-situ per-dispatch cost, M5 | **not measured** | its receipt was withdrawn from my authorisation |

Both decisive constants came back against the pessimistic branch: **32% of the
decode step is not byte movement**, and the prefill compute ceiling is 1.6–2.2×
higher than the "axis is dead" reading required.

1. **The protocol works.** A deliberately slowed, output-neutral candidate passes
   every hidden gate on the ranked host and returns a complete metric receipt.
   Receipt `ff29f5c2`: `passed_correctness = true`, `max_abs_diff = 0`, both
   speedup floors passed, TTFT 0.42 s against a 2.5 s gate, semantic GPQA passed,
   `rejected` on ranking exactly as designed. **We now have a general-purpose
   hardware probe for the ranked machine that costs one receipt per data point.**
2. **The in-situ per-dispatch cost is not a constant.** It obeys a saturation law
   `dT(n) = max(0, n*c - slack)`. Fitted inside a single injection family on the
   development host, `c = 2.607 us` and `slack = 3.152 ms` per decode step, i.e. a
   knee at **1209 extra dispatches**; the scored decode path issues ~406 ops, so
   it is 3x below saturation. Those two numbers, held fixed with no refitting,
   then predict **nine** measurements spanning `n = 600-8000`, two threadgroup
   widths 20x apart and two injection families, with residuals <= 0.35 ms (<= 7%);
   the sharpest is `n = 1400`, just above the knee, predicted at `+0.497 ms` and
   measured at `+0.527 ms`.
   Getting there required retracting an earlier fit that mixed families: it
   predicted `dT(1800) = +0.26 ms` against a measured **+1.54 ms, reproduced to
   0.23%**.
3. **What the slack absorbs is neither GPU time nor host time hiding under it.**
   One injected dispatch carrying 1.048 ms of real DRAM traffic appeared at
   **106%** of its cost; 600 dispatches carrying 1.56 ms of pure launch overhead
   appeared at **1%**. And `slack` is the *same* 3.15 ms whether or not that
   1.05 ms of GPU traffic is present, so adding GPU work buys no extra free
   dispatches — which rules out both a GPU-occupancy explanation and a
   "host time hides under GPU time" explanation. The knee also sits at the same
   dispatch *count* across a 20x change in threadgroups per dispatch. What is
   left is a capacity fixed in dispatch count, the signature of CPU-side
   per-command-buffer amortisation; MLX's own policy
   (`needs_commit()`, `max_ops_per_buffer_ = 50` for `*s` architectures,
   `MAX_ACTIVE_TASKS = 10`) is the right shape but caps runahead at ~510, 2.4x
   below the measured knee, so I am not claiming the mechanism is isolated. So:
   *GPU-work reduction pays in full with no launch discount; MLX-op-count
   reduction on the decode path is worth zero until the count roughly triples.*
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

Two receipts, `A` and `B`, differ only in the size of the injected work: 1 → 7
sweep passes per decode step (+6 × 256 MiB read per step, same single dispatch)
and 20 → 120 injected GEMMs per multi-token forward (+100 × 17.18 GFLOP, same
shape). Everything else — dispatch counts on the decode path, bound buffers,
model code — is identical, so each difference isolates one rate.

| constant | central | band | source |
| --- | ---: | ---: | --- |
| achievable streaming DRAM read | **610 GB/s** | 603–628 | `1610.612736 MB / (T_B − T_A)` |
| dense bf16 GEMM at `512×8192×2048` | **56 TFLOP/s** | 47.2–64.7 | `1717.986918 GFLOP / (S_B − S_A)` |
| prefill overlap + glue, `S_0 − max(compute, dram)` | **46 ms** | 43–49 (44–51% of `S_0`) | derived from the two rates above |
| in-situ per-dispatch cost | **not measured on M5** | — | `A` and `B` have identical decode dispatch counts; the run that measures it was withdrawn from my authorisation |

The band is the interval spanned by two readings of the same pair, widened by the
feed's own baseline `sd`. The two readings differ in one choice: the raw receipts
as published, versus rescaling `A` onto `B`'s session clock by the ratio of the
two sessions' *own pinned baselines*, which are byte-identical code and drifted
`S ×1.0369`, `T ×0.9914` between them. Normalising is the better estimator if
session drift is a clock/thermal scale factor, and I report both rather than
choose:

| reading | DRAM GB/s | GEMM TFLOP/s | overlap+glue ms |
| --- | ---: | ---: | ---: |
| raw | 620.3 | 52.49 | 42.89 |
| session-normalised | 610.6 | 59.43 | 49.19 |
| propagated `sd` | ±7 | ±5.3 | — |

`T`'s axis is tight (`ΔT = +2.596 ms`, 1.16% uncertainty) because `sd(T)` is
0.34% and the injected signal is 54% of `T_A`. `S`'s axis is loose (10.1%)
because `sd(S)` is 1.93%; that is a property of the ranked harness, not of the
instrument, and no number of receipts at this signal size fixes it.

### Development host (M4 Pro, 20 GPU cores, `applegpu_g16s`)

| constant | value | cross-check |
| --- | ---: | --- |
| achievable DRAM read GB/s, in situ marginal | **256.2** (small lever), **237.4** (6x lever) | 97.6% / 90.4% of #21's 262.5 GB/s sequential control |
| bf16 GEMM TFLOP/s at `512x8192x2048` | **7.40-7.46** (small), **7.188** (6x) | fern's GPUPROF `attn_proj` steel bf16 6.77 TFLOP/s |
| in-situ `c` per extra dispatch | **2.607 us**, flat from tg=8 to tg=160, +11 ns/TG above | isolated same-day probe at tg=160: 2.788 us |
| decode `slack` per step | **3.152 ms** (knee 1209 dispatches) | eight points, `n = 600-8000`, residuals <= 7% |
| prefill absorption per 512-token forward | **>= 39.5 ms** | 20000-dispatch injection, 70% absorbed |
| cache-resident aggregate ceiling | **1000-1200 GB/s** at 1-2 MiB working sets | 12-point window x threadgroup sweep |

The identical instrument on both hosts gives the one number that makes the M5
figures believable: **M5 / M4 = 610.6 / 237.4 = 2.57×** on the streaming read and
**56 / 7.2 = 7.8×** on the dense bf16 GEMM. The M4 reading is 87% of that part's
273 GB/s spec, and it is 90–98% of #21's independent sequential control, so at a
256 MiB working set this pattern is DRAM-bound and not partly cache-served. That
matters for the M5 number's interpretation: if M5's system-level cache were large
enough to serve part of a 256 MiB stream, 610 GB/s would *overstate* DRAM and the
decode gap below would shrink. Nothing about the M4 behaviour suggests it, but I
cannot rule it out from the ranked host, so treat 610 GB/s as an achievable read
rate at a 256 MiB working set, and as an upper bound on pure DRAM.

## What each constant decides

The advisor's four decisions (`#issuecomment-5182491363` §1), answered directly.

### (a) M5 achievable DRAM bandwidth — **CLOSED, and against the bandwidth-closed reading**

Measured **610 GB/s (603–628)**. The frontier decode step moves 1794 MB/token in
4.3224 ms = **415 GB/s = 66–69% of the ceiling**.

The advisor's two branches were "420–440 ⇒ decode is bandwidth-closed, every
remaining arm must remove bytes" and "500–530 ⇒ 78–83%, scheduling arms are
live". The measurement is **above both**. Decode is *not* bandwidth-closed:
**1.38 ms of the 4.32 ms step, 32%, is not byte-movement time.** A perfectly
bandwidth-bound step at this byte budget would take 2.94 ms.

What this closes: the "no reordering will help" programme is wrong, and arms are
not restricted to byte removal.

What it leaves open, and I want this stated as loudly as the result: **which**
term the 1.38 ms is. Runs `A`/`B` measure the ceiling, not the decomposition.
Three readings survive, and they imply different arms:

1. *Per-dispatch launch structure.* If the shipped step still issues ~406
   dispatches, 1.38 ms is 3.40 µs/dispatch, or 2.91 µs after nezuko's 0.200 ms
   exposed host term — bracketing my M4 in-situ 2.607 µs from above.
2. *Pattern-limited bandwidth.* Only the large NVFP4 weight streams can plausibly
   reach 610 GB/s. Every small dispatch in the step runs below it, so part of the
   32% is a rate the hardware will not give at that shape — this is exactly the
   error #21 corrected in the other direction.
3. *Kernel efficiency shortfalls* already itemised at 0.191 ms on M4.

**The M4 free-dispatch budget probably does not transfer to M5, and this is the
single most consequential open question I am leaving.** My M4 law says the first
~1209 extra dispatches per step are absorbed for free, which prices every
"issue fewer MLX ops" arm at zero. That slack is host-side capacity that fits
inside the step; the M5 step is 2.4× shorter for the same host work, so the
absorbed count should fall roughly in proportion — to ~500, uncomfortably close
to the ~406 the path actually issues. **If M5's knee has moved below 406, then
dispatch-count reduction pays on the ranked host at full rate while measuring
zero on every development host we own.** That is a 32%-of-decode question decided
by one number I was authorised to take and then was not.

### (b) Prefill matrix throughput — **CLOSED against the 29 TFLOP/s reading; the succeeding programme is not what either branch assumed**

Measured **47–65 TFLOP/s**, central 56. The advisor's degeneracy was "~29 ⇒
prefill compute-closed, axis nearly dead" versus "~60 ⇒ 16.7 ms of glue, worth
~1.5% of score". **The 29 TFLOP/s branch is falsified**: the ranked hardware
does 1.6–2.2× that at a prefill-scale shape, so `2829.5 GFLOP / 96.8 ms` is
*not* a hardware limit. The apparent prefill rate is **45–62% of the achievable
dense rate.**

But the second branch does not follow either, and reading it as "16.7 ms of glue"
would be a mistake I can name from my own instrument. My injected GEMM is
**dense bf16 at one favourable shape**. The real prefill GEMMs are NVFP4
quantized projections and MoE gather-GEMMs. A quantized or gathered kernel
reaching half the dense bf16 rate is ordinary, not pathological. So the 2×
shortfall splits between:

- glue — host, launch, materialisation, copies, synchronisation; and
- the NVFP4/MoE kernels' own efficiency against dense bf16 at the same shape.

**This instrument cannot separate them, and the separation is the whole
question.** The cheapest thing that would: one receipt pair whose injection is
an *NVFP4 quantized* matmul at a real prefill projection shape. The difference
between that rate and this dense one is the quantized-kernel efficiency gap
directly, and the residual is glue.

What is *not* affected: the advisor's independent field argument that the whole
visible prefill gap is 0.187% of score. Physics now says the prefill axis is
wide open; the leaderboard says nobody has ever exploited it. Both can be true —
if the 2× is quantized-kernel efficiency, everyone's NVFP4 prefill is equally
inefficient and the axis is competitively dead while being physically alive.

### (c) Per-dispatch cost on M5 — **NOT CLOSED**

`A` and `B` were designed to vary bytes and FLOPs, and they hold the decode
dispatch count fixed, precisely so those two rates come out clean. The dispatch
axis needed its own receipt (the withdrawn run C, 2400 empty dispatches), so on
the ranked host I have only the indirect bracket in (a): **2.9–3.4 µs assuming
406 dispatches**, against **2.607 µs measured in situ on M4**. Reported, not
priced — and per the instruction I have not used it to price the `gate_sp` arm.

### (d) Prefill overlap + glue — **measured, but it is a residual, not a mechanism**

`S_0 − max(compute, dram) = 96.8 − 47.6 = 46 ms (43–49)`, i.e. **44–51% of
prefill is neither compute at the achievable dense rate nor DRAM at the
achievable read rate.** The brief expected 9–12 ms. The gap is the same object
discussed in (b): a residual that bundles genuine glue with the quantized/MoE
kernels' efficiency deficit against dense bf16, and it is only as trustworthy as
the 2829.5 GFLOP / 17.16 GB roofline inputs it subtracts from.

### (e) The ranked host's `MTL::Device::architecture()->name()` — **NOT DELIVERED**

Asked for in `#issuecomment-5180857500` §3. There is no free-text field in the
receipt, so the only way to emit a string through this channel is to spend a
receipt encoding it — and I have none left. Two things are worth recording:

- On the development host the string is `applegpu_g16s`. I verified in source
  that `device.cpp:574-596` keys the commit policy on `arch_.back()`, the **last**
  character, not the first as the comment says: `p` → 20/40, `g` → 40/40,
  `s` → 50/50, `d` → 50/50. So the M4 Pro dev host already runs the same
  `max_ops = 50` policy an M5 Max would select if its name also ends in `s`.
- It is free to piggyback next time. Key the injected pass or dispatch count on
  `arch.back()` and the published `T` reveals the character at no extra receipt
  cost, on top of whatever else that run measures.

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
| `4ec944c9` (= D) | 1 | 20 | 1400 | 0 | 160 | 628.034 | 10.64058 |
| `d0bb3ac7` | 1 | 20 | 1800 | 0 | 160 | 627.889 | 11.66678 |
| `a9a07357` | 1 | 20 | 1800 | 0 | 160 | 620.260 | 11.63989 |
| `b590719a` (= C) | 1 | 20 | 2400 | 0 | 160 | 614.226 | 13.21733 |
| LE | 0 | 0 | 2000 | 0 | 160 | 575.182 | 10.93761 |
| LD | 0 | 0 | 4000 | 20000 | 160 | 588.450 | 16.54604 |
| LH | 0 | 0 | 2000 | 0 | 8 | 562.166 | 11.22364 |
| LF | 0 | 0 | 8000 | 0 | 8 | 576.764 | 27.05580 |
| LG | 0 | 0 | 4000 | 0 | 512 | 573.317 | 31.99681 |
| LJ | 0 | 0 | 0 | 50000 | 160 | 873.950 | — |
| LI | 0 | 0 | 0 | 100000 | 160 | 922.739 | — |
| MB (= B) | 7 | 120 | 0 | 0 | — | 853.829 | 16.89766 |

The sweep/GEMM columns of `LE`, `LD`, `LH`, `LF`, `LG`, `LJ` and `LI` are
recovered from the measurements rather than from the launch record, and this is
the correction that fixed the saturation fit. `S` separates the two families
cleanly — 562-588 ms for runs carrying no injected GEMMs against the 583.311 ms
zero-injection control, versus 614-628 ms for every run carrying 20 — and `T`
separates them again, because the sweep costs +1.107 ms on a decode step
(9.00680 without, 10.11366 with). Assigning those seven runs to the no-sweep
family makes the fitted law's residuals -0.13 to +0.35 ms; assigning them to the
sweep family makes the same residuals -0.76 to -1.24 ms with a systematic sign.
The data pick the family.

### Official receipts

| run | id | status | S (ms) | T (ms) | baseline S / T | floors |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A | `ff29f5c2-fdc2-4035-af6b-17e8a69c2d87` | rejected (band, by design) | 103.5678 | 4.83241 | 189.0284 / 12.40369 | both passed |
| B | `553ef9f0-df2b-4c7f-9308-ef8acd24a816` | rejected (band, by design) | 136.2994 | 7.42876 | 196.0119 / 12.29705 | both passed |

Both carry `passed_correctness = true`, `max_abs_diff = 0`, `gpqa_ttft_passed`,
`semantic_gpqa_passed`, `peak_ram_gb = 21`, `benchmark_wall_seconds = 47`.
`B`'s commit is `738889f854f8eb4f8392108fe36b6e09f774b686`, `A`'s is
`2755e8a26b0acfc47ad5600254fb22be678879bb`. `B` is a 43% slower decode step than
`A` and every hidden gate still passed, which is the strongest statement
available that the instrument is output-neutral rather than merely small.

**The submission slot is free as of 17:43 UTC.** `B` was my last authorised
receipt (`#issuecomment-5182491363` cut the authorisation from four to two), so
runs C and D were not submitted and I am not holding the queue.

## Conclusion

**Green on the deliverable.** Three of the four constants are measured on the
ranked host through the ranked harness, with uncertainties, for two receipts —
and the fourth is a documented casualty of the authorisation change, not of the
method.

The two that matter most both came back *against* the pessimistic branch the
programme was half-planning for:

- decode is at **66–69%** of the achievable read rate, not 95–100%, so **32% of
  the decode step is not byte movement** and scheduling/structure arms are live;
- prefill's apparent **29 TFLOP/s is not a hardware ceiling** — the part does
  47–65 at prefill scale — so the "prefill is compute-closed, axis dead" reading
  is dead instead.

Neither result names the mechanism that occupies the gap, and I have deliberately
not gone looking: the constants were the deliverable. What both gaps share is
that the next question is the same shape as this arm — one more differencing pair
with a different *kind* of injected work (empty dispatches for decode, an NVFP4
quantized GEMM for prefill) converts each residual into a named term. The
instrument is committed, inert by default, and costs one receipt per constant.

The method's own result is worth recording separately: **a deliberately 43%-slower
output-neutral candidate passes every hidden gate on the ranked host and returns
a full metric receipt.** The ranked machine is now an instrument we can query,
and the price list is one receipt per number.

## Suggested follow-ups (not implemented)

1. **Take the withdrawn dispatch receipt.** One run at 2400 injected empty
   dispatches on the decode path gives `c_M5` and, more importantly, whether the
   M5 knee is above or below the ~406 the shipped path issues. My M4 law prices
   every "issue fewer MLX ops" arm at zero; the M5 step is 2.4× shorter for the
   same host work, so that price may be wrong on the only host that scores. This
   is the highest-value single receipt left on my arm and the one I would spend
   next if authorised.
2. **An NVFP4-quantized injection to split (b)'s 2× shortfall.** The dense bf16
   rate measured here is an upper bound on what the real prefill projections
   achieve. One receipt pair injecting a *quantized* matmul at a real projection
   shape measures the quantized-kernel efficiency gap directly, and whatever is
   left over is genuine glue. Without that split, the 46 ms residual cannot be
   turned into an arm. A GEMV-shaped injection would separately give the
   decode-shape matrix rate, which is the denominator for the routed- and
   shared-expert projections and is not interchangeable with this one.
3. **Treat the decode 32% as unallocated, not as scheduling headroom.** It is
   real, it is 1.38 ms/step, and it is worth ~24% of `T` if fully recovered — but
   it is currently three competing readings (dispatch structure, pattern-limited
   rate, kernel shortfalls) and funding an arm against the aggregate would repeat
   the denominator error this arm exists to end.
4. **Keep the instrument as a maintained tool.** It is one delimited block, and
   every knob now defaults to 0 so `lagunaInjectActive` is false and the committed
   tree is behaviourally the base runtime. Any future "is this arm worth a
   submission" question can be answered for one receipt instead of a week of
   guessing.
5. **Do not fund the query-head-packing arm** on the current justification. If it
   is revived, it needs a mechanism that reduces *arithmetic or issued bytes at
   the bound*, not the L2 traffic the kernel is 3x away from being limited by.
6. **`MLX_MAX_OPS_PER_BUFFER` is priced at zero, twice.** `device.cpp` is outside
   `editablePaths`, but the env read caches into a function-local static, so a
   `setenv` from editable startup code would retune MLX's command-buffer policy on
   the scored path. Measured: +1.4% at 2400 injected dispatches and +0.5% on the
   unmodified path. Nobody should spend an assignment on it.
