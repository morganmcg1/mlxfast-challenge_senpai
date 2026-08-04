# SENPAI Research State

- **2026-08-04 10:00 UTC** — advisor `meridian`, campaign `mlxfast-maple-20260804`
- Most recent human research direction: operator authorised the advisor and all
  four students to dispatch official `mlxfast submit` runs from the AWS Macs.
- Base branch: `codex/mlxfast-maple-20260804-advisor` @
  `3e8e43522aeb3222cef45fe8852fb78eed673e10`
- Companion document: **`research/FIELD_MECHANISM_MAP.md`** — public-corpus
  leaderboard, session-draw distribution, promotion arithmetic, and the
  mechanism-coverage map that tells us which axes the field has and has not
  worked.
- Students: `maple-frieren`, `maple-fern`, `maple-tanjiro`, `maple-nezuko`
  (M4 Pro / 48 GB / 20-core GPU). Official host: M5 Max / 128 GB.
- Goal: maximise `score = decode_speedup^0.75 * prefill_speedup^0.25`.

> **This target has no W&B integration.** Every `runs` array in every result is
> empty by design. Evidence is code, local harness measurements, and — as of
> today — official M5 submission metrics.

---

## THE THREE THINGS TO READ FIRST

### 1. Student hosts cannot measure the prefill path at all (fern, #11)

`mlx::core::metal::is_nax_available()`
(`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`) requires macOS >= 26.2
**and GPU arch gen >= 17**. Our M4 Pro hosts report `arch=applegpu_g16s gen=16`:
the OS gate passes, the **GPU generation gate fails**.

Measured consequence: **94.2% of prefill GPU time on a student host runs Metal
functions the official M5 never executes.** Not the same kernel at different
occupancy — *different kernels*: `nvfp4_gather_qmm_rhs_nt` 48.5%,
`steel_gemm_fused_nt_bm64_bn64_bk16` 33.4%, split-K 6.0%,
`steel_attention_bfloat16_bq32_bk16` 5.1%, `nvfp4_qmm_t` 1.2%.

By contrast the **steady decode step is 100% host-independent**: every dispatch
is a hand-written `laguna_*` kernel (or `rms`/`gather_front`), none behind a NAX
or `#available` gate. The only capability gate in all of `Sources/` is
`lagunaExpertAlignedGatherEnabled` (`LagunaRuntimeModel.swift:235-249`), used at
exactly one **prefill** site (`:9631`).

This is the mechanistic explanation for the campaign's entire track record:
decode work measured on M4 exercises the code M5 runs; prefill work does not.
It also means the `_nax` editable surface — the kernels the M5 actually selects
— is only measurable through official submissions.

Operational rules:

- Never run a prefill *kernel* experiment on a student host. Local timing there
  is not weak evidence, it is evidence about different code.
- Prefill mechanisms must be justified by **host-independent** reasoning
  (routing statistics, byte budgets, analytic rooflines) and then measured
  officially.
- `fp_gather_qmm_rhs_expert_nax` is **JIT-only** — never instantiated in the AOT
  metallib, built at runtime from the string in
  `mlx-generated/fp_quantized_nax.cpp`. Editing the header alone changes nothing
  at runtime; the generated `.cpp` must be edited too, and the header kept
  identical because the AOT metallib compiles it for other kernels.

### 2. The exact score decomposition (fern, #11)

The reported decode metric charges the 512-token seed forward into itself, and
the same forward is the whole prefill metric:

```
D = decode_seconds_per_token  = S/128 + T
P = prefill_seconds_per_token = S/512
=>  S = 512 * P        T = D - S/128        sigma = (S/128)/D
d ln score / d ln S = -(0.25 + 0.75*sigma)
d ln score / d ln T = -0.75*(1 - sigma)          # the two sum to -1
```

Validated against our official receipt: `S_base/S = 1.9718` vs published
`prefill_speedup 1.971861`; `D_base/D = 2.7018` vs `decode_speedup 2.701815`.

| | S (ms) | T (ms) | sigma | fwd elasticity | step elasticity |
| --- | ---: | ---: | ---: | ---: | ---: |
| M5 baseline (our session) | 193.544 | 12.3206 | 10.93% | | |
| M5 candidate `27b9c7c6` | 98.153 | **4.3530** | **14.98%** | **0.362** | **0.638** |
| M5 promoted best `8415f63c` | 97.820 | 4.3587 | 14.92% | | |
| M4 host, `--local-iterate` | 585.6 | 8.769 | 33.6% | 0.502 | 0.498 |
| M4 host, `--local-submit` (1023 steps) | | | ~5.9% | ~0.294 | ~0.706 |

Both figures I previously circulated (0.52 and 0.25) were wrong. Correct values:
**seed forward 0.362, steady decode step 0.638.** The steady step is worth 1.76x
more per percent.

Measurement corrections that follow:

- A student host **under-reports a pure steady-step win by 1.28x**
  (0.638 / 0.498). Multiply local score deltas by 1.28.
- A student host **over-reports a pure seed-forward win by 1.385x**
  (0.502 / 0.362). Divide by 1.385.
- `--local-submit` drives sigma to ~5.9%, so it nearly hides forward wins. Size
  every forward change with `--local-iterate`; use `--local-submit` only as a
  packaging check.
- Report `S` and `T` for every official run, candidate and paired baseline.
  `decode_speedup` alone is uninterpretable because it blends a 2.83x step with
  a 1.97x forward.

Two derived observations: our tree sped the steady step up **2.830x** but the
forward only **1.972x**, so **the forward is our laggard**; and sigma *rises* as
the step improves (10.9% -> 15.0%), so forward work becomes progressively more
valuable, not less.

### 3. M4 wall-clock does not transfer to M5 for threadgroup-geometry changes

Nezuko's #7 (`outputs_per_simd` 1→4, grid `/4`, i.e. 4× fewer threadgroups)
measured **+7.32% decode on M4** (0.0146282 → 0.0136301 s/token, bit-exact,
repeated) and delivered **≈0.0% on M5**. Tanjiro predicted exactly this class of
inversion in #10 from his occupancy model and reverted his own M4-winning kernel
because of it; I merged #7 anyway. He was right.

Consequence: no M4 wall-clock number may be used as evidence for a geometry
change again. Classify every proposal as either

- **work-reducing / byte-reducing / host-CPU-reducing** → plausibly transfers, or
- **thread re-tiling across cores** → does not transfer; must be measured on M5.

---

## Official M5 measurement channel (opened today)

Rejected submissions still return **complete** official metrics. An official run
is therefore a measurement device, not just a scoreboard entry. Round trip
≈35 minutes (`27b9c7c6`: created 07:53, resolved 08:29). No documented rate
limit. 1372 submissions exist: 769 rejected, 463 failed, 139 accepted
(138 promoted).

```bash
# full metrics for one submission (never print the token)
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  https://api.mlx.fast/api/submissions/<full-uuid> | python3 -m json.tool

# every submission for the benchmark (no query params, returns all)
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions
```

Token resolution order is `MLXFAST_API_TOKEN` → `YUKON_API_TOKEN` →
`SUPABASE_ACCESS_TOKEN` → `~/.config/mlxfast/config.json`
(`/usr/local/libexec/mlxfast.js:20960`); header format is `Bearer` (`:5987`).

### Submission 1 — `27b9c7c6-14bf-4e23-a39c-09d82d331aa0`

Tree = imported frontier + nezuko's #7 only. **Rejected**, reason
`"score did not improve current best"`. All correctness gates passed:
`max_abs_diff 0`, 1344 checked steps, GPQA TTFT 9/9 (p50 0.071 s, max 2.5 s),
semantic GPQA 8/9 cases with `semantic_gpqa_passed: true`, both 0.95 floors
passed, `peak_ram_gb 21`, `bandwidth_gb_per_token 0`.

| metric | ours `27b9c7c6` | best `8415f63c` |
| --- | ---: | ---: |
| `decode_speedup` | 2.701815 | 2.742050 |
| `prefill_speedup` | 1.971861 | 2.016350 |
| `decode_seconds_per_token` | 0.0051197747 | 0.0051229000 |
| `prefill_seconds_per_token` | 0.000191705 | 0.000191054 |
| `baseline_decode_seconds_per_token` | 0.013832684 | 0.014047243 |
| `baseline_prefill_seconds_per_token` | 0.000378016 | 0.000385232 |
| official score | 2.49724 | 2.53921 |

---

## Baseline draw is a ~1–1.6% component of the published score

`baseline_decode_seconds_per_token` over the last 12 promoted runs: **10 of 12
inside 0.013875–0.013911 (±0.13%)**, with excursions to 0.014008 and 0.014047.
`baseline_prefill_seconds_per_token` clusters near 0.000384 ± 0.5%.

The paired baseline is measured fresh per session, so it is the noisy term and it
multiplies straight into the score. Promotion is a max over draws, so the
leaderboard systematically harvests the fat tail: **`8415f63c` became "best" on
the slowest baseline of the last 12 (+1.1% above the cluster)**, and our run drew
the fastest prefill baseline of all 12 (−1.6%).

### Canonical normalisation (use this for every cross-session comparison)

```
norm_decode_su  = 0.013890 / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
norm_score      = norm_decode_su**0.75 * norm_prefill_su**0.25
```

| tree | abs decode s/tok | abs prefill s/tok | norm score |
| --- | ---: | ---: | ---: |
| `21f1d1a3` metaspartan 08-03 19:20 | 0.00509782 | 0.000191036 | **2.52606** |
| `0a9d439b` davidtai 08-03 12:28 | 0.00510069 | 0.000190838 | 2.52581 |
| `8415f63c` a-github-name 08-03 19:32 — **our imported base** | 0.00512290 | 0.000191054 | 2.51648 |
| `27b9c7c6` ours (base + #7) | 0.00511977 | 0.000191705 | 2.51521 |

Two consequences:

1. **We are ~0.4% off the true frontier, not 1.68%.** The published gap is mostly
   baseline draw.
2. **The tree the whole team is sitting on is ~0.38% slower than a tree promoted
   12 minutes earlier.** `8415f63c` and `21f1d1a3` are near-simultaneous siblings
   of `0a9d439b`, so `21f1d1a3` contains a real improvement our base lacks and it
   was lost only because a luckier draw overwrote it as "best".

---

## The corpus is public and readable — this is the largest untapped asset

`mlxfast reset <submission>` is documented as *"Restore editable paths from any
submission's commit, accepted or not."* `mlxfast sync` is how our base was
created. Every submission carries a mandatory public note
(`mlxfast submission-note <id>`). The read path is deliberate: this is a
cumulative public competition.

So all 1372 trees are inspectable, including the **769 rejected** ones — which
contain real improvements that merely lost the promotion race. The field advances
about **0.28% per promotion**; harvesting three independent lost siblings would
beat every kernel idea currently on our board, with **zero M4→M5 transfer risk**
because each candidate has already been measured on the official M5.

Safe recipe (never push a `scratch/*` branch):

```bash
git checkout -b scratch/harvest-<shortid> <BASE_SHA>
mlxfast reset <submission-id> --force
git add -A && git commit -F <message-file>
git checkout <work-branch>
git --no-pager diff <BASE_SHA> scratch/harvest-<shortid>
```

We attribute every harvested mechanism by submission id and solver in our own
public note.

---

## Current research focus

The campaign has moved off kernel micro-optimisation. Four concurrent arms:

| PR | student | arm | why now |
| --- | --- | --- | --- |
| #12 | nezuko | harvest the public submission corpus; normalised leaderboard over all 1372 records; diff the **nine trees that beat our base** and land what we lack | highest EV, no transfer risk |
| #13 | tanjiro | **calibrate the M5 instrument**: submit `BASE_SHA` unmodified twice for a noise floor on `S` and `T` separately, which also reads the never-measured combined M5 value of #4 + #5; then one or two wave-model-optimal sliding-attention geometries | we cannot tell a real 1% from a lucky draw; wave quantisation has **1 mention in 1372** public notes |
| #14 | frieren | cut per-step host CPU ≥25% on the steady decode step; separate host CPU that overlaps GPU from host CPU on the critical path | only axis with evidence of surviving the transfer, and the M5 step is 4.353 ms so host time is ~2× more exposed there than locally |
| #19 | fern | the **cold first-touch component of the scored 512-token forward**: ~30.5 ms of M4's 585.6 ms forward is first-touch, an absolute cost that should be near-invariant across hosts and is therefore ~31% of M5's 98.15 ms forward | explains why our forward is the laggard (1.97× vs 2.83×) and why the entire field's prefill is frozen within 0.3%; residency/first-touch has 53 field mentions and a best of 2.4944, i.e. tried and never landed |

Terminal this round: **#11 fern merged** — byte-identical scored surface, three
structural findings (sections 1–2 above plus the routing histogram), five
mechanisms killed with numbers, and measured M4 MMA/bandwidth ceilings.

Submission authorisation this round: nezuko 3, tanjiro 5, frieren 3, fern 3. One
in flight per student; every submission id plus complete `officialMetrics`
reported in the PR, **decomposed into `S` and `T`**.

### Promotion target

Promotion requires `officialScore > 2.53921`. From the session-draw distribution
(`research/FIELD_MECHANISM_MAP.md`), the expected number of submissions needed is
~130 at the best normalised score anyone has ever posted (2.5331) and ~12 at
2.5450. **Our tree is at 2.5152. Target ns >= 2.545.** Resubmission alone is not
a viable path — the tree has to get ~1.2% better than the best public tree.

### The unifying hypothesis under test (frieren #14, tanjiro #13 part 3)

**M5 decode is much closer to host-CPU/latency-limited than M4 decode is.** M4:
~8.5 ms GPU-busy vs ~4–5 ms host CPU per step → GPU-bound, so GPU wins show. M5
has ~2× cores and more bandwidth; if that halves GPU time while host time barely
moves, the step becomes host-comparable and GPU wins get absorbed. This single
mechanism explains **all** of:

- #7: +7.32% M4 → 0.0% M5;
- #9: deleting 40 of 406 dispatches/step (10%) returned exactly zero;
- `gpu_busy_sum == gpu_busy_union` to 6 ns — no GPU-side concurrency to win;
- frieren's #4 host-CPU win being invisible on M4.

Falsifiable: a 25% host-CPU cut that does not move the official M5 normalised
score beyond tanjiro's noise floor kills it.

---

## Established facts (do not re-derive)

**Score / protocol**
- `score = decode_speedup^0.75 * prefill_speedup^0.25`; verified against
  `officialScore` to 1e-4 on `27b9c7c6`.
- Speedups are `baseline_* / candidate_*` from the same session; verified to 1e-5.
- The **1.053 acceptance-band upper edge is not enforced on the ranked timing
  path.** `Constants.swift:150-166` says the `officialBaseline*` constants are not
  the ranked denominator; the band-checking harness pass runs under
  `MLXFAST_BENCHMARK_SKIP_TIMED=1` (`.github/workflows/benchmark.yml:1511`) so its
  speedups are 1.0 by construction; the only trusted judge of measured timing is
  `.github/scripts/overlay-paired-timing.sh:129-169`, which applies only the 0.95
  floors. Empirically 120 of 126 promoted receipts are faster than any pinned
  reference band permits, and one accepted submission carried a +7.86% decode
  step. **Never throttle or stage a win to fit a band.** `senpai/program.md` and
  organizer `TASK.md` still state the band as enforced — unreconciled prose.
- Acceptance is purely `"score did not improve current best"`. Rejections cost
  nothing and still return full metrics.
- Surface budget: 3,000,000 B total, 524,288 B/file, `fileCount == 142` pinned
  (`Tests/MLXFastTests/BenchmarkScriptTests.swift:2557`). Local warns
  (`MLXFastCLI/main.swift:1394-1402`), official throws. Headroom now **≈67,056 B**
  after #8.
- `editablePaths` has 97 entries. **`metal_kernel.cpp` and MLX's `device.cpp` are
  NOT among them** — so the encoder/dispatch policy (serial vs concurrent) is
  off-surface and the concurrent-dispatch idea is permanently closed. Editable
  vendor surface does include `steel/gemm`, `steel/attn`, `sdpa_vector.h`,
  `quantized*`, `fp_quantized*`, and all the `_nax` twins the M5 selects.

**Decode microarchitecture (M4, treat as M4-specific)**
- Step is ~96.7% GPU-busy; 1.7929 GB/step at 188.8 GB/s = 72.5% of the measured
  260.2 GB/s ceiling; DRAM floor 6.891 ms; 406 dispatches / 45 command buffers.
- **Per-dispatch `µs/call` from split-command-buffer mode is biased.** Each split
  measurement carries 1.33 µs of command-buffer overhead absent at 45 CBs/step,
  so the cheapest dispatches are overstated most (`gate_sp` by 25%, router top-8
  by 54%). Any table built that way over-ranks cheap kernels. (nezuko #9)
- **Occupancy quantisation is real and dominates.** Exactly 20 concurrent
  1024-thread threadgroups fit on the 20-core M4 (risers at g=21 and g=41),
  identical for 9216 B and 17920 B threadgroup memory — which independently
  explains fern's threadgroup-memory null. Fit `T_tg(w) = 16.16 + 6.65w` µs.
  Always report `ceil(TGs/cores)` for **20 and 40 cores**. (tanjiro #10)
- `residual_rms_router` at rpg8 = 32 threadgroups = 2 waves on 20 cores ≈ the 60%
  of ceiling observed, but **1 wave on 40 cores** — so it is an M4-only artifact.
  Several "sub-roofline" entries in the M4 table are M4 wave artifacts that
  vanish on M5.
- Largest remaining pool: `sliding_fused_attn_ring_v1` at 36% of the M4 ceiling,
  ~428 µs/step, ~8 threadgroups after #5's KV-group widening → 12 idle cores on
  M4, ~32 on M5. Bit-exact direction is more lanes over the 512 sliding
  positions; a split-K flash combine reassociates and is out.
- Elasticity: `decode_seconds_per_token = (charged 512-token seed forward + 128
  steps)/128`, seed ≈546 ms vs ≈9 ms steps on M4, so ≈31% of the reported decode
  number is the seed forward and every "% of steady step" must be multiplied by
  ≈0.69 to reach the metric. My earlier 0.51 figure was too conservative.
- Prefill is nearly saturated field-wide: 0.0001966 → 0.0001910 s/token
  (−2.9%) across the last 12 promotions, top six within 0.3%, exponent 0.25.
  Decode moved 0.005229 → 0.005098 (−2.5%) over the same window.

**Closed families — do not reopen without new evidence**
- Dispatch-count reduction / kernel fusion for latency. A bit-exact fusion
  deleting 10% of dispatches returned zero and added +38 µs/step to the absorbing
  kernel. M3 (router into `residual_rms_router`) is structurally blocked: the
  router needs all 256 logits in one 256-lane threadgroup while
  `residual_rms_router` runs 32×512 threads holding 8 logits each. (#9)
- Concurrent encoder dispatch — policy is off-surface (`device.cpp`).
- Sliding-window KV re-read reduction — re-reads are cache-absorbed. (#5)
- Certified LM-head screening. (#6, closed)
- M4-argmax-driven geometry tuning as a source of evidence.
- **Routed-MoE row-tile widening.** BM 64→128 cuts chunks/layer only 220.5→207.9
  (−5.7%) because the median expert holds 7 rows and ~80% of experts need one
  chunk at any BM. (#11)
- **Reducing rows-per-simdgroup below 16 in the NVFP4 gather-GEMM.** `TM = SM/16`
  (`fp_quantized_nax.h:1719`) and `kFragRows = 16` (`steel/gemm/nax.h:28`). SM=8
  gives `TM=0`, so `tile_matmad_nax`'s `mm < TM` loop runs zero times **with no
  diagnostic**. A 16-row MMA operand cannot be sub-masked; this is why the repo's
  own FRAGSKIP was rejected (`quantized.cpp:1443-1447`). The 31.3% MMA row
  padding at 512 tokens is a hardware floor, not a tunable.
- **Skipping zero-row expert threadgroup columns for DRAM savings.** No early
  return exists because none is needed: `run_start == run_end` makes the chunk
  loop (`fp_quantized_nax.h:1777-1783`) iterate zero times, and every
  weight-stage, scale-read and accumulator-init site is inside it. A zero-row
  threadgroup costs a launch, 9216 B of statically reserved threadgroup memory,
  two lanes' binary searches, and one barrier. Remaining prize is occupancy only,
  i.e. bucket B. (#11)
- **`arangeuint32` caching** — the 76 dispatches' apparent 134 ms is a
  command-buffer overlap artifact; busy sum minus arange matches the busy union
  to 0.19%, so ~0 ms real. (#11)
- **Prefill host-CPU / command-buffer reduction** — prefill GPU-busy union is
  99.4% of wall. No gap. (#11)
- **`DARKBLOOM_ATTN_QHOIST`** — ≤0.33% of score even if perfect, and NAX-only
  dead code on any student host. (#11)
- **`GEMM_TPARAM_MACRO` medium-device tile retune** — M4-only code path, cannot
  affect M5 by construction. (#11)

**Prefill / seed-forward facts (host-independent, from #11)**
- Per-expert routing at 512 tokens, pooled over 76 layer instances: mean 16.00
  rows, stdev 28.77 (CV **1.80**), p50 **7**, p75 19, p90 39, p95 58, p99 142,
  max 505, **20.3% zero-row experts**. Busiest 8 experts hold 26.0% of a layer's
  assignments; busiest 32 hold 54.7%. Per-layer max 243.1 vs mean 16.0 = 15.2×
  imbalance. Routing depends on model + prompt, not GPU, so this transfers.
- The organizer's own gather-GEMM tuning notes state their run-elision figures
  were "**Simulated over uniform routing**" (`quantized.cpp:1405-1415`). That
  assumption is empirically false. The shipped tile choice is calibrated against
  a distribution that does not occur.
- Analytic 512-token forward budget: 2830.2 GFLOP over 26.68 GB = **106.1
  FLOP/byte**, against an M4 machine balance of 110.5 — the forward sits on the
  balance point. Stage shares of FLOP: attn_proj_qkvo 51.8%, routed_experts
  35.5%, attn_core 5.7%, shared_expert 4.4%, dense_mlp_layer0 1.8%, router 0.7%.
- Measured M4 Pro ceilings: scalar FMA f32 7.07 TFLOP/s, f16 7.59, **simdgroup
  MMA bf16 28.76**, MMA f16 28.96, DRAM 260.2 GB/s. The forward runs at 16.8% of
  the MMA ceiling; the routed gather-GEMM at 13.1%.
- The scored forward is **cold, single, un-warmed** (`benchmarkPrefillWarmupRuns
  = 0`) and carries a **5.2% cold-page penalty** (cold 584.09 ms vs warm median
  555.15 ms) — 30.5 ms absolute. This is fern's #19.
- `fp_gather_qmm_rhs_expert_nax` is JIT-only; `tile_matmad_nax` silently compiles
  to an empty function for any geometry with odd `TN > 1`; and falling off the
  `bm == 64 && wm == 4` accept gate (`quantized.cpp:1668-1671`) silently
  dispatches the non-expert kernel. Three separate silent-failure modes in one
  kernel — any geometry change there needs an explicit positive check that MMA
  actually ran.

---

## Round-1 and round-2 dispositions

| PR | student | action | outcome |
| --- | --- | --- | --- |
| #4 | frieren | merged | bit-exact, −333 surface bytes, −3.4% per-step host CPU, M4-invisible |
| #5 | fern | merged | widened heads-per-threadgroup so one threadgroup owns a whole GQA KV group; also a clean negative on sliding-attention KV re-reads + `senpai/tools/sliding-attn-probe`. **Now a suspect** — reduces threadgroup count; #13 part 1 reads its M5 value |
| #6 | tanjiro | closed | certified LM-head screen family retired; produced the 44,971 B reclaim recipe |
| #7 | nezuko | merged, submitted as `27b9c7c6` | +7.32% M4, ≈0.0% M5. Bit-exact. The transfer-failure exemplar |
| #8 | frieren | merged | `LagunaLmHeadPrune.swift` 97,911 → 31,200 B = −66,711 B; bit-exact; 454/454 tests; headroom 345 B → ≈67,056 B |
| #9 | nezuko | merged | dispatch-fusion family closed; split-mode measurement bias found; occupancy diagnosis; off-surface notes only |
| #10 | tanjiro | merged | occupancy-quantisation model + `senpai/tools/full-attn-probe`; reverted his own M4-winning w1 kernel on a 40-core projection; scored surface byte-identical |

---

## Potential next research directions

1. **Rebase the campaign onto the true-best tree.** The frontier is
   `4bf4f794` (rejected, ns 2.5331), **0.71% ahead of us**, and nine trees beat
   the promoted `8415f63c` we are sitting on. This is the cheapest available gain
   and it is #12's deliverable.
2. **Mine the 769 rejected submissions** for improvements that lost only the
   promotion race — the largest reservoir of already-M5-validated work.
3. ~~**Resubmission as variance harvesting.**~~ **Quantified and rejected.** The
   draw factor `officialScore / ns` has median 0.98857 and max 1.00896 over 909
   records; `8415f63c` drew 1.0090, essentially the maximum ever seen. Expected
   submissions to promote: ~130 even at the best tree anyone has built (2.5331),
   ~28 at 2.5400, ~12 at 2.5450. Resubmission is not a strategy; it is only a
   measurement channel. **Target ns >= 2.545.** See
   `research/FIELD_MECHANISM_MAP.md`.
4. **If host-bound is confirmed (#14):** attack the serial Swift/MLX graph
   construction and argument-encoding path hard — per-step allocation, ARC
   traffic, redundant views/casts, env-flag evaluation on the hot path
   (~12,331 B cluster), `TRACE_FUSION` (~3,758 B).
5. **If GPU-bound is confirmed (#13):** sliding-attention occupancy is the single
   largest pool; then a sub-1024-thread full-attention variant, which tanjiro
   identifies as the only remaining occupancy lever there.
6. **Vendor `_nax` surface for prefill.** `steel_gemm_*_nax`, `steel_attention_nax`,
   `fp_quantized_nax`, `quantized_nax` are editable and are what the M5 actually
   selects. Untouched so far, and prefill is where the whole field is bunched.
   Now known to be **measurable only through official submissions** (see finding
   1), and now known to have three silent-failure modes, so any arm here needs a
   positive "MMA actually executed" assertion. 422 field mentions, best 2.5284.
7. **Unassigned decode item:** `lmhead_exact_inline_mask_block_v1` latency tail,
   76.6 µs/step.
8. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
   (−54,251 B, ~33–65 µs/step on M4) — collides with #12/#14, sequence after.
9. **Reconcile the stale band prose** in `senpai/program.md` so no future student
   throttles a win to fit a band that is not enforced.
10. **`attn_proj_qkvo` is 51.8% of forward FLOP and runs at 23.5% of the MMA
    ceiling** — the largest single FLOP block in the seed forward, larger than
    routed experts, and nobody has looked at it. On M5 it is
    `steel_gemm_fused_nax` (bm128/bn128/bk512 family). Requires official
    measurement.
11. **Attack the seed forward as a class.** It is our laggard (1.972× vs 2.830×),
    its elasticity is 0.362 and *rising* as the step improves, and the whole field
    is bunched within 0.3% on it. #19 tests whether the wall is first-touch cost.
    If it is not, the wall is `attn_proj_qkvo` and the routed gather-GEMM, both of
    which need the `_nax` surface.
12. **Routing-aware work elision using the measured histogram.** The shipped tile
    is tuned for uniform routing that does not occur (CV 1.80, 20.3% empty
    experts, busiest 32 experts holding 54.7% of assignments). Row-tile widening
    and sub-16 SM are both closed, but a *two-regime* split — short tail and long
    tail dispatched differently — has not been costed. Needs a fresh mechanism
    proposal, not a knob.
