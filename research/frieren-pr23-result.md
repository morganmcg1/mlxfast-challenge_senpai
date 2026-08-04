SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- Student / PR: maple-frieren / #23 (`maple-2026-08-04e-head-latency`, r1)
- Hypothesis and target cost: the ~0.29–0.32 ms exposed decode-step head region
  splits into host work, driver launch latency, and tail idle; if the host part
  is large it is attackable by committing the first command buffer earlier.
- Decision: **dead hypothesis, on measurement, for both parts.** Part 1 — the
  head region is confirmed at 0.301 ms but only 35.7 µs of it is editable, which
  fires the assignment's stop rule and the advisor's explicit gate. Part 2 — the
  sub-layer boundary family is null (`ab`) to strongly negative (`abc`, +1.93 %),
  and it refuted my own interim mechanism claim.
- `BASE_SHA` / candidate commit: `969fea003eb6964f702c1f7c3e0234d022406a9f` /
  no candidate — `Sources/` and `Vendor/` are byte-identical to the assignment
  base `7017ba2`, and **no official submission was spent** (3 still unspent).
- Submitted candidate files: none.
- Supporting test or documentation files (all under `research/`, outside
  `editablePaths`): `frieren-pr23-head-region.md` (full memo),
  `frieren_head_region.py` (trace analyser), `frieren_dose_stats.py`
  (drift-cancelled contrasts), and the screen drivers
  `frieren_cb_count_arms.sh`, `frieren_cb_mb_sweep.sh`,
  `frieren_cb_first_commit.sh`, `frieren_cbprof_ranked.sh`,
  `frieren_sublayer_rungs.sh`, `frieren_rung_dose.sh`.
  Research-only instrumentation (`FRIEREN_CBPROF` in `device.cpp`,
  `FrierenStepProf` in `LagunaRuntimeModel.swift`; commits `0816a72`, `9529e3a`)
  and the sub-layer rung implementation (`9a00e8f`, `e722f65`, `a309168`) exist in
  this branch's history for reuse but have been **reverted out of the branch head**,
  so nothing instrumented or experimental is on the submitted surface.

### Evidence

- Host, memory profile, toolchain, thermal policy: AWS M4 Pro, 48 GiB,
  low-memory startup profile by default; the command-buffer arms ran under
  `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` for ranked parity. Direct worker
  probe, no thermal gate needed (no `--local-iterate` pair in the measurement
  set beyond the recorded baseline).
- Exact baseline and candidate commands: in the memo's Reproduction section.
- Tests and risk-based checks run: none required — the submitted surface is
  unchanged. The recorded same-host baseline (`score.local-iterate.baseline.json`,
  commit `7017ba2`) reported `passed_correctness = true`, `max_abs_diff = 0`,
  decode 0.0135023349609375 s/tok, prefill 0.001124003580078125 s/tok, i.e.
  `S = 575.5 ms`, `T = 9.006 ms`.
- Correctness and serial-protocol verdict: unchanged behaviour; both probes are
  read-only timestamp recorders behind default-off env gates. The measured
  invocation computes logits and KV rows only for the single supplied token,
  advances KV position by exactly one, and leaves no pending future token,
  logits, deferred cache row, or cross-request state. No drafting, lookahead,
  prompt-lookup, or multi-row evaluation of an unsupplied token anywhere.
- Peak RAM: the ranked/full startup profile runs on a 48 GiB host (useful
  campaign capability), at a ~3.4 % absolute step-time penalty from its memory
  settings, so only within-profile comparisons are valid.

### Part 1 — the three requested numbers (M4 Pro, **ranked parity**, medians over 278 steady steps)

All three numbers below are measured under `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`
so the command-buffer thresholds are the shipped 200 Mi-elements / 400 ops, not
the low-memory 128/64. 16 595 command buffers traced, 0 clock violations.

| # | Region | µs | se | spread |
| --- | --- | ---: | ---: | --- |
| 1 | step entry → first command-buffer commit (**editable host work**) | **35.7** | 0.8 | — |
| 2 | first commit → first GPU kernel start (driver + firmware) | **67.1** | 0.5 | p10 61.9 / p90 83.4 |
| 3 | tail GPU idle after the model call returns | **0.0** | — | **0.0 at p90** |

Region 3 is *exactly* zero at both the median and p90: when the scored call
returns, the GPU still has ~3.8 ms of queued work. There is no drain to remove.

Plus two terms the same trace exposed: **122.1 µs** from previous-step GPU end to
next-step entry (trusted harness: IPC + the blocking `argMax().item()` in
`LagunaRuntimeBenchmark.swift:891`) and **75.9 µs** of interior GPU idle spread
over 47 command-buffer boundaries. Frame: step 8834.4 µs, GPU busy 8533.1 µs,
**total GPU idle 300.8 µs**, GPU busy fraction 96.59 %, **48 command buffers per
step**, 4 dispatches in the first command buffer, encoding-thread CPU 2.51 ms/step.

The 300.8 µs total idle lands inside the advisor's 0.29–0.32 ms exposed-term
estimate, so the target the assignment was written against is confirmed. What the
decomposition changes is *who owns it*: 122 µs trusted harness, 67 µs
driver/firmware, 76 µs GPU-side boundary cost, 36 µs editable host work, 0 µs drain.

In-loop idle — GPU starvation at any point after the first commit — is **0.0 µs at
both the median and p90**. The encoding thread runs 2.51 ms of CPU per 8.83 ms
step, ~3.5× ahead of the GPU, so after the first commit nothing the host does is
on the critical path.

### Stop rule

Both stop conditions hold, and more decisively at ranked parity than they would
have at the low-memory setting. Driver launch latency (67.1 µs) dominates the
editable host portion (35.7 µs), and 35.7 µs is a third of the 0.1 ms threshold.
Perfect elimination of *every* editable head microsecond is 0.40 % of this host's
step, 0.82 % of the 4.353 ms ranked step, and **0.52 % of score as an absolute
ceiling** — under the 0.61 % bar before any noise or implementation loss.

Measured rather than assumed: forcing the cut immediately after the fused
embedding+RoPE dispatch (`max_mb=195`, a proxy for candidate 1 that is not
itself shippable) moved first-commit from 35.7 → 25.6 µs and the step by
−0.30 %, i.e. ≈0.15 % of score. That is the realistic size of candidate 1, a
third of the bar.

### The ratio argument, made explicit and checked

`predicted M5 step = GPU_busy / r + serial_idle`. Solving
`4353 = 8512.3 / r + 269.9` gives `r = 2.085`, which is exactly the achievable-
bandwidth ratio if the M4 Pro sustains ~240 GB/s of 273 nominal and the M5 Max
~500 GB/s of 614 — inside your 485–530 band. So the measured split reproduces
the ranked step time with no free parameters beyond that ratio, and:

- a serial microsecond removed locally is one microsecond removed on M5;
- as a fraction it is worth `8834.4 / 4353 = 2.03×` more there;
- the whole ~270–300 µs serial term is ~3.1–3.4 % of the local step and
  **6.2–6.9 % of the ranked step** — your point, confirmed rather than assumed;
- but only 35.7 of those 300.8 µs are editable host work.

### Scaling-law decomposition (ranked-parity figures)

| Term | µs | Scales with | M5 |
| --- | ---: | --- | --- |
| Swift pre-encode bookkeeping | ~7 | CPU clock/IPC | ~0.85× |
| MLX graph walk + encoder setup, head's 4 ops | ~24 | dispatch count × CPU clock | ~0.85× |
| `commit` (IOKit submit) | ~5 | fixed per-command-buffer OS cost | ~1.0× |
| kernel-driver ingest + submission processing | ~37 | fixed per-CB driver cost | ~1.0× |
| firmware queue → GPU launch | ~30 | fixed firmware/hardware latency | ~1.0× |
| trusted IPC + JSON | ~90 | CPU clock, pipe syscalls | ~0.85× |
| `argMax().item()` readback | ~32 | fixed GPU→CPU sync latency | ~1.0× |
| inter-command-buffer GPU cost | 75.9 | **command-buffer count** × ~1.6 µs | scales with CB count |
| post-return drain | 0.0 | — | 0.0 |

Only rows 1–2 and 6 scale with CPU clock; only row 8 scales with command-buffer
structure; the rest are fixed OS, driver, firmware and sync latencies that
neither a faster CPU nor a faster GPU removes. **A term that scales with dispatch
count is ~24 µs of a 301 µs serial budget** — which is why attacking dispatch
count could not have worked.

### Reconciliation with #9's exact zero (δ ≤ 1.05 µs/dispatch)

Consistent, and now explained. The worker's encoding thread uses 2.51 ms of CPU
per 8.83 ms step — ~3.5× ahead of the GPU — so after the first commit every
dispatch's encode cost is **hidden**, not exposed. The direct measurement is
that in-loop GPU idle is 0.0 µs at the median *and* at p90. My decomposition
attributes ~0 exposed cost per dispatch, well inside your bound. The only
unhidden encode is the head's 4 ops. And MLX cuts command buffers on
**referenced input volume**, not op count (`device.cpp:564`, `:393-401`), so
fusing dispatches changes neither command-buffer count nor the boundary cost.
#9's zero is not evidence that per-dispatch cost is small in principle; it is
evidence that on this path all of it except the head is already hidden behind a
bandwidth-bound GPU.

There is a second, stronger reason, and it is a campaign-level caveat: the byte
volume of one decode step is ≈2.2–2.9 GB, which at 273 GB/s nominal is a
7.9–10.6 ms floor against a measured 8.51 ms GPU-busy region. **This host runs
decode at ~90–100 % of its memory-bandwidth wall.** A launch-overhead change
*cannot* show a win here. That is not evidence it is worthless on the ranked M5,
which has ~2× the achievable bandwidth for the same bytes. I would re-test the
#9 patches on M5 before treating that family as closed.

### Command buffers per ranked decode step

**Measured: 48/step** (mean 44.3 over 16 595 traced buffers at 200/400). My
pre-registered prediction was "~50, range 40–60", so this is a confirmed
prediction rather than a post-hoc reading. It supersedes my earlier "~45/step",
which was a low-memory artifact I had not yet traced.

Why the prediction was needed at all: the low-memory profile force-sets
128 Mi-elements / 64 ops with `setenv(..., overwrite=1)`
(`RuntimeStartupMemoryPolicy.swift:174-183`) — so an external `MLX_MAX_*` is
silently ignored on any <64 GiB host, which invalidates the obvious env screen
(I burned one 6-arm run finding this out; it became a 6-repeat A/A floor of
sd 0.20 %). The ranked profile sets 200/400 with `overwrite=0`
(`LagunaRuntimeWeights.swift:380-390`). At the 128 threshold I measure 78
buffers/step; at 200 it is 48. The op cap never binds (406 dispatches vs a 400
cap → 2 buffers), which is why the cut is volume-driven.

Correction worth recording: the threshold unit is Mi-**elements**, not MB, and
the bf16 embedding table is exactly **196** — so the first `set_input_array` of a
decode step forces a cut iff `max_mb ≤ 195`. At the ranked cap of 200 it does
*not* cut, which is why the ranked first command buffer holds **4** dispatches
and commits at 35.7 µs while the low-memory one holds 1 and commits at 26.0 µs.
This is also the lever used to price candidate 1 above.

### Part 2 candidate (a) — refuted with source and timing evidence

The advisor's candidate (a) was "the lazy graph is rebuilt every token; compile
it and save ≈406 × 0.7 µs = 0.28 ms". The premise is true and the conclusion is
false.

The premise, confirmed: nothing in `Sources/` references `CompiledDecode`,
`CompilableKVCache`, `CompilableRotatingKVCache`, or `DynamicSlice`.
`GenerationBatch` and `TokenIterator` are unreferenced — the scored driver calls
the model directly (`LagunaRuntimeWorker.swift:208`,
`LagunaRuntimeBenchmark.swift:867`, `:890`). The two casts at
`RoPEApplication.swift:31,34` are always nil because the runtime builds
`KVCacheSimple` + `RotatingKVCache(maxSize: 512, keep: 0)`
(`LagunaRuntimeModel.swift:10888-10893`), and `decodeRoPEAtlasPosition` explicitly
excludes compilable subclasses at `:10627-10629`. So
`MLXHardwareInfo.isCompiledDecodeSupported` being true by default is inert on the
scored path: it reaches only the three small call sites the advisor found
(`:5175`, `:5197`, `:6058`).

The conclusion fails on the measurement. The encoding thread already spends
**2.51 ms** of CPU per step on those ~406 dispatches — 6.2 µs/op, ~9× the 0.7 µs
estimate — and **0.0 µs of it is exposed** at the median or p90, because it runs
3.5× ahead of a bandwidth-bound GPU. Only the 35.7 µs before the first commit is
on the critical path. Removing host graph-construction cost therefore predicts
**≈0**, and the 406 × 0.7 µs ≈ 0.28 ms coincidence with the 0.30 ms idle term is
numerology: the two quantities have no causal link. This is the same
"already hidden" structure as #9's exact zero, measured directly this time.

I also closed the two side questions the advisor raised:

- **Inert-extra-bindings scaling test** — unnecessary. Its answer is already
  bounded by #14's absorbed 2.0 ms in-loop CPU spin combined with the measured
  0.0 µs in-loop idle: the loop has ≥2 ms of slack, so binding-count cost cannot
  surface. (This is also why `DARKBLOOM_SHARED_FIRST_DOWN`'s +0.10 ms regression
  must be an encoder-wide memory-barrier effect on the *GPU* side, as the advisor
  suspected, not a host cost.)
- **`DARKBLOOM_ROPE_ATLAS_VIEWS` "two probes overlap the front"** — no longer
  applies to this base. The current code fuses the embedding gather and both RoPE
  rows into a **single** dispatch (`:10665-10674`, kernel at `:10440-10494`), and
  the trace confirms exactly one MLX dispatch between step entry and layer 0.

### Adjacent finding: the command-buffer volume threshold

Screened under `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` (ranked parity),
`ops=400`, 2000 steps/arm:

| max_mb | ms/step | n |
| ---: | ---: | ---: |
| 8 | 9.0297 | 2 |
| 16 | 9.0402 | 2 |
| 25 | 9.0196 | 2 |
| **50** | **8.9579 ± 0.0028** | 5 |
| 100 | 9.0442 | 2 |
| 200 (ranked) | 9.0893 ± 0.0318 | 4 |
| 4096 | 9.4137 ± 0.0041 | 3 |

Non-monotone with a minimum at 50 (also MLX's stock M5 Max default, which this
repo raised to 200). `t ≈ 4.1` for 50 vs 200 against a 0.20 % A/A floor.

**Self-correction, retracting my earlier "cap-200 bimodality".** I previously
flagged the four cap-200 arms as bimodal (9.0341/9.0344 vs 9.1423/9.1465, nothing
between) and called it unexplained. It is explained, and it is not bimodality: it
is **monotone arm-position drift within a single worker process**. Repeated
*identical* control arms at script positions 1, 5 and 7 read 9.0356 / 9.1076 /
9.1136 ms — a ~0.8 % upward drift, larger than any effect I am chasing. That is
why an unbalanced multi-arm screen reads null on a real effect (`ab` came out
−0.26 % ± 0.28 %) while an adjacent-position traced pair of the same contrast
reads −0.61 %. Every conclusion below therefore comes from either
position-adjacent pairs or a position-balanced design, and I now treat any
unbalanced arm ordering in this campaign as untrustworthy at the sub-1 % level.
(Tracing overhead itself is negligible: traced control 9.1136 vs untraced control
at the same position 9.1076.)

**But this must not ship as a cap change.** Three isolated ranked receipts in
`research/nezuko-normalised-leaderboard.md` §5.2 change only this cap against a
cap-200 frontier control: 400 → `T +0.056 % / S +0.130 %`; 240 →
`T −0.069 % / S +2.783 %`; 160 → `T −0.838 % / S +1.464 %`. Scoring the 160
receipt end to end gives `1.00496^0.75 × 0.98557^0.25 = 1.0001` — the cap trades
decode against prefill and nets zero. It is read once into a `Device` member at
first device construction and `device.h`/`device.cpp` are outside
`editablePaths`, so it cannot be made phase-dependent from the submission
surface.

The reachable form is decode-only: `decodeFireMask` /
`DARKBLOOM_DECODE_ASYNC_STAGE` already fires `asyncEval` after selected layers
under an `isSingleTokenDecode` guard (`LagunaRuntimeModel.swift:10550-10562`,
`:10781`), and prefill has a separate ladder, so a decode-only boundary change
leaves `S` untouched by construction. That axis is tuned at *layer* granularity
(default `at:0,1,7,15,23,31,39`; notes/52), and `decodeFireMask` **cannot express
a non-layer-boundary fire point** — bits 40–63 parse but are inert. So the
sub-layer question needed new code, not a new mask value.

Layer-granularity rungs capture **none** of the cap gap, measured directly:
cap 200 default 9.1506, cap 200 `ladder1` 9.1396, cap 200 control repeat 9.0721,
cap 50 default 8.9594, cap 50 `ladder1` 8.9697. Adding whole-layer fires on top of
a volume cut does nothing because the volume cut already lands ~1.2 boundaries per
layer. The remaining headroom is strictly *inside* the layer.

### Part 2 — the sub-layer boundary test, and my own refuted mechanism

MLX's cap has exactly one consumer: `max_mb_per_buffer_` is read only at
`device.cpp:564` inside `needs_commit()` —
`(buffer_ops_ > max_ops) || ((buffer_sizes_ >> 20) > max_mb)` — with
`buffer_sizes_ += a.data_size()` at `:398` charging elements per *distinct input
buffer*. So the only thing the cap does is decide where command buffers end.

I therefore implemented three sub-layer `asyncEval` fire points behind
`DARKBLOOM_DECODE_SUBLAYER_ASYNC` (default off, guarded by the existing
`isSingleTokenDecode` shape check, so prefill and `S` are untouched by
construction): **a** after the attention output, **b** after the h/normalized
residual chain, **c** after the MoE router top-k. They raise command buffers per
step from 48 to 90 (`ab`) and 129 (`abc`).

**Interim claim I made and am now retracting.** From two traced position-adjacent
arms I fitted a per-boundary law:

| arm | cbs/step | GPU busy µs | GPU idle µs | step µs |
| --- | ---: | ---: | ---: | ---: |
| control | 48 | 8839.8 | 288.1 | 9126.2 |
| `ab` | 90 | 8782.1 | 288.9 | 9070.5 |
| `max_mb=50` (not shippable) | 140 | 8716.3 | 269.0 | 8678.6 |

`ab` gave −57.7 µs of GPU busy over +42 boundaries = −1.37 µs/boundary; cap 50
gave −123.5 µs over +92 = −1.35 µs/boundary. Two interventions sharing nothing
but boundary placement, agreeing to 1.5 %, with GPU *idle* flat across the rung
contrast — which read as the GPU genuinely executing less work. I predicted `abc`
at ~115 cbs would give −1.02 % of step, i.e. +0.65 % of score, just over the bar.

**The dose-response test refuted it.** Position-balanced design, 2000 steps/arm,
ranked parity, positions 1–9 = `off, ab, abc, abc, off, ab, ab, abc, off` so each
level's positions sum to 15 and a linear drift term cancels exactly:

| arm | ms/step (n=3) | se | vs `off` | t |
| --- | ---: | ---: | ---: | ---: |
| `off` | 9.0677 | 0.0361 | — | — |
| `ab` | 9.0531 | 0.0140 | **−0.161 %** ± 0.427 % | −0.38 |
| `abc` | 9.2423 | 0.0047 | **+1.925 %** ± 0.402 % | **+4.79** |

And the traced `abc` arm kills the per-boundary law outright: **129 cbs/step,
GPU busy 8923.4 µs** (from busy fraction 97.10 % of a 9189.9 µs step), GPU idle
265.3 µs. Across 48 → 90 → 129 boundaries, GPU busy goes 8839.8 → 8782.1 →
8923.4 µs. **Non-monotone.** A two-point linear fit with no position-matched
error bars on the busy term was not evidence, and I should not have presented it
as "the strongest single piece of evidence in this arm".

**Why the cap and `asyncEval` are not the same intervention** — the thing I got
wrong. The cap changes *only* the submission boundary: identical graph, identical
ops, identical kernel fusion, identical buffer donation. `asyncEval` changes the
**graph partition**: the forced arrays must be materialised, which blocks fusion
and buffer donation across the fire point and adds real byte traffic. That is why
GPU busy *rises* with rung count. Sub-layer `asyncEval` can therefore never be a
clean proxy for the cap, and since `device.h`/`device.cpp` are outside
`editablePaths`, **the cap's win is unreachable from the submission surface**. I
consider that the durable finding of Part 2.

Rung `c` is the worst precisely because of this: forcing the router's `inds` and
`weights` immediately before the expert gather breaks the top-k → gather fusion
and materialises the routing tensors, and it cuts a boundary on nearly every
layer (120 fires → 129 cbs, so `c` alone adds ~39 boundaries against `ab`'s 42
from 80 fires). It also matches the advisor's `DARKBLOOM_SHARED_FIRST_DOWN`
observation that Metal memory barriers are encoder-wide, so an extra encoder
boundary mid-MoE is expensive.

**Honest note on the residual.** The three `off` arms are not exchangeable: the
position-1 arm read 8.9961 against 9.1119 and 9.0951 at positions 5 and 9, so the
drift is a *saturating* warm-up rather than the linear trend my balancing assumed.
Excluding position 1 post hoc gives `ab` −0.553 % ± 0.18 % (t = −3.1) and `abc`
+1.524 %. So `ab` may be a genuine small win. Even taken at face value it does
not clear the bar: −0.553 % local pure-step × the campaign's 1.28 elasticity =
−0.708 % on M5 ⇒ decode speedup 1.00713 ⇒ `1.00713^0.75` = **+0.53 % of score**,
under the 0.61 % acceptance bar, and the balanced-as-designed reading is +0.15 %.
Since the decision is the same either way, I did not spend more compute
sharpening it.

**Consequence for the `issued` vs `unique` byte rule.** I no longer claim a
GPU-busy re-read term that a unique-byte roofline would miss, so I withdraw my
suggestion that #21's launch-ramp term might not need its 30 % overlap credit —
that suggestion rested on the refuted slope. Stating it explicitly per the new
team rule: **I have no byte-numerator claim of either kind surviving from this
arm.** The one thing I can still say is that the cap sweep's win is real
(8.9579 ± 0.0028 at cap 50, n=5) and is *not* explained by boundary count, since
matching the boundary count with `asyncEval` reproduces none of it.

### Answer to your explicit stop gate (comment 5181156130)

> Measure the per-step graph-construction cost on your host first, as briefed —
> if it is not ~0.28 ms, say so and we stop.

**It is not ~0.28 ms, and it misses in both directions at once. We stop.**

- Host graph construction + encoding **costs 2.51 ms per step** — 9× your 0.28 ms
  estimate, not 1×. The estimate `406 × 0.7 µs` under-priced the true per-op cost
  by that factor (measured ~6.2 µs/op).
- The part of it that is **exposed is 35.7 µs** — 13× *smaller* than 0.28 ms.
  In-loop GPU idle is 0.0 µs at the median *and* at p90, because the encoding
  thread runs 3.5× ahead of a 96.6 %-busy GPU. Everything after the first commit
  is hidden.

So the coincidence between `406 × 0.7 µs ≈ 0.28 ms` and the measured ~0.30 ms of
exposed time was numerology: the two numbers are unrelated, and the true values of
the two quantities are 2.51 ms and 0.0357 ms. Compiling or otherwise eliminating
host graph construction predicts **≈0** on the scored path.

Your re-pricing of the 0.200 ms as "the most trustworthy line in the budget" is
right about *trustworthiness* — it is a difference of two measured quantities, and
my trace reproduces it (I measure 0.301 ms of total GPU idle at ranked parity,
inside your 0.29–0.32 ms). Where I have to disagree is **ownership**. Your model
was `wall ≈ head_latency + GPU_total`, i.e. treat the whole gap as head latency.
Resolving the gap in time shows it is not one term:

| component of the 301 µs | µs | owner |
| --- | ---: | --- |
| prev GPU end → next step entry | 122.1 | **trusted harness** (IPC + blocking `argMax().item()`, `LagunaRuntimeBenchmark.swift:891`) |
| step entry → first cb commit | 35.7 | **editable host work** |
| first commit → first GPU start | 67.1 | driver + firmware |
| interior gaps at cb boundaries | 75.9 | GPU-side, 47 boundaries |
| tail drain after call returns | 0.0 | — |

88 % of the trustworthy 0.30 ms is off the submission surface. The editable head
is 35.7 µs, whose complete elimination is 0.82 % of the ranked step and **0.52 %
of score** — under the 0.61 % bar before any implementation loss. Measured
proxy for the realistic version (force the cut after the fused embedding+RoPE
dispatch): first commit 35.7 → 25.6 µs, step −0.30 %, ≈**0.15 % of score**.

### Where your correction and my Part 2 agree

Your correction says: drop any sub-arm whose mechanism is "fewer dispatches or
fewer threadgroups", priced at **−0.228 ms per 40 dispatches removed** by nezuko's
`FUSE=1` arm, because the absorbing kernel slowed by +0.95 µs/call and broke
additivity by +8.23 µs/layer.

My Part 2 is the *same phenomenon with the sign flipped on the intervention*, and
it independently reproduces your conclusion. I went the other way — I *added*
graph partition points instead of removing them — and got the same kind of
penalty: `abc` adds 81 command buffers and costs **+1.93 %** of step, with GPU
busy rising 8839.8 → 8923.4 µs. Both results say the same thing: **on this decode
path, changing the graph partition costs real GPU work that dominates any
launch-accounting term, in whichever direction you move it.** Repartitioning is
priced negative both ways.

That also gives the clean reason why the `max_mb` cap sweep is not reachable: the
cap changes only *where a command buffer is submitted* (same graph, same fusion,
same buffer donation), whereas every lever on the submission surface —
`asyncEval`, fusion, dispatch merging — changes the *partition*. The cap's
8.9579 ms at 50 is real and none of it is recoverable through partition changes.

Two smaller consequences:

- I withdraw my own speculation (previous comment) that #21's launch-ramp term
  might not need its 30 % overlap credit. That rested on a per-boundary GPU-busy
  slope I have now refuted. Your `gpu_busy_sum == gpu_busy_union` to 6 ns settles
  it better than I could: there is no concurrency, so there is no overlap credit
  to argue about. The live question was never overlap, it was recoverability, and
  the answer is that it is not recoverable.
- Per the new issued-vs-unique rule: **no byte-numerator claim of either kind
  survives from this arm.** I had one and it is retracted.

### Conclusion

- What happened and why: the head region is real, confirmed at 0.301 ms, and
  almost entirely not mine — 35.7 µs of it is editable host work, against 122 µs
  of trusted harness, 67 µs of driver/firmware, 76 µs of GPU-side boundary cost,
  and 0 µs of drain. The assignment's stop rule fires on measurement, and so does
  your explicit gate. Part 2's sub-layer boundary family is null (`ab`, −0.16 % ±
  0.43 %) to strongly negative (`abc`, +1.93 %, t = 4.8).
- Evidence for/against: the bandwidth-scaling identity reproduces the ranked step
  time from the local split with one parameter (`r = 2.085`, exactly the
  achievable-bandwidth ratio); in-loop idle of 0.0 µs at p90 is a direct
  refutation of every "hidden host cost" story; and the `abc` arm's *rising* GPU
  busy is a direct refutation of my own per-boundary law.
- Two self-corrections recorded: (i) my "cap-200 bimodality" was arm-position
  warm-up drift (identical controls at positions 1/5/7 read 9.0356 / 9.1076 /
  9.1136), and it is saturating rather than linear, so linear balancing does not
  fully remove it; (ii) my −1.35 µs/boundary law was a two-point fit and is
  refuted.
- Uncertainty / M5 transfer risk: the local host runs decode at ~90–100 % of its
  bandwidth wall, so it *cannot* measure launch-overhead wins; local nulls on
  scheduling changes carry little information about M5, which has ~2× the
  achievable bandwidth for the same bytes. This is the one caveat I would keep
  alive: a materialisation penalty is charged at local bandwidth, so the `ab`
  rungs are penalised locally more than they would be on M5.
- Submitted candidate: **none.** `Sources/` and `Vendor/` are byte-identical to
  `7017ba2`; only `research/` files were added. **No official submission spent —
  3 remain.**
- Smallest useful next action: nothing in this family. If anyone wants the `ab`
  rungs swept on M5, the implementation is preserved in this branch's history at
  `9a00e8f` / `e722f65` / `a309168` and can be cherry-picked; I do not recommend
  spending a submission on it, since its best-case face value is +0.53 % of score
  against a 0.61 % bar.
- Recommendation: **close this arm.** Head region is a dead hypothesis on
  measurement; sub-layer repartitioning is a measured regression; the `max_mb`
  cap is unreachable from the submission surface. The one thing worth carrying
  forward is the general rule the two negative results now jointly support:
  **decode-step graph repartitioning is priced negative in both directions on
  this path**, so future arms should change bytes or arithmetic, not partition.
