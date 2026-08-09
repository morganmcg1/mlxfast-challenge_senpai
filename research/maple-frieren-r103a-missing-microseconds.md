# R103-A — reproduce the missing ~19 µs/step off-M5 and localise it to a kernel

Student: maple-frieren · PR #571 · branch `maple-frieren/r103-missing-microseconds-localize`
Assignment `maple-r103-a-missing-microseconds-localize`, revision `r103-a-rev1`
Base `0f6862d099252d40a807df30abfbbd7c9cd596ae`

Measurement host: **Apple M4 Pro**, 14 CPU, 48 GiB unified memory, peak memory
bandwidth **266.3 GB/s** (M5 Max reference: 610 GB/s measured / 614 GB/s
nominal). The ranked host is M5 Max; every number below is off-M5 evidence and
is labelled as such.

---

## § 1 Preregistration

**Written and committed before any timed run.** Commit history is the proof:
this section is committed in isolation, ahead of the build and timing commits.

### 1.1 The quantity under test

Two official receipts bracket the round-100 frontier adoption plus the three
restorations that followed it:

| | revision | receipt | decode µs/step | prefill µs/token |
|---|---|---|---|---|
| OLD | `30f752df` (merge of PR #481) | `7ce1262d` | 4893.712 | 188.043 |
| NEW | `0f6862d0` (this assignment's base) | `e08d759f` | 4913.117 | 187.857 |

The published decode metric is not the marginal step. The teacher-forced decode
axis is a 512-token seed prefill `S` followed by 128 one-token steps `T`, and
the reported figure is `(S + 128·T)/128 = S/128 + T`. Using the prefill axis to
price `S = 512 × prefill_µs_per_token`:

```
S_old  = 512 × 188.043 = 96,278.0 µs      S_old/128  =  752.172 µs
S_new  = 512 × 187.857 = 96,182.8 µs      S_new/128  =  751.428 µs

T_old  = 4893.712 − 752.172 = 4141.540 µs/step
T_new  = 4913.117 − 751.428 = 4161.689 µs/step

ΔT     = T_new − T_old      = +20.149 µs/step
ΔT/T_old                    = +0.4865 %
```

The reported decode delta is +19.405 µs/step, and prefill actually *improved*
(ΔS = −95.2 µs, worth −0.744 µs/step on the decode axis). Removing that prefill
credit shows the regression concentrated in the marginal step is **larger** than
the headline: **+20.149 µs/step, +0.4865 % of the OLD steady step**. This is the
quantity R103-A must reproduce. Prefill is explicitly *not* under test — the
frontier is already ahead of Arm R there.

### 1.2 Revisions

* **OLD** `30f752df` — confirmed present in this checkout, `git cat-file -e` OK.
* **NEW** `0f6862d0` — the assignment base; the branch head `657e9ba5` carries an
  empty diff against it (assignment metadata only), so the working tree already
  *is* NEW.
* 318 commits separate them. Fallback anchors if OLD refuses to build, in
  order: `74e89d71` → `e510bb3d` → `6ada66c9`. `74e89d71` and `6ada66c9` are
  ancestors of OLD; `e510bb3d` is not, and using it would change the contrast's
  meaning, so it is a last resort and would be reported as such.

### 1.3 Instrument and why not `--local-iterate`

`./benchmark.sh --local-iterate` reports `S/128 + T`, so it dilutes the effect
under test with a prefill axis that moved the other way, and it costs a thermal
gate per measurement. The instrument is instead
`research/decode_probe.py` steady-step wall time against snapshotted worker
binaries: it measures `T` directly, drops step 0, and is teacher-forced against
`correctness_prompts/public_longcopy_gate_english_512_256.json` (512 prompt
tokens, 256 expected tokens). At `--steps 250` every step is teacher-forced
(the probe free-runs only past index 254), so the token stream is fixed by the
fixture and identical across arms by construction.

Both arms run the **shipped** runtime end to end. Consequences:

* **Rule 77** (reproduce shipped dispatch geometry and name it) is satisfied by
  construction — the geometry is whatever `LagunaRuntimeModel.swift` dispatches
  in each revision, not a re-authored harness. Rung 2 names the geometry per
  kernel from the in-situ census.
* **Rule 71** (SLC-resident *and* SLC-defeat modes) is satisfied by
  construction for an in-situ measurement: the working set is the real
  21.6 GB resident text tower, which is neither an artificially SLC-resident
  microbenchmark footprint nor an artificial SLC-defeating one. No synthetic
  footprint is introduced at either rung, so there is no second mode to run.
* **Rule 80** (bandwidth always divided by host peak in the same sentence) —
  rungs 1 and 2 report wall time, not bandwidth. If any GB/s figure appears it
  will carry `÷ 266.3 GB/s` in the same sentence.

### 1.4 Design: 4-slot position-matched ABBA with an embedded null

Four snapshotted binaries per repetition:

```
SLOTS = [oldA, old, new, oldB]
order = SLOTS  if rep is even  else  reversed(SLOTS)
```

`oldA` and `oldB` are **byte-identical copies of the OLD binary**. Over any even
number of repetitions:

| arm | positions occupied | mean position |
|---|---|---|
| `old` | {2, 3} | 2.5 |
| `new` | {3, 2} | 2.5 |
| `oldA` | {1, 4} | 2.5 |
| `oldB` | {4, 1} | 2.5 |

So the **real contrast** `new − old` is position-matched on the two *interior*
slots, and the **rule-79 identical-code null** `oldB − oldA` is position-matched
on the two *exterior* slots, in the same session, sharing the same drift.

The asymmetry is deliberate and is declared here: exterior slots absorb more
session drift than interior ones, so the null is a **conservative upper bound**
on the noise floor that applies to the real contrast. A null that is tight
therefore certifies the real contrast; a null that is wide does not by itself
condemn it, and that case will be reported rather than spun.

`REPS = 26`. The **first two repetitions are discarded** (one full even/odd
cycle, so the discard cannot unbalance position matching), leaving
**K = 24 paired observations** for each of the real contrast and the null —
above the K ≥ 16 floor. `--steps 250` per slot.

### 1.5 Preregistered thresholds — fixed now, not after seeing data

**Precision target.** Paired 95 % CI half-width on the real contrast
**< 8 µs/step**. The achieved half-width is reported whatever it is; if it lands
≥ 8 µs/step that is stated as a power failure and the verdict is downgraded
accordingly, not quietly widened.

**Decision rule** on `ΔT_M4 = mean(T_new − T_old)`, 95 % CI from the paired
t-distribution on K = 24 pairs:

| # | condition | verdict | action |
|---|---|---|---|
| 1 | point estimate ≥ **+20.0 µs/step** *and* CI lower bound > 0 | reproduced off-M5 | proceed to rung 2 |
| 2 | CI **upper** bound < **+20.0 µs/step** and CI upper bound > 0 | does not transfer at M5 magnitude → M5-specific | **report and stop** |
| 3 | CI upper bound < 0 | sign flip, NEW faster on M4 | **report and stop** |
| 4 | CI contains +20.0 but point estimate < +20.0, or CI contains 0 while spanning +20.0 | underpowered | report as **inconclusive-underpowered**; no rung 2 |

Outcome 4 exists so that an ambiguous CI cannot be argued into outcome 1 after
the fact.

**Secondary read (relative transfer).** The M5 effect is +0.4865 % of the steady
step. `T_old` on M4 is not yet known, so the relative equivalent of the 20 µs
bar cannot be fixed in absolute terms in advance; the *relative* effect
`ΔT_M4 / T_old_M4` and its CI are reported alongside, and compared with
0.4865 %. This is a descriptive companion, **not** a second chance at outcome 1:
the primary decision uses the absolute +20.0 µs/step bar from the assignment
exactly as written. If the two disagree — e.g. the absolute bar is missed but
the relative effect matches M5 — that disagreement is reported as the finding.

### 1.5a Addendum — per-slot statistic (declared before any timed run)

§ 1.3 said only "drops step 0". Fixing the rest of the estimator now, before
any timing data exists, so it cannot be chosen to suit the answer:

* **Primary per-slot statistic: the median of steps 1 … 249** (0-indexed;
  step 0 is the first decode after the seed prefill and is not a steady step).
  The median is used because a decode slot is occasionally interrupted by the
  OS, and a single 50 ms outlier moves a 250-sample mean by 200 µs — two orders
  of magnitude above the effect under test.
* **Declared secondaries, reported alongside whatever they say:** the 10 %
  trimmed mean and the raw mean over the same window.
* The preregistered outcome in § 1.5 is decided on the **median** contrast. The
  secondaries are reported for transparency and any disagreement between them
  is reported as a finding, not resolved by picking a favourite.

This addendum is committed after the rung-0 build and before the rung-1 timing
job starts; the commit order is verifiable from history.

### 1.5b Addendum — retained one-time-cost diagnostics (declared before any timed run)

An independent design critique pointed out a real blind spot in § 1.3: a
fresh worker process per slot plus a steady-state estimator plus discarded
warm-up repetitions is a design that *cannot see* a one-time in-window cost.
That matters, because one of the candidate mechanisms for the M5 regression is
exactly that: `ΔT × 128 = 2.58 ms`, which is the order of a handful of extra
Metal pipeline creations or a JIT compile inside the timed window. Under the
§ 1.5 estimator such a mechanism reads as a clean null, and a clean null would
then be over-interpreted.

The design is not changed — the outcome rule still runs off the steady median,
and the warm-up repetitions are still excluded from the verdict. What is added
is that the discarded data is **kept and reported**:

* **`step0`** — the first decode step of each slot, paired the same way.
* **`mean_first128`** — the mean of steps 0 … 127, which mirrors the window the
  official harness actually times, so a one-time cost that the official metric
  amortises over 128 steps appears here at the same dilution.
* Both contrasts are additionally reported over the **discarded warm-up
  repetitions** and over **all repetitions**, not only the analysed ones.

These are diagnostics, not decision variables: they do not enter § 1.5 and
cannot change the outcome code. Their purpose is to stop a null on the steady
median from being written up as "there is nothing here" when the instrument was
never able to see a one-time cost in the first place. The corresponding
analyser change is committed before the rung-1 timing job starts.

The 40-step pipeline smoke test run before this commit is validation of the
driver and the parser only. Its numbers back no verdict and are not used
anywhere in §§ 3–6.

### 1.6 Rung 0 gates (a failure here stops everything)

* **G0.1 build** — both revisions build a `mlxfast-runtime-worker`.
* **G0.2 token parity** — `--dump-tokens` output byte-identical between OLD and
  NEW over 250 teacher-forced steps, and zero teacher-forcing divergences
  reported by either arm. A parity failure means the two trees are not
  computing the same thing and the timing contrast is meaningless.
* **G0.3 distinct binaries** — the OLD and NEW worker binaries must not be
  byte-identical (that would mean the swap silently failed).
* **G0.4 rule 75 working-set digests** — sha256 over the full `Sources/` +
  `Vendor/` tree published before and after every timed run, and the digest must
  round-trip to its NEW value after the OLD checkout is restored.
* **G0.5 metallib** — the AOT metallib is rebuilt at OLD into a scratch path and
  its sha256 compared with NEW's. If identical, one metallib serves both arms
  and that fact is published; if different, each arm carries its own.

### 1.7 Rung 2 (only if outcome 1)

Reuse `research/maple-nezuko-r100c-census.sh` /
`research/maple_r89_insitu.py` — the PR #558 position-matched in-situ per-kernel
census, resolution ±0.43 µs/step/kernel. Not re-authored. Deliverable: one table
of µs/step at OLD and NEW, paired diff, 95 % CI, sign counts, sorted by |diff|,
followed by the **reconciliation residual** `ΔT_e2e − Σ(per-kernel diffs)`.

### 1.8 Preregistered nulls

* **N-1 receipt noise.** The +19.405 µs/step M5 headline is a difference of two
  single receipts. Verdict from the rung-1 null and from the known receipt
  spread; if the M5 delta is inside receipt noise the whole target is a ghost.
* **N-2 thermal / session drift.** Verdict from the rule-79 identical-code null
  CI. If the null CI excludes 0 with magnitude comparable to the real contrast,
  drift contaminates and the real contrast is not trustworthy.
* **N-3 diffuse.** If the rung-2 reconciliation residual exceeds 50 % of the
  rung-1 e2e delta, the cause is diffuse rather than one kernel → hand to
  fern R103-D.
* **N-4 the vendored comment carve** `f720e9e7` (176,468 B, nezuko's R103-C).
  Confirmed **inside** the OLD→NEW range (`f720e9e7` is an ancestor of NEW and
  not of OLD), so rung 1 measures it bundled with everything else. A static
  pre-read is in § 2 below and constrains what N-4 can possibly explain.

### 1.9 Non-negotiables carried from the assignment

* **Zero submitted bytes.** Nothing under `Sources/`, `Vendor/`, or
  `benchmark.json` on the merged branch. Probe scaffolding lives in `research/`
  and any patch applied to build an arm is reverted before timing, with the
  rule-75 digest proving it.
* **Zero official receipts consumed.**
* First leg discarded (here: the first two repetitions).
* K ≥ 16 dispatch replicates.
* Do **not** design or land a fix. R103-A localises; it does not repair.

### 1.10 Stopping rule

Stop at the first of: (1) rung-1 outcome 2, 3, or 4; (2) rung-2 table published
with its reconciliation residual; (3) rung 0 blocked after exhausting the
fallback anchors.

---

## § 2 Static pre-read of the OLD→NEW delta (no timing)

This was completed before any build and it materially narrows N-4. Method: for
every file differing between `30f752df` and `0f6862d0`, strip comment lines and
re-diff, counting only non-comment changed lines.

### 2.1 The vendored surface is comment-only

| surface | files | non-comment changed lines |
|---|---|---|
| `Vendor/mlx-swift/.../backend/metal/kernels/*.metal`, `*.h` (`arg_reduce`, `binary`, `gemv`, `rms_norm`, `rope`, `scaled_dot_product_attention`, `sdpa_vector.h`) | 7 | **0** |
| `Vendor/mlx-swift/.../{jit_kernels.cpp, kernels.h, quantized.cpp, matmul.cpp}` | 4 | 68 lines, **all** trailing/inline comment removals |
| `Vendor/mlx-swift-lm/.../MLXLMCommon/*`, `MLXLLM/Models/Laguna.swift` | 12 | **0** semantic |
| `Sources/MLXFastModel/LagunaConfig.swift` | 1 | **0** semantic |

The 68 "non-comment" lines in the four C++ files are an artefact of line-based
comment stripping, not real edits — each is a comment amputated from a code
line: `} // namespace` → `}`, `int ndim /* = -1 */,` → `int ndim ,`, the
`case 1..5` bm/wm annotations in `quantized.cpp`, and
`int swizzle_log = 0; // tm >= 6 ? …` → `int swizzle_log = 0;`.

**Consequence for N-4.** The carve cannot change AOT codegen (the `.metal`/`.h`
sources are unchanged after comment stripping, so the metallib is a
byte-for-byte question settled by gate G0.5) and cannot change host dispatch
semantics. Its only possible timing channels are (a) JIT source-string bytes
and therefore JIT cache keys, and (b) binary/code layout. Both are diffuse
mechanisms, which points N-4 at N-3 rather than at a single kernel.

### 2.2 `Sources/MLXFastTransform` does not touch the weights

`AffineMetadataCoding.swift` and `TiedHeadMetadataCoding.swift` are new, and
`Transform.swift` gains 55 lines, but the new sidecar generation is gated to
`case .gemma4`; `case .laguna` emits nothing. The 20 GB `weights/` tree is
therefore identical across the two arms and needs no rebuild — only code layout
can differ.

### 2.3 The one substantive surface is `Sources/MLXFastModel`

```
Sources/MLXFastModel/LagunaConfig.swift            +6    −1
Sources/MLXFastModel/LagunaRuntimeLayers.swift      0 −2597
Sources/MLXFastModel/LagunaRuntimeModel.swift   +2784   −17
```

OLD carries `LagunaRuntimeLayers.swift` (2597 lines) beside
`LagunaRuntimeModel.swift`; NEW merges them into one file. To separate the
merge from real edits, both sides were reduced to sorted multisets of
comment-stripped, whitespace-normalised code lines: OLD 9205 lines, NEW 9354,
with 197 differing (173 NEW-only, 24 OLD-only).

**The 24 "OLD-only" lines are re-wrapping artefacts, not removals.** Every
symbol they mention has an identical occurrence count in both revisions:

| symbol | OLD | NEW |
|---|---|---|
| `lagunaDecodeEmbeddingRoPEAtlas` | 4 | 4 |
| `lagunaRoPEAngleAtlasLength` | 13 | 13 |
| `lagunaTerminalPrefillFusionEnabled` | 2 | 2 |
| `lagunaResidualRMSNormRouterSource` | 2 | 2 |
| `lagunaResidualRMSNormRouterKernels` | 2 | 2 |
| `lagunaRouterPrecomputedKeysEnabled` | 10 | 10 |

So **nothing that OLD had was dropped**. This kills the most attractive naive
hypothesis — that frontier adoption deleted an Arm R optimisation and nobody
restored it.

**What NEW adds** (0 occurrences in OLD):

| symbol | NEW | what it is |
|---|---|---|
| `pipe_kc`, `pipe_kd`, `piped_score0`, `pipec_*` | 10 / 8 | embedded-MSL 4-way pipelined attention inner loop |
| `prefetchGroups`, `prefetchEarly`, `prefetchLate` | 7 / 2 / 2 | router weight-prefetch splice points |
| `armSuffix` | 2 | JIT kernel-name arm suffix |

and correspondingly the SDPA-vector inner loop goes from
`for (; i + BN < N; i += 2 * BN)` in OLD to
`for (; i + 3 * BN < N; i += 4 * BN)` in NEW, with a
`[0, 1, 5].map { prefetch -> (Int, MLXFast.MLXFastKernel) in` slot map building
three prefetch arms.

**This inverts the framing of the task.** The missing ~19 µs/step is not
subtraction — NEW contains *more* machinery than OLD in exactly the decode
attention and router paths. Candidate mechanisms therefore become: the 4-way
pipelined attention loop being slower than OLD's 2-way loop at the decode
shape (one query row, sliding window ≤ 512); a prefetch arm default selecting a
worse variant; or extra JIT variants inflating specialisation/dispatch cost.
Rung 2's per-kernel census is the right instrument to choose among these, and
rung 1 must first establish that the effect exists off-M5 at all.

Caveat recorded before timing: the `[0, 1, 5]` prefetch slot map and `armSuffix`
originate in #558's env-var arm scaffolding, so some of this NEW-only content is
research selection machinery rather than a changed default. Rung 2 must not
attribute cost to an arm that the shipped default never selects.

### 2.4 Kernel reachability on the M4 host (rule 77) — settled statically, before timing

Rule 77 and `AGENTS.md` both warn that an M4 Pro reports Apple GPU generation 16
and therefore does not select the `_nax` kernels the ranked M5 uses. If the
NEW-only machinery were behind an architecture gate, an M4 null would be
uninformative — it would only say "this host does not run the changed code".
That had to be settled *before* the timing job, not after, so it could not be
used to explain away an inconvenient result. It was, and the answer is clean:

* **`LagunaRuntimeModel.swift` contains exactly one GPU-architecture branch**,
  `lagunaExpertAlignedGatherEnabled` (`:253-265`), resting on the file's only
  `GPU.deviceInfo()` call (`:262`) via `lagunaNAXAvailable` (`:242-247`,
  `generation >= 17`). On this M4 Pro it evaluates **false**.
* **Its every consumer is prefill-only.** `lagunaFusedSortedRoutedGateUp`
  (`:10527`, arch use at `:10578`) is called under `x.dim(1) > 1` (`:10981`);
  the packed-scale views (`:10753`, `:10766`) are consumed only in the
  `x.dim(1) > 1` branch (`:10989-11009`). Nothing on the one-row decode path
  changes as a function of architecture.
* There is no `supportsFamily`, no `deviceName`, and no literal `_nax` test in
  the file.

So the three NEW-only mechanisms are all reached on this host with no env
overrides:

| mechanism | gate | on M4 decode? |
|---|---|---|
| 4-deep pipelined ring, `laguna_sliding_fused_attn_ring_v1` (`:1639`) | `DARKBLOOM_FUSED_SLIDING_ATTN != "0"` (default ON) + `B==1 && L==1` + `isSliding` + `nHeads==64` + `RotatingKVCache(maxSize:512)` with `offset >= 512` | **yes**, from decode step 1 |
| router weight-prefetch peel + `armSuffix` | `DARKBLOOM_ROUTER_ROWS_PER_GROUP` (default 8) → `rowsPerThread==1`; `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` (default 1) | **yes**, `_pf1` arm |
| `DARKBLOOM_NVFP4_NIBBLE_SPLIT` nibble form (`:6653`, default 1) | env only | **yes** |

Three consequences for how rung 1 may be read, all fixed before the data exists:

1. **A null on M4 is informative.** It cannot be dismissed as "wrong kernel
   family" for these mechanisms. It remains uninformative about anything
   `_nax`, but § 2.1 and gate G0.5 already showed the AOT surface — where the
   `_nax` variants live — is byte-identical across OLD and NEW, so no `_nax`
   kernel *changed* in this range.
2. **The prefill/decode asymmetry now has a named candidate.** The 4-deep ring
   is guarded by `B == 1 && L == 1`; it is structurally unreachable during
   prefill, and it applies to the 30 sliding layers only, not the 10 full-
   attention layers (whose twin `laguna_full_fused_attn_grow_v1` `:2027` still
   uses the 2-deep loop `:2168`). A decode-only regression alongside a prefill
   *improvement* is exactly the shape this predicts. That is a hypothesis for
   rung 2 to test, not a conclusion.
3. **One candidate mechanism is downgraded before it is measured.**
   `armSuffix` (`:1127`) is evaluated inside the eager kernel-table build at
   `:1120-1146`, not per dispatch; the decode path does a dictionary lookup
   `lagunaResidualRMSNormRouterKernels[rowsPerGroup * 8 + prefetch]!`
   (`:1223-1224`). So "extra per-dispatch host cost from the variant
   machinery" is not supported by the code and should not be offered as an
   explanation. What the `[0, 1, 5]` map *does* add is a table of **21** kernels
   where OLD (`30f752df:1038-1050`, keyed on `rowsPerGroup` alone) had **7**.
   That is a construction cost, and because a Swift file-scope `let` is
   initialised lazily on first access it is paid inside the process, not at
   load. It is nonetheless unlikely to be the decode mechanism: the same table
   is used by the terminal-prefill row (`:11268`), so first access precedes the
   decode window — and prefill *improved* over this range. The § 1.5b step-0 and
   first-128 diagnostics are what would show otherwise.

Caveat kept: this is a static read of the gating, cross-checked against the OLD
tree (`armSuffix`, `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, `pipe_kc`,
`for (; i + 3 * BN < N;` all have zero occurrences at `30f752df`). It is not a
runtime trace. The `--profile` hook (`research/nezuko-pr158-gpuprof-hook.patch`)
is deliberately not applied to these snapshots, because applying it would edit
the submitted surface of both arms and break the clean OLD/NEW contrast.

---

## § 3 Rung 0 — build and parity

Driver `research/maple-frieren-r103a-build-arms.sh`, run as job
`52c9ddb2-4658-4d33-b80b-632279af2f6c`, exit 0, 165 s wall. Full log kept at
`/tmp/maple-r103a/rung0-provenance.txt`; the load-bearing lines are reproduced
below verbatim.

### 3.1 Gate results

| gate | what it asserts | result |
| --- | --- | --- |
| G0.1 | both arms build the scored worker product | **PASS** — NEW 83.33 s, OLD 68.98 s, both `Build ... complete!` |
| G0.2 | teacher-forced greedy tokens identical across every slot | deferred to rung 1 (checked on all 104 slots, § 4.1) |
| G0.3 | the two arms are genuinely different binaries | **PASS** |
| G0.4 | rule-75 digest round-trip: the tree returns to HEAD | **PASS** |
| G0.5 | AOT `mlx.metallib` identical across arms | **PASS** |

```text
digest_head           = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
digest_at_new_build   = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
digest_at_old         = 82f0f5a86ed1426d5339933975181904319d84ca6013bc353f688e4bd9b38db8
digest_after_restore  = c3fafd30b4fdba6d3058746e79a715a53a072c5d5c77b0716a3a73dbd385f492
```

The digest is `find Sources Vendor -type f -print0 | sort -z | xargs -0
shasum -a 256 | shasum -a 256`. It is taken before the NEW build, after the
`git checkout 30f752df -- Sources Vendor`, and after the restore. The first and
last agree, so the checkout of OLD over the submitted surface left nothing
behind: **the branch's submitted bytes are unchanged by this experiment**, which
is the non-negotiable the assignment is strictest about.

### 3.2 Snapshots

```text
32d0a3d4ce245a2d70ea55852f549cd9461f1e21c334b069913691b597881ddb  new/mlxfast-runtime-worker   49,190,344 B
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  old/mlxfast-runtime-worker   49,094,856 B
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  oldA/mlxfast-runtime-worker
d36a981fc38ec0576f809aec4fd2021f67006b803a94270d0eb0cfa4a41a911e  oldB/mlxfast-runtime-worker
8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec  {new,old,oldA,oldB}/mlx.metallib
```

`oldA` and `oldB` are `cp` copies of `old`, not rebuilds: the § 1.4 null arm has
to be byte-identical code, and rebuilding it would let build nondeterminism
leak into the very quantity the null is supposed to bound.

### 3.3 What G0.5 buys

`mlx.metallib` is the ahead-of-time compiled Metal library — RoPE, RMSNorm, SDPA
vector, `arg_reduce`, and the rest of the AOT surface. It is **byte-identical**
across the two arms. Together with § 2.1 (every changed `.metal`/`.h` file is
comment-only) and § 2.2 (the transform emits nothing for Laguna, so the ~20 GB
`weights/` tree is bit-identical), this narrows the causal surface hard:

> Whatever the ~20 µs/step is, it is produced by **Swift host code and the Metal
> shader sources embedded as Swift string literals in
> `Sources/MLXFastModel/LagunaRuntimeModel.swift`, JIT-compiled at runtime** —
> not by the AOT kernels, not by the weights, and not by the vendored runtime.

The 95,488-byte difference in executable size is consistent with that: the
NEW binary carries the longer embedded shader sources and the wider variant
table of § 2.3.

### 3.4 A caveat G0.5 does *not* remove

Identical AOT metallibs do not imply identical *JIT* products. The embedded
shader strings differ, so the runtime-compiled pipelines differ by
construction; that is the intended contrast, not a confound. It does mean the
first-touch JIT compile cost differs between arms, which is exactly why § 1.5b
carries `step0` and `mean_first128` as separate diagnostics and why the
decision statistic is a median over steps 1…249.

## § 4 Rung 1 — paired ABBA e2e decode on M4

_Pending._

## § 5 Rung 2 — position-matched per-kernel census

_Pending (gated on rung-1 outcome 1)._

## § 6 Verdicts on N-1 … N-4

_Pending._

## § Reply

_Pending._
