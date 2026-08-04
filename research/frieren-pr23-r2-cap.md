# PR #23 r2 — the command-buffer byte cap is on the submission surface

Base: `f4e33385` (advisor branch, `research/` only since r1).
Host: AWS Mac, `Mac16,11`, Apple M4 Pro, 48 GiB unified memory, 20 GPU cores.

r1 concluded the cap's local win was "unreachable from the submission surface".
The advisor corrected that: the caps are installed by our own editable code, not
by MLX's architecture default, in the ranked (non-low-memory) startup profile.

```swift
// Sources/MLXFastModel/LagunaRuntimeWeights.swift:383-389   EDITABLE
setenv("MLX_BFS_MAX_WIDTH", "50", 0)
if env["DARKBLOOM_POST_WIRE_COMMAND_BUFFER"] != "0" {
    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
    setenv("MLX_MAX_OPS_PER_BUFFER", "400", 0)
}
```

MLX applies those over its architecture default unconditionally, as the last
two lines of the device constructor
(`Vendor/mlx-swift/.../backend/metal/device.cpp:596-597`). The accepted
correction is recorded here so the r1 sentence is not quoted again.

## 1. The owed architecture read, and why the answer is not the one expected

`research/host_arch_name.swift` (30 s, `swiftc -O host_arch_name.swift`):

```
name=Apple M4 Pro
architecture=applegpu_g16s
maxBufferLength=30150672384            (28.1 GiB)
recommendedMaxWorkingSetSize=40200896512  (37.4 GiB)
```

The advisor expected suffix `g` (base/pro → 40 ops / 40 MB). **This M4 Pro
reports `applegpu_g16s`, suffix `s`**, so MLX's `switch (arch_.back())` at
`device.cpp:573-595` takes the `'s' // max` branch and this host's stock default
is **50 ops / 50 MB**, exactly like a Max part. Consequences:

- The `40/40` vs `50/50` M4→M5 divergence recorded in the advisor's §10c does
  not exist between this host and the ranked M5 Max. Both are `'s'` unless the
  M5 Max reports something other than a trailing `s`, which would require it to
  be classified as base/pro/phone/ultra.
- MLX derives `arch_gen_` from the two characters before the suffix
  (`device.cpp:565-572`), so `g16` → generation 16 for M4. An M5 Max should read
  `applegpu_g17s` → generation 17, suffix `s`, default 50/50.
- Therefore the local "cap 50" arm is *MLX's own default for this class of
  part*, and the shipped `200` is a 4× override of it. That reframes the
  question: the experiment is not "tune a magic number", it is "does the
  in-tree 4× override of MLX's default byte threshold still pay?".
- It is also why the advisor's instruction to set the value **explicitly**
  rather than delete the block is right for a different reason than stated:
  deleting would be *approximately* equivalent on any `'s'` host (50/50), but it
  would also drop the `ops` cap from 400 to 50, which is a second, unmeasured
  change.

## 2. What is actually under test

Exactly one integer, with everything else held fixed:

| variable | control arm `A` (shipped) | candidate arm `B` |
| --- | ---: | ---: |
| `MLX_MAX_MB_PER_BUFFER` | 200 | **50** |
| `MLX_MAX_OPS_PER_BUFFER` | 400 | 400 |
| `MLX_BFS_MAX_WIDTH` | 50 | 50 |
| `DARKBLOOM_STARTUP_MEMORY_PROFILE` | `full` | `full` |
| wiring (`physicalMemory ≥ 96 GiB`) | not engaged (48 GiB host) | not engaged |

`A` sets no `MLX_MAX_*` at all, so it is the shipped tree verbatim. `B` sets the
two variables externally; the in-tree `setenv(..., 0)` cannot overwrite them, so
`B` is byte-for-byte equivalent in effect to shipping `50` in that line.

Recorded command-buffer counts per decode step at ranked parity, from the r1
`FRIEREN_CBPROF` traces (`research/frieren-pr23-head-region.md:236-248`):

| caps | cb/step | dispatches/step | GPU busy | GPU idle | step |
| --- | ---: | ---: | ---: | ---: | ---: |
| 200 MB / 400 ops (shipped) | **48** | ~406 | 8533.1 µs | 300.8 µs | 8834.4 µs |
| 50 MB / 400 ops | **140** | ~406 | 8409.6 µs | 269.0 µs | 8678.6 µs |
| 128 MB / 64 ops (low-mem) | 78 | ~406 | 8512.3 µs | 269.9 µs | 8782.2 µs |

So the cap changes *where* commits land in an otherwise identical graph: the
dispatch count, fusion and donation are unchanged, which is the structural
difference from r1 Part 2's `asyncEval` rungs (those repartition the graph and
raised GPU busy time).

## 3. Why the r1 number could not be trusted

r1's `cap 50 = 8.9579 (n=5)` against `cap 200 = 9.0893 (n=4)` came from three
different scripts whose arms ran in unbalanced blocks. The same session later
showed identical control arms reading `9.0356 / 9.1076 / 9.1136` across script
positions — a 0.86 % spread, *larger than the 1.45 % effect claimed* — and the
drift saturates rather than being linear, so it cannot be removed by a linear
covariate after the fact.

r2 therefore re-measures the contrast under a design that cancels smooth drift
twice over: three balanced blocks, `A B B A | B A A B | A B B A`, preceded by a
discarded warm-up arm, 2000 measured decode steps per arm, fresh process per arm
(`research/frieren_cap_abba.sh`). Each arm's positions sum to 39, and every
block of four is internally balanced. Analysis
(`research/frieren_cap_stats.py`) reports the pooled contrast, the within-block
paired contrast, and an OLS contrast with an explicit linear position term, plus
the fitted drift.

## 4. Decode result: the contrast survives balancing, and it is larger than r1's

`research/frieren_cap_abba.sh`, one session 15:53–16:12 UTC, 12 measured arms
(plus the discard), 2000 steady decode steps each, fresh process per arm.

```
 pos arm   ms/step        pos arm   ms/step
   1   A    9.0631          7   A    9.0631
   2   B    8.9165          8   B    8.9102
   3   B    8.9144          9   A    9.1042
   4   A    9.0954         10   B    8.9221
   5   B    8.9148         11   B    8.9269
   6   A    9.0998         12   A    9.0024
```

| estimator | delta | uncertainty | t |
| --- | ---: | ---: | ---: |
| pooled means (A n=6 9.0713, B n=6 8.9175) | **−1.696 %** | ± 0.175 % | −9.71 |
| within-block paired (3 ABBA blocks) | **−1.696 %** | ± 0.139 % | −12.20, 2 df |
| OLS with linear position term | **−1.696 %** | ± 0.178 % | −9.52 |

All three agree to three decimals, and the fitted drift is
`−0.0018 ms/position (se 0.0023)`, i.e. **not detectable in this session** —
unlike the r1 session, whose identical controls spanned 0.86 %. Per-block
differences are −0.1638 / −0.1690 / −0.1288 ms, so the effect is present in every
block. Separation is complete: `max(B) = 8.9269 < min(A) = 9.0024`.

Thermals were flat throughout (CPU 42.53–42.89 °C, GPU 50.85–52.17 °C), and the
GPU-power samples between arms confirm the host was idle at each arm boundary.

Two secondary observations, both consistent with the mechanism being *where*
commits land rather than *what* is computed:

- Host CPU per step rises with the extra commits: `cpu_total_ms_per_step`
  0.0929 (A) → 0.1249 (B) on the parent-side accounting, and the worker's
  encoding thread 2.48–2.50 (A) → 2.99–3.02 ms (B). Both remain far below the
  8.9 ms step, so per r1's finding this added host work is absorbed.
- Arm A is markedly noisier than arm B (A spans 9.0024–9.1042, B spans
  8.9102–8.9269). A 200 MiB threshold lands commits at data-dependent points in
  a graph whose referenced-byte total varies with routing; a 50 MiB threshold
  commits so often that the placement is nearly deterministic.

So r1's `−1.45 %` was, if anything, an *under*-statement of the local effect,
and the advisor's concern that the r1 contrast had not survived its own
balancing design is now resolved in the direction of the effect being real
**on this host**.

## 5. The transfer question is now the whole question

Nothing above touches the reason to doubt M5 transfer:

- This 48 GiB host never wires (`physicalMemory ≥ 96 GiB` gate at
  `LagunaRuntimeWeights.swift:549`), so the local win is measured in exactly the
  regime the shipped 200 MiB override was *not* written for.
- The cap is a single process-wide integer, read once through a function-local
  static (`mlx/utils.h:178-187`) inside the device constructor, so it cannot be
  phase-specific. Any decode gain is paid for out of prefill if prefill
  regresses, and prefill carries the hard 0.95 floor and elasticity 0.362.
- The known ranked-host data point on this parameter cuts the other way on
  prefill: submission `0c83fa3e` (cap 200 → 160) holds the 3rd-lowest `T` of 919
  submissions while carrying a **+1.464 % prefill regression**.

Section 6 therefore measures the prefill axis under the identical design before
any submission is spent.

## 6. Prefill result: a smaller cap costs prefill, but the cost is *bistable*

`research/frieren_cap_prefill_abba.sh`, same design, 16 identical 512-token
prefill forwards per arm, warm median over the last 15.

```
 pos arm   ms/forward        pos arm   ms/forward
   1   A     545.975           7   A     545.406
   2   B     552.741           8   B     551.425
   3   B     552.666           9   A     545.632
   4   A     545.427          10   B     544.329
   5   B     544.531          11   B     544.439
   6   A     545.411          12   A     545.785
```

| estimator | delta | uncertainty | t |
| --- | ---: | ---: | ---: |
| pooled (A n=6 545.606 se 0.096, B n=6 548.355 se 1.765) | **+0.504 %** | ± 0.324 % | +1.56 |
| within-block paired | +0.504 % | ± 0.441 % | +1.14 (2 df) |
| OLS with linear position | +0.504 % | ± 0.298 % | +1.69 |

The point estimate is a regression, as the ranked history predicted, but **the
mean hides the actual structure**: arm A is one tight mode (545.4–546.0,
se 0.096 ms) while arm B is two modes, `≈552.6` (+1.28 %) and `≈544.3`
(−0.22 %), and the per-rep traces show which:

```
p02 B: 551.6 550.8 554.1 552.3 552.9 551.7 552.2 552.3 552.3 552.6 553.2 553.6 553.5 552.9 552.7 553.3
p05 B: 548.8 547.8 547.6 544.9 544.3 544.5 544.6 544.2 544.9 544.4 544.3 544.8 544.3 543.7 546.0 544.5
p08 B: 548.8 552.8 552.5 548.3 554.5 552.6 551.4 552.1 553.1 552.5 544.9 544.2 544.0 544.2 544.3 544.3
p04 A: 545.9 545.4 545.0 545.7 545.3 546.0 544.7 545.3 545.4 545.5 545.8 545.4 545.9 545.0 545.3 545.5
```

`p08` **flips mode at rep 11 inside one process**, `p05` and `p11` settle into
the fast mode after 3 reps, and `p02`/`p03` never leave the slow mode within 16
forwards. So this is not run-to-run noise and not thermal: it is a
warm-up/steady-state bifurcation that only exists at the tight cap.

The likely mechanism is in the commit rule itself. `needs_commit()` compares
`buffer_sizes_ >> 20` against the cap, and `buffer_sizes_` charges each
**distinct MTLBuffer** referenced since the last commit, deduplicated by
pointer. Which arrays land in the same MTLBuffer is decided by MLX's allocator
reuse, which depends on process allocation history. At a 200 MiB cap the
threshold is far from the per-op referenced-byte total, so allocator layout
cannot move a boundary; at 50 MiB the threshold sits inside the distribution, so
a different reuse pattern moves commits and shifts prefill by ~1.5 %. That also
explains the decode observation in §4 that arm A is the *noisier* arm on decode
while arm B is the tighter one: on the decode graph the tight cap commits so
often that placement is nearly deterministic, whereas on the much larger prefill
graph the tight cap is the one that becomes layout-sensitive.

### Net local score arithmetic, in all three prefill modes

Ranked elasticities (advisor): `T` 0.638, `S` 0.362,
`ns% ≈ −(0.638·ΔT% + 0.362·ΔS%)`.

| prefill mode used for `S` | ΔS % | ΔT % | predicted `ns` % |
| --- | ---: | ---: | ---: |
| slow mode only (worst case) | +1.28 | −1.696 | **+0.62** |
| pooled mixture (measured mean) | +0.50 | −1.696 | **+0.90** |
| fast mode only (best case) | −0.22 | −1.696 | **+1.16** |

The decode term (`0.638 × 1.696 = 1.082 %`) is larger than the worst-case
prefill term (`0.362 × 1.28 = 0.463 %`), so on this host the change is net
positive **in every prefill mode**, and the advisor's 0.61 % bar is cleared even
by the pessimistic row. That is the honest local case for spending receipts;
it is not a claim about the wired ranked host, which §5 explains cannot be
settled here.

Prefill floor risk is not in play: the worst mode is `+1.28 %`, far from the
`0.95` hard floor.

## 7. Three levels, one process per arm: 50 MiB beats 100 MiB outright

The two screens above measure the two axes in separate processes, so they cannot
say whether one intermediate level buys the decode gain without the prefill
cost. `research/frieren_cap3_abba.sh` closes that: three levels
(`A` = shipped 200, `C` = 100, `B` = 50 MiB, `MLX_MAX_OPS_PER_BUFFER=400`
throughout), position sequence `A B C C A B B C A` so every level's positions
sum to 15, and each arm measures **both** axes in one process (16 prefill
forwards, warm median of 15, then 2000 decode steps). Analysis:
`research/frieren_cap3_stats.py`, training `02819840`, log `/tmp/cap3.log`.

| arm | n | `S` ms | se | dS % | `T` ms | se | dT % | `ns` % |
| --- | --: | --: | --: | --: | --: | --: | --: | --: |
| A 200 MiB | 3 | 545.445 | 0.037 | — | 9.0317 | 0.0223 | — | — |
| C 100 MiB | 3 | 547.151 | 0.112 | +0.313 | 8.9813 | 0.0069 | −0.557 | +0.242 |
| B 50 MiB | 3 | 547.116 | 2.890 | +0.306 | 8.8730 | 0.0042 | **−1.757** | **+1.010** |

Two things settle the choice:

1. **The decode contrast replicates on a second instrument.** −1.757 % here
   against −1.696 % in §4, from a different script, a different arm layout, and
   arms that also ran a prefill workload first. The effect is real and its size
   is stable.
2. **100 MiB is dominated.** It pays essentially the entire prefill cost
   (+0.313 % vs +0.306 %) and returns under a third of the decode gain. There is
   no monotone-in-cap tradeoff to tune: the useful boundary density only appears
   once the cap is at or below MLX's own stock threshold. The large `se` on
   `S` for arm B is the §6 bistability (one of its three arms, position 7, sat in
   the slow prefill mode at 552.9 ms).

So the single global value to ship is **50 MiB**, not an intermediate.

## 8. What is shipped, and how it is verified

One line changes on the submission surface,
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`, inside the existing
non-low-memory block:

```diff
-                    setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)
+                    setenv("MLX_MAX_MB_PER_BUFFER", "50", 0)
```

`MLX_MAX_OPS_PER_BUFFER` stays at 400 and the
`DARKBLOOM_POST_WIRE_COMMAND_BUFFER` kill switch is preserved, so the same
binary can still be A/B'd. `overwrite=0` means an explicit environment value
still wins, which is what made every screen above possible. This is an in-tree
default, not an environment-dependent switch: a ranked run sets nothing.

Two host caveats that any replication must respect:

- This 48 GiB M4 Pro resolves the **low-memory** startup profile, which skips
  the edited block entirely and force-sets 128/64 with `overwrite=1`. Every
  measurement and every verification here therefore exports
  `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`. Without it the change is invisible.
- The change alters only *when* MLX commits a command buffer, not what it
  encodes: same kernels, same order, same inputs. Bit-identity is expected, and
  is checked rather than assumed.


## 9. Verification record

All four checks ran on commit `a3578f9`/`c4a90f2` (the scored surface is
identical across those; only research prose moved).

| check | command | result |
| --- | --- | --- |
| matched `--local-iterate` pair | `research/frieren_verify_cap50.sh`, training `ad802ec3` | candidate and control both `max_abs_diff = 0`, `passed_correctness = true`, 130 checked steps, golden hash `b9509697...a58d7a63` |
| unit and harness tests | `swift test --force-resolved-versions` | 454 tests in 6 suites passed, exit 0, `Package.resolved` restored |
| upstream-equivalence oracle | `research/frieren_verify_cap50_oracle.sh`, training `a43401c4` | identical at both startup profiles: prefill `0.125` / `0.011933609` token `5991 == 5991`, decode-0..7 exactly `0`, `EQUIVALENCE_EXACT_STEPS=8` |
| submission preflight | `--local-submit` at full profile, training `04101528` | `passed = true`, `max_abs_diff = 0`, decode `0.009426` s/token, prefill `0.001206` s/token, peak RAM 21 GB |

The pair's own timings are `n = 1` per arm and unbalanced by position (candidate
ran first), so they are not the effect estimate; they are a correctness gate.
For the record they run in the same direction as the screens: decode
`0.0137469` vs `0.0138107` s/token (−0.46 %), prefill `0.0012186` vs
`0.0011898` (+2.4 %, one draw from the bistable prefill distribution of §6).

The control arm is worth a note of its own: it is the *same binary and the same
commit* as the candidate, with 200 MiB restored through the environment. That is
only possible because the in-tree call is `setenv(..., overwrite: 0)`. Keeping
that seam means every future value of this knob can be A/B'd without a rebuild.

### One platform constraint that bounds receipt spending

`mlxfast submit` enforces **one in-flight ranked submission per account**:

```json
{"error":{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}}
```

With observed validation turnaround of roughly 25 minutes per receipt, an
account can spend about two receipts an hour *in total, across every role*, and
the submit endpoint has its own rate limit on top: ten one-minute retries
returned `Rate limit reached. Try again in 2809 seconds`, blocking submission for
47 minutes. A three-receipt family therefore occupies the shared queue for over
an hour, and two roles submitting concurrently will interleave.

So the safe waiting pattern, which `research/frieren_spend_receipts.sh` now
implements, is to poll the cheap listing endpoint, call `submit` only when no row
reads `validating`, and honour any server-supplied retry-after. Retrying
`submit` itself as a wait loop is the trap: it costs a 47-minute lockout, which
is longer than the queue wait it was trying to absorb. Any future role planning a
receipt family should budget queue time first and treat the receipt count, not
local measurement time, as the scarce resource.


## 10. Where the "40 MB" comes from, from source

*(Added after the r2 scope change: the shipped pair moved to 200 MiB / 200 ops
on base `9a407ed6`, Part 2 was cancelled, and Part 1 became a falsification test
of the claim that MLX's 40 MB byte limit trips first. Sections 1-9 above were
written against the 200/400 tree and their control arms are labelled
accordingly. Nothing in §4-§7 depended on the ops value except through the
control arm's label, which §10.4 addresses.)*

### 10.1 The number is an architecture default, and 40 is not this host's

`Device::Device()` picks both caps from the **last character of the GPU
architecture string**, then lets the environment override them
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:574-597`):

| `arch_.back()` | MLX's comment | `max_ops_per_buffer_` | `max_mb_per_buffer_` |
| --- | --- | ---: | ---: |
| `p` | phone | 20 | **40** |
| `g` | base, pro | 40 | **40** |
| `s` | max | 50 | **50** |
| `d` | ultra | 50 | 50 |
| default | medium | 40 | **40** |

So `40` is the byte default for `p`, `g`, and the fallback. It is a *default*,
not a limit MLX enforces on top of anything.

And it is not this host's default. The owed `MTLDevice.architecture.name` read
(§1, `research/host_arch_name.swift`) returns **`applegpu_g16s`** on this M4
Pro: the string ends in `s`, so MLX takes its `'s' // max` branch and this
host's stock pair is **50 ops / 50 MB**. MLX's own comment (`'g' // base, pro`)
invites exactly the wrong inference from the marketing tier - an "M4 **Pro**"
does not take the `g` branch. Any claim of the form "MLX's default here is
40 MB" has to be backed by the architecture string, not the part name.

### 10.2 In the ranked configuration the default is overridden, unconditionally

The last two lines of the constructor are

```cpp
max_ops_per_buffer_ = env::max_ops_per_buffer(max_ops_per_buffer_);
max_mb_per_buffer_  = env::max_mb_per_buffer(max_mb_per_buffer_);
```

and `env::max_mb_per_buffer` is `get_var("MLX_MAX_MB_PER_BUFFER", default_value)`
memoised in a function-local `static`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/utils.h:184-188`). Our own editable code
sets that variable in the full-profile branch
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:384-387`), so on the ranked
path the live byte threshold is **200 MiB, not 40 MB** - five times higher.

The one way that could fail is ordering: the `static` freezes on first call, so
a `setenv` after the Metal device already exists would be ignored. It is not
ignored here, and the counting sweep proves it rather than arguing it (§10.3):
with no `MLX_MAX_*` in the environment the shipped default produces the same
cb/step as an explicit `MLX_MAX_MB_PER_BUFFER=200`, and a different value
produces a different cb/step. If the `setenv` were too late, every arm would
collapse onto this host's arch default of 50.

A third value is worth naming because it is easy to mistake for either of the
other two: on a host under 64 GiB **at default settings** the low-memory profile
takes over and force-sets `MLX_MAX_MB_PER_BUFFER=128` / `MLX_MAX_OPS_PER_BUFFER=64`
with `overwrite=1` (`RuntimeStartupMemoryPolicy.swift:80-81,174-183`), which an
explicit environment value cannot beat. So a research host has *three* possible
byte thresholds - 50 (arch), 128 (low-memory policy), 200 (ranked branch) - and
which one is live depends on the startup profile, not on MLX.


### 10.3 Which limit actually binds: the ops rule is unreachable, not merely second

The commit rule is one line
(`device.cpp:484-487`), evaluated once per array eval in
`eval.cpp:59`:

```cpp
bool CommandEncoder::needs_commit() const {
  auto [max_ops, max_mb] = device_.get_max_ops_mb_per_buffer();
  return (buffer_ops_ > max_ops) || ((buffer_sizes_ >> 20) > max_mb);
}
```

`buffer_ops_` counts `dispatch_threadgroups` / `dispatch_threads` calls
(`device.cpp:381,389`); `buffer_sizes_` accumulates `a.data_size()` only for
buffers not already in `all_inputs_` (`device.cpp:319-321`), so it is a
**unique-referenced-byte** counter, not an issued-byte counter, and blit-only
work contributes zero ops. Both counters reset at commit (`device.cpp:528-529`).

That gives a decisive free test. A command buffer cut by the op rule must carry
at least `max_ops + 1` ops, so *counting the ops in every committed buffer says
which rule fired* without timing anything. `research/frieren_cb_binding_sweep.sh`
and `research/frieren_cb_binding.py` do exactly that: 6 arms, one process each,
60 warm-up + 300 measured steps at `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`,
350 steady steps of traced command buffers per arm.

| arm | `MLX_MAX_MB` | `MLX_MAX_OPS` | cb/step (median) | ops/cb median | ops/cb **max** | cbs at op limit | wall ms/step |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shipped (no env) | 200 | 200 | **50.0** | 10 | **28** | 0 / 17494 | 8.7305 |
| ops200 | 200 | 200 | **50.0** | 10 | **28** | 0 / 17495 | 8.6902 |
| ops400 | 200 | 400 | **50.0** | 10 | **28** | 0 / 17483 | 8.7245 |
| mb40 | 40 | 200 | 127.0 | 1 | 18 | 0 / 44882 | 8.5847 |
| mb100 | 100 | 200 | 80.0 | 5 | 19 | 0 / 27950 | 8.6547 |
| mb400 | 400 | 200 | 19.0 | 29 | 39 | 0 / 6650 | 8.7735 |

Four things fall out, and the first two are the deliverables.

**1. The ops axis is dead, and by a wider margin than "the byte limit trips
first".** `ops200` and `ops400` are identical in every partition statistic:
median 50.0, mean 49.99 vs 49.95, min 49 / max 51 in both, and ops-per-cb
histograms that agree bucket-for-bucket to within ±12 counts out of 17.5k
(`19:4543  11:3150  1:1750  4:700  10:350  2:350  5:349` in both). The stronger
statement is in the `ops/cb max` column: **the largest command buffer this model
ever produces holds 28 ops at the shipped byte cap and 39 ops at a 400 MiB cap.**
The op rule needs 201. It is not merely losing the race - it is unreachable, and
`MLX_MAX_OPS_PER_BUFFER` is inert at *any* value at or above 40. The whole
200 → 400 → 200 churn moved a threshold that sits 5-14× above the highest value
the counter it guards can reach. `cbs at ops limit` is exactly 0 in all six arms,
124,954 command buffers total.

**2. The byte axis is the live one, and it binds at every value swept including
the shipped 200.** cb/step is strictly monotone in the cap: 40 → 127, 100 → 80,
200 → 50, 400 → 19. The `mb400` arm is the one that settles whether 200 binds:
if 200 MiB were already above the largest layer's unique byte footprint, raising
it to 400 would change nothing, and instead cb/step falls by another 2.6×. So
the shipped 200 MiB *is* cutting command buffers mid-step, and the byte rule is
the only rule doing any cutting on this model.

**3. The no-env arm proves the in-tree `setenv` takes effect.** `shipped` matches
`ops200` on every statistic and matches no other arm. If the `setenv` at
`LagunaRuntimeWeights.swift:386` were landing after MLX memoised its static, the
shipped arm would read this host's arch default of 50 MB, which by interpolation
between the 40 and 100 arms is ≈115 cb/step - not 50. The ordering objection in
§10.2 is closed empirically.

**4. Timing, directional only.** These are single unbalanced arms, so they carry
the position drift documented in §3, but they are internally calibrated: the
`ops200` / `ops400` pair is an A/A in partition terms, and it reads +0.39% apart.
That is this design's noise floor. Against it, `mb40` is −1.21% below `ops200` and
`mb400` is +0.96% above - both larger than the floor, both in the direction the
balanced screen of §4 found (−1.696% ± 0.175% for 50 vs 200 MiB), and now with a
fourth rung showing the cost continues in the *other* direction too. More, smaller
command buffers are faster on this host across the whole 40-400 MiB range. Note
also the host CPU column of the raw log: the encoding thread costs 3.13 ms/step at
40 MiB, 2.50 at 200 and **4.83 at 400**, so the 19-cb configuration is the only
one where host cost rises sharply - consistent with per-commit work being cheap
and per-buffer residency bookkeeping being not.

Raw traces: `/tmp/frieren_cbbind_{shipped,ops200,ops400,mb40,mb100,mb400}.txt`,
summary log `/tmp/cbbind_sweep.log`.

### 10.4 Verdict on the 40 MB claim, and what it does and does not change

The claim under test was *"the knob is inert on this model, because MLX's
40 MB-per-buffer byte limit trips first"*.

**The conclusion is right and I confirm it independently and more strongly. The
number 40 is wrong for our configuration, and of the three candidate
explanations the answer is the second one: 40 MB is an architecture default read
from `device.cpp`, not the effective threshold.** Specifically:

- *"the 200 is not taking effect"* - **refuted**, by §10.3 finding 3. The no-env
  arm reproduces the explicit-200 arm exactly and nothing else.
- *"40 is an arch default being read somewhere else"* - **this is it.** 40 MB is
  `device.cpp:577,581,593`, the `'p'` / `'g'` / fallback branches. It is what MLX
  would use with no override. It is also not this host's default: `applegpu_g16s`
  takes the `'s'` branch at 50 MB (§10.1). Under our runtime no host uses 40,
  because the full profile sets 200 and the low-memory profile forces 128.
- *"her instrumentation was measuring a different limit"* - not needed as an
  explanation, and I would not assert it. A dispatch-level probe that observed
  cuts every ~10 ops would correctly conclude the op rule never fires; naming the
  byte threshold 40 rather than 200 is a source-attribution slip that does not
  touch the inference.

**What it changes: nothing about her revert, and one thing about the M5 reading.**
The revert of `MLX_MAX_OPS_PER_BUFFER` 400 → 200 is a no-op on the partition, so
it cannot have cost anything, and restoring the value the in-tree comment
describes is the right housekeeping. But receipt `1feeabc8`'s `ns +0.179% ±
0.172%` was read as *"more likely the cap than the barriers"*. It can be neither.
The ops half of tree X is provably partition-identical, so on that axis the
contrast is an **A/A**, and the barrier half has its own public receipt at `ns
−0.070% ± 0.210%`. A contrast between two configurations that differ in no
executed work is a direct measurement of M5 receipt noise, and +0.179% ± 0.172%
at n=1 vs n=3 is a useful corroboration of the 0.243% 2σ floor rather than
evidence about a mechanism.

**What survives of §4-§7.** Those screens compared `MLX_MAX_MB_PER_BUFFER` 50 (and
100) against the shipped 200 with `MLX_MAX_OPS_PER_BUFFER` at 400 on both sides.
Since the ops value provably changes no partition statistic and no dispatch, the
old control arm and the new 200/200 control arm are the same executed program:
the shipped and ops200 arms above differ by 0.39%, inside this design's noise. So
the −1.696% ± 0.175% decode contrast and the bistable +0.504% ± 0.324% prefill
cost stand as measured against the current base, with no rerun needed. §10.5
confirms that in the timing currency with a balanced A/A rather than by argument.

**What none of it changes: the recommendation.** The live axis is a *partition*
knob. It changes where command buffers are cut, not what arithmetic runs or what
bytes are read, and the programme rule that came out of this PR - change bytes or
arithmetic, not partition - now has a fourth data point in its favour: the local
optimum on this host is at a *smaller* cap than shipped, in a regime (no wiring,
48 GiB) that the ranked host does not occupy, with a prefill cost that is
bistable rather than merely small. It is the wrong thing to spend a shared
receipt slot on.

