# r97-b — prefill threadgroup/dispatch-count arm — result

Assignment `maple-r97-b-prefill-tg-count`, revision `r97-b-rev1`, PR #527,
branch `maple-tanjiro/r97-prefill-tg-count`, base
`codex/mlxfast-maple-20260804-advisor` @ `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.

Preregistration: [`research/tanjiro-r97-prefill-tg-preregistration.md`](tanjiro-r97-prefill-tg-preregistration.md)
(registered at `afb7034`, before any timed run; Amendments 1–3 each registered
before the receipt they could have been fitted to).

## 1. Three-state summary

| mechanism | state | evidence |
|---|---|---|
| **P2** — `DARKBLOOM_FUSED_QKV` row-concatenated `[Wq;Wk;Wv]` BF16 prefill bank | implemented, correctness-verified, **submitted (R1)** | §3, §4, §5 |
| **P2b** — `int32[4]` layout descriptor removing the 78 strided copies P2 introduces | implemented, correctness-verified, census-confirmed, **submitted (R1)** | §3, §4, §5 |
| **P3** — skinny-N NAX retile (`bn` 128→64, `wn` 4→2) | implemented then reverted; **dead by construction, not submitted** | §6 |

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

## 4. Correctness

| check | result |
|---|---|
| `./benchmark.sh --local-submit` at `723e628` (job `5b3686a6`, exit 0, 174 s) | `passed_correctness: true`, `max_abs_diff: 0`, `error: ""`, `checked_steps: 1025`, `num_layers: 40`, golden `f49e4c2c…` |
| 4-rep paired ABBA, 8 arms | correctness green in all 8, `max_abs_diff = 0`, single golden hash `b9509697c08a` |
| adversarial review of all four `_v3` kernels (frontier agent `a7285910`) | no blocker: all four equivalent to `_v2` under both layouts; `uint32` addressing safe at these magnitudes; outputs always freshly allocated; layer 39 causal prefill routes through `callLastPrefillRow`; the slices P2b removes were confirmed dead |
| `research/run_upstream_equivalence.sh` | `EQUIVALENCE_EXIT=1` from **pre-existing** non-M5 prefill near-tie drift (max 0.125, mean 0.0119) that reproduces on the unmodified base. Also note `LagunaUpstreamEquivalence.swift:74-90` bypasses `prepareFusedRuntimeWeights()`, so the oracle is structurally blind to `DARKBLOOM_FUSED_QKV` and is not an instrument for this arm. |

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

Receipt budget: 6. Spent: **1**.

| # | submission id | commit | correctness | decode floor | prefill floor | baseline decode s/tok | baseline prefill s/tok | candidate decode s/tok | candidate prefill s/tok | ranked score | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `b3b6457f-25b6-40f8-8ebf-a417ba11b1a0` | `723e628` | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |

Note file: `research/tanjiro-r97-r1-note.md`.

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

Editable-surface budget at `723e628`:
`current=2903610/3000000, headroom=96390, growth=4134/262144, files=141` — PASS.

## 9. Conclusion

_pending R1 receipt._

## 10. Suggested follow-ups (not implemented)

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
  path is expensive enough to be worth auditing globally.
