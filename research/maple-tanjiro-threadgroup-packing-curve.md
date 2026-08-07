# Decode QKV-GEMV threadgroup-packing curve

PR #308 · branch `maple-tanjiro/threadgroup-packing-curve` ·
base `63ab67c888e1892086b7b5b623de4dd0ebe68c90`

Host: Apple **M4 Pro**, 14 CPU, 48 GiB (low-memory startup profile),
macOS 26.5.2, Apple GPU generation **16** (no `_nax` kernels).
Every number below is an **M4 Pro** number. Nothing here is a ranked-M5 claim.

W&B: [`tanjiro-pr308-threadgroup-packing-curve`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/8st0k26f)
(run id `8st0k26f`) — per-arm table, adjacent-step table, pre-registered
contrasts, and the decision keys.

**Headline.** The packing curve is a **shallow basin, not a step and not
monotone**: `S ∈ {1, 2}` flat, bottom at `S ∈ {4, 8, 16}`, partial recovery at
`S = 32`. M4 argmax `S = 8` at **−36.9 µs/step (95 % CI [−61.0, −12.9])**,
statistically tied with `S = 16` (`R - G` = +3.6, CI [−20.5, +27.6]). PR #298's
`S = 16` point replicates to within 2 µs. Prefill is a measured null. Bit-exact
at every `S`, with a load-bearing fault-injection control. **Recommended ship
without an M5 run: `S = 8` (§5.3), not the raw argmax** — and no ranked claim is
made.

---

## 0. Corrections to the assignment before any measurement

These matter because they change what the experiment *is*.

### 0.1 The knob does not exist in `Sources/`. Stage 0/1 is not a zero-source-edit sweep.

The assignment says to sweep `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS`, and
describes it as an existing control. It is not:

```
$ grep -rn "SIMDGROUPS" Sources/
(no output)
```

The identifier appears at the assignment base only inside an **unapplied**
research patch, `research/nezuko_pr48_deconfound.patch` (369 lines, 16,815 B),
which PR #298 used and never landed. So the −35.4 µs/step PR #298 result was
measured through a patched worker, and reproducing or extending it *requires*
applying a patch and rebuilding. Any plan that treats this sweep as
"flip an env var against the shipped binary" is wrong.

I did not reuse nezuko's patch. It bundles the packing knob together with the
folded-norm prologue (`DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`), which is exactly
the confound PR #298 spent eight runs per arm untangling, and the fold is also
the thing that would make threadgroup memory scale with `S`. Instead I wrote a
78-line single-axis knob, `research/tanjiro_packing_geometry.patch`, that
changes nothing but the packing geometry.

**State of `Sources/` at the PR tip.** The knob is landed as an *unapplied*
patch. Per standing rule 11 nothing temporary stays in `Sources/` at the tip, so
`git diff 63ab67c8 -- Sources/` is empty at the final commit and
`senpai/check-editable-budget.sh` reports `growth=0`. During the session
`Sources/` did carry the applied knob — with a `_sg\(S)` kernel-name suffix, so
even the `S=2` build is named `…_sg2` rather than the stock name. That renaming
is why every arm in Stage 1 gets its own compiled pipeline instead of silently
sharing the cached `S=2` one, and it is also why the `S=2` arm is a legitimate
reference: §1.2 shows the `S=2` dispatch is bit-identical to the stock one.

**Reproduction.** The three patches apply cleanly to base `63ab67c8`, verified
with `patch -p1 --dry-run` against `git show 63ab67c8:Sources/MLXFastModel/…`:

| patch | applies to | purpose |
|---|---|---|
| `research/tanjiro_packing_geometry.patch` | base | the `S` knob alone — used for all Stage 1 timing |
| `research/tanjiro_packing_probe.patch` | base | knob **+** `PACKPROBE` geometry instrumentation (Stage 0) |
| `research/tanjiro_packing_fault.patch` | base **+ geometry** | corrected fault injection (§3.2) |
| `research/tanjiro_packing_default_flip.patch` | base | Stage 3 default flip to `S=8`, **+29 bytes** (§7.2) |

Full sequence, from a clean checkout of `63ab67c8`:

```bash
patch -p1 < research/tanjiro_packing_geometry.patch
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

bash research/tanjiro_packing_stage0.sh /tmp/pk/stage0          # reachability + geometry
bash research/tanjiro_packing_gate.sh   /tmp/pk/gate            # golden gate, every S
bash research/tanjiro_packing_abba.sh   /tmp/pk/abba   4 200    # Stage 1, 48 scored runs
python3 research/tanjiro_packing_stats.py /tmp/pk/abba          # curve + contrasts
python3 research/tanjiro_packing_stats.py /tmp/pk/abba --trim 0.05
python3 research/tanjiro_packing_wandb.py /tmp/pk/abba          # W&B record

PREFILL=1 ARM_SEQ="0 R R 0" bash research/tanjiro_packing_abba.sh /tmp/pk/prefill 2 8
python3 research/tanjiro_packing_prefill_stats.py /tmp/pk/prefill
```

Stage 1 took **2305 s** (48 scored runs + 1 discarded warm-up); the prefill arm
took **393 s**. The fault control needs the extra patch and inverted expectation:

```bash
patch -p1 < research/tanjiro_packing_fault.patch   # on top of geometry
# rebuild worker, then
EXPECT=fail ARMS="2 16 1" bash research/tanjiro_packing_gate.sh /tmp/pk/fault
```

`research/tanjiro_packing_stats.py` deliberately does **not** reimplement the
statistics: it `importlib`-loads `research/nezuko_pr48_stats.py` and overrides
only the arm labels, the pre-registered contrast list, and the curve verdict.
The OLS, block model, `t95`, trimming, and outlier rule are the shared,
previously reviewed code.

### 0.2 `S=1` is a real arm here; under nezuko's patch it was a silent no-op.

nezuko's validator accepts only `[2, 4, 8, 16]`, so `S=1` silently falls back to
`2`. The assignment lists `1/2/4/8/16` as the sweep. My knob accepts
`[1, 2, 4, 8, 16, 32]`, and Stage 0 below proves that `S=1` and `S=32` both
reach the kernel with the encoded geometry they claim. Had I inherited
nezuko's patch, the `S=1` arm would have produced a perfect statistical tie
with the default for the uninteresting reason that it *was* the default.

### 0.3 Minor: the fold flag's real name

The assignment writes `DARKBLOOM_DECODE_NVFP4_QKV_R1_NORM_QKV_FUSE`. The actual
variable in nezuko's patch is `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`. My driver
pins the correct name to `0`.

### 0.4 The assignment's fault injection is a semantic no-op. I had to redesign it.

The assignment asks for "an off-by-one row mapping". I implemented the literal
version first —

```
uint out_row = tile * num_simdgroups + ((simd_gid + 1) % num_simdgroups);
```

— and the public 64-step golden gate **passed** it at both `S=2` and `S=16`
(training `6a499c27-b0bf-43b1-b6a9-70e750b707df`). That is not a broken
tripwire. It is a correct verdict on a patch that does nothing.

In this kernel `out_row` is the *only* row identity. It gates the weight-code
pointer, the scale-nibble read, the scale-base read, the weight-scale read, and
the output store `projected[out_row]` — all five together. So any **bijection**
over `out_row` still computes every row exactly once from that row's own weights
and writes it to that row's own output slot. Rotating `simd_gid` inside a
threadgroup is a bijection. It is literally identity on the output.

The corrected fault (§3) keeps every *read* on the true `out_row` and rotates
only a new `store_row` used at `projected[store_row]`. That desynchronises read
row from write row, which is the row-mapping mistake a repack can actually make,
and it stays in bounds so the gate has to catch a wrong *answer* rather than an
out-of-bounds write. I deliberately deviated from the assignment's bare `+1`
(which would also have been an out-of-bounds store, a weaker test) for that
reason.

The same observation is the positive half of §1.2: it is *why* the sweep is
bit-exact.

### 0.5 The trusted CLI holds no model code, so the per-arm golden gate is valid

I checked whether `correctness --golden` was actually exercising my rebuilt
kernel, because `.build/release/mlxfast-swift` was stale relative to the worker.
It does not matter: the CLI contains no MLX or Laguna code at all
(`laguna_decode_nvfp4_qkv_r1`, `lagunaDecodeNVFP4`, `mlx::core` are all absent
from its symbol and string tables). It delegates every model execution to
`MLXFAST_RUNTIME_WORKER_EXECUTABLE`. The per-arm gate therefore ran the rebuilt
worker in every arm.

One trap worth recording: Swift stores small string literals (`_sg`, `_fault`,
`_pw1`, `_se1`) as inline register immediates, so they are **invisible to
`strings`**. Only large literals such as the embedded Metal source show up. To
verify which variant a binary contains, grep the Metal source text
(e.g. `num_simdgroups = `), not the Swift-side suffix.

---

## 1. Stage 0 — reachability, guard chain, and encoded geometry

### 1.1 Guard chain down to a default value

All line numbers are at the assignment base,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`.

1. **Decode call site, `:5735-5790`.** The step first tries `fusedQKV`, which
   requires `lagunaFusedNormAffineQKVEnabled` (`:5295`) *and*
   `fusedAffine.mode == .affine, bits == 8, groupSize == 32`. The runtime
   quantizes QKV as `.nvfp4 / 16 / 4` at `:2914` because
   `lagunaNativeAffineNVFP4From` (`:2861-2867`) **defaults to `0`**. So
   `fusedQKV` is unconditionally `nil` on the default configuration and control
   falls through to `lagunaDecodeNVFP4QKVR1(normalized:bank:heads:)` at `:5766`.

2. **`lagunaDecodeNVFP4QKVR1`, `:4815`.** Requires
   `lagunaDecodeNVFP4QKVR1Enabled` (`:4620`), which is
   `environment[...] != "0"` — i.e. **default `true`**. Then shape guards; note
   `normalized.dims == (1, 1, hidden)` at `:4823`, which is why prefill is
   structurally excluded from this kernel (rule-17 note, §4).

3. **Lane-major branch, `:4834`.** Requires `bank.laneMajorScales` non-nil and
   `lane.pairwise == lagunaAttnScalePairwiseQKVEnabled`
   (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:686`). The bank is
   populated at `:5571` under
   `lagunaAttnScaleNarrowQKVEnabled && mode == .nvfp4 && bits == 4 && groupSize == 16`,
   all of which hold by default. **This is the branch that runs.**

4. Fallbacks that must *not* fire: narrow branch `:4852`, plain R1 `:4867`,
   generic `quantizedMM` last. The Stage 0 probe emits a `PACKPROBE FALLBACK`
   line from each of these, so a silent fallback cannot be mistaken for a
   timing null.

### 1.2 Why the repack is bit-exact by construction

Inside `lagunaDecodeNVFP4QKVLaneMajorSource` the only statement that reads
`num_simdgroups` is

```metal
uint out_row = tile * num_simdgroups + simd_gid;
```

Every statement below it is simdgroup-local (`simd_lid`-indexed loads, a
register K-loop, one `simd_sum`, one `projected[out_row]` store). With `grid.x =
rows * 32` and `threadGroup.x = S * 32`, the set of `(out_row)` values covered
is exactly `[0, rows)` for any `S` that divides `rows`, each visited by exactly
one simdgroup, with one row per simdgroup in every arm. Total simdgroups,
arithmetic, and bytes read are therefore invariant; only the packing changes.

The shipped dispatch is `grid: ((rows/2)*64, 1, 1)`, `threadGroup: (64, 1, 1)`.
My parameterized dispatch at `S=2` is `grid: (rows*32, 1, 1)`,
`threadGroup: (2*32, 1, 1)` — **bit-identical**, so the `S=2` arm is the
unpatched stock path and is a legitimate reference.

### 1.3 Divisibility — and why the curve can be pushed to S=32

`LagunaConfig.swift`: `hiddenSize=2048`, `numKeyValueHeads=8`, `headDim=128`,
`fullAttentionHeads=48`, `slidingAttentionHeads=64`. Fused QKV row counts:

| layer type | heads | rows | factorization |
|---|---|---|---|
| full attention | 48 | `(48+16)*128 = 8192` | `2^13` |
| sliding window | 64 | `(64+16)*128 = 10240` | `2^11 · 5` |

Both row counts must be divisible by `S`, so the divisibility cap is
`gcd(8192, 10240) = 2048`. That is not the binding constraint. **The operative
cap is Metal's 1024-threads-per-threadgroup limit**: with 32 threads per
simdgroup, `S ≤ 32`. So the sweep `S ∈ {1, 2, 4, 8, 16, 32}` is limited by the
hardware dispatch limit, not by the row factorization, and `S=32` sits exactly
on that limit.

**Because the fold is pinned off, the prologue is empty and no threadgroup
memory scales with `S`** — the >32 KB pipeline-build failure the assignment
warns about cannot occur in this sweep, which is what lets me extend the curve
two points past PR #298's `S=16` and answer "does it keep improving?".

### 1.4 Encoded geometry actually observed

`research/tanjiro_packing_probe.patch` (unapplied at the PR tip) adds a
`PACKPROBE` line per distinct `(heads, S)` tuple, printed from the dispatch site
*after* the guard chain, plus `PACKPROBE FALLBACK` from all three fallbacks.
Raw logs: `research/packing-curve-logs/stage0/`.

Driver `research/tanjiro_packing_stage0.sh`, training
`418d95ae-ee1b-45cd-ad50-3e75ee1ea2c0` (exit 0, 229.7 s), raw logs in
`research/packing-curve-logs/stage0/`. The instrumentation is landed
**unapplied** as `research/tanjiro_packing_probe.patch` (standing rule 11), and
prints one deduplicated line per distinct dispatch shape:

```
PACKPROBE lane-major heads=48 rows=8192 sg_per_tg=16 threadgroups=512 \
  rows_per_sg=1 threads_per_tg=512 grid_threads=262144 total_sg=8192
```

All six arms reached the lane-major kernel. **There is no `PACKPROBE FALLBACK`
line anywhere in the six logs**, i.e. the narrow (`:4852`), plain-R1 (`:4867`),
and generic `quantizedMM` fallbacks never fired, so every arm is the same kernel
family with a different packing.

| `S` | full attn `heads=48`, `rows=8192` | sliding `heads=64`, `rows=10240` | threads/TG | grid_threads | total_sg | rows/sg |
|---|---|---|---|---|---|---|
| 1 | 8192 TGs | 10240 TGs | 32 | 262144 / 327680 | 8192 / 10240 | 1 |
| **2** (default) | **4096 TGs** | **5120 TGs** | **64** | 262144 / 327680 | 8192 / 10240 | 1 |
| 4 | 2048 TGs | 2560 TGs | 128 | 262144 / 327680 | 8192 / 10240 | 1 |
| 8 | 1024 TGs | 1280 TGs | 256 | 262144 / 327680 | 8192 / 10240 | 1 |
| 16 | 512 TGs | 640 TGs | 512 | 262144 / 327680 | 8192 / 10240 | 1 |
| 32 | 256 TGs | 320 TGs | 1024 | 262144 / 327680 | 8192 / 10240 | 1 |

The invariants the experiment depends on all hold across arms:
`grid_threads` constant, `total_sg` constant, `rows_per_sg = 1` everywhere.
Only `threadgroups` and `threads_per_tg` move, and they move as exact
reciprocals. `S=32` reaches 1024 threads/TG, the Metal maximum, and builds
because with `NORM_QKV_FUSE=0` no threadgroup memory scales with `S`.

Every arm also reported `teacher-forced greedy tokens: 0 divergences (all
match)` on the probe's own short check, and the full public 64-step golden gate
passed at all six arms (training `177c27d5-e2cc-45e7-ac02-63f20c34fe42`, archived
in `research/packing-curve-logs/stage0-gate/`):

| `S` | `passed` | `checked_steps` | `first_failing_step` | `golden_hash` |
|---|---|---|---|---|
| 1 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 2 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 4 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 8 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 16 | `True` | 64 | `None` | `b9509697c08a2cf3…` |
| 32 | `True` | 64 | `None` | `b9509697c08a2cf3…` |

Stage 0 therefore answers the assignment's gating question: **the knob does
change encoded geometry**, so Stage 1 is a real timing experiment rather than a
null one.

The tiny-`n` medians from the 6-step probe runs already hinted at the shape that
Stage 1 measures properly — `S=1` clearly slow, everything else close with
`S=16` lowest:

| `S` | 1 | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|---|
| 6-step median (ms/step) | 8.411 | 8.224 | 8.224 | 8.190 | **8.173** | 8.188 |

`n=6` with no ABBA structure, so this is a sanity check on direction, not
evidence.

---

## 2. Stage 1 — the packing curve

### 2.1 Design as executed

| Item | Value |
|---|---|
| Driver | `research/tanjiro_packing_abba.sh /tmp/tanjiro/abba 4 200` |
| Statistics | `research/tanjiro_packing_stats.py` (wraps `research/nezuko_pr48_stats.py`; only `ARM_DESC`/`CONTRASTS` overridden, plus a new curve verdict — the fit itself is PR #298's, unmodified) |
| Arms | 6: `S ∈ {1, 2, 4, 8, 16, 32}`, labelled `RV, 0, V, G, R, N` (PR #298's alphabet; `0` = shipped default `S=2` = reference) |
| Block order | palindromic `0 RV V G R N N R G V RV 0` |
| Blocks | 4 scored + 1 discarded warm-up block (`blk=0`) |
| Runs | **48 scored** (8 per arm), 49 launched |
| Steps | 200 requested, first 8 dropped as warm-up, **192 kept per run** |
| Session | one, one quiet M4 Pro host, one `run_training` invocation (`31d5c157-d675-46d0-b5f5-17e98cd6707f`, exit 0, 2 305 s) |
| Fuse knob | `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0` pinned in every arm |
| Raw data | `research/packing-curve-logs/stage1/` (both fits, driver log, `steps.tar.gz`) |

The assignment asked for `S ∈ {1,2,4,8,16}`; I added `S = 32` because §1.3 shows
`S = 32` is the largest legal setting (Metal's 1 024 threads/threadgroup cap), so
it is the only way to bound the curve on the right. That turned out to matter.

### 2.2 Per-arm results (untrimmed, n = 8 per arm)

| `S` | arm | mean µs/step | sd of run means | median within-run sd |
|---|---|---|---|---|
| 1 | `RV` | 8196.2 | 29.3 | 60.5 |
| **2** | **`0`** | **8196.8** | 27.1 | 52.4 |
| 4 | `V` | 8180.1 | 9.1 | 49.7 |
| **8** | **`G`** | **8159.9** | 27.6 | 48.2 |
| 16 | `R` | 8163.5 | 24.7 | 65.7 |
| 32 | `N` | 8184.4 | 13.9 | 42.1 |

Per-block arm means, showing the ABBA design is doing its job (block 4 drifted
slow on the reference arm and the fit absorbs it):

| block | `S=2` | `S=1` | `S=4` | `S=8` | `S=16` | `S=32` |
|---|---|---|---|---|---|---|
| 1 | 8197.5 | 8223.9 | 8177.0 | 8144.3 | 8151.3 | 8190.9 |
| 2 | 8189.4 | 8187.7 | 8186.8 | 8174.1 | 8163.0 | 8188.9 |
| 3 | 8180.6 | 8197.4 | 8181.8 | 8151.9 | 8147.4 | 8188.9 |
| 4 | 8219.9 | 8175.8 | 8174.8 | 8169.3 | 8192.1 | 8169.2 |

**Within-run sd / outlier flag.** Median 38.4 µs, max 143.7 µs. **No run exceeds
4× the cohort median**, so unlike PR #298 (which had one such run) there is no
outlier to flag here. The 5 % upper trim is therefore a pure sensitivity check
rather than a correction; §2.5 reports it because the assignment asks for it and
because it turns out to matter for one contrast.

### 2.3 The curve (two-way fixed effects, 39 df, residual sd 23.8 µs)

Effects are µs/step relative to the shipped default `S = 2`; negative is faster.

| `S` | arm | effect | se | t | 95 % CI | % of score |
|---|---|---|---|---|---|---|
| 1 | `RV` | −0.6 | 11.9 | −0.05 | [−24.7, +23.4] | 0.01 |
| 2 | `0` | 0.0 | — | — | — | 0.00 |
| 4 | `V` | −16.8 | 11.9 | −1.41 | [−40.8, +7.3] | 0.26 |
| **8** | **`G`** | **−36.9** | 11.9 | **−3.10** | **[−61.0, −12.9]** | **0.56** |
| **16** | **`R`** | **−33.4** | 11.9 | **−2.80** | **[−57.4, −9.3]** | **0.51** |
| 32 | `N` | −12.4 | 11.9 | −1.04 | [−36.4, +11.7] | 0.19 |

Reference `S=2` absolute mean **8196.8 µs/step**. `%` of score uses the campaign
constant 0.015280 % per µs/step of decode.

**argmax `S = 8` at −36.9 µs/step; statistically tied set = `[4, 8, 16]`.**

Two arms have CIs excluding zero: `S = 8` and `S = 16`. `S = 8` and `S = 16` are
themselves indistinguishable (`R − G` below). So the honest one-line summary is:
**packing at `S ∈ {8, 16}` is worth ≈ 0.5 % of score over the shipped `S = 2`, and
this experiment cannot tell 8 from 16 apart.**

**Replication of PR #298.** #298 measured `S = 16` at **−35.4 µs/step, se 13.6,
39 df**. I measure **−33.4 µs/step, se 11.9, 39 df** — a 2.0 µs difference, far
inside either interval, from an independent session with an independently written
knob. This axis is real and reproducible, which was the single most important
thing to establish.

### 2.4 Pre-registered contrasts

Both estimators are shown, as PR #298 did. Block-paired differences the two
occurrences of each arm within a block; fixed-effects pools all 48 runs. They
agree on every sign.

| contrast | meaning | block-paired mean (sd, t) | fixed-effects mean (se, t) | FE 95 % CI |
|---|---|---|---|---|
| `RV−0` | `S=1` vs default | −0.6 (31.2, −0.04) | −0.6 (11.9, −0.05) | [−24.7, +23.4] |
| `V−0` | `S=4` vs default | −16.8 (21.1, −1.59) | −16.8 (11.9, −1.41) | [−40.8, +7.3] |
| `G−0` | `S=8` vs default | −36.9 (18.2, **−4.07**) | −36.9 (11.9, **−3.10**) | **[−61.0, −12.9]** |
| `R−0` | `S=16` vs default | −33.4 (9.0, **−7.40**) | −33.4 (11.9, **−2.80**) | **[−57.4, −9.3]** |
| `N−0` | `S=32` vs default | −12.4 (26.3, −0.94) | −12.4 (11.9, −1.04) | [−36.4, +11.7] |
| `N−R` | does the curve keep improving past 16? | +21.0 (30.1, 1.40) | +21.0 (11.9, 1.76) | [−3.1, +45.1] |
| `R−G` | local slope at the #298 winner | +3.6 (14.9, 0.48) | +3.6 (11.9, 0.30) | [−20.5, +27.6] |
| `V−RV` | local slope at the small end | −16.1 (21.7, −1.49) | −16.1 (11.9, −1.35) | [−40.2, +8.0] |

Answering the two questions those contrasts were registered to answer:

- **`N−R`: no, the curve does not keep improving past `S = 16`.** The point
  estimate is a *regression* of +21.0 µs/step, but it does **not** clear its own
  95 % half-width untrimmed. The right-hand turn is **suggested, not established**
  (see §2.5 — this is the one contrast the trim moves across the significance
  boundary, so I treat it as unresolved).
- **`R−G`: `S = 16` and `S = 8` are a dead null** (+3.6 ± 24.1, t = 0.30). This is
  the precondition §5.3 depends on, and it holds under both trims.

### 2.5 Trim sensitivity (5 % upper trim)

| contrast | untrimmed | trimmed | moves? |
|---|---|---|---|
| `RV−0` | −0.6 [−24.7, +23.4] | −1.9 [−27.0, +23.2] | no |
| `V−0` | −16.8 [−40.8, +7.3] | −16.2 [−41.3, +8.9] | no |
| `G−0` | −36.9 [−61.0, −12.9] | −36.0 [−61.1, −10.9] | no |
| `R−0` | −33.4 [−57.4, −9.3] | −35.7 [−60.8, −10.6] | no |
| `N−0` | −12.4 [−36.4, +11.7] | −10.2 [−35.3, +14.9] | no |
| **`N−R`** | **+21.0 [−3.1, +45.1]** | **+25.5 [+0.4, +50.6]** | **yes — crosses zero** |
| `R−G` | +3.6 [−20.5, +27.6] | +0.3 [−24.8, +25.4] | no |
| `V−RV` | −16.1 [−40.2, +8.0] | −14.3 [−39.4, +10.8] | no |

Every headline conclusion is trim-invariant **except `N−R`**, whose trimmed CI
lower bound is `+0.4` — i.e. it "achieves significance" by 0.4 µs on a 25 µs
half-width. I am not going to call that a result. **The `S = 32` regression is a
consistent point estimate under both trims and a resolved contrast under
neither.**

### 2.6 Monotonicity verdict — and why the assignment's question is the wrong one

The assignment asked for "monotone in `S`, U-shaped, or flat with one outlier".
Reported literally, from adjacent steps:

| step | effect ± 95 % half-width | untrimmed | trimmed |
|---|---|---|---|
| `S=1 → 2` | +0.6 ± 24.1 | flat | flat |
| `S=2 → 4` | −16.8 ± 24.1 | flat | flat |
| `S=4 → 8` | −20.2 ± 24.1 | flat | flat |
| `S=8 → 16` | +3.6 ± 24.1 | flat | flat |
| `S=16 → 32` | +21.0 ± 24.1 | flat | **slower** |

**Adjacent-step verdict: `FLAT` untrimmed** (0 faster, 0 slower, 5 flat);
`MONOTONE-INCREASING` trimmed. Both labels are misleading, and the reason is
worth stating because it is a general trap in this kind of sweep:

> No *adjacent* step clears the ±24 µs half-width, because each step is worth
> ≈ 17–21 µs. But the *cumulative* move `S=2 → S=8` is −36.9 µs and clears it
> comfortably. A verdict computed only from adjacent differences therefore reports
> "flat" about a curve with a statistically solid 0.56 %-of-score basin in it.

That is why I extended the stats script with an **interior-optimum test**: is an
arm significantly better than **both** sweep endpoints (`S=1` and `S=32`)?

| candidate | vs `S=1` | vs `S=32` | untrimmed | trimmed |
|---|---|---|---|---|
| `S=16` (pre-registered pivot) | −32.7 ± 24.1 | −21.0 ± 24.1 | not established | INTERIOR OPTIMUM |
| `S=8` (observed argmax) | −36.3 ± 24.1 | −24.6 ± 24.1 | INTERIOR OPTIMUM | INTERIOR OPTIMUM |

The pivot `S = 16` was fixed **before** the data (it is PR #298's winner); the
argmax `S = 8` is **selection-biased** by construction, so its "established"
label is the weaker of the two. Being strict, I report:

> **Shape verdict: a broad interior basin over `S ∈ {4, 8, 16}` with both ends of
> the legal range worse.** Best point estimate `S = 8`. `S = 8` vs `S = 16` is
> unresolvable at this power. The left shoulder `S = 1 ≈ S = 2` is flat (`RV−0` is
> a dead null — there is *no* left wall at `S = 1`, the plateau simply extends
> down to it). The right shoulder `S = 32` gives back roughly two-thirds of the
> gain by point estimate but is not a resolved regression.

Note what this rules out: **"bigger `S` is always better" is false.** The maximum
legal setting `S = 32` is the second-worst arm in the sweep. Anyone extrapolating
PR #298's single `2 → 16` point to `S = 32` would have shipped away most of the
gain.

### 2.7 Power, and the null arms

The 95 % half-width on any arm-vs-default contrast is **±24.1 µs/step = ±0.29 %
of the step time = ±0.37 % of score**. For context, a single
`--local-iterate` pair on this host has an MDE of ±0.73 %, so this 48-run design
resolves about **2× finer** than the standard local comparison.

So the three non-significant arms are *bounded*, not merely unmeasured:

- `S = 1` (`−0.6 ± 24.1`) — bounded to worse than −25 µs. A genuine null.
- `S = 4` (`−16.8 ± 24.1`) — **underpowered, not null.** The point estimate is
  45 % of the `S = 8` effect and the CI comfortably contains it. `S = 4` is
  probably a real but smaller gain; this design cannot separate it from zero.
- `S = 32` (`−12.4 ± 24.1`) — same situation, on the other side of the basin.

Doubling to 16 runs/arm would shrink the half-width to ≈ ±17 µs, which is still
not enough to separate `S = 8` from `S = 16` (they differ by 3.6 µs). **Separating
8 from 16 on M4 is not worth buying**; §5.3 argues the decision should be made on
the transfer argument instead, and §7.2 explains that one paired M5 run answers it
directly.

### 2.8 Correctness, every arm

The tripwire
`correctness --golden correctness_prompts/public_longcopy_gate_english_512_256.json`
was run at **all six** values of `S` in §1.4 (training
`177c27d5-e2cc-45e7-ac02-63f20c34fe42`), and all six returned
`passed=True, checked_steps=64, first_failing_step=None, error=''` with the
**identical** `golden_hash`
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

I did not re-run it after the timing sweep, deliberately: the sweep used the same
worker binary and the same six env settings, so a second run would recompute the
same six results. The gate is cited, not assumed — and §3 shows it is
load-bearing rather than vacuous.

---

## 3. Fault injection — is the tripwire load-bearing?

The assignment makes this mandatory: if an injected row-mapping defect cannot
make the tripwire fail, Stage 1 is `INVALID`. It took two attempts, and the
first attempt is the more instructive one.

### 3.1 Attempt 1 — the assignment's literal fault is identity (INVALID by design)

Patch: `out_row = tile * num_simdgroups + ((simd_gid + 1) % num_simdgroups)`.
Training `6a499c27-b0bf-43b1-b6a9-70e750b707df`.

| `S` | `passed` | `checked_steps` | verdict |
|---|---|---|---|
| 2 | `True` | 64 | gate passed an injected "fault" |
| 16 | `True` | 64 | gate passed an injected "fault" |

My gate script correctly refused this (`exit 2`). But the conclusion is **not**
"the tripwire is weak" — it is that the patch is a no-op, for the reason in
§0.4: `out_row` gates all four weight/scale reads *and* the store together, so
any bijection over rows recomputes the same set of rows into the same set of
slots. See §1.2: this is exactly the argument that makes the whole sweep
bit-exact, so it had to be true.

### 3.2 Attempt 2 — desynchronise the store row from the read row (VALID)

`research/tanjiro_packing_fault.patch` (37 lines). Reads stay on the true
`out_row`; a new `store_row = tile * num_simdgroups + ((simd_gid + 1) %
num_simdgroups)` is used only at `projected[store_row]`. Still in bounds, and the
kernel name gains a `_fault` suffix so no cached compiled kernel can mask it.

Training `0010f873-b274-4dca-b4ca-a96fa7dddccc`, archived in
`research/packing-curve-logs/fault/`:

| `S` | `passed` | `checked_steps` | `first_failing_step` | `error` |
|---|---|---|---|---|
| 2 | **`False`** | 2 | 1 | `teacher-forced token mismatch` |
| 16 | **`False`** | 2 | 1 | `teacher-forced token mismatch` |
| 1 | `True` | 64 | `None` | `''` (negative control, see below) |

The public 64-step tripwire catches the defect **on the very first decode step**
at both the default packing and the PR #298 winner packing. The tripwire is
load-bearing, so the Stage 1 per-arm passes in §1.4 are meaningful and Stage 1 is
**VALID**.

`S=1` passing is not a hole — it is the control that makes the result
interpretable. At `S=1` the rotation is `(0 + 1) % 1 == 0`, i.e. the fault patch
compiles to identity. So the same rebuilt, `_fault`-suffixed binary passes at
`S=1` and fails at `S ∈ {2, 16}`. That rules out "the rebuild broke something"
and "the gate fails any patched worker": the verdict tracks the injected defect
and only the injected defect. My driver's global `EXPECT=fail` flagged `S=1` as
unexpected and exited 2; that is the script being rigid, and the three raw JSONs
are the evidence.

---

## 4. Rule 17 — the prefill axis

Rule 17 requires measuring both axes when a `DARKBLOOM_*` flag moves, because
prefill carries 25 % of the score and has its own hard `0.95` floor.

Here the answer is **structural before it is empirical**. The guard at
`LagunaRuntimeModel.swift:4823` is

```swift
normalized.dims(1, 1, hidden)
```

so `lagunaDecodeNVFP4QKVR1` can only fire for a single-token input. Prefill
passes `seq = 512` and never reaches this kernel at all — it goes through the
quantized-matmul path. `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` therefore
cannot influence prefill by construction, not merely by measurement.

I measured it anyway, because a structural argument that is wrong is worse than
no argument, and because the ranked prefill floor is a hard gate. Same driver,
same session discipline, `PREFILL=1 ARM_SEQ="0 R R 0"`, two blocks, 8 scored
512-token prefills (4 per arm) plus one discarded warm-up
(`research/packing-curve-logs/prefill/`, training id
`5f636fbe-1ca0-41b1-9e52-c0b0d7d9fb6b`, exit 0):

| arm | `S` | n | mean prefill (ms) | sd (ms) |
|---|---|---|---|---|
| `0` | 2 (default) | 4 | 547.905 | 0.460 |
| `R` | 16 | 4 | 547.898 | 0.999 |

- **`R - 0` = −0.007 ms (−0.015 µs/token), 95 % CI ±1.346 ms (±0.246 % of
  prefill).** Block-paired: `+0.710` ms in block 1, `−0.725` ms in block 2,
  mean `−0.008` ms — the two blocks disagree in sign and cancel almost exactly.
- The point estimate is **1/78 of the CI half-width**. This is not "a small
  effect I cannot resolve"; it is the signature of *no mechanism at all*, which
  is what the guard predicts.

Two notes on reading this. First, prefill on this host is a far quieter
measurement than decode — a between-run sd of 0.46–1.0 ms on 548 ms is
0.08–0.18 %, so the ±0.246 % MDE here is tight enough to have caught a real
effect an order of magnitude below the decode effect's relative size (the decode
argmax is −0.45 % of a step). A null this clean at this resolution is
informative. Second, the flag is **not** free of prefill risk in general: this
result licenses only the specific claim that *this* knob on *this* kernel does
not touch prefill. Any Stage 2 site that also runs at `seq = 512` (the routed
MoE and o_proj kernels do) would need its own prefill arm, and §6.2's `PURSUE`
recommendation should be read with that attached.

**Rule 17 verdict: satisfied, prefill unaffected, no floor risk from this knob.**

---

## 5. M4 → M5 transfer

This is the section that should decide what, if anything, ships. The repo's own
history is blunt about the failure mode: PR #48 arm `N` measured **−55.0 µs/step
on M4** and **+10.0 µs/step on ranked M5**, and PR #7 was **+7.32 % on M4 and
≈0.0 % on M5**. Both were core-count quantisation. A threadgroup-packing sweep is
*precisely* a core-count-quantisation experiment, so the prior for naive transfer
should be low.

### 5.1 The kernel is DRAM-stream-bound, so the effect is small by construction

Each row streams ≈1.06 KB on the hot path (1024 B of NVFP4 codes + 32 scale
nibbles + scale bases + row scale). Per kernel that is ≈8.7 MB at `rows=8192`
and ≈10.9 MB at `rows=10240`. At M4 Pro's ≈273 GB/s that is a **≈32 µs (full
attention) / ≈40 µs (sliding) bandwidth floor per kernel**, and the measured
kernel time is close to it.

`LagunaConfig.swift:15` gives `numHiddenLayers = 40`, and the fused QKV GEMV
fires once per layer per decode step, so there are **40** such kernels per step,
not the ≈28 I first wrote. Spreading PR #298's 35 µs/step across 40 kernels
gives **≈0.88 µs per kernel, i.e. 2.2–2.8 % of the per-kernel floor**.

So this is not a compute or arithmetic win at all; it is an *edges and
residency* win — ramp, drain, and how many simdgroups are resident — layered on
top of a stream-bound kernel, and it is a **sub-3 % perturbation** of a kernel
that is already near its bandwidth floor. That framing matters twice: it caps
how large any packing effect can plausibly be, and it means the effect lives
entirely in ramp/drain and residency, which scale with **core count** — the axis
that differs between this host and the ranked machine.

### 5.2 Candidate mechanisms, and which of them transfer

| # | Mechanism | Direction | Transfers to M5? |
|---|---|---|---|
| 1 | Resident-simdgroup shortfall at small `S` (per-core TG-slot granularity, plus TG issue/retire rate — at `S=2` the distributor must place one TG every ≈8.5 ns machine-wide) | penalises **small** `S` | yes, roughly in TGs-per-core units |
| 2 | Per-TG ramp/drain at kernel boundaries (naive estimate ≈2.5–5 µs at `S=2` vs ≈0.3–0.6 µs at `S=16` — **see the consistency note below**) | penalises **small** `S` | yes, and *grows* with core count |
| 3 | Wave/tail quantisation | penalises **large** `S` | **sign can flip** — this is the documented cause of this project's M4→M5 reversals |
| 4 | DRAM page locality | weakly favours large `S` | weak either way |
| 5–7 | Input-vector reuse, i-cache pressure, intra-TG coalescing | ≈nil (the input vector is 4 KB and already L2/L1-resident; loads are already fully coalesced within a simdgroup) | n/a |

Composite prediction from 1+2 fighting 3: **a shallow U with a wide flat bottom
around `S ≈ 8–16`, a steep left wall at `S = 1–2`, and a machine-dependent right
wall.** Stage 1 (§2) is the test of that prediction, and it **partly refutes
it**: the flat bottom is confirmed at `S ∈ {4, 8, 16}`, but there is **no left
wall** — `S = 1` and `S = 2` are indistinguishable (`RV - 0` = −0.6 µs/step),
which means mechanisms 1 and 2 are already saturated by `S = 2` on this host and
gain nothing further from `S = 1`. The right-hand rise toward `S = 32` appears
with a consistent sign but is not statistically resolved (§2.4). So the
mechanistic story survives only in its coarse form; the sharp asymmetry it
predicted at the left edge is not there.

**Consistency note on mechanism 2.** The ≈2.5–5 µs-per-kernel ramp/drain
estimate is **3–5× larger than the entire measured effect** (§5.1: ≈0.88 µs per
kernel). Both cannot be right. Either the ramp/drain estimate is badly
over-stated — most likely, since it assumes serial ramp with no overlap between
retiring and launching threadgroups, whereas Apple's distributor overlaps them —
or mechanism 3 (tail quantisation) is already cancelling most of mechanism 2 at
`S=16` on this host. I cannot distinguish these from the end-to-end timing in
§2. This is a real weakness in the mechanistic story and it is the main reason
the microbenchmark in §5.5 is my top follow-up: it would measure the per-launch
cost directly instead of estimating it.

The `S=32` rise has a plausible concrete cause even with zero threadgroup memory:
a 1024-thread TG must be resident **atomically on one core**, needing ≈160–256 KB
of register file, which fragments internally and strands registers at retire
granularity; and 256 TGs over ≈40 M5 cores is only 6.4 TGs/core, which is too
coarse to balance. §2.4 measures the rise with a consistent positive sign but
cannot resolve it from zero, so this remains a mechanism *hypothesis* for an
observed point estimate, not an explanation of a confirmed wall.

### 5.3 The transfer argument, in TGs-per-core

**Threadgroups per GPU core** is *a* plausible invariant — not a demonstrated
one. I have no measurement that shows the curve is a function of TGs/core rather
than of `S`, TG count, or threads/TG directly; §5.5 lists what would test it.
Two things I do know point weakly toward it: residency headroom and tail
quantisation both depend on how many threadgroups each core sees, and Apple does
not scale per-core threadgroup-slot counts with die size. Treat the table below
as a **regret-minimising heuristic**, not a law. This host has **20** GPU cores;
the ranked M5 Max has **≈40**.

| `S` | TGs full (8192 rows) | TGs sliding (10240 rows) | TGs/core M4 Pro (20) | TGs/core M5 Max (40) |
|---|---|---|---|---|
| 1 | 8192 | 10240 | 409.6 / 512 | 204.8 / 256 |
| 2 | 4096 | 5120 | 204.8 / 256 | 102.4 / 128 |
| 4 | 2048 | 2560 | 102.4 / 128 | 51.2 / 64 |
| 8 | 1024 | 1280 | 51.2 / 64 | **25.6 / 32** |
| 16 | 512 | 640 | **25.6 / 32** | 12.8 / 16 |
| 32 | 256 | 320 | 12.8 / 16 | 6.4 / 8 |

Read that table across the diagonal. Because the M5 Max has almost exactly twice
this host's core count, and because the two head counts (48 full, 64 sliding)
sit in the same ratio at every `S`, the correspondence is clean: **one step up in
`S` on M4 is the same TGs-per-core load as the next-lower `S` on M5.**

- **M5 at `S=8`** sits at 25.6 / 32 TGs per core — numerically the same load as
  **M4 at `S=16`** (−33.4 µs/step here, inside the flat bottom).
- **M5 at `S=16`** sits at 12.8 / 16 — the same load as **M4 at `S=32`**
  (−12.4 µs/step here, roughly a third of the available gain and not
  distinguishable from zero).

That second line is the crux. Note carefully what it does and does not rest on.
It does **not** require `S=32` to be a *significant* regression against `S=16`:
§2.4 measures `N-R` at **+21.0 µs/step (95 % CI [−3.1, +45.1])** untrimmed and
**+25.5 [+0.4, +50.6]** under the 5 % upper trim, i.e. a consistently
positive point estimate that is **resolved under neither trim** — the only
contrast in the whole sweep whose sign verdict moves with the trim. Calling it a
right *wall* would overstate the evidence.

What the min-regret argument actually needs is weaker and is robust under both
trims: `S=32`'s *own* effect against the default (`N-0` = −12.4 untrimmed,
−10.2 trimmed) recovers only about a third of what `S=16` (−33.4 / −35.7) and
`S=8` (−36.9 / −36.0) recover. So the TGs-per-core load that `S=16` would
produce on M5 is the load at which **this host measured most of the gain
evaporating**, even though the sweep cannot prove that evaporation is
statistically complete. Under the heuristic, shipping the raw M4 argmax risks
placing the ranked host at that load.

Two caveats were open when this section was drafted. Stage 1 resolves both, and
it is worth recording that they were resolved rather than assumed:

1. **Was the recommendation conditional on Stage 1?** Yes: `S=8` would only be a
   cheap choice if `S=8 ≈ S=16` on M4. Had `S=16` come out strictly and
   significantly better than `S=8`, recommending `S=8` would have been a
   *measured* M4 loss traded for an *unmeasured* M5 hope. §2 measures the `R-G`
   contrast (`S=16` vs `S=8`) as a dead null (**+3.6 µs/step, CI [−20.5, +27.6]**
   untrimmed; **+0.3** trimmed), so the trade costs nothing measurable on this
   host. The precondition held.
2. **PR #298 never measured `S=8`.** Its arms were `S=2` and `S=16` only, so at
   the time of drafting `S=8` was pure interpolation with no timing evidence on
   any machine. §2 is its first direct measurement, and it lands in the flat
   bottom rather than on either shoulder.

So the **min-regret** choice if exactly one value must ship without an M5
measurement is **`S=8`**. Two facts support it, and it is worth separating them
because only the first is independent evidence:

- `S=8` keeps the ranked host at the TGs-per-core load that measured *best*
  here, a full factor of two away from the load where most of the gain
  disappeared. This is the min-regret argument and it does not depend on which
  M4 arm happened to win.
- `S=8` also *is* the observed M4 argmax (−36.9 µs/step). This is a coincidence,
  not confirmation: `S=8` and `S=16` are statistically tied (`R-G` above), so
  which of the two takes the argmax on a given host is noise. I would still
  recommend `S=8` had `S=16` taken the argmax, exactly as this section argued
  before the final block landed.

`S=16` is defensible **only** with a paired M5 measurement: shipping the raw M4
argmax is exactly what PR #48 arm `N` did (−55.0 µs/step on M4, **+10.0 on M5**),
and what PR #7 did (+7.32 % on M4, ≈0.0 % on M5).

This also yields a **falsifiable prediction** for whoever runs the M5, which is
more useful than the recommendation itself: if TGs-per-core is the operative
invariant, then on M5 the ordering should be `S=8` best, `S=16` measurably worse
than `S=8`, and `S=4` roughly tied with `S=8`. If instead M5 reproduces the M4
curve in `S` directly (`S=16` best), the invariant is `S` or threads/TG, not
TGs/core, and this whole section is wrong in a way that one paired official run
would expose.

### 5.4 Rule of thumb for the Stage 2 sites

Falling out of §5.1–5.3, an `S`-repack has a plausible upside only when **both**
hold —

1. the TG count *after* the repack still covers every core with several
   threadgroups to spare, so tail quantisation cannot eat the gain; and
2. the kernel currently uses **≤64-thread TGs** with few rows per simdgroup, so
   there is a residency and ramp/drain deficit to recover in the first place.

Criterion 1 is a *comparative* test, not a fixed threshold. An earlier draft
wrote it as "≳400 TGs on a 40-core M5", and §6.2 shows why that was wrong: the
same cutoff would have killed the one site I recommend pursuing. What matters is
that the chosen `S` leaves every core loaded — which for a small kernel means
picking a smaller `S`, not abandoning the site. §6 applies this to every
candidate site.

### 5.5 Stated uncertainties

Apple does not publish per-core threadgroup-slot counts or the distributor's TG
issue rate, so mechanisms 1 and 2 are inferred, not measured. Published M1/M2-era
occupancy numbers may not carry to M4/M5 under Dynamic Caching (M3+). And the M4
evidence that motivated this whole assignment was a single two-point A/B whose
effect size has roughly ±2× uncertainty. Stage 1 fixes the two-point problem on
M4; it cannot fix the cross-generation problem.

Three further assumptions are load-bearing and unverified:

- **Per-core threadgroup slots are the same on gen 16 and gen 17.** This host is
  Apple GPU generation **16**; the ranked M5 is generation **17**. If Apple
  changed per-core TG-slot count, register-file size, or retire granularity in
  gen 17, the whole §5.3 diagonal shifts by an unknown amount and `S=8` loses its
  claim to be the safe transfer. I have no way to check this locally.
- **Equal memory bandwidth per core.** The TGs/core framing implicitly treats
  bandwidth-per-core as constant across M4 Pro and M5 Max. It is not: M5 Max has
  roughly twice the cores but well over twice the bandwidth. Since this kernel is
  stream-bound (§5.1), an M5 core may be *less* bandwidth-starved per TG, which
  weakens the residency mechanism specifically on the machine that matters.
- **`_nax` kernel selection.** Per `AGENTS.md`, the ranked M5 selects `_nax`
  variants where available and this gen-16 host does not. The lane-major QKV GEMV
  I patched has no `_nax` twin, so the decode result is not disqualified on that
  ground — but the prefill axis (§4) would be, if I had a prefill effect to
  report.

The cheapest measurement that would *discriminate* mechanism 1 from mechanism 2 —
and therefore settle transfer without an M5 — is an isolated dependency-chained
QKV-GEMV microbenchmark at `S=2` vs `S=16` (the pattern already exists at
`research/frieren_pr101_gatesp_dispatch_bench.swift`), recording
`GPUStartTime`/`GPUEndTime` and converting to achieved GB/s. If `S=2` shows
*lower achieved bandwidth*, it is mechanism 1, which transfers and predicts
`S=8 ≈ S=16` on M5. If both arms achieve the same GB/s and the gap is a constant
≈1 µs per launch, it is mechanism 2, whose gain scales with TG count *and* core
count — which would make the routed-MoE site in §6 the next real win. I did not
run this; it is the top follow-up.

---

## 6. Stage 2 — generalizing the repack

The assignment asks for the repack to be generalized behind
`DARKBLOOM_<KERNEL>_SIMDGROUPS` with the recipe

```
global_sg  = tgid.x * S + simd_index
old_group  = global_sg / OLD_SG
old_simd   = global_sg % OLD_SG
```

and an encode-time `total_sg % S == 0` assertion. I audited every decode GEMV
site that packs more than one simdgroup per threadgroup before writing any code,
because the audit changes the answer: **one site is safe and clearly worth
measuring, one is structurally unsafe, and two are safe but low-prior.**

### 6.1 Site audit

All line numbers are in `Sources/MLXFastModel/LagunaRuntimeModel.swift` **at base
`63ab67c8`** (an earlier draft of this table quoted worktree lines, which are
+19 inside the generator functions that follow my patch insertion point; the
o_proj site precedes the insertion point and is unshifted).

| # | Site | current sg/TG | row index | rows/simd | TG mem | barrier | TGs now | Safe? |
|---|---|---|---|---|---|---|---|---|
| 1 | routed MoE gate/up packed top-8 R1 (`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, name literal @ **7546**) | hardcoded `* 2` @ **7569** | 7569 `logical_row = tile * 2 + simd_group` | 1 | none | none | 2048 (64-thread) | **SAFE** |
| 2 | o_proj gated affine NVFP4 (`lagunaGatedAffineOProjNVFP4Source`, 4035-4231) | `num_simdgroups = 2` @ **4170** | 4180-4181, already parametric | 4 | `gt[gate_heads]` @ 4091 | **4103** | 256 | SAFE for `S ≥ 2` |
| 3 | shared-expert gate/up rows1 (`laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`, name literal @ **6802**) | hardcoded `* 2` @ **6816** | 6816 `row = tile * 2 + simd_group` | 1 | none | none | 256 | **SAFE** |
| 4 | fused down+residual `_r1_v5` (decl 7851-7970) | 9, from `threadGroup: (288,…)` @ **8024** | 7886 `first_row = tile * outputs_per_simd` | 4 | 7935-7937 | **7944** | 512 (288-thread) | **UNSAFE** |

**Site 4 is unsafe for a general `S` sweep and the reason is structural, not
incidental.** At 7884 `uint slot = simdgroup_index_in_threadgroup;` and at 7887
`bool is_shared = slot == shared_slot;` — the nine simdgroups **are** the eight
routed experts plus the shared expert. Simdgroup index is *expert identity*, not
a row group. There is a real `threadgroup_barrier` at 7944 and a `slot == 0`
cross-simdgroup reduction at 7946-7966 over `threadgroup bfloat down_outputs[…]`
(7935-7937). The assignment's `global_sg / OLD_SG` recipe would silently
reassign experts. The only legal variant here is a multiple-of-9 packing
(`9·M`, `M ≤ 3` before hitting the thread cap), which is a different experiment.

**Site 2 is unsafe specifically at `S=1`** for the raw-logit arm: the
`threadgroup float gt[gate_heads]` at 4090-4103 is filled by `if (lid <
gate_heads)`, which requires `32·S ≥ gate_heads` (48 or 64 depending on layer).
The pre-activated twins (4364, 4382) have no gate block and are safe at all `S`.
Threadgroup memory is ≤256 B and constant in `S`, so it never limits occupancy.

### 6.2 Applying the §5.4 rule of thumb — one clear PURSUE, two low-prior

An earlier draft of this section evaluated every site at `S=16` and called sites
2 and 3 "provably unprofitable". **That was wrong on two counts**, and the
corrected reading is below.

First, `S=16` is not the only repack available. Sites 2 and 3 have 512 total
simdgroups; the right column to look at is `S=4`:

| # | Site | total sg | TGs at `S=4` | TGs/core (40-core M5) | TGs at `S=16` | TGs/core |
|---|---|---|---|---|---|---|
| 1 | routed MoE gate/up | 4096 | 1024 | 25.6 | 256 | 6.4 |
| 2 | o_proj gated affine | 512 | **128** | **3.2** | 32 | 0.8 |
| 3 | shared-expert gate/up | 512 | **128** | **3.2** | 32 | 0.8 |
| 4 | fused down+residual | 4608 | n/a (already 288-thread TGs) | 12.8 today | n/a | n/a |

At `S=4` sites 2 and 3 keep **128 threadgroups on 40 cores — every core gets
work**, and each core sees ≥3 threadgroups. The `S=16` idle-core argument simply
does not apply to the `S=4` repack, so "provably unprofitable" is false and I
withdraw it.

Second, the ≥400-TG cutoff in §5.4 criterion 1 was arbitrary and **internally
inconsistent**: I used it to kill sites 2 and 3 while calling site 1 `PURSUE` at
`S=16`, where site 1 has only 6.4 TGs/core — *worse* than sites 2/3 at `S=4`. A
cutoff cannot be applied in one direction only. Corrected verdicts:

| # | Site | Verdict | Reason |
|---|---|---|---|
| 1 | routed MoE gate/up | **PURSUE at `S=4`–`S=8`** | 4096 sg, 64-thread TGs, no TG mem, no barrier, 1 row/simd; `S=8` → 512 TGs (12.8/core), `S=4` → 1024 TGs (25.6/core). Both criteria pass with real headroom. |
| 2 | o_proj gated affine | **LOW PRIOR** (not killed) | Safe at `S ≥ 2`; `S=4` keeps 128 TGs. But it already runs **4 rows/simdgroup**, so each simdgroup is ~4× longer-lived and the ramp/drain amortisation the repack buys is largely already paid. Small expected effect, not zero. |
| 3 | shared-expert gate/up | **LOW PRIOR** (not killed) | Safe at all `S`; `S=4` keeps 128 TGs. 1 row/simdgroup, so unlike site 2 the residency deficit is real — but at only 512 total simdgroups the kernel is ≈8× smaller than site 1, so the same relative gain is ≈8× less absolute time. |
| 4 | fused down+residual | **KILL** | Criterion 2 fails outright: already 288-thread TGs, no ≤64-thread residency deficit to recover. Plus the structural expert-identity problem in §6.1. |

Two things I cannot resolve from static reading, and which should be measured
rather than argued:

- **Kernel-duration asymmetry.** Sites 2 and 3 are ≈8× smaller than site 1 in
  total simdgroups, so their absolute contribution to a decode step is much
  smaller — but I never measured what fraction of the step each kernel occupies.
  A per-kernel breakdown would order these three sites properly and would replace
  the whole TGs/core argument with a direct answer.
- **`S=4` on site 1.** §5.3 argued for `S=8` on the QKV kernel because that is
  where the M4 optimum transfers. On site 1 the same diagonal makes `S=4` the M5
  analogue of the good M4 point, so the routed-MoE sweep should include `S=4`,
  not start at `S=8`.

Implementation note for site 1 if it is picked up: its kernel name is a static
literal at base 7546, so it needs an `_sgN` suffix exactly like §1's knob,
otherwise the compiled-kernel cache will serve the `S=2` variant to every arm and
the sweep will silently measure nothing. This is the single easiest way to fake a
null result on this axis, and worth stating explicitly.

### 6.3 What I did not build

I did not land a generalized `DARKBLOOM_<KERNEL>_SIMDGROUPS` mechanism. With one
clear `PURSUE` site, one structural `KILL`, and two low-prior sites, a shared
four-site abstraction would add editable-surface bytes ahead of the evidence that
says which sites deserve them. The audit table plus the `_sgN` note above makes
site 1 a one-session experiment for whoever picks it up, and the site-1 knob is
a near-copy of `research/tanjiro_packing_geometry.patch`.

---

## 7. Verdicts

### 7.1 The axis itself

**`PURSUE`.** Threadgroup packing at fixed total simdgroups is a real, bit-exact,
zero-byte-cost lever on this decode path, and §2 measures it as a curve rather
than a point. That is the assignment's core question and it is answered.

Three things are now known that were not known before:

1. The curve is **not monotone in `S`**, and it is **not a step function
   either** — the two hypotheses the assignment set up. It is a shallow basin:
   a flat left shoulder covering `S ∈ {1, 2}` (`RV - 0` = **−0.6 µs/step**, a
   dead null — so there is *no* left wall at `S = 1`, which I had predicted and
   which the data refutes), a bottom at `S ∈ {4, 8, 16}`, and a partial recovery
   toward `S = 32` (`N - 0` = −12.4, about a third of the gain). Whether the
   right-hand rise is *statistically* resolved depends on the trim: `N - R` is
   **+21.0 µs/step [−3.1, +45.1]** untrimmed and **+25.5 [+0.4, +50.6]** trimmed,
   so I report the right side as a **consistent but unresolved rise**, not a
   wall. What *is* solid is that `S = 32` recovers materially less than
   `S ∈ {8, 16}` under both trims — enough for §5.3's regret argument, not enough
   to call it a proven regression.
2. PR #298's single point **replicates**: the `S = 16` effect here (−33.4 µs/step)
   is within 2 µs of #298's `-35.4`, from an independent session with a different
   knob implementation. This axis is not a one-session artefact.
3. `S = 8` is measured for the first time, takes the **argmax** (−36.9 µs/step,
   CI [−61.0, −12.9]), and lands **statistically tied** with `S = 16` (`R - G` =
   +3.6 [−20.5, +27.6], a dead null under both trims). The tie is the important
   half: it means the argmax label is noise between those two, and it is what
   makes §5.3's `S = 8` recommendation cheap rather than a sacrifice.

### 7.2 What I recommend shipping, and what I do not claim

**Recommend: default `S = 8`, flagged as requiring one paired M5 measurement
before promotion.** `research/tanjiro_packing_default_flip.patch` implements
exactly that in **+29 bytes** of submitted surface (verified `patch -p1
--dry-run` clean against `63ab67c8`), well inside this PR's 12,000 B budget. I
have deliberately left it **unapplied**, so `growth` at my PR tip is `0`.

**I do not claim a ranked win.** This is an M4 Pro curve on Apple GPU
generation 16 with 20 GPU cores, and the ranked host is an M5 Max with 40. §5.3
sets out why `S = 8` and not `S = 16`: the one candidate invariant that survives
the core-count change is **threadgroups per core**, and under it
`M5 @ S=8 ≡ M4 @ S=16` (−33.4 µs/step, in the basin) while
`M5 @ S=16 ≡ M4 @ S=32` (−12.4 µs/step, where two thirds of the gain is gone).
Shipping `S = 16` therefore risks landing the ranked host at the load where this
host recovered least. Note that the M4 argmax happens to *be* `S = 8`, but that
is not the argument — `S = 8` and `S = 16` are a dead null here, so §5.3 would
recommend `S = 8` either way. The repo's own precedent is blunt about the cost of
ignoring core-count transfer: PR #48 arm `N` measured `-55.0 µs/step` on M4 and
`+10.0 µs/step` on the ranked M5.

That argument is a **regret-minimising heuristic, not a law**, and §5.3 states the
falsifiable version: if TGs/core is the invariant, the M5 ordering should be
`S = 8` best, `S = 16` measurably worse than `S = 8`, and `S = 4 ≈ S = 8`. If the
M5 instead reproduces the M4 curve in `S` directly, then the invariant is `S` or
threads/TG, §5.3 is wrong, and `S = 16` is the right default. **One paired
official run settles it**, and it is the cheapest high-information run available
from this whole experiment.

### 7.3 Per-kernel verdicts (Stage 2 static audit, §6.2)

| # | Kernel | Verdict |
|---|---|---|
| 0 | **decode NVFP4 QKV lane-major** (`:4735`, this experiment) | **PURSUE** — measured, bit-exact, basin-shaped; M4 argmax `S = 8` (−36.9 µs/step) tied with `S = 16` (−33.4); ship `S = 8` per §5.3. |
| 1 | **routed MoE gate/up packed top-8 R1** (`:7545`) | **PURSUE at `S = 4`–`S = 8`** — 4096 simdgroups, 64-thread TGs, 1 row/simdgroup, no threadgroup memory, no barrier. Structurally the closest twin of kernel 0 and ~the same size. Highest-value single follow-up. |
| 2 | **o_proj gated affine** (`:4035`) | **LOW PRIOR** (explicitly *not* killed) — safe at `S ≥ 2`, but already runs 4 rows/simdgroup, so the ramp/drain amortisation the repack buys is largely already paid. |
| 3 | **shared-expert gate/up rows1** (`:6801`) | **LOW PRIOR** (explicitly *not* killed) — 1 row/simdgroup, so the residency deficit is real, but at 512 total simdgroups it is ≈8× smaller than kernel 1, so the same relative gain is ≈8× less absolute time. |
| 4 | **fused down+residual `_r1_v5`** (`:7851`) | **KILL** — already dispatches 288-thread threadgroups, so there is no ≤64-thread residency deficit to recover, plus the structural expert-identity problem in §6.1. |

I did **not** build the generalized `DARKBLOOM_<KERNEL>_SIMDGROUPS` mechanism
(§6.3): with one clear `PURSUE`, one structural `KILL`, and two low-prior sites, a
shared four-site abstraction would spend editable bytes ahead of the evidence
that says which sites deserve them.

### 7.4 Rule 17

**Prefill: structurally unreachable, and measured null.** The guard at
`LagunaRuntimeModel.swift:4823` requires `normalized.dims(1, 1, hidden)`, so
`lagunaDecodeNVFP4QKVR1` cannot fire for a `seq = 512` prefill. §4 confirms it
empirically at `S = 16` vs the `S = 2` default: **−0.007 ms on 547.9 ms, 95 % CI
±1.346 ms**, with the two blocks disagreeing in sign. No prefill floor risk from
this knob. The caveat that Stage 2 sites *do* run at `seq = 512` and would each
need their own prefill arm is recorded in §4.

### 7.5 Follow-ups I did not implement

Ordered by information per GPU-hour:

1. **One paired M5 run of `S = 8` vs `S = 16` vs default `S = 2`.** Settles §5.3's
   invariant question, decides the default, and is the only measurement that can
   turn this M4 curve into a ranked claim.
2. **The isolated dependency-chained QKV-GEMV microbenchmark** (§5.5; pattern at
   `research/frieren_pr101_gatesp_dispatch_bench.swift`). `S = 2` vs `S = 16`,
   read `GPUStartTime`/`GPUEndTime`, convert to achieved GB/s. If `S = 2` shows
   *lower* achieved bandwidth, the mechanism is resident-simdgroup shortfall and
   it transfers to the M5 with more cores. If both arms hit the same GB/s and the
   gap is a constant ≈1 µs per launch, the mechanism is per-threadgroup
   ramp/drain — and routed MoE (kernel 1) is the next win. This is also the direct
   test of the weakness admitted in §5.2, where my ramp/drain estimate is 3–5×
   larger than the effect actually measured per kernel.
3. **Kernel 1 (routed MoE gate/up) swept over `S ∈ {2, 4, 8, 16}`** with the same
   ABBA design. **Read the `_sgN` implementation note at the end of §6.2 first**:
   kernel 1's name is a static literal at base `:7546`, so without a suffix the
   compiled-kernel cache serves the `S = 2` pipeline to every arm and the sweep
   silently measures nothing. That is the easiest way to fake a null here.
4. **A per-kernel duration breakdown of one decode step.** §6.2 could not resolve
   kernel-duration asymmetry statically; a breakdown would order sites 1–3
   properly and replace the whole TGs-per-core argument with a direct answer.
