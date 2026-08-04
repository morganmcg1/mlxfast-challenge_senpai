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
  `LagunaRuntimeWeights.swift:551`), so the local win is measured in exactly the
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

## 6. Prefill result

_(filled in when the prefill screen completes)_
