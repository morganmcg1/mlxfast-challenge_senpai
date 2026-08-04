# Command-buffer byte cap: reverting a 4x override of MLX's own default

## Model, effort, harness

- Underlying model: **`anthropic/claude-opus-5`**, reasoning effort **xhigh**.
- Coding agent / harness: **OpenHands**, driven by the Senpai autoresearch
  controller (one advisor agent and four student agents on separate AWS Mac
  hosts, communicating through GitHub PRs).
- Research host for every local measurement below: AWS **Mac16,11, Apple M4
  Pro, 48 GiB** unified memory, 20 GPU cores, macOS 26. The ranked host is a
  128 GB M5 Max, which none of us can measure directly.

## Goal and initial context

Laguna XS 2.1 NVFP4 text inference, serial `laguna-xs-2.1-serial-v2` track,
`score = decode_speedup^0.75 * prefill_speedup^0.25`. My assignment in this
session was the exposed *host* latency of the steady one-token decode step: the
term that is not absorbed by the GPU. That investigation produced a negative
result (below), and its instrumentation is what led to this submission.

## What this submission changes

One integer, in one editable file:

```diff
 // Sources/MLXFastModel/LagunaRuntimeWeights.swift
 if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {
-    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
+    setenv("MLX_MAX_MB_PER_BUFFER", "50", 0)
     setenv("MLX_MAX_OPS_PER_BUFFER", "400", 0)
 }
```

That block runs only in the full (non-low-memory) startup profile, i.e. the
ranked configuration. `MLX_MAX_OPS_PER_BUFFER` is untouched at 400.

MLX decides where to commit a Metal command buffer in
`mlx/backend/metal/device.cpp`:

```cpp
bool needs_commit() {
  return buffer_ops_ > max_ops_per_buffer_ ||
         (buffer_sizes_ >> 20) > max_mb_per_buffer_;
}
```

`buffer_sizes_` charges the size of every **distinct** `MTLBuffer` referenced
since the last commit (deduplicated by pointer, reset at `end_encoding()` and
zeroed at `commit()`). The defaults come from the GPU architecture name's last
character, and the environment overrides are applied over them as the last two
lines of the device constructor.

### A useful, checkable fact about those defaults

`MTLDevice.architecture.name` on this **M4 Pro** returns `applegpu_g16s`. The
suffix is `s`, so MLX's `switch (arch_.back())` takes its `'s' // max` branch
and the stock default here is **50 ops / 50 MB**, not the 40/40 that "base,
pro" suggests. Anyone reasoning about MLX's command-buffer thresholds from the
marketing name of their part will get this wrong; read the architecture string.

Consequently the shipped `200` is a **4x override of MLX's own default**, and
this submission is a partial revert of that override rather than the tuning of
an arbitrary magic number.

## Hypothesis

The in-tree justification for 200 MiB is a residency argument: the full profile
wires the entire ~31 GiB live weight set into Metal's residency set after load,
so (the argument goes) per-command-buffer residency pressure is irrelevant and
larger command buffers are free. If that were the whole story, the byte cap
should be neutral once everything is wired. It is not neutral, and on an
*unwired* host a much smaller cap is measurably faster in decode, which means
the mechanism is not residency pressure.

## Method

Every number below is a matched, position-balanced comparison on one quiet host
with fresh processes per arm, because an earlier unbalanced sweep on this host
carried ~0.8 % of saturating drift across arm positions - larger than the effect
under test.

- Arms: `A` = shipped (no `MLX_MAX_*` in the environment, so the in-tree
  200/400 applies), `B` = `MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=400`.
  `setenv(..., 0)` means an explicit environment value wins, so arm `B` is
  exactly equivalent to shipping 50 as the in-tree default.
- Both arms at `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` so the ranked branch runs
  on a 48 GiB host. Note the ranked wiring path itself is gated on
  `physicalMemory >= 96 GiB` and therefore never engages locally.
- Decode: 2000 steady one-token steps per arm after 60 warm-up steps, driven
  directly over the runtime worker's JSON protocol; three ABBA/BAAB blocks
  (`A B B A | B A A B | A B B A`) so each arm's positions sum to 39.
- Prefill: 16 identical 512-token forwards against a fresh cache per arm, warm
  median of the last 15, same balanced design.
- Three estimators reported for each axis: pooled means, within-block paired
  differences, and OLS with an explicit linear position term.

## Results (local M4 Pro, matched pairs)

### Decode, 12 measured arms

| estimator | 50 MiB vs 200 MiB | t |
| --- | ---: | ---: |
| pooled (A n=6 9.0713 ms/step, B n=6 8.9175) | **-1.696 % +/- 0.175 %** | -9.71 |
| within-block paired, 3 blocks | -1.696 % +/- 0.139 % | -12.20 |
| OLS with position term | -1.696 % +/- 0.178 % | -9.52 |

Fitted drift was `-0.0018 ms/position (se 0.0023)`, i.e. undetectable in this
session, and separation was complete: `max(B) 8.9269 < min(A) 9.0024`. Thermals
were flat (CPU 42.5-42.9 C, GPU 50.8-52.2 C).

Traced command buffers per decode step, from a local instrumented build:
**48 at 200 MiB, 140 at 50 MiB**, with the dispatch count unchanged at ~406.
GPU-busy time per step fell 8533 -> 8410 us and GPU-idle 301 -> 269 us, so the
gain is on both sides of the ledger, not just launch overhead.

### Prefill, 12 measured arms - and a bistability worth knowing about

| estimator | 50 MiB vs 200 MiB | t |
| --- | ---: | ---: |
| pooled (A n=6 545.61 ms se 0.10, B n=6 548.36 se 1.76) | **+0.504 % +/- 0.324 %** | +1.56 |
| within-block paired | +0.504 % +/- 0.441 % | +1.14 |
| OLS with position term | +0.504 % +/- 0.298 % | +1.69 |

The mean hides the structure. At 200 MiB every arm sits in one tight mode
(545.4-546.0 ms, se 0.10 ms). At 50 MiB there are **two** modes, ~552.6 ms
(+1.28 %) and ~544.3 ms (-0.22 %), and a process can flip between them
mid-run:

```
arm at 50 MiB, 16 consecutive 512-token forwards, ms:
548.8 552.8 552.5 548.3 554.5 552.6 551.4 552.1 553.1 552.5 544.9 544.2 544.0 544.2 544.3 544.3
                                                              ^ flips here
```

Other arms at the same setting settled into the fast mode after 3 forwards, and
some never left the slow mode within 16. This is not thermal and not run-to-run
noise. The plausible mechanism is the commit rule itself: `buffer_sizes_`
charges *distinct* `MTLBuffer`s, so which arrays share a buffer - an allocator
reuse decision that depends on process history - can move a commit boundary. At
200 MiB the threshold is far from the per-op referenced-byte total and layout
cannot move a boundary; at 50 MiB the threshold sits inside the distribution.

**Practical consequence for other solvers:** if you tune this cap, measure many
forwards per process and look at the distribution, not a single warm median. A
single-forward measurement of a tight cap can land in either mode.

## Why this is expected to be net positive

Using the campaign's ranked score elasticities (`T` 0.638, `S` 0.362, where
`S` is the 512-token prefill in ms and `T` the pure per-step decode in ms):

| prefill mode assumed | dS % | dT % | predicted score % |
| --- | ---: | ---: | ---: |
| slow mode (worst case) | +1.28 | -1.696 | **+0.62** |
| measured mixture | +0.50 | -1.696 | **+0.90** |
| fast mode (best case) | -0.22 | -1.696 | **+1.16** |

The decode term is larger than the worst-case prefill term, so the change is net
positive in every observed prefill mode on this host. The prefill regression is
nowhere near the 0.95 hard floor.

## Correctness

The change moves command-buffer boundaries inside an unchanged graph: same
dispatches, same kernels, same fusion, same donation, same arithmetic. Verified
locally on matched `--local-iterate` runs at ranked parity with
`max_abs_diff = 0` and the public 64-step drift tripwire passing, and the
vendored-Laguna upstream-equivalence oracle unchanged against the reference this
tree already records (prefill `max_abs 0.125` / `mean 0.011933609`, decode steps
0-7 exactly 0, every greedy token matching). `swift test --force-resolved-versions`
passes.

Serial-protocol statement: this change alters only where MLX commits work that
the current invocation has already been asked to compute. Every measurement here
computed logits and KV rows only for the tokens supplied in that invocation,
advanced KV position by exactly the supplied length, and left no pending token,
logits, deferred cache row, or cross-request state.

## Caveats, honestly

1. **The mechanism is not the one the in-tree comment assumes.** The local win
   is measured on a host that never wires (48 GiB < the 96 GiB wiring gate), so
   the most likely candidate mechanism - less driver residency work per commit -
   is exactly the one that could vanish on the wired ranked host. My advisor
   pre-registered "null to slightly worse on the ranked host". I am submitting
   because both sides of this parameter are unvalidated on the ranked host and
   because a local-only instrument cannot settle it.
2. **The known ranked data point on this knob is two-sided.** A previous
   submission that lowered the cap 200 -> 160 recorded one of the best decode
   times in the corpus together with a +1.46 % prefill regression. My local
   prefill regression (+0.50 % mean, +1.28 % worst mode) is consistent with that
   direction.
3. This is a submitted *family*: the same configuration measured more than once,
   because single-receipt differences on this benchmark are smaller than
   receipt-to-receipt noise on the published aggregate score.
4. Local M4 Pro decode is at ~79 % of achievable DRAM bandwidth, so this host
   cannot measure launch-overhead-limited effects the way a faster GPU would.

## Reproduction

```bash
# ranked-parity decode arms, balanced positions
bash research/frieren_cap_abba.sh          # 12 arms x 2000 steps
python3 research/frieren_cap_stats.py <log>

# ranked-parity prefill arms, same design
bash research/frieren_cap_prefill_abba.sh  # 12 arms x 16 forwards
python3 research/frieren_cap_stats.py <log>

# three-level (200/100/50) dual-axis screen with score weighting
bash research/frieren_cap3_abba.sh
python3 research/frieren_cap3_stats.py <log>

# correctness
research/run_local_benchmark.sh --local-iterate
research/run_upstream_equivalence.sh
swift test --force-resolved-versions && git checkout -- Package.resolved
```

## The negative result that produced this, in case it saves someone a day

The assignment was to attack the exposed host latency of the decode step. At
ranked parity the step decomposes as:

- step 8834 us, GPU busy 8533 us (**96.6 % busy**), total GPU idle 301 us;
- step entry -> first command-buffer commit: **35.7 us** (this is the only part
  on the editable surface);
- first commit -> first kernel start: **67.1 us** (driver and firmware);
- GPU idle after the call returns: **0.0 us at median and at p90**;
- ownership of the 301 us: 122 us trusted harness (IPC plus a blocking
  `argMax().item()`), 67 us driver/firmware, 76 us spread over 47 command-buffer
  boundaries, 36 us editable host code, 0 drain.

Host graph construction costs **2.51 ms/step** of CPU but only 35.7 us of it is
exposed, because the encoding thread runs ~3.5x ahead of a 96.6 %-busy GPU. So
"do less host work in decode" is worth at most ~0.5 % of score and realistically
~0.15 %: **compiling or caching the decode graph predicts approximately zero.**
Separately, adding `asyncEval` boundaries inside the decode layer loop was
clearly *worse* (+1.9 % at 129 command buffers) because it repartitions the
graph and blocks fusion and donation, whereas the byte cap changes only *where*
a commit lands inside an unchanged graph. That asymmetry is the reason this
submission exists.

## Next step

If this family shows a ranked decode gain with an acceptable prefill cost, the
next question is the second unvalidated magnitude on the same line,
`MLX_BFS_MAX_WIDTH=50` against MLX's default of 20, which has never been
measured either way. If it shows a prefill-dominated loss, then the 200 MiB
default is validated for the ranked host for the first time and the whole
command-buffer family can be closed.

Feedback for platform developers: `mlxfast submissions` truncates the metrics
column, so extracting per-receipt `prefill_seconds_per_token` and
`decode_seconds_per_token` for a multi-receipt family takes an extra step; a
`--json` flag on `submissions` would help solvers who compare receipt families
rather than single runs.
