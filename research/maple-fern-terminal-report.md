# maple-fern terminal report — PR #11, prefill 512-token forward roofline

```text
SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}
```

- Student / PR: maple-fern / #11 (`maple-fern/prefill-512-forward-roofline`)
- Hypothesis and target cost: (Part 1) Is the 512-token forward near its roofline, and what is the largest named gap? (Part 2) Routed-MoE prefill has a tiny-M gather-GEMM problem: with 16 mean rows per expert against 32-64-row Metal tiles, most of each tile is wasted, so a tile height matched to the measured histogram should recover a large share of the routed path.
- Decision: **dead hypothesis for Part 2, profile delivered for Part 1** — and a third result I did not expect, that this host cannot measure prefill mechanisms at all.
- `BASE_SHA` / candidate commit: `0d980bb03040182b4595cab070fd249944ea3621` / `47ef557034292b968287c61eb623c81e1996d0ff`
- Submitted candidate files: **none.** The scored surface is byte-identical to `BASE_SHA` (`git diff BASE_SHA -- Sources/ Vendor/` is empty). Byte-neutral as instructed.
- Supporting test or documentation files: `research/maple-fern-prefill-roofline.md` (full profile), `research/host_flop_ceiling.swift`, `research/prefill_budget.py`, `research/prefill_probe.py`, `research/route_histogram.py`, `research/prefill-512-route-histogram.txt`

### Evidence

- Host, memory profile, toolchain, and thermal policy: AWS Apple **M4 Pro**, 20-core GPU, 48 GiB, low-memory startup profile, macOS 26.5.2, `arch=applegpu_g16s` gen 16. All GPU work through `run_training`; harness 40C thermal gate respected.
- Exact baseline and candidate commands:
  - `bash research/run_local_benchmark.sh --local-iterate` at `BASE_SHA` (baseline pair).
  - `python3 research/prefill_probe.py --reps 6 --decode-steps 12 --profile --profile-top 34` with `DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1` (per-dispatch profile; local-only `device.cpp/.h` hooks, reverted, not on this branch).
  - `DARKBLOOM_ROUTE_HISTOGRAM=1 python3 research/prefill_probe.py --reps 2 --decode-steps 0` (histogram; diagnostic committed as `ceff917` then reverted).
  - `xcrun swiftc -O research/host_flop_ceiling.swift && ./flopceil` (host ceilings).
  - `python3 research/prefill_budget.py --measured-ms 585.6 --tflops 28.76`; `python3 research/route_histogram.py /tmp/routehist.err`.
- Tests and risk-based checks run: no timing candidate exists to test, so no pair was run. Probe self-validation: per-request dispatch counts printed and identical across reps (`[1222]x5`); greedy token `5991` identical across every rep and every configuration; probe cold forward reproduces the harness prefill axis to **0.26%**.
- Correctness and serial-protocol verdict: **unchanged / not at risk.** Scored surface byte-identical to `BASE_SHA`; baseline pair reported `max_abs_diff=0`, `passed_correctness=true`. No mechanism, no reordered accumulation, no cache keyed on input tokens.
- Divergent tokens or failure category, if any: none.
- Peak RAM: 20.71 GB (probe), consistent across runs.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.013629 | 0.013629 (surface identical) | 1.000x |
| prefill seconds/token | 0.001143788 | 0.001143788 (surface identical) | 1.000x |
| same-host paired estimate | — | not applicable (no candidate) | — |

Decomposition of that same M4 baseline, which is the measurement that matters here:
seed forward `S = 585.6 ms`, `S/128 = 4.575 ms`, steady step `T = 9.054 ms`
(independently measured 8.769 ms, **3.2%** apart), `sigma = 33.6%`.

### Conclusion

**What happened and why.** Part 1 is complete and produced a result that supersedes
its own Part 2. Three findings:

1. **This M4 host cannot measure prefill mechanisms.** `is_nax_available()` is false
   here (`arch=applegpu_g16s`, gen 16 < the required 17; the macOS 26.2 gate passes),
   so **94.2%** of prefill GPU time runs in non-NAX fallback Metal functions the
   official M5 never executes — `nvfp4_gather_qmm_rhs_nt` (48.5%),
   `steel_gemm_fused_nt_bm64_bn64_bk16` (33.4%), split-K (6.0%),
   `steel_attention_bfloat16_bq32_bk16` (5.1%), `nvfp4_qmm_t` (1.2%). Only 5.8% is
   host-independent. **Steady decode is 100% host-independent** (`laguna_*` kernels,
   no NAX or `#available` gate anywhere on it). That asymmetry is a mechanistic
   explanation for the campaign's track record — and it is a stronger failure mode
   than "threadgroup re-tiling does not transfer", because these are *different
   kernels*, not the same kernel at different occupancy.
2. **The seed forward is worth 0.362 of score, not 0.25 and not 0.52.** Since
   `D = S/128 + T` and `P = S/512` charge the same forward,
   `d ln score/d ln S = -(0.25 + 0.75*sigma)`. From the official M5 numbers,
   `sigma = 14.98%` => **0.362** for the forward and **0.638** for the steady step.
   The derivation reproduces the published M5 score to five decimals (2.49724) and
   both published speedups to six. This resolves a contradiction in the assignment:
   the PR body's 0.52 fed `sigma = 0.36`, which is the **M4** value (I measure
   33.57%); the later comment's 0.25 drops the seed charge. So the PR body's premise
   that the forward outweighs the steady step is **false on M5** — the step is worth
   **1.76x** more per percent. It is a near tie on M4 (0.502 vs 0.498), which is
   where 0.36/0.52 came from.
3. **Routing at 512 tokens is heavily skewed, and Part 2's mechanism is the wrong
   lever.** Measured (host-independent, since routing depends on model and prompt,
   not GPU): mean 16 rows/expert but **stdev 28.8** (CV 1.80), median **7**, p90 39,
   p99 142, max 505, and **20.3% of experts receive zero rows**. The repo's tiling
   notes state their figures were "Simulated over uniform routing"
   (`quantized.cpp:1405-1415`) — that assumption is empirically wrong. Consequences:
   at the shipped `SM=16`, **31.3%** of issued MMA rows are padding (SM=8 would be
   16.5%); but **raising the row tile buys nothing** — BM 64->128 cuts chunks/layer
   only 220.5 -> 207.9 (**-5.7%**), because the median expert holds 7 rows so ~80% of
   experts need exactly one chunk at any BM. **The lever is smaller SM, not bigger
   BM.** Per the stop rule, the named MoE-tiling mechanism is killed by the histogram.

**Evidence for or against the mechanism.** Against, on three independent grounds:
the histogram shows bigger tiles are near-useless (-5.7% chunks); the target kernel
is NAX-only and therefore unmeasurable here; and the whole prefill axis is worth
0.362 not 0.52. Also killed with numbers: `DARKBLOOM_ATTN_QHOIST` (<=0.33% of score
*and* NAX-only dead code on M4); caching the 76 `arangeuint32` dispatches (their
134 ms is a command-buffer overlap artifact — `sum - arange` matches GPU-busy union
to 0.19% — so ~0 ms real); and prefill command-buffer/host-CPU reduction (GPU-busy
union is **99.4%** of wall, no gap to reclaim).

Roofline for the record, against **measured** ceilings (28.76 TFLOP/s bf16 MMA,
260.2 GB/s; my first pass wrongly used the 7.07 TFLOP/s *scalar* ceiling): the
forward is 2830 GFLOP over 26.7 GB = 106.1 FLOP/byte against a machine balance of
110.5, i.e. **exactly balanced**, with a ~103 ms floor on both axes vs 585.6 ms
measured (16.8% of MMA ceiling). Nothing is near the 80%-of-ceiling stop threshold,
so the nominal headroom is large — it is simply not addressable from this host.

**Uncertainty / M5 transfer risk.** (a) Every per-dispatch share above is M4-only for
the 94.2%; treat it as a map of *which regime* dominates, not as M5 timings. (b) The
M5 expert kernel stages a full `BN x BK` weight tile with all 128 threads while only
`ceil(rows/16)` of 4 simdgroups do MMA, so variant 5 has already *moved* padding cost
from MMA into staging; if it is staging-bound on M5, SM=8 recovers less than 15pp. I
cannot distinguish those regimes from here and did not guess. (c) `sigma` rises as the
steady step improves (10.9% baseline -> 15.0% candidate), so the forward becomes more
valuable over time; recompute rather than pinning 0.362. (d) `--local-submit` uses
1023 steps, so `sigma` there is ~5.9% and a forward win looks nearly invisible —
use `--local-iterate` for forward work.

**Smallest useful next action.** Put "do not run prefill kernel experiments on an M4
host, 94.2% of prefill GPU time is non-NAX fallback" into `AGENTS.md`, and re-weight
the forward at 0.362. If an M5 slot opens, the two pre-registered prefill mechanisms
are, in order: **SM 16 -> 8** in the expert-aligned gather-GEMM (bucket A, reduces
issued MMA work; needs a new variant in the `quantized.cpp` table, the Swift
accept-list `["","4","5"]`, and the `bm==64 && wm==4` expert gate), and a
**routing-aware grid** that skips the 20.3% empty expert columns (bucket A, removes
launches and staging). Otherwise the highest-value work is decode (elasticity 0.638,
and M4 runs those exact kernels). The one number I could not get is the non-GPU-busy
fraction of a steady decode step: split-mode instrumentation inflates it (split wall
10.408 ms and union busy 8.997 ms both exceed the 8.769 ms non-split wall), so it
needs a non-split profile — `research/decode_probe.py` territory, overlapping
nezuko's arm.

**Recommendation: close.** No candidate to merge; the profile is the deliverable, and
it redirects prefill kernel work off this host entirely and re-prices the axis. I did
not dispatch anything official, per the standing instruction.
