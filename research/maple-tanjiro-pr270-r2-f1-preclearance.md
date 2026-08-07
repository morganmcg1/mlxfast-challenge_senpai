# PR #270 r2 — F1 Step 0 pre-clearance (`DARKBLOOM_FUSED_QKV=1`)

Student: maple-tanjiro. Assignment `maple-2026-08-07i-nonmoe-prefill-census`, revision r2.
Host: M4 Pro, 20 GPU cores, Apple GPU generation 16 (no `_nax` prefill kernels),
48 GiB unified memory, macOS 26.5.2. No ranked slot consumed. No submitted-path
file was changed by this revision; F1 was exercised purely as an environment flip.

## Verdict first

**F1 must not get a ranked slot — not as specified, and not after a guard fix
either.** Two independent reasons:

1. **It fails the decode floor.** A bare `DARKBLOOM_FUSED_QKV=1` flip gives
   `decode_speedup` 0.7705 against the 0.95 floor (+39.99 % seconds/token),
   because the flag is not prefill-only: materialising `_fusedQKVWeight`
   *disables* the fused decode norm+INT8-QKV block (finding A). That part is
   fixable in ~1 line.
2. **The prefill win it is supposed to buy does not exist on M5.** The advisor's
   −78 dispatch prediction is **confirmed exactly**, but the −78 turns out to be
   −156 steel GEMM dispatches *cancelled by* +78 brand-new `g2_copy` kernels, and
   the whole −156 comes from `wk`/`wv` split-K GEMMs and their accums — a route
   that **only M4 takes**. Projected onto M5 the net dispatch delta is **≈ 0**
   (finding D). That is not fixable in 1 line.

The M4 prefill measurement is also weaker than it first looks: −0.67 % under the
dispatch probe versus −1.61 % under `--local-iterate`, i.e. 0.66–1.58 ms on the M5
score model, straddling the ≈1.35 ms 3σ bar with a central estimate **below** it.

Findings A–D below are worth more than the pre-clearance verdict itself. Finding B
in particular is a team-wide correctness-oracle caveat affecting **every**
experiment gated on `prepareFusedRuntimeWeights()`, not just F1.

## Task 1 — branch hygiene so the PR can merge

`74e3bfd` dropped the three advisor-owned research-state documents that r1 had
carried, restoring them to their branch-point bytes. The branch then merged the
assigned research base `5daa838` (`52fa216`), so it now carries the advisor's
*exact* current bytes for all three:

| file | HEAD vs `5daa838` |
| --- | --- |
| `research/CURRENT_RESEARCH_STATE.md` | identical |
| `research/RESEARCH_STATE_ARCHIVE_rounds-22-28.md` | identical |
| `research/maple-byte-recovery-census-2026-08-07.md` | identical |

Merging the branch back therefore proposes no change to any advisor-owned file.
`git diff 5daa838 HEAD -- Sources/ Vendor/` is empty, and
`senpai/check-editable-budget.sh 5daa838` reports
`current=2950855/3000000 headroom=49145 growth=0/262144 files=142`. The complete
delta against the base is 25 research-only files: this report, the r1 census
deliverable, three driver scripts, and the `research/pr270-logs/` evidence.

## Item 2.1 — correctness with the flag on

### 2.1a `research/run_upstream_equivalence.sh`

Flag-on run `07f99185-a2f2-4aaf-86d6-71ef779efa6a` (exit 0, 71.5 s);
matched flag-off control `adeeec58-40e7-4a4e-a728-c0c5c53193be` (exit 0, 17.9 s).
Logs: `research/pr270-logs/equivalence.{on,off}.log`. Non-zero test count, so the
wrapper's zero-test guard did not fire.

Both arms emit a **byte-identical** report:

```
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
prefill: maximumAbsoluteLogitError 0.125, meanAbsoluteLogitError 0.011933609,
         runtimeToken 5991 == upstreamToken 5991
decode-0..7: maximumAbsoluteLogitError 0.0, all tokens identical
             (509/902/5991/509/902/5991/509/902)
✘ Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() failed
  ... .passes(maximumAbsoluteLogitError: tolerance → 0.0)
```

The `EXIT=1` prefill 0.125 divergence reproduces on the **unchanged base** on this
host, so it is a pre-existing gen-16 near-tie condition, not something the flag
caused. Because the control arm is byte-identical, no matched-control follow-up
was needed beyond the one already run.

### 2.1b public 64-step drift tripwire

Real correctness evidence for the flag comes from the public tripwire that
`--local-iterate` runs. **Both** arms of the item-2.4 pair reported:

```
passed_correctness   = True
max_abs_diff         = 0
checked_steps        = 130
first_failing_step   = None
golden_hash          = b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
```

`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **not** set in either arm. `max_abs_diff = 0`
is consistent with the in-code bit-exactness claim at
`LagunaRuntimeModel.swift:104-106` (fused dispatch keeps the same K-loop and scale
order as the separate dispatches).

## Item 2.2 — prefill dispatch-count delta

Run `1335f438-efcc-4870-a4e3-b1c6b9770ee7` (exit 0, 135.3 s, four sequential arms,
`ALLDONE`, all four sub-exits 0), instrumented worker built at the LOCAL-ONLY
commit that is reverted at the tip of this branch. Byte-emitting MLX dispatch
hook, `research/prefill_probe.py --reps 3 --profile --profile-top 90`.

```
########## DISPATCH TAG=off        ########## DISPATCH TAG=on
DARKBLOOM_FUSED_QKV=UNSET          DARKBLOOM_FUSED_QKV=1
cbs= 1066  dispatches= 1222        cbs=  988  dispatches= 1144
  command buffers  1066.0/request    command buffers   988.0/request
  dispatches       1222.0/request    dispatches       1144.0/request
```

**Delta = −78 dispatches per request (and −78 command buffers). The advisor's
prediction of exactly −78 is confirmed.** My own preregistered prediction of −156
was wrong, and *why* it was wrong is the useful part.

### The −78 is a coincidence of two opposite effects

−78 is **not** "78 fewer GEMMs". The per-family table decomposes it exactly:

| family | off n/req | on n/req | delta |
|---|---|---|---|
| `steel_gemm_bf16` | 392.0 | 236.0 | **−156** |
| `qk_norm_rope` | 41.0 | 119.0 | **+78** |
| every other family (`routed_gather_gemm` 76, `sort_scatter` 154, `attention_core` 40, `nvfp4_dense_qmm` 116, `elementwise` 234, `moe_tail` 38, `rms_norm` 83, `router` 40, `lm_head` 5, `other` 3) | — | unchanged | 0 |
| **total** | **1222** | **1144** | **−78** |

So my −156 was the correct *steel* delta (78 split-K GEMMs **plus** their 78
`steel_gemm_splitk_accum` dispatches, exactly as preregistered — the accums *are*
counted). It was cancelled halfway by a cost neither prediction included.

### The +78 is `g2_copy`: slicing the fused bank

The `qk_norm_rope` family gains 78 dispatches, and the per-kernel table names them:

```
off: laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v2                       29.0   3.283 ms
     laguna_prefill_full_qk_norm_yarn_bf16_128_h1_v2                          10.0   0.905 ms
on:  MIXED:g2_copybfloat16bfloat16+laguna_prefill_sliding_qk_norm_rope_bf16_128  87.0   4.513 ms
     MIXED:g2_copybfloat16bfloat16+laguna_prefill_full_qk_norm_yarn_bf16_128_h1  30.0   1.191 ms
```

`87 = 29 + 2·29` and `30 = 10 + 2·10`, i.e. **exactly two `g2_copy` general-strided
copies per layer × 39 layers = +78**. Those are the `queries`/`keys`/`values`
slices at `LagunaRuntimeModel.swift:5892-5894` being materialised: the code takes
three slices of the `[512, 10240]` fused output, and the reshape of a
row-strided slice cannot stay a view. The in-code comment at `:5885-5887` already
anticipated this — *"the slices are views and the reshapes below may copy, which
does not change values"* — but the cost was never quantified. It is
**+78 dispatches and +1.516 ms/request** on this host.

## Item 2.3 — steel route delta

`research/tanjiro_steel_trace.sh` methodology (`DARKBLOOM_STEEL_TRACE=1`,
`--reps 1`, matching r1). Raw counts below are halved from the traces because the
probe issues a warmup request plus one measured request.

### Route table, per request

| route | shape | off | on |
|---|---|---|---|
| split-K `bm32_bn32_bk16_wm2_wn2` `MN_taligned_K_taligned` | M=512 **N=1024** K=2048 parts=2 grid=(32,16,2) group=(32,2,2) — **wk + wv** | **78** | **0** |
| split-K same | M=512 N=256 K=2048 parts=2 — router | 38 | 38 |
| split-K same | M=512 N=64 K=2048 parts=4 — `g_proj` sliding | 29 | 29 |
| split-K `MN_naligned_K_taligned` | M=512 N=48 K=2048 parts=4 — `g_proj` full | 10 | 10 |
| **split-K subtotal** | | **155** | **77** |
| regular `steel_gemm_fused_nt_bf16_bf16_bm64_bn64_bk16_wm2_wn2` | M=512 **N=10240** K=2048 grid=**(160,8,1)** group=(32,2,2) — **fused [Wq;Wk;Wv], sliding** | 0 | **29** |
| regular same | M=512 **N=8192** K=2048 grid=**(128,8,1)** group=(32,2,2) | 31 (29 = **wq sliding** + 2 unrelated) | 12 (10 = **fused QKV, full** + 2 unrelated) |
| regular same | M=512 **N=6144** K=2048 grid=(96,8,1) group=(32,2,2) — **wq full** | 10 | **0** |
| regular same | M=512 N=2048 K=8192 — `o_proj` sliding | 30 | 30 |
| regular same | M=512 N=2048 K=6144 — `o_proj` full | 10 | 10 |
| regular same | M=512 N=2048 K=2048 | 1 | 1 |
| **regular subtotal** | | **82** | **82** |
| split-K accums (`steel_gemm_splitk_accum_bfloat16_float32`) | one per split-K GEMM | 155 | 77 |
| **`steel_gemm_bf16` family total** | | **392** | **236** |

**Answering the question directly: the 155 split-K / 82 regular split becomes
77 split-K / 82 regular.** The regular count is *identical* — 39 `wq` GEMMs leave
and 39 fused GEMMs arrive — so the entire steel saving is the 78 `wk`/`wv`
split-K GEMMs and their 78 accums.

The fused projection routes **regular, not split-K**, as preregistered: N grows to
`Nq + 2·1024` (10240 sliding, 8192 full), and the large N keeps the split-K
predicate at `matmul.cpp:971-983` from firing. Same kernel and threadgroup shape
as the `wq` GEMM it replaces (`group=(32,2,2)`), grid widening 128→160 (sliding)
and 96→128 (full). Note the 39/40 asymmetry is unchanged from r1: layer 39 already
carries a fused `[K;V]` bank, so only 39 layers are affected.

### Where the time actually goes

| sub-family | off ms/req | on ms/req | delta |
|---|---|---|---|
| regular steel GEMM | 182.918 | 203.974 | **+21.056** |
| split-K GEMM + accum | 35.758 | 7.488 | **−28.270** |
| `steel_gemm_bf16` total | 218.675 | 211.462 | **−7.213** |
| `qk_norm_rope` (incl. the new copies) | 4.203 | 5.719 | **+1.516** |
| net accounted | | | **−5.697** |

Probe wall clock, mean of the two steady reps (rep 0 is warm-up):
**548.985 → 545.315 ms, −3.670 ms (−0.67 %)**.

That is **less than half** the −1.61 % the `--local-iterate` pair reported in item
2.4. Honest range for the prefill win on this host: **−0.67 % to −1.61 %**, i.e.
−3.7 to −9.4 ms out of ~549–583 ms. Extrapolated onto the M5 score model
(S = 97.895 ms) that is **0.66 ms to 1.58 ms**, straddling the ≈1.35 ms 3σ bar,
with a central estimate *below* it. This is consistent with r1 census §7, which
predicted only −0.3 to −1.5 ms for this component.

One caveat worth recording: `sort_scatter` reports 30.875 → 11.901 ms/req with an
**identical** 154 dispatch count. With no count change and no causal path from a
QKV projection to the MoE routing sort, that −19 ms is almost certainly a
GPU-overlap attribution artefact (per-family `%wall` sums to 105.4 % in the off
arm), not a saving. I do **not** claim it, and it is the reason I quote wall clock
rather than a sum of family times.

## Finding D — the M4 dispatch win does not exist on M5

This is the most decisive result of the pre-clearance, and it follows from
combining item 2.3 with the r1 census's cross-architecture route table.

The **entire** −156 steel saving is `wk`/`wv` **split-K** GEMMs plus their accums.
But r1 established that on M5 `wk`/`wv` do **not** route split-K — the predicate
`K > 2·max` is the exact tie `2048 > 2048`, which is false — so they are already
plain regular GEMMs there (M5 split-K 117 vs M4 155; M5 steel family 354 vs 392).

Projecting F1 onto M5:

| | M5 off | M5 on | delta |
|---|---|---|---|
| `wq`+`wk`+`wv` regular GEMMs | 117 | 0 | −117 |
| fused QKV regular GEMMs | 0 | 39 | +39 |
| split-K accums for `wk`/`wv` | **0** | 0 | **0** |
| `g2_copy` slice kernels | 0 | 78 | **+78** |
| **net dispatches** | | | **≈ 0** |

On M5 there are no `wk`/`wv` accums to delete, so the steel saving shrinks from
−156 to −78, and the +78 `g2_copy` cancels it **exactly**. What remains is only
the arithmetic/bandwidth consolidation of reading the `[512, 2048]` activation
once instead of three times (≈156 MB of avoided reads across 39 layers, order
0.4 ms) against the cost of writing 78 fresh `[512, 1024]` slice copies (≈156 MB
of traffic, the same order). Those roughly cancel too.

**So F1's measured M4 prefill win is largely an artefact of M4-specific split-K
routing for `wk`/`wv`, and the mechanism it exploits is absent on the ranked
host.** This independently explains the prior ablation note quoted in finding C
("a mild prefill cost with no decode gain") and is a direct warning against
spending a ranked slot on F1 in any form until the `g2_copy` problem is solved.

### The follow-up that would make F1 real

Eliminate the 78 `g2_copy` dispatches by letting the `qk_norm_rope` kernels read
Q/K/V directly out of the fused `[512, 10240]` bank with a row offset and a
stride, instead of demanding three contiguous arrays. Both
`laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v2` and
`laguna_prefill_full_qk_norm_yarn_bf16_128_h1_v2` are already Laguna-owned
kernels on the submitted surface, so this is reachable. That would turn the M5
delta from ≈0 into a true −78 dispatches with the activation read once, and
would take M4 to −156. Combined with the `:5709` decode-guard fix from finding A,
*that* is the version of F1 worth a ranked slot.

## Item 2.4 — one matched `--local-iterate` pair (directional only)

Explicitly **not** decisive, per the assignment. Note also that `--local-iterate`
labels its own baseline *"official-runner constants; local speedups are
directional"* — the baseline is a **pinned M5 constant**. So the absolute
`prefill_speedup ≈ 0.32` and `passed_prefill_speedup_floor: false` in both arms is
host mismatch (gen 16 selects no `_nax` prefill kernels), **not** a regression.
Only the absolute seconds/token compare between arms. `decode_speedup`, however,
is computed against the same pinned constant in both arms, so its *change* between
arms is meaningful.

- Control (flag off): `1247bd17-6fdc-409e-9488-3230d218ee4e`, exit 0, 284.8 s, commit `94442a4`.
- Candidate (flag on): `09c4ed52-53e8-4315-8cf6-6c5afaa55320`, exit 0, commit `596026e`;
  driver log line 1 confirms `tag=on DARKBLOOM_FUSED_QKV=1`.

| metric | off | on | delta |
|---|---|---|---|
| prefill s/tok | 0.001138663248046875 | 0.001120292806640625 | **−1.61 %** (582.996 → 573.590 ms per 512 tok; −9.406 ms) |
| decode s/tok | 0.0128459124375 | 0.0179835325546875 | **+39.99 %** (+5.138 ms/step) |
| `decode_speedup` | 1.0786475641626645 | **0.7704944575277318** | **fails the 0.95 floor** |
| `prefill_speedup` | 0.3227638986245973 | 0.3280565464507634 | (host-mismatched constant) |
| score proxy `d^0.75·p^0.25` | 0.79778 | 0.62239 | **−21.98 %** |

Both arms: `decode_steps=128`, `repeats=1`, `num_layers=40`, `peak_ram_gb=21`;
`correctness_seconds` 2.2 (off) / 2.9 (on). Control steady-state decode
`last_step_seconds ≈ 0.008134`; the reported `decode_seconds_per_token` amortises
the seed prefill (`includes_seed_prefill=true`).

Extrapolating only the prefill fraction onto the M5 score model (S = 97.895 ms,
0.374750 %/ms): 1.61 % of S ⇒ **≈1.579 ms**, marginally above the ≈1.35 ms 3σ bar
(paired σ ≈ 0.4497 ms). Single repeat, different kernel family — directional only.

Artifacts: `research/pr270-logs/f1-iterate.{off,on}.{log,json}`.

## Finding A — `DARKBLOOM_FUSED_QKV=1` is not prefill-only; it costs decode

`LagunaRuntimeModel.swift:5709` guards the **entire** fused decode norm+INT8-QKV
block on `_fusedQKVWeight == nil`. Setting the flag materialises that bank
(`:11027` → `prepareFusedQKVWeight()`, bank built `:5590-5609` via
`concatenated([wq, wk, wv], axis: 0)`), so the `B == 1, L == 1` decode path stops
taking the fused block and falls back to stock BF16 separate projections at
`:5905-5908`. That silently gives up:

- `lagunaNormAffineQKV`,
- the group-32 INT8 native-affine QKV bank,
- the gate rows riding on that bank, and
- the deferred-gate / fused-gated-output path.

The bank's *use* site at `:5881` is already gated on `L > 1`, so the fused bank is
only ever consumed by prefill anyway — the decode regression is pure collateral
from the `== nil` guard.

Measured cost: **+5.138 ms/step, `decode_speedup` 0.7705**. The in-code note at
`:5877-5880` predicted only about +1.4 ms/step; the real cost is roughly 3.7×
larger. Decode carries 75 % of the score weight and this is code-path *selection*
rather than a kernel-timing artefact, so it transfers to M5.

Minimal fix: relax the `_fusedQKVWeight == nil` condition at `:5709` so decode
keeps its fused INT8 path while prefill uses the fused bank. That is a ~1-line
submitted-path change, so it is **described here, not smuggled into this
research-only PR**.

## Finding B — `LagunaUpstreamEquivalence` is blind to the whole fused-weight family

`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:74-90` builds
`LagunaRuntimeModel(runtimeConfig)` and calls `update(parameters:)` + `eval`
**directly**, bypassing the weight cache. `prepareFusedRuntimeWeights()`
(`LagunaRuntimeModel.swift:11016`) has exactly **one** caller —
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:637` — so the equivalence harness
never invokes it.

Consequences on the equivalence path:

- `_fusedQKVWeight` stays nil, so `DARKBLOOM_FUSED_QKV` is a **no-op** there;
- `prepareNativeAffineQKVWeight`, `prepareNativeAffineOProjWeight`,
  `prepareRoPEAngleAtlases`, `prepareLastPrefillProjectionWeights` and
  `prepareFusedSharedGateUp` are all absent as well.

That fully explains why decode error is exactly 0.0 in both arms and why the two
reports are byte-identical. **The oracle is structurally insensitive to every
change gated on `prepareFusedRuntimeWeights()`, not just F1.** Any future
experiment touching that family should treat the public tripwire (and the hidden
M5 gates) as its only real correctness evidence, and should not read an
equivalence pass as coverage.

## Finding C — an env flip can never be how F1 ships, and a prior ablation already saw a prefill loss

The ranked workflow never sets `DARKBLOOM_*` in either ranked phase (that is the
stated rationale behind the worker-env allowlist in
`Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1936-2030`, whose
allowed-prefix list is what lets the flag reach the worker under
`--local-iterate` at all). Landing F1 therefore requires flipping the
`lagunaFusedQKVEnabled` default at `LagunaRuntimeModel.swift:108-114` in a
submitted path — which should be bundled with the `:5709` guard relaxation from
finding A.

That same default-site comment records, verbatim:

> "Ablation on the paired local benchmark showed a mild prefill cost with no
> decode gain, so this ships opt-in."

The "no decode gain" half is now fully explained by finding A. The "mild prefill
cost" half is the **opposite sign** to what this revision measured (−1.61 %,
i.e. a prefill win) and to the r1 census prediction, which is a reason to insist
on a properly matched M5 pair before committing a ranked slot to guard-fixed F1.

## Recommendation

1. Do **not** spend a ranked slot on bare F1. It fails the decode floor.
2. Do **not** spend a ranked slot on a guard-fixed F1 either. Fixing `:5709`
   removes the decode regression but leaves a projected **≈0** M5 dispatch delta
   and a prefill effect whose central estimate is below the 3σ bar.
3. If the QKV fusion idea is still wanted, the *prerequisite* is removing the 78
   `g2_copy` slice kernels — teach the two `laguna_prefill_*_qk_norm_*` kernels to
   read Q/K/V from the fused bank with a row offset and stride. Only that version
   has a mechanism that survives on M5. Sequence it as: (a) strided-read kernels,
   (b) `:5709` decode-guard relaxation, (c) `:108-114` default flip, (d) local
   floor re-check, (e) ranked slot.
4. Treat finding B as a standing caveat for the whole team: an equivalence pass is
   **not** correctness coverage for anything in the `prepareFusedRuntimeWeights()`
   family.
5. F4, which r2 said waits on F1, should be re-triaged on its own merits rather
   than inheriting an F1 go-ahead.

## Reproduction

```bash
# item 2.1
research/run_upstream_equivalence.sh                       # control
DARKBLOOM_FUSED_QKV=1 research/run_upstream_equivalence.sh # candidate

# item 2.4 (matched pair, one after the other on a quiet host)
research/tanjiro_f1_iterate.sh off
research/tanjiro_f1_iterate.sh on

# items 2.2 / 2.3 need the byte-emitting MLX dispatch + steel-GEMM
# instrumentation. Its diff is recorded on this branch at commit b0096e3
# (applied) / 3f2c90c (reverted); r2 reapplied it locally to rebuild
# .build-worker, and the tip of this branch is again byte-identical to base
# under Vendor/ and Sources/. With that worker in place:
DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_GPU_PROFILE=1 \
  DARKBLOOM_GPU_PROFILE_SPLIT=1 \
  python3 research/prefill_probe.py --reps 3 --profile --profile-top 90
DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_STEEL_TRACE=1 \
  python3 research/prefill_probe.py --reps 1
# prefix either with DARKBLOOM_FUSED_QKV=1 for the candidate arm
```

### Committed artifacts

| file | contents |
|---|---|
| `research/pr270-logs/equivalence.{off,on}.log` | item 2.1a, both arms |
| `research/pr270-logs/f1-iterate.{off,on}.{log,json}` | item 2.4 matched pair |
| `research/pr270-logs/f1-dispatch.{off,on}.log` | item 2.2 dispatch counts plus per-family and per-kernel profile tables |
| `research/pr270-logs/f1-steel.{off,on}.log` | item 2.3 traced-line counts |
| `research/pr270-logs/f1-steel.{off,on}.worker.err` | item 2.3 raw per-dispatch steel route traces |

The two `f1-dispatch.*.worker.err` raw byte streams (≈1 MB each) are **not**
committed; everything cited from them is already aggregated into the
corresponding `f1-dispatch.*.log`.
