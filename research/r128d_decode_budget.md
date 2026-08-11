# R128-D — Decode wall-vs-busy attribution

Student: maple-alphonse. Assignment `maple-r128-d-decode-wall-vs-busy-attribution`,
revision `r128-d-rev1`. PR #744.
Base `codex/mlxfast-maple-20260804-advisor` @ `67396bb6283cf2765a388b05ce4ac64174bb8ef6`.

**Nothing was fired.** No official submission, no `senpai/submit-official.sh`,
no `--official` run. No landing hunk: `git diff base..HEAD -- Sources/ Vendor/`
is empty (verified at the end of this document).

## Measurement host

All µs/step numbers produced by this assignment were measured on **this M4 Pro**
unless the sentence explicitly names another host (Rule 9).

| property | value |
| --- | --- |
| chip | Apple M4 Pro, 14 CPU cores |
| unified memory | 48 GiB (below 64 GiB ⇒ low-memory startup profile) |
| OS | macOS 26.5.2 (25F84) |
| Apple GPU generation | 16 ⇒ **never selects the `_nax` kernels the ranked M5 selects** |

Consequences that bound every claim below: this host does not execute the
ranked prefill kernel family, its steady decode step is roughly 1.7x the ranked
host's, and threadgroup-geometry-sensitive conclusions do not transfer. What
*does* transfer is the *structural* question this assignment asks — whether a
wall-minus-busy residual of the claimed size exists at all, and what it is made
of — because the residual is dominated by dispatch/encode/completion structure
rather than by kernel arithmetic.

Currencies used for pricing (never 0.00586 %/µs, which is unsourced):

| currency | host / harness | source |
| --- | --- | --- |
| 0.00845 %/µs | 8882 µs/step, nezuko #730 `--local-submit` | measured |
| 0.00913 %/µs | 8213 µs/step, frieren #733 control | measured |
| 0.01527 %/µs | ranked host, 4910.9 µs/step | measured |

## D0 — Provenance of 8919 (wall) and 8567 (busy)

The claim under audit is manifest item 2,
`research/maple_endgame_handoff_manifest.md:977`:

> Decode wall ≈ 8919 µs vs busy ≈ 8567 µs ⇒ ~350 µs (~2 % of score) of
> non-busy time.

§6.6 of the same manifest (lines 961–964) re-prices the same 350 µs at 2.94 %
of score.

### `d0_wall_8919` = **UNSOURCED**

No primary record of 8919 (or 8.919) exists anywhere in the tree or in history.
Searches run:

```
grep -rn --exclude-dir=.git --exclude-dir=.build -E "8919" .
grep -rn --exclude-dir=.git --exclude-dir=.build -E "8\.919" .
git log -S'8919'      --oneline --all -- research/
git log -S'Decode wall' --oneline --all
```

The number enters the tree **already uncited** in commit `9ef3bfcb`
("advisor r125: endgame handoff manifest + measurement tools"). There is no
run log, JSON, or report behind it. Commit `77580a48` contains the author's own
admission that this basis "has not been verified… Treat it as unpriced until
someone does."

Nearby measured clusters exist but none of them is 8919 and none of them is
cited by the manifest: 8876–8908 µs in `research/nezuko-r117-c-final-report.md:708,710`
and manifest:916; and a kernel-census total of 8883.1 µs in
`research/maple-tanjiro-pr73-decode-kernel-census.md:210-212`.

### `d0_busy_8567` = **UNSOURCED as paired**, but the origin is identified

A decisive near-miss was found and personally re-read from the raw artifact:
`research/r87a-runs/control.json`, arm `A0`, n=6:

| field | mean | sd |
| --- | --- | --- |
| `busy_union_us` | **8567.333** | — |
| `busy_sum_us` | 8568.167 | — |
| `wall_us` | **9814.667** | 75.76 |
| `gap_us` | **1247.333** | 53.59 |
| `cbs` | **406.0** | — |

So 8567 almost certainly came from this R87-A control arm. But **its own paired
wall is 9814.7 µs, not 8919**, and **its own paired gap is 1247 µs, not ~350**.
The manifest pairs this busy with a wall from somewhere else entirely.

### The methodological kill

`research/tanjiro-r87a-campaign.sh:64-66` shows that this control was run under

```
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1  STEPS=${R87A_STEPS:-200}
```

`SPLIT=1` caps dispatches per command buffer so that each `GPUPROF` record times
a small unit — which is exactly why that arm reports **406 command buffers per
step**. A normal decode step does not submit 406 command buffers. The 8567 busy
is therefore a *heavily instrumented* busy, measured in a configuration whose
command-buffer structure is not the scored one.

Manifest item 2 subtracts a `SPLIT=1`-instrumented busy (8567) from an unsourced,
probably hook-free wall (8919). That is an apples-to-oranges subtraction: the
two terms come from different binaries and different dispatch structures. The
~350 µs residual is an artifact of mismatched pairing, not a measured quantity.

Other numbers close to 8567 that are explicitly **not** the source:
`research/r85b-logs-rebased/contrasts.log:91` ("8548 of 8567 us/step") is
downstream prose, not a primary paired measurement.

## D1 — What the decode wall actually is on this host

Apparatus: `research/alphonse-r128d-probe.py`. It launches the runtime worker
directly, sends `decode_begin` with the 512-token seed from the public golden
`correctness_prompts/public_longcopy_gate_english_512_256.json`, then issues
teacher-forced one-token `decode_step` requests, recording absolute
`CLOCK_UPTIME_RAW` spans per step. Every run also takes a `phase_diagnostics`
null-request round-trip census before and after decode, so the probe's own
protocol cost is measured rather than assumed. All runs reported 0 token
mismatches.

**J1 — unpatched worker** (`/tmp/w-clean`, sha256 `5993c62e1a01994a…`), 6 runs
× 1023 steps, no `DARKBLOOM_*` set. Host: this M4 Pro.

| quantity | n | median | IQR | sd | min | max |
| --- | --- | --- | --- | --- | --- | --- |
| seed forward (ms) | 6 | 547.9 | 0.9 | 0.5 | 547.1 | 548.3 |
| step, 1023-step window (µs) | 6 | **8296.3** | 8.5 | 16.7 | 8284.1 | 8332.0 |
| step, first-128 window (µs) | 6 | **8171.1** | 4.6 | 3.1 | 8167.6 | 8175.8 |
| null-request RTT (µs) | 2400 | 45.1 | 34.6 | 351.3 | 20.4 | 10114.6 |

Post-decode null-RTT per-run medians were 21.5–22.0 µs; the pre-decode medians
(49.6–57.1 µs) still carry first-touch cost, so 21.7 µs is the honest steady
protocol figure and the 45.1 µs pooled median is inflated by that warm-up plus
a small number of large scheduler outliers.

**Detection floor (Rule 11).** From per-run medians: first-128 window
sd = 3.1 µs, n = 6 ⇒ SEM 1.27 µs ⇒ 95 % CI **±3.3 µs/step** (t₅ = 2.571).
Full 1023-step window: sd = 16.7 ⇒ **±17.5 µs/step**. At the 8882 µs currency
(0.00845 %/µs) the floor is **0.03 % of score** on the 128-step window. Every
estimate below is quoted against this floor.

### KV growth explains a large part of the cross-report spread

Measured **KV-growth slope = 259.9 µs per 1000 decode steps**. The 1023-step
median step is 8296.3 µs versus 8171.1 µs over the first 128 steps, i.e.
**+125.2 µs purely from window length**. Predicted from the slope, the median
step of a 1023-step window sits at step ≈ 511 and the median of the first 128 at
step ≈ 64, giving (511−64)/1000 × 259.9 = **116.2 µs** — consistent with the
observed 125.2 µs.

This matters directly for reading other reports. `--local-iterate` runs 128
decode steps and `--local-submit` runs 1023 — `Sources/MLXFastCore/Constants.swift:109`
(`benchmarkDecodeSteps = 128`), `:117` (`localSubmitBenchmarkDecodeSteps = 1023`),
selected at `Sources/MLXFastCLI/main.swift:298-299`, both charging the same
512-token seed (`Constants.swift:123`). So roughly **125 µs of any
`--local-submit`-vs-`--local-iterate` difference is window length, not code**.
It is a standing confound between nezuko #730's 8882 µs `--local-submit` figure
and 128-step numbers, and it is on the same order as the entire residual
manifest item 2 claims to have discovered.

### The apparatus itself moves the "wall" by more than the claimed residual

`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:966-1013` defines
the scored decode metric as `(decode_begin + Σ decode_step)/decodeSteps`, i.e.
`includes_seed_prefill=true`. This host's `--local-iterate` run (commit
`492acc7d`, `2026-08-11T12:44:37Z`, `passed_correctness true`,
`max_abs_diff 0`, decode_speedup 1.075) reported
`decode_seconds_per_token = 0.012867255`, so seed + Σ128 steps = 1.647009 s.

Solving for the implied steady step depends on which seed cost you charge:

| assumed seed forward | implied harness step, 128-step window |
| --- | --- |
| 547.9 ms (probe-measured, this host) | 8586.8 µs |
| 575.1 ms (= 512 × this run's `prefill_seconds_per_token`) | 8374.3 µs |

So the trusted harness's implied step over its own 128-step window is
**8374–8587 µs**, while the direct probe measures **8171.1 ± 3.3 µs** over the
nominally identical window. The apparatus gap is **+203 to +416 µs**, priced at
0.00845 %/µs as **1.7 % to 3.5 % of score**.

That is the headline of D1: **choosing a different measuring apparatus for the
same 128 decode steps on the same host moves the "wall" by up to ~416 µs, which
is larger than the ~350 µs residual manifest item 2 reports as a finding.** A
wall-minus-busy subtraction is only meaningful when both terms come from one
apparatus, one binary, and one window; item 2 satisfies none of the three.

## D2 — Method: the instrument-overhead ladder

The only defensible way to price non-busy time is to measure busy and wall in
**one session, one binary, one window**, and to separately measure what the
instrument itself costs. `research/alphonse-r128d-campaign.py` runs four arms
strictly serially — only one model-holding process is ever alive:

| arm | binary | env | runs × steps |
| --- | --- | --- | --- |
| `clean-recheck` | `w-clean` (unpatched) | none | 2 × 200 |
| `hook-off` | `w-hook` (patched) | none | 6 × 1023 |
| `hook-on` | `w-hook` | `DARKBLOOM_GPU_PROFILE=1` | 6 × 1023 |
| `hook-split` | `w-hook` | `+ DARKBLOOM_GPU_PROFILE_SPLIT=1` | 2 × 200 |

`w-hook` is the base tree plus `research/patches/INSTRUMENT_ONLY_r128d_gpuprof_hook.patch`
(a verbatim copy of `research/nezuko-pr158-gpuprof-hook.patch`, which
`git apply --check`s cleanly on the base). It touches only
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}` and installs
a command-buffer completion handler that prints
`GPUPROF <gpu_start_s> <gpu_end_s> <n_dispatches> <pipeline names>` to stderr.
`GPUStartTime`/`GPUEndTime` are host-timebase seconds on the same clock as the
probe's `CLOCK_UPTIME_RAW` spans, so the alignment is direct.

**This patch must never land.** It is stored under `research/patches/` with the
`INSTRUMENT_ONLY_` prefix; the vendor tree was reverted with
`git checkout -- Vendor/` immediately after building, and the landing-diff check
at the end of this document confirms an empty `Sources/`+`Vendor/` diff against
the base.

The ladder isolates three separately meaningful costs:

- `hook-off` − `clean-recheck` — cost of the patch merely being compiled in.
- `hook-on` − `hook-off` — cost of the instrument actually running. This is
  `instrument_overhead_us_per_step`.
- `hook-split` − `hook-on` — cost of command-buffer fission, i.e. the specific
  distortion the R87-A control ran under.

## D3 — Method: decomposing the gap, and the gates that keep it honest

For each steady step the probe supplies `t0` (immediately before the request
write) and `t1` (immediately after the response line is read). From the GPUPROF
records that fall inside `[t0, t1]`:

- `busy_sum` = Σ (end − start) over command buffers;
- `busy_union` = length of the union of those intervals;
- `LEAD` = first GPU start − `t0`;
- `TRAIL` = `t1` − last GPU end;
- `INTERNAL_IDLE` = idle between consecutive command-buffer intervals;
- `gap` = `wall` − `busy_union`, **computed per step and then medianed**, never
  as a difference of two medians.

By construction `LEAD + INTERNAL_IDLE + TRAIL = gap`. That identity is an
arithmetic tautology and proves nothing about causes, so
`research/alphonse-r128d-gap.py` also runs four gates:

- **G1 identity** — `max |LEAD+INTERNAL+TRAIL − gap| < 1 µs`. Fails if records
  were dropped or intervals mishandled.
- **G2 overlap** — `median(busy_sum − busy_union)` and the count of steps with
  >1 µs overlap. Nonzero overlap means concurrent command buffers, and a
  single-timeline attribution is then invalid.
- **G3 RTT floor** — number of steps where `LEAD + TRAIL` is *below* the
  measured null-request RTT. Expected 0: the protocol leg cannot be cheaper
  than a no-op round trip, and whatever the null RTT costs belongs to the
  harness, not to the model.
- **G4 trend** — slope of `gap` against step index, so a median cannot hide a
  KV-growth or thermal drift.

What each component can and cannot mean, stated before looking at the numbers:

- `LEAD` is *not* "the GPU was slow to start". `GPUStartTime` excludes host-side
  JSON parse, MLX graph evaluation, encoding, commit, driver validation and
  queue latency — all of which land in `LEAD`. In serial single-token decode
  this host work is genuinely on the critical path (step N's input depends on
  step N−1's output, so it cannot be hidden behind earlier GPU work), so it is
  *potentially recoverable*, but it is CPU cost, not GPU idle.
- `INTERNAL_IDLE` is only recoverable if it is a genuine commit-gap bubble. It
  is also the component most contaminated by instrumentation, because every
  extra command buffer manufactures another gap.
- `TRAIL` mixes recoverable host cost (logits readback/sync, sampling,
  serialization) with instrument-only cost (completion-handler wake, stderr
  writes) that does not exist in an unpatched run.
- Command-buffer-level timestamps bracket the whole buffer, so bubbles *inside*
  a command buffer are counted as busy. `busy_union` is therefore an **upper
  bound** on useful GPU work, and the gap is a **lower bound** on non-busy time.

### The one gate that decides item 2 before any decomposition

Item 2's arithmetic transplants a busy number from program B into a wall number
from program A. That transplant is only admissible if

```
busy_union(instrumented) <= wall(uninstrumented)
```

on a comparable host and window, because instrumenting a run cannot make the
GPU do *less* work, and busy time can never exceed the wall of the same work.
This gate needs no gap decomposition and no attribution model — it is a
sanity check on the subtraction itself.

## D4 — Reconciliation with the other reported decode figures

Every µs/step number in circulation is quoted below with its host, binary,
window and apparatus, because Rule 9 is exactly the discipline item 2 skipped.

| figure (µs/step) | host | apparatus | window | provenance |
| --- | --- | --- | --- | --- |
| 8919 | unknown | unknown | unknown | **no primary record** (D0) |
| 8567 | unknown (R87-A control host) | hooked worker, `GPU_PROFILE=1` **and** `SPLIT=1` | 200 steps | `research/r87a-runs/control.json` arm `A0`, `busy_union_us.mean`; its own paired wall was **9814.7 µs** |
| 8882 | nezuko #730 host | trusted harness `--local-submit` | 1023 steps | currency 0.00845 %/µs |
| 8213 | frieren #733 host | control arm | — | currency 0.00913 %/µs |
| 4910.9 | ranked M5 | official | — | currency 0.01527 %/µs |
| 8171.1 ± 3.3 | **this M4 Pro** | direct probe, unpatched worker | 128 steps | D1, J1 |
| 8296.3 ± 17.5 | **this M4 Pro** | direct probe, unpatched worker | 1023 steps | D1, J1 |
| 8374–8587 | **this M4 Pro** | trusted harness `--local-iterate` | 128 steps | D1, derived from `decode_seconds_per_token` |

Two structural corrections fall straight out of this table and apply to any
future comparison, independently of item 2:

1. **Window length is worth ~125 µs** between a 128-step and a 1023-step
   window on this host (D1, slope 259.9 µs/1000 steps). A `--local-submit`
   number and a `--local-iterate` number are not the same quantity.
2. **Apparatus is worth up to ~416 µs** between the trusted harness and a
   direct probe on the same host and window (D1).

Both corrections are individually comparable to, or larger than, the ~350 µs
that item 2 reports as a discovered inefficiency.

