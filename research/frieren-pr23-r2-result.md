# PR #23 r2 result: the command-buffer cap axis, closed from source and by counting

Student `maple-frieren`, PR #23, branch `maple-frieren/head-latency`,
`BASE_SHA = 9a407ed699f6127754efde955e85756a327af040`.

**Decision: dead hypothesis. No receipts spent (authorisation was withdrawn
mid-arm and I spent nothing before or after).** The scored surface is
byte-identical to the base; the whole diff is `research/`.

Detail memo: `research/frieren-pr23-r2-cap.md` (§1-§10).

---

## 1. What was asked, and what the answer is

The r2 brief authorised a 3-receipt family on the command-buffer cap. Comment
`5182398994` cancelled that and replaced it with three free deliverables, all
aimed at one structural claim: *"the ops knob is inert because MLX's 40 MB
byte limit trips first."*

| deliverable | answer |
| --- | --- |
| cb/step at ops ∈ {200, 400}, MB held at 200 | **identical** - the ops axis is dead |
| cb/step over MB ∈ {40, 100, 200, 400}, ops held at 200 | 127 / 80 / 50 / 19 - the MB axis is the live one and it binds at the shipped 200 |
| reconcile the 40 MB figure from source | the conclusion is right; **40 MB is an arch default in `device.cpp`, not the effective threshold**, which is 200 |

And one consequence the brief did not anticipate: because the ops axis provably
changes nothing, **every M5 receipt that differs only in that knob is an A/A**.
Five such trees are already paid for - the frontier control, the three public
160/240/400 sweep receipts, and tree X `1feeabc8` - so the programme has a
free ranked-host noise measurement it did not know it had, and the `S +0.130%`
that was the only mechanism story for PR #12's `S` regression cannot be one (§5).

## 2. The instrument: count ops per committed buffer, do not time anything

MLX's commit rule is one line, evaluated once per array eval
(`device.cpp:484-487`, called from `eval.cpp:59`):

```cpp
return (buffer_ops_ > max_ops) || ((buffer_sizes_ >> 20) > max_mb);
```

`buffer_ops_` counts `dispatch_threadgroups`/`dispatch_threads`
(`device.cpp:381,389`). `buffer_sizes_` adds `a.data_size()` only for buffers not
already in `all_inputs_` (`device.cpp:319-321`), so it is a **unique-referenced-byte**
counter, not an issued-byte counter. Both reset at commit (`device.cpp:528-529`).

Therefore a buffer cut by the op rule must carry at least `max_ops + 1` ops.
Counting the ops in every committed buffer says which rule fired, with no timing
and no noise. `research/frieren_cb_binding_sweep.sh` +
`research/frieren_cb_binding.py`: 6 arms, one process each, 60 warm-up + 300
measured steps at `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, 350 steady traced
steps per arm, 131,954 command buffers total.

## 3. The binding table

| arm | `MLX_MAX_MB` | `MLX_MAX_OPS` | cb/step median (mean, min-max) | ops/cb median | ops/cb **max** | cbs at op limit | wall ms/step |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shipped (no env) | 200 | 200 | **50.0** (49.98, 49-51) | 10 | **28** | 0 / 17494 | 8.7305 |
| ops200 | 200 | 200 | **50.0** (49.99, 49-51) | 10 | **28** | 0 / 17495 | 8.6902 |
| ops400 | 200 | 400 | **50.0** (49.95, 49-51) | 10 | **28** | 0 / 17483 | 8.7245 |
| mb40 | 40 | 200 | 127.0 (128.23, 116-144) | 1 | 18 | 0 / 44882 | 8.5847 |
| mb100 | 100 | 200 | 80.0 (79.86, 78-81) | 5 | 19 | 0 / 27950 | 8.6547 |
| mb400 | 400 | 200 | 19.0 (19.00, 19-19) | 29 | 39 | 0 / 6650 | 8.7735 |

**(a) The ops axis is dead, and by more than "the byte limit wins the race".**
`ops200` and `ops400` agree on median, mean, min, max, and their ops-per-cb
histograms match bucket for bucket to within ±12 counts out of 17.5k
(`19:4543 11:3150 1:1750 4:700 10:350 2:350 5:349` in both). The decisive column
is `ops/cb max`: **the largest command buffer this model ever builds holds 28 ops
at the shipped cap and 39 ops even at a 400 MiB cap.** The op rule needs 201.
`MLX_MAX_OPS_PER_BUFFER` is inert at *any* value ≥ 40, and `cbs at op limit` is
exactly 0 in all six arms. The 200 → 400 → 200 churn moved a threshold sitting
5-14× above the highest value the counter it guards can reach.

**(b) The MB axis is live and binds at the shipped value.** cb/step is strictly
monotone: 40 → 127, 100 → 80, 200 → 50, 400 → 19. The `mb400` rung is what
settles it: if 200 MiB were already above the largest per-step byte run, raising
it would change nothing, and instead cb/step falls another 2.6×.

**(c) The in-tree `setenv` takes effect.** The no-env `shipped` arm matches
`ops200` on every statistic and matches nothing else. Had the `setenv` at
`LagunaRuntimeWeights.swift:386` landed after MLX memoised its static
(`utils.h:184-188`), the shipped arm would have read this host's arch default of
50 MB - ≈115 cb/step by interpolation between the 40 and 100 rungs, not 50. The
ordering objection is closed empirically rather than argued.

## 4. Source reconciliation: which of the three explanations is right

| candidate explanation | verdict |
| --- | --- |
| the 200 is not taking effect | **refuted** by §3(c) |
| 40 is an arch default read somewhere else | **this is the answer** |
| the instrumentation measured a different limit | not needed, and I would not assert it |

`Device::Device()` picks both caps from the *last character of the GPU
architecture string*, then applies the environment over them unconditionally
(`device.cpp:573-597`):

| `arch_.back()` | MLX's comment | max ops | max MB |
| --- | --- | ---: | ---: |
| `p` | phone | 20 | **40** |
| `g` | base, pro | 40 | **40** |
| `s` | max | 50 | 50 |
| `d` | ultra | 50 | 50 |
| default | - | 40 | **40** |

So 40 MB is real, and it is `device.cpp:577,581,593` - the `p`, `g` and fallback
defaults. It is what MLX *would* use with no override. Under our runtime no host
uses it: the full profile sets 200 (`LagunaRuntimeWeights.swift:384-387`) and the
low-memory profile force-sets 128/64 with `overwrite=1`
(`RuntimeStartupMemoryPolicy.swift:80-81,174-183`).

Two traps worth recording for the team:

1. **The owed architecture read.** `MTLDevice.architecture.name` on this host is
   **`applegpu_g16s`** (`research/host_arch_name.swift`; "Apple M4 Pro",
   `maxBufferLength` 30150672384). The string ends in `s`, so MLX takes its
   `'s' // max` branch: this host's stock pair is **50/50, not 40/40**. MLX's own
   comment `'g' // base, pro` invites exactly the wrong inference from the
   marketing tier. Any "MLX's default here is 40 MB" claim needs the arch string,
   not the part name.
2. **A research host has three possible byte thresholds** - 50 (arch), 128
   (low-memory policy), 200 (ranked branch) - and which is live depends on the
   startup profile. Every cap measurement in this arm therefore ran at
   `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`; without it this 48 GiB host measures
   128/64 and nothing about the ranked configuration.

None of this disturbs nezuko's revert. Restoring the value her in-tree comment
describes is correct housekeeping and, being a no-op on the partition, cannot
have cost anything.

## 5. The bonus: every M5 receipt on the ops axis is an A/A

Structural inertness has a consequence nobody has drawn yet. If
`MLX_MAX_OPS_PER_BUFFER` cannot change any executed work at any value ≥ 40, then
**every receipt that differs only in that knob is an A/A**, and the spread across
them measures ranked-host receipt noise rather than a mechanism.

There are five such trees already paid for.

**Tree X, `1feeabc8`.** Comment `5182398994` read its `ns +0.179% ± 0.172%` as
*"more likely the cap than the barriers"*. It can be neither: the ops half is
partition-identical by §3(a), and the barrier half has its own isolated public
receipt at `ns −0.070% ± 0.210%`. So X vs C0 is a contrast between two trees that
execute the same program, and `+0.179% ± 0.172%` at n=1 vs n=3 is a direct
**corroboration of the 0.243% 2σ floor** rather than evidence about the cap.

**The three public sweep receipts.** The #20 revert commit message says:

> Three public receipts sweep that knob (400, 240, 160) against the same frontier
> control: `T` is non-monotone and inside noise, while `S` gets worse in both
> directions from the shipped 200. The 400 receipt costs `S` +0.130%, which is the
> only mechanism story available for the `S` +0.236% regression the PR #12 tip
> carried.

160, 240 and 400 are all ≥ 40, so if those trees differ from the control only in
that knob - as the description states - **all three are A/A too**, and the
observed pattern is exactly the signature of noise: non-monotone `T`, and `S`
drifting in *both* directions from the centre. That is what four independent draws
from one distribution look like.

Two consequences, and the second one matters more than this arm:

1. `S +0.130%` on the 400 receipt **cannot be caused by the knob**, so it is not a
   mechanism story for the PR #12 tip's `S +0.236%` regression.

   **Retracted 2026-08-05 (self-correction under the advisor's metric rule).** The
   original wording here was "that regression is still unexplained and should be
   reopened". That is a sub-noise over-read and I withdraw it. My three
   bit-identical base free receipts give candidate `S` a 1σ of **0.2603%**
   (`research/m5-calibration/`, n=3: 97.6222 / 97.5129 / 97.9979 ms). The quoted
   `S +0.236%` is **below one standard deviation of a single `S` draw**, so the
   correct statement is that there is no evidence a regression exists at all. It
   needs no mechanism story and should not be reopened; it should be treated as
   one draw from the `S` distribution. Anyone who wants to know whether a real
   `S` shift of that size is present needs replicates, not an explanation.
2. Control + 160 + 240 + 400 + X is a **five-tree A/A family already paid for on
   the ranked host**. Anyone wanting an empirical ranked-host dispersion for `T`,
   `S` and `ns` - instead of the propagated 2σ floor - can read it straight off
   those receipts at zero cost. That is the most valuable by-product of this arm.

**The caveat, stated precisely.** My op counts are M4. The commit rule's inputs are
architecture-independent in principle - `buffer_sizes_` sums `array::data_size()`
and `buffer_ops_` counts dispatches - but the M5 selects `_nax` kernel variants
where available, and a variant could change the dispatch count per primitive. For
the conclusion to fail, the M5 would need **more than 5.7×** the ops per command
buffer inside the same 200 MiB byte window (28 → 161). I do not believe any kernel
substitution does that, but the free way to confirm it is to run
`research/frieren_cb_binding_sweep.sh` on the ranked host, and it needs no
receipt.

## 6. Timing on the live axis, and why no rerun was needed

The r2 brief asked for the cap contrast to be re-measured under the
position-balanced design, because the r1 `n=5` reading sat inside its own control
drift. Done before the cancellation, and it survives (full detail in the memo
§4-§7). All arms `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, 2000 steps/arm, 12
balanced positions (`A B B A | B A A B | A B B A`) plus a discarded warm-up arm.

| screen | contrast | estimate | t |
| --- | --- | ---: | ---: |
| decode, 3 ABBA blocks | 50 MiB vs shipped 200 | **−1.696% ± 0.175%** | −9.71 |
| same, within-block paired | | −1.696% ± 0.139% | −12.20 |
| same, OLS with linear position term | | −1.696% ± 0.178% | −9.52 |
| prefill, 3 ABBA blocks | 50 MiB vs shipped 200 | **+0.504% ± 0.324%** | +1.56 |
| three-level dose, ops fixed | 100 MiB vs 200 | decode −0.557%, prefill +0.313% | - |
| three-level dose, ops fixed | 50 MiB vs 200 | decode −1.757%, prefill +0.306% | - |

The decode contrast has complete separation (max B arm 8.9269 < min A arm 9.0024),
per-block differences of −0.1638 / −0.1690 / −0.1288 ms, and a fitted drift of
−0.0018 ms/position (se 0.0023) - so there is no drift left to explain it, and it
survived exactly the design the r2 brief asked for.

**Prefill at 50 MiB is bistable**, which is a different and worse problem than
being slower. Arm A is one tight mode (545.4-546.0, se 0.096 ms); arm B is two,
≈552.6 (+1.28%) and ≈544.3 (−0.22%), and arm p08 **flips between them at
repetition 11 inside a single process**. The floor is not the issue - +1.28% is a
prefill speedup of 0.987, far from 0.95 - the issue is that a receipt would sample
a mode rather than measure a value. The likely cause is in the commit rule itself:
`buffer_sizes_` charges each *distinct* MTLBuffer since the last commit, so which
arrays share a buffer depends on allocator reuse and therefore on process
allocation history. At 200 MiB the threshold sits far from the per-op referenced
total and layout cannot move a boundary; at 50 MiB it sits inside the
distribution. The same explanation covers why arm A is the *noisier* arm on decode
while arm B is tighter: on the small decode graph the tight cap commits so often
that placement is nearly deterministic.

**The uncomfortable part, stated plainly, because it argues against my own
recommendation.** Put through the ranked elasticities (`T` 0.638, `S` 0.362), the
local numbers clear the 0.61% bar in *every* prefill mode:

| prefill mode used for `S` | ΔS % | ΔT % | predicted `ns` % |
| --- | ---: | ---: | ---: |
| slow mode only (worst case) | +1.28 | −1.696 | **+0.62** |
| pooled mixture (measured mean) | +0.50 | −1.696 | **+0.90** |
| fast mode only (best case) | −0.22 | −1.696 | **+1.16** |

So the honest position is not "the local evidence is weak". It is: *the local
evidence is strong and I still do not think it should be bought*, for four
independent reasons - the mechanism most likely responsible (less driver residency
work per commit) disappears once the live set is wired, and this 48 GiB host never
wires; prefill is bistable at the tight cap, so a receipt samples a mode; the axis
is a partition knob, which the programme now prices negative in both directions;
and the receipt queue is one shared slot at ~1.7 receipts/hour for four students.
Any one of those would be a reason to wait. Together they are a reason to close.

Those screens used `MLX_MAX_OPS_PER_BUFFER=400` on both sides, because that was
the shipped value at the time. §3(a) proves the ops value changes no partition
statistic and no dispatch, so the old control and the new 200/200 control are the
same executed program, and the contrast stands against the current base without a
rerun. I confirmed that in the metric currency rather than by argument, with a
balanced A/A on the ops axis alone (`research/frieren_ops_aa.sh`, same design,
2000 steps/arm, 12 positions):

```
 pos arm   ms/step        pos arm   ms/step
   1   A    8.9535          7   A    8.9496
   2   B    8.9326          8   B    8.9461
   3   B    8.9492          9   A    8.9432
   4   A    8.9149         10   B    8.9565
   5   B    8.9217         11   B    8.9524
   6   A    8.9294         12   A    8.8908
```

| estimator | delta | uncertainty | t |
| --- | ---: | ---: | ---: |
| pooled means (A n=6 8.9302 se 0.0098, B n=6 8.9431 se 0.0054) | +0.144% | ± 0.125% | +1.15 |
| within-block paired (3 blocks) | +0.144% | ± 0.143% | +1.00, 2 df |
| OLS with linear position term | +0.144% | ± 0.130% | +1.10 |

Fitted drift −0.0008 ms/position (se 0.0017) - none. All three estimators agree at
`+0.144%` with `t ≈ 1`, i.e. **null**, as the partition data predicts. So the ops
axis is closed in the metric currency too, not only in cb/step.

This is also the calibration I wanted. **This harness's A/A noise floor at 2000
steps/arm over 12 balanced positions is ±0.13% (1σ), ≈±0.29% at 2σ.** The decode
cap contrast of −1.696% is 11.8× the A/A point estimate and `t = −9.71` against
`t = +1.15`, so §6's decode effect is not an artefact of the design. One honest
detail: the third block is the loose one (`B−A = +0.0375` against +0.0067 and
−0.0056), driven by `p12-A = 8.8908`, the lowest reading in the screen, whose
`cpu_user_ms_per_step` jumped to 0.1206 from the 0.062 baseline - i.e. host
activity, not the arm. Even taking the loosest block at face value the contrast is
null.

## 7. Head-region numbers, restated (r1 doctrine, unchanged)

At ranked parity, medians over 278 steady steps, 16,595 traced command buffers:

| quantity | value |
| --- | ---: |
| step entry → first cb commit (editable host work) | **35.7 µs** (se 0.8) |
| first commit → first GPU kernel start (driver/firmware) | **67.1 µs** (se 0.5; p10 61.9 / p90 83.4) |
| tail idle after call return | **0.0 µs at median and at p90** |

Frame: step 8834.4 µs, GPU busy 8533.1 (96.59%), total GPU idle 300.8 µs, owned as
122.1 trusted harness (IPC + the blocking `argMax().item()` at
`LagunaRuntimeBenchmark.swift:891`) + 67.1 driver/firmware + 75.9 GPU-side across
47 cb boundaries + **35.7 editable** + 0.0 drain. 88% is off the submission
surface. Host graph construction costs 2.51 ms/step while the encoding thread
runs 3.5× ahead of the GPU.

## 8. Correctness and the serial rule

`max_abs_diff = 0`. The scored surface (`Sources/`, `Vendor/`) is byte-identical
to `9a407ed6` - `git diff 9a407ed6 -- Sources Vendor` is empty - so identity is
definitional for the submitted content, and there is nothing left in the tree
that could move a token.

The verification record from the 50 MiB candidate this arm did build and then
revert, all at `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`:

- matched `--local-iterate` pair, candidate 50 MiB and control 200 MiB from the
  same binary: both `max_abs_diff = 0`, `passed_correctness true`, 130 checked
  steps, golden hash
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`;
- `--local-submit` preflight: `passed = true`, `max_abs_diff = 0`, decode
  0.009426 s/tok, prefill 0.001206 s/tok, peak RAM 21 GB;
- upstream-equivalence oracle, identical at **both** startup profiles: prefill
  `max_abs 0.125` / `mean 0.011933609`, decode-0 through decode-7 exactly 0,
  tokens 509/902/5991 all matching, `EQUIVALENCE_EXACT_STEPS=8`, exit 1 explained
  by zero tolerance applied to prefill - i.e. unchanged against the reference this
  arm established in r1;
- `swift test --force-resolved-versions`: **454 tests in 6 suites passed** (17.2 s,
  exit 0), re-run on the final tree after the instrumentation revert, then
  `git checkout -- Package.resolved`.

**Serial non-speculative rule.** Every measurement in this arm computed logits and
KV rows only for the token supplied in that invocation, advanced logical and
physical KV position by exactly the supplied input length, and left no pending
future token, logits, deferred cache row, or cross-request commit/rollback state.
The command-buffer cap changes only *where* MLX submits work that the current
invocation already enqueued; it does not enqueue anything for a token this
invocation was not given. The `FRIEREN_CBPROF` probe used for the binding sweep
was local-only research instrumentation in a non-editable file and has been
reverted; it is not part of the candidate.

## 9. Platform findings that constrain everyone's receipt planning

Learned by attempting the r2 family before it was cancelled, at zero receipt cost:

- `mlxfast submit` returns
  `{"error":{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}}`
  when a sibling holds the slot. The limit is **per account**, not per student.
- Retrying `submit` as a wait loop is a trap: it trips
  `Rate limit reached. Try again in 2809 seconds` - a ~47 minute lockout, longer
  than the queue wait it was trying to absorb. The safe pattern, now in
  `research/frieren_spend_receipts.sh`, is to poll the cheap listing endpoint and
  call `submit` only when no row reads `validating`, honouring any server-supplied
  retry-after.
- `mlxfast submit` accepts only `--note` / `--note-file` and `--model`; there is
  no way to reserve, queue, or pre-empt.

## 10. Conclusion

The cap is a **partition** knob: it changes where command buffers are cut, not
what arithmetic runs or what bytes are read. On the ops axis it is provably inert.
On the byte axis it is live, and this host's local optimum is at a *smaller* cap
than shipped - measured in a regime the ranked host does not occupy, since
`wireResidentWeightsIfEnabled()` requires ≥ 96 GiB
(`LagunaRuntimeWeights.swift:549`) and this 48 GiB host never wires - with a
prefill cost that is bistable rather than small. The programme rule that came out
of r1, *change bytes or arithmetic, not partition*, now has a fourth data point in
its favour, and this is the wrong mechanism to spend a shared receipt slot on.

**Recommendation: close the cap parameter.** Record 200 MiB / 200 ops as
correct-as-shipped, record `MLX_MAX_OPS_PER_BUFFER` as structurally inert at any
value ≥ 40 so nobody sweeps it again, and treat the 40 MB figure as an arch
default rather than an effective threshold.

### Follow-ups I did not implement

1. **`MLX_BFS_MAX_WIDTH = 50` against MLX's default of 20** (`utils.h:174`) is
   still unmeasured and is explicitly out of scope for this arm. It is *not* a
   partition knob in the same sense - it changes graph traversal width, which can
   change fusion and therefore bytes - so it does not fall under the rule that
   retires the cap. It is the one item in this neighbourhood I would still test.
2. **The 19-cb rung is the interesting anomaly, not the 127-cb one.** At 400 MiB
   the encoding thread's CPU cost jumps to 4.83 ms/step from 2.50 at 200 and 3.13
   at 40. Per-commit work is cheap; something per-buffer is not, and it is
   superlinear in buffer size. If anyone wants to understand why command-buffer
   size costs the host anything at all, that rung is where the signal is.
3. **The in-tree cap comment is spliced.** `LagunaRuntimeWeights.swift:370-380`
   opens a sentence about a "512 MiB budget" that "fits one complete decode layer
   (attention plus the routed/shared gate-up and down banks are ~507 MiB for the",
   which then runs straight into the 200 MiB / 200-op provenance note. Two edits
   collided and the surviving text argues for a value that is not set. Worth one
   comment-only cleanup by whoever owns that file next, and worth not quoting
   until then.
