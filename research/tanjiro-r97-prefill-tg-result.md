# r97-b — prefill threadgroup/dispatch-count arm — result

Assignment `maple-r97-b-prefill-tg-count`, revision `r97-b-rev1`, PR #527,
branch `maple-tanjiro/r97-prefill-tg-count`, base
`codex/mlxfast-maple-20260804-advisor` @ `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.

Preregistration: [`research/tanjiro-r97-prefill-tg-preregistration.md`](tanjiro-r97-prefill-tg-preregistration.md)
(registered at `afb7034`, before any timed run; Amendments 1–3 each registered
before the receipt they could have been fitted to).

## 1. Three-state summary

| mechanism | final state | evidence |
|---|---|---|
| **P2** — `DARKBLOOM_FUSED_QKV` row-concatenated `[Wq;Wk;Wv]` BF16 prefill bank | submitted (R1), **measured M5 regression `+0.639 ms`, REVERTED** | §3, §4, §5, §7.0 |
| **P2b** — `int32[4]` layout descriptor removing the 78 strided copies P2 introduces | submitted (R1) inside the same binary, **reverted with P2** | §3, §4, §5, §7.0 |
| **P3** — skinny-N NAX retile (`bn` 128→64, `wn` 4→2) | **dead by construction, never submitted** (no receipt spent) | §6 |
| **P4** — swizzle depth 2→3 for `tiles_m % 8 == 0` in `steel_matmul_regular_axpby_nax` | submitted (R2), **measured null `−0.014 ms` (`t = −0.10`), REVERTED** per Amendment 8 | §3, §7.0c |

**The branch's `git diff` against the base is now empty across `Sources/`,
`Vendor/` and `Package.swift`.** All three submitted mechanisms are reverted and
all of the value is in `research/`. That is the honest shape of this result.

**Headline: the arm's primary hypothesis is refuted on M5.** Reducing the BF16
GEMM dispatch count by 20 % (392 → 236 `steel_gemm_bf16` dispatches, and 1222 →
1066 total) at bit-identical output made M5 prefill **slower by 0.639 ms**
(prediction-`t` 4.43, distribution-free p ≤ 0.07), worth **−0.242 %** of score.
The M5 prefill `steel_gemm_bf16` pool is **not** dispatch-count-bound. The same
change is worth **−11.2 ms** on M4 Pro, which is why cross-machine directional
evidence was not sufficient here.

**Second headline: R2 is a preregistered negative control and it passed.** With
P2/P2b reverted, candidate prefill returned to the control-population mean
(`−0.014 ms`, `t = −0.10`) and candidate decode to its mean (`+0.08 σ`). The
R1 regression was therefore caused by the code, not by drift, session artifact
or a mis-specified control population — the single most important check on the
verdict above, and it was registered in §14.6 before R1 was even read.

## 2. Hypothesis

The M5 prefill `steel_gemm_bf16` pool is dispatch-count-bound rather than
purely FLOP-bound: 392 BF16 GEMM dispatches per prefill, of which 117 are the
per-layer `wq`/`wk`/`wv` projections, each launching a small grid that cannot
fill a 40-core M5 Max. Reducing dispatch count at identical FLOPs should reduce
prefill wall time.

## 3. What was implemented

### P2 — fused QKV bank (`64fa273`)

`Sources/MLXFastModel/LagunaRuntimeModel.swift`:

- `DARKBLOOM_FUSED_QKV` flag at `:108-114`, tested `!= "0"` so the mechanism is
  **default ON**. Environment variables do not propagate through the official
  measurement wrapper, so any behaviour that must reach the ranked run has to be
  compiled in as the default.
- `prepareFusedQKVWeight()` (`:5828-5848`) builds
  `concatenated([wq, wk, wv], axis: 0)` once, off the scored hot path, from
  `prepareFusedRuntimeWeights()` (`:9342`).
- Consumption at `:6143`: `if let fusedQKVWeight = _fusedQKVWeight, L > 1`.
  One GEMM replaces three; the result is sliced back into `q`, `k`, `v` at
  `:6163-6165`. `L > 1` restricts it to prefill; decode keeps its INT8 fused
  norm+QKV path.
- The decode INT8 fused-norm guard previously required `_fusedQKVWeight == nil`.
  That clause was removed. Without this fix, populating the bank silently
  disabled decode's INT8 path (+39.99 % per decode step).

Prefill BF16 GEMM dispatches: 392 → 236 (−156).

### P2b — layout descriptor (`84a5c4b`, `c32c537`)

P2 alone hands slices with a non-unit row stride to the prefill QK-norm custom
kernels. `Vendor/mlx-swift/.../metal/custom_kernel.cpp:39-47` reacts to
`ensure_row_contiguous_ && !row_contiguous` by inserting a
`copy_gpu(..., CopyType::General, s)` — 78 general strided copies per prefill,
which gave back most of P2's saving.

Four prefill QK-norm kernels were revised `_v2` → `_v3`
(`laguna_prefill_sliding_qk_norm_rope_bf16_128_v3` ~`:2525`, `..._h1_v3`
~`:2610`, `laguna_prefill_full_qk_norm_yarn_bf16_128_v3` ~`:2698`, `..._h1_v3`
~`:2790`). Each gained a seventh input `"layout"` (`int32[4]`) after
`"offsets"`, and the eight addressing expressions became

```
input = raw_queries + t * uint(layout[0]) + uint(layout[1]) + head * head_dim;
input = raw_keys    + t * uint(layout[2]) + uint(layout[3]) + khead * head_dim;
```

`prefillQKLayout(bank:)` (`:5853-5875`) emits `[queryDim, 0, kvDim, 0]` for the
unbanked case and `[width, 0, width, queryDim]` for the banked case, so the
kernel reads the bank in place. `lagunaPrecheckQKLayout` / `lagunaQKLayout`
(`:2977-3009`) are shape-only by design. The descriptor is cached keyed on bank
presence (`c32c537`).

### P4 — swizzle depth for `tiles_m % 8 == 0` (`f0ed1d7`)

After P2/P2b were reverted, P4 is the **entire** code delta of this branch
against the base. `git diff --stat b78e7cdb -- Sources Vendor Package.swift`
reports exactly `matmul.cpp | 7 ++++++-`.
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp:302-311`, inside
`steel_matmul_regular_axpby_nax`:

```cpp
int swizzle_log = tm <= 3 ? 0 : 1;
if (devc == 's' || devc == 'c' || devc == 'd') {
  swizzle_log = (tm >= 8 && (tm % 8) == 0) ? 3 : 2;
}
```

Every regular-`_nax` prefill class on M5 has `tiles_m = 8`, so this raises the
launch swizzle from depth 2 to depth 3 for all of them. It changes only grid
mapping (`matmul.cpp:325-330`: `tile = 1<<sl; tm = ceil(tm/tile); tn *= tile`),
never accumulation order, so it is bit-exact by construction. `matmul.cpp` is
in `editablePaths` (`benchmark.json:26`). `./setup.sh` was re-run after the
edit, as required for a changed AOT/JIT kernel source.

**P4 is unmeasurable on this host** (gen 16 never reaches `_nax`), so its only
evidence is the R2 receipt. Its registered most-likely outcome is null: the
Wq-class GEMM is compute-bound (arithmetic intensity ≈ 221 FLOP/B against a
machine balance of 55–125), so halving B-side traffic mostly hides under
compute.


## 4. Correctness

| check | result |
|---|---|
| `./benchmark.sh --local-submit` at `723e628` (job `5b3686a6`, exit 0, 174 s) | `passed_correctness: true`, `max_abs_diff: 0`, `error: ""`, `checked_steps: 1025`, `num_layers: 40`, golden `f49e4c2c…` |
| 4-rep paired ABBA, 8 arms | correctness green in all 8, `max_abs_diff = 0`, single golden hash `b9509697c08a` |
| adversarial review of all four `_v3` kernels (frontier agent `a7285910`) | no blocker: all four equivalent to `_v2` under both layouts; `uint32` addressing safe at these magnitudes; outputs always freshly allocated; layer 39 causal prefill routes through `callLastPrefillRow`; the slices P2b removes were confirmed dead |
| `research/run_upstream_equivalence.sh` | `EQUIVALENCE_EXIT=1` from **pre-existing** non-M5 prefill near-tie drift (max 0.125, mean 0.0119) that reproduces on the unmodified base. Also note `LagunaUpstreamEquivalence.swift:74-90` bypasses `prepareFusedRuntimeWeights()`, so the oracle is structurally blind to `DARKBLOOM_FUSED_QKV` and is not an instrument for this arm. |
| `./benchmark.sh --local-submit` at `f0ed1d7` (base + P4 only, job `c3616fe4`, exit 0, 203.7 s) | `passed: true`, `passed_correctness: true`, `max_abs_diff: 0`, `checked_steps: 1025`, `peak_ram_gb: 20.729`; decode floor **pass** (0.008943 s/tok, 1.549×); prefill floor `false` — the same host artifact documented in §7.2 |

## 5. Local evidence (M4 Pro — directional only)

**Host caveat.** This host is an Apple M4 Pro, 20 GPU cores, Apple GPU
generation 16. `Vendor/mlx-swift/.../device.cpp:913-930` requires macOS ≥26.2
and GPU generation ≥17 to select the `_nax` kernel family. This host therefore
**never** selects `_nax`, and on it `wk`/`wv` take the split-K route
(`matmul.cpp:960-966`) that the ranked M5 does not take (M5 fails split-K
admission by the exact tie `2048 > 2048` = false). Local prefill *magnitudes*
do not transfer. Dispatch counts, per-kernel censuses, correctness, and the
sign of the P2b copy-elimination **do** transfer.

### 5.1 GPU dispatch census (job `37d994aa`)

| quantity | baseline (OFF) | P2 only | **P2 + P2b** |
|---|---:|---:|---:|
| total dispatches | 1222 | 1144 | **1066** |
| `steel_gemm_bf16` dispatches | 392 | 236 | **236** |
| `qk_norm_rope` dispatches | 41 | 119 | **41** |
| `qk_norm_rope` ms | 4.188 | 5.704 | **4.209** |
| peak RAM (GB) | 20.7147 | — | 20.7151 |

P2 alone converts 156 GEMM dispatches into 78 extra strided-copy dispatches,
costing 1.516 ms of `qk_norm_rope` time. P2b recovers 1.495 ms of that 1.516 ms
and returns the kernel count to the baseline 41.

### 5.2 4-rep paired ABBA (`e595e08`, analysed by `research/tanjiro_r97_ab_stats.py`)

| rep | order | prefill off (ms) | prefill on (ms) | Δ prefill | decode off (ms) | decode on (ms) | Δ decode |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | off,on | 578.16 | 572.40 | −5.75 | 12.947 | 12.790 | −0.157 |
| 2 | on,off | 575.91 | 567.81 | −8.10 | 13.002 | 12.813 | −0.189 |
| 3 | off,on | 582.40 | 564.19 | −18.21 | 13.017 | 12.876 | −0.141 |
| 4 | on,off | 582.50 | 569.69 | −12.80 | 12.957 | 12.842 | −0.115 |

Mean **prefill −11.216 ms (sem 2.755)**, **decode −0.1504 ms (sem 0.0154)**;
4/4 reps favour the candidate on both axes. True ABBA ordering confirmed from
file mtimes. Of the decode delta, −0.088 ms is the mechanical `S/128`
amortisation of the prefill saving; the −0.063 ms residual is not attributed
and is **not** claimed.

## 6. P3 — negative by construction

P3 was implemented (helper `darkbloom_steel_regular_skinny_tile()` after
`matmul.cpp:93`, guard after `:249`) and then reverted, because its guard

```
bn == 128 && wn == 4 && N % 64 == 0 && tiles_m >= 4 && tiles_m * tiles_n <= 96
```

selects exactly one prefill class — the 78 `wk`/`wv` projections at
`M=512, N=1024, K=2048` (`8 × 8 = 64` tiles) — and **P2 deletes that class**.
Under P2 the shape is `M=512, N=10240, K=2048`, i.e. `8 × 80 = 640` tiles,
6.5× over the 96-tile ceiling. Every other prefill class was already excluded
and stays excluded:

| class after P2 | M | N | K | route | tiles | P3 guard |
|---|---:|---:|---:|---|---:|---|
| fused `[Wq;Wk;Wv]` bank | 512 | 10240 | 2048 | regular-`_nax` | 640 | exclude |
| dense `gate`/`up` | 512 | 8192 | 2048 | regular-`_nax` | 512 | exclude |
| layer-39 `[K;V]` bank | 512 | 2048 | 2048 | regular-`_nax` | 128 | exclude |
| `wo`, `down`, router, `g_proj` | 512 | ≤2048 | ≥6144 | `_nax` split-K | — | never reached |
| every decode projection | 1 | — | 2048 | regular-`_nax` | — | `tiles_m < 4` |

The fused bank stays on the regular `_nax` path: split-K admission
(`matmul.cpp:1015-1017`) needs `K ≥ 3·max(M,N)` or
`max(M,N) ≤ 1024 && K > 2·max(M,N)`, and `N=10240` fails both.

**P3 stacked on P2 is a literal no-op.** Moreover P2 addresses P3's own premise
(a 1.6-wave occupancy deficit) by a strictly better route — folding those 64
threadgroups into a 640-threadgroup launch (16 waves) rather than splitting them
into 128 threadgroups (3.2 waves), and without P3's +33 % A re-read. R1's
receipt therefore closes P3 in both branches: a material gain means P2 already
captured the value, and a null means the premise was false.

Registered as Amendment 3 (`084bfb4`) **before** the R1 receipt returned.

## 7. Official M5 receipts

Receipt budget: 6. Spent: **2**.

Floor verdicts and correctness are read **separately from ranking status**, as
the target contract requires: a `rejected` receipt can mean only that the score
did not beat the current best.

| # | submission id | commit | arms | correctness | decode floor | prefill floor | `bl_dec` ms/step | `bl_pre` ms | `cand_dec` ms/step | `cand_pre` ms | decode speedup | prefill speedup | ranked score | ranking status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `b3b6457f-25b6-40f8-8ebf-a417ba11b1a0` | `723e628` | base + P2 + P2b | **pass** (`max_abs_diff 0`, 1344 checked steps, GPQA 9/9, TTFT 9/9) | **pass** | **pass** | 13.8089 | 187.976 | 4.92433 | **96.797** | 2.804213 | 1.941974 | 2.55810946477023 | rejected — *"score did not improve current best"* (ranking only; `error: ""`) |
| R2 | `048674e9-cff4-449f-90e2-97811149cf97` | `2dddec8` | base + P4 (P2/P2b reverted) | **pass** (`max_abs_diff 0`, 1344 checked steps, GPQA/TTFT 9/9, semantic GPQA 8/9 pass) | **pass** | **pass** | 13.8270 | 188.712 | 4.91326 | **96.144** | 2.81422492674266 | 1.9628057429555446 | 2.5718073554706 | rejected — *"score did not improve current best"* (ranking only; `error: ""`) |

Note files: `research/tanjiro-r97-r1-note.md`, `research/tanjiro-r97-r2-note.md`.
Raw receipts: `research/r97-logs/receipt.r1.json`, `research/r97-logs/receipt.r2.json`.
`peak_ram_gb` was 21 on both receipts — no memory pressure. R2 landed
2026-08-09T12:19:52Z (`createdAt 2026-08-09T12:11:05.855Z`), `golden_hash
be7738fc…`, `harness_hash 8ee45419…`, `num_layers 40`,
`weights_byte_count 21568891382`, `benchmark_wall_seconds 52`.

### 7.0 R1 verdict: P2 + P2b are a measured M5 regression

The published score is **not** the observable to read. The same-session
*baseline* prefill wanders 186.821–196.395 ms (≈5 %) across contemporaneous
receipts, so score-to-score comparison is dominated by baseline draw. The
low-noise observable is the **candidate** prefill wall.

Control population: the 13 contemporaneous scored receipts on this account
between the promoted frontier and R1 give candidate prefill
**96.158 ± 0.139 ms (n = 13)**. R1 sits at **96.797 ms**.

| statistic | value |
|---|---|
| effect | **+0.639 ms** |
| 95 % CI | **[+0.325, +0.953] ms** |
| prediction-`t` (12 dof, se `s·√(1+1/n)` = 0.1441) | **4.43** |
| 95 % prediction interval for a healthy new receipt | [95.844, 96.472] — R1 is outside |
| distribution-free bound (max of 14 exchangeable draws) | p ≤ 0.071 |
| chronological drift (OLS on time) | −0.0059 ms/h, `t = −0.27` — excluded; drift-adjusted `t = +3.18` |

The preregistered `> +0.3 ms` row means *unmodelled regression ⇒ revert, report
negative*, and the advisor's own registered NO-GO for this arm was "if the
receipt shows prefill regressed". Both fire. **P2 and P2b are reverted**
(`4b3af0b`). After the Amendment-8 P4 revert (`9638f0a`) the branch's `git diff`
against the base is empty across `Sources/`, `Vendor/` and `Package.swift`.

An earlier "+4.6 σ" headline was withdrawn as arithmetically wrong (it divided
by the population sd rather than the prediction sd). See Amendment 6 (§15) of
the preregistration for the full audit — drift, prefill-code homogeneity across
the control subgroups, and receipt bookkeeping.

### 7.1a What the regression cost, correctly priced

Prefill is charged **twice**: the 512-token seed forward runs inside the decode
timer (`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift` — timer
opens at line 966, `beginDecode(seedTokens:)` at 968, closes at 1010, and the
harness prints `includes_seed_prefill=true` at 967). With
`CD = 4·CP + T̄` and `f = 4·CP/CD` recomputed from **R1's own JSON**
(`CP = 189.057 µs/tok`, `CD = 4924.33 µs/step` ⇒ `f = 0.153570`), the forward
exponent is `0.25 + 0.75f = 0.365178` and one millisecond of prefill is worth
**0.3773 %**.

Exact counterfactual at the control-mean prefill, propagating the mandatory
`4·ΔCP = +4.99 µs/step` back out of decode: `2.564298` vs the observed
`2.558109` ⇒ the regression cost **−0.242 %**. The remaining gap to our promoted
best `2.58883` is baseline-draw noise, not candidate regression.

### 7.1b The `_nax` trap did not fire

The advisor's registered static trap for this arm was that a fused `N = 10240`
shape might fall off the `_nax` kernel family on Apple GPU generation ≥ 17.
It did not: the selection proof committed at `1628e9c` shows the fused shape
still selects the regular `_nax` path (split-K admission
`K ≥ 3·max(M,N) || (max(M,N) ≤ 1024 && K > 2·max(M,N))` fails for it on M5, as
it does for the unfused `wq`). The regression is therefore **not** the trap, and
that is itself the reportable finding: identical kernel family, identical tile
geometry (`bm=64 bn=128 bk=256 wm=2 wn=4 swizzle_log=2`), identical total
threadgroup count (640 either way) — and still 0.64 ms slower.

### 7.0c R2 verdict: P4 is null, and the negative control passed

R2 is `base + P4` with P2/P2b reverted, so it does two jobs at once. Both
read-outs were registered before R1 was read (§14.6) or before R2 returned
(Amendment 8, §17).

**(a) P4 is null.** Registered point prediction was **−0.4 ms**; registered
bands were `≤ −0.30 ms` keep, `−0.30 … −0.10 ms` inconclusive/repeat,
`−0.10 … +0.10 ms` null ⇒ revert, `≥ +0.30 ms` regression ⇒ revert.

| statistic | value |
|---|---|
| R2 `cand_pre` | **96.1439 ms** |
| control mean ± sd (n = 13) | 96.1580 ± 0.1389 ms |
| effect | **−0.0141 ms** |
| prediction-`t` (12 dof, se = 0.1442) | **−0.098** |
| preregistered null band | 96.02 … 96.30 ms — R2 is inside |
| registered −0.4 ms prediction | excluded at ≈ **2.7** prediction-se |

Widening the `steel_matmul_regular_axpby_nax` swizzle from 2 to 3 for
`tiles_m % 8 == 0` shapes changes nothing measurable on M5. The plausible
reason is that all M5 regular-`_nax` prefill classes already have `tiles_m = 8`,
i.e. exactly one swizzle group at depth 3 — the reorder relabels threadgroups
without changing how many are resident, and the M5 dispatcher was evidently
already scheduling them well. Per Amendment 8 the null band mandates a revert,
which was taken at `9638f0a`.

**(b) The negative control passed.** R2's only relationship to R1 is that it
removes P2/P2b. If R1's `+0.639 ms` had come from drift, a bad session, or a
mis-specified control population, R2 would have inherited it. It did not:

| axis | R2 | control population | deviation |
|---|---|---|---|
| candidate prefill | 96.1439 ms | 96.1580 ± 0.1389 (n = 13) | **−0.10** prediction-se |
| candidate decode | 4.91326 ms/step | 4.91182 ± 0.01716 (n = 9 healthy) | **+0.08 σ** |

Both axes returned to their population means in the same receipt. That is a
clean instrument check: the control population is correctly specified, the
session was healthy, and **R1's regression was caused by the P2/P2b code**.
Registering this control in §14.6 before R1 was read is what makes it evidence
rather than a post-hoc rescue.

**(c) Pricing, recomputed from R2's own JSON** as the standing rule requires:
`CP = 187.781 µs/tok`, `CD = 4913.26 µs/step` ⇒ `f = 0.152877`, forward
exponent `0.25 + 0.75f = 0.364658`, so one millisecond of prefill is worth
**0.3793 %** of score here. The registered `−0.4 ms` P4 prediction would have
been worth **+0.151 %**; the measured null is worth `+0.005 %`, i.e. nothing.

### 7.1 Read-out thresholds registered before R1 (Amendment 2, §11.3)

| observed M5 prefill delta | reading | consequence |
|---|---|---|
| ≤ −1.0 ms | dispatches serialise | promote P2+P2b; occupancy premise live |
| −0.3 to −1.0 ms | partial overlap | keep, repeat on R3 per §10.6 |
| > −0.3 ms | overlap confirmed | close the dispatch-count family |
| > +0.3 ms | unmodelled regression | revert, report negative |

Registered point prediction: **−0.16 ms** (≈ +0.06 % score), from
78 dispatches × ≈2.0 µs of launch overhead. Scoring sensitivity used
throughout: **0.378 % score per ms of prefill**.

### 7.2 Why the local `--local-submit` prefill floor reads `false`

`--local-submit` at `723e628` reported `passed_prefill_speedup_floor: false`
(0.001114 s/tok, 0.330×). This is a **pure host artifact**, not a property of
the candidate: `--local-submit` compares against a pinned M5-class baseline
constant of `0.000368 s/token`, and this M4 Pro runs prefill at
`0.001114 s/token` regardless of the change. The byte-identical base misses the
same floor by the same margin, and the ABBA `off` arm is *slower* than the `on`
arm in all four reps. The decode floor passed on the same run
(`0.008892 s/tok`, 1.558×). This was disclosed in §8 of the R1 note before
submission.

## 8. Reproduction

```bash
# correctness + local scored path
./benchmark.sh --local-submit

# paired ABBA A/B (4 reps, writes research/r97-logs/ab.{1..4}.{off,on}.json)
research/tanjiro-r97-ab.sh 4
research/tanjiro_r97_ab_stats.py ab 4

# GPU dispatch census
research/tanjiro-r97-census.sh

# P2b-specific gate
research/tanjiro-r97-p2b-gate.sh

# upstream-equivalence oracle (see §4 caveat)
research/run_upstream_equivalence.sh
```

Evidence under `research/r97-logs/` is force-added (`git add -f`); that
directory's `.gitignore` is `*` / `!.gitignore`.

Editable-surface budget, `senpai/check-editable-budget.sh b78e7cdb`:

| commit | current | headroom | growth | files |
|---|---|---|---|---|
| `723e628` (R1: base + P2 + P2b) | 2903610 | 96390 | 4134 / 262144 | 141 |
| `2dddec8` (R2: base + P4) | 2899882 | 100118 | 406 / 262144 | 141 |
| `9638f0a` (final: everything reverted) | 2899476 | 100524 | **0** / 262144 | 141 |

All PASS. The final `growth=0` is an independent confirmation that the branch
carries no submitted-surface change.

**Caveat for anyone reproducing the GPU dispatch census:** the local
`DARKBLOOM_GPU_PROFILE` hooks in the vendored MLX device were deliberately
reverted at `131ebfa` to keep the editable surface clean, so
`research/tanjiro-r97-census.sh` on the current tree produces no per-pool
records. Re-apply the hooks locally (research-only, never submitted) before
running a census. The census numbers in §5.1 were taken with the hooks present.

## 9. Conclusion

**The arm is a negative result, and the negative is well measured.**

1. **P2 (fused QKV bank) + P2b (layout descriptor) regress M5 prefill by
   +0.639 ms**, 95 % CI [+0.325, +0.953], prediction-`t` = 4.43 against a 13-receipt
   contemporaneous control population. Correctly priced (prefill charged twice),
   that cost **−0.242 %** of score. Reverted at `4b3af0b`. This crosses both the
   preregistered `> +0.3 ms` revert row and the advisor's own registered NO-GO.
2. **The regression is not the `_nax` trap.** The fused `N = 10240` shape stays
   on the regular `_nax` kernel with the identical tile geometry and the
   identical 640 total threadgroups. Removing 78 dispatches and 156 GEMM launches
   made prefill *slower* while changing nothing the dispatch-count model can see.
   The dispatch-count premise for this arm is therefore **falsified on M5**, and
   the M4 win (−11.2 ms) is fully explained by split-K elimination on `Wk`/`Wv`,
   a transition that does not exist on M5.
3. **The residual is a memory-system effect, not a launch-overhead effect.** Two
   surviving hypotheses, neither of which this arm can separate without another
   receipt: (a) an SLC capacity crossing — the fused 41.94 MB weight bank versus
   the 33.55 MB `Wq` bank forces a band-2 DRAM refetch worth ≈16 µs/layer ≈ 0.6 ms
   over 40 layers, which matches the observed effect almost exactly; (b) loss of
   inter-dispatch overlap, since read-after-read is never hazard-tracked
   (`device.cpp:547-548`) and three independent GEMMs on the same input could
   previously overlap where one large GEMM cannot.
4. **P3 (skinny-N NAX retile) is dead by construction**, registered as
   Amendment 3 *before* R1 returned: the `_nax` kernel's `bn = 128` is already the
   minimum instantiated tile width, so there is no skinnier N to retile to. It was
   never submitted and consumed no receipt.
5. **P4 (swizzle depth 2 → 3 for `tiles_m % 8 == 0`) measured null on M5** —
   `−0.014 ms`, prediction-`t` = −0.098, squarely inside the preregistered
   `−0.10 … +0.10 ms` null band, with the registered `−0.4 ms` point prediction
   excluded at ≈2.7 prediction-se. Amendment 8 (registered while R2 was still
   `validating`) mandates a revert for that band, taken at `9638f0a`. All M5
   regular-`_nax` prefill classes already have `tiles_m = 8`, so depth 3 yields
   exactly one swizzle group: it relabels threadgroups without changing residency.
   It was unmeasurable on this M4 Pro host, which reports Apple GPU generation 16
   and never selects `_nax` at all, so R2 was the only way to read it. §7.0c.
6. **The preregistered negative control passed, and that is what makes point 1
   safe.** R2 differs from R1 only by removing P2/P2b, and in the same receipt
   candidate prefill returned to `−0.10` prediction-se of the control mean and
   candidate decode to `+0.08 σ` of its mean. Drift, session artifact, and
   mis-specified controls are therefore all excluded as explanations of R1's
   `+0.639 ms`; the code caused it. This control was registered in §14.6 before
   R1 was read. **The branch's code diff against the base is now empty** —
   every submitted mechanism is reverted and all surviving value is in
   `research/`.
7. **A methodological result worth carrying forward:** the published ranked score
   is a poor observable for a prefill arm because the same-session *baseline*
   prefill wanders ≈5 % while the candidate prefill wall has sd 0.139 ms
   (0.14 %). Reading the candidate wall against a contemporaneous control
   population turned an apparently ambiguous `rejected` receipt into a
   4.4-sigma-equivalent regression call. Any future prefill arm should be read
   this way.
8. **The pricing correction is accepted and fully propagated.** Prefill is
   charged twice, `f` must be recomputed from each candidate's own JSON, and the
   score conversion is 0.3773 %/ms on R1 and 0.3793 %/ms on R2, rather than the
   stored 0.330 exponent. Every figure in this document has been restated; no
   GO/NO-GO bar moved because all bars are expressed in milliseconds.

**Recommendation to the advisor: stop spending receipts on the prefill
dispatch-count family and move the next arm to the decode axis.** The remaining
gap to the leader is 1.05 %, which needs ≈ −2.8 ms of prefill — more than four
times the entire measured effect of the most aggressive fusion available — or
≈ −0.069 ms/token of decode. Decode also carries 75 % of the weight directly
*and* the 15 % of it that is seed prefill, and `f` rises as decode improves, so
decode work appreciates both terms at once.

## 10. Suggested follow-ups (not implemented)

- **Move the next arm to the decode axis (highest value).** See §9. The
  prefill dispatch-count family is closed by this arm; the SLC-capacity story in
  §9.3 predicts that *any* weight-bank enlargement on M5 prefill will cost
  roughly this much, which also argues against the naive `[K;V]` fusion below
  unless it is paired with a tiling change that shrinks the streamed footprint.
- **Tall-M retile (P3′).** For the large-N prefill shapes on M5, move
  `bm 64 → 128`, `wm 2 → 4`. This holds `SM = bm/wm = 32` and `SN = bn/wn = 32`,
  so it reuses the same `gemm_loop` instantiation and should be bit-exact by the
  same argument that made P3 bit-exact. It halves `tiles_m` (8 → 4) and
  therefore halves the number of times the weight matrix is streamed: for the
  fused bank, `8·10240·2048` → `4·10240·2048` BF16 elements per layer, i.e.
  335 MB → 168 MB of B traffic per layer against a 42 MB per-layer weight that
  cannot be SLC-resident. Open risks: threads/threadgroup rises to 512 (16
  simdgroups) and must clear `max_total_threads_per_threadgroup`; register
  pressure; AOT/JIT dispatchability of the geometry; occupancy at 320
  threadgroups.
- **Fuse the layer-39 `[K;V]` bank into the same concatenation** so that the
  final layer also takes one GEMM instead of two.
- **Extend the layout-descriptor trick to any other custom kernel** that
  currently forces `ensure_row_contiguous_`; the census shows the general-copy
  path is expensive enough to be worth auditing globally. Note P2b was reverted
  only because it was bundled with P2 in a single receipt — it removes 78 strided
  copies and 156 dispatches and was never independently measured on M5. If the
  advisor wants one more prefill receipt, **P2b alone** is the cheapest way to
  split P2's regression from P2b's benefit, and it is the only unmeasured
  mechanism left in this arm.
- **Discriminate the two §9.3 hypotheses with one cheap receipt.** Submit P2
  fused as `[Wk;Wv]` only (bank 8.39 MB, *smaller* than `Wq`, dispatch count
  still reduced). SLC-capacity predicts no regression; loss-of-overlap predicts
  the same per-dispatch penalty. That is a clean one-bit experiment and it costs
  one receipt.
- **Adopt the control-population read-out as standard practice** for every
  prefill arm: publish `cand_pre` against the contemporaneous scored-receipt
  population rather than reading the ranked score, and recompute `f` from the
  candidate's own JSON. `research/tanjiro_r97_control_audit.py` and
  `research/tanjiro_r97_wandb.py --receipt LABEL=PATH` already do this end to end.

## 11. Reply to advisor feedback `r97-b-fb1-prefill-price-confirmed`

Posted here because the PR-comment channel returned HTTP 403 for this role; this
section is the reply of record. Advisor comment id `5231447437`,
2026-08-09T12:11:02Z.

1. **Pricing correction accepted**, and verified in source rather than taken on
   trust — see §7.1a for the exact line numbers. Standing rule adopted: `f` is
   recomputed from each candidate's own score JSON and never carried; in
   particular the 0.330 exponent in `research/frieren-r97-rule58-result.md` is
   not reused. R1 re-priced at 0.3773 %/ms; the regression cost **−0.242 %**,
   not the −0.166 % first published. Downstream restatements: P4's registered
   −0.4 ms is worth **+0.151 %**; the leader gap needs **≈ −2.8 ms** of prefill.
   No GO/NO-GO bar moved — every bar in this arm is in milliseconds, and the
   *preregistered* 0.378 %/ms sensitivity was already correct. Only the post-hoc
   §14.4 counterfactual was wrong; it is marked superseded. Amendment 7
   (`b243ec8`).
2. **This arm has no power to test rule 58 and does not claim to.** The +0.639 ms
   prefill regression necessarily injects +4.99 µs/step into decode; the observed
   +10.3 µs/step against a prediction se of ≈18.5 µs is consistent but is only
   0.27 of the decode prediction sd. The advisor's M4 measurement stands
   unchallenged.
3. **P2 + P2b: terminal NO-GO**, crossing the advisor's own registered bar. §7.0.
4. **The advisor's `_nax` static trap did not fire**, and that is the reportable
   finding: the dispatch-count premise is falsified on M5 at fixed kernel family,
   fixed tile geometry and fixed threadgroup count. §7.1b, §9.2, §9.3.
5. **P3 is dead by construction**, registered before R1 returned. §6. The
   advisor's stopping rule "P2 terminal AND P3 terminal or shown not to fit" is
   satisfied on both limbs.
6. **R2 has landed and is a null for P4** (`−0.014 ms`, `t = −0.098`), read
   against bars registered before submission; Amendment 8's null band mandates
   the revert, taken at `9638f0a`. R2 also **passed as the preregistered
   negative control**: with P2/P2b removed, candidate prefill and decode both
   returned to their control-population means, which is what licenses the causal
   claim in item 3. The branch's code diff against the base is now empty. §7.0c.
7. **Recommendation: move the next arm to decode.** §9. If one more prefill
   receipt is preferred, the two highest-information single-receipt options are
   **P2b alone** and **`[Wk;Wv]`-only fusion**; see §10.

## 12. W&B record

Single terminal run for the whole arm:
**https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/l8fvmhf3**
(run id `l8fvmhf3`, project `wandb-applied-ai-team/mlxfast-maple`, name
`r97-b-prefill-tg-count-terminal`, state `finished`).

It carries 132 summary keys plus three artifacts (`abreps`, `censusfamilies`,
`officialreceipts`). The M5 read-outs are logged under `official/R1/*` and
`official/R2/*`, each with its own independently recomputed price block, so the
pricing rule is auditable per receipt rather than inherited:

| key | R1 | R2 |
|---|---|---|
| `candidate_prefill_ms` | 96.79658 | 96.14388 |
| `candidate_decode_ms_per_step` | 4.924326 | 4.913256 |
| `vs_control/delta_ms` | **+0.638583** | **−0.014125** |
| `vs_control/prediction_t` | **+4.42903** | **−0.09797** |
| `vs_control/score_pct` | **−0.240913** | +0.005357 |
| `price/f_prefill_share_of_decode` | 0.1535689 | 0.1528771 |
| `price/score_pct_per_ms_prefill` | 0.377262 | 0.379283 |
| `official_score` | 2.5581095 | 2.5718074 |
| `passed_correctness` / floors | True / True / True | True / True / True |
| `max_abs_diff` | 0 | 0 |

The M4 ABBA and census series are logged as directional-only context and are
labelled as such; nothing in the verdict rests on them.
