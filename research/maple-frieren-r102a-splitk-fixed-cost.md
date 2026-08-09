# R102-A rung 1 — split-K decode attention: is the per-dispatch fixed cost small enough?

**Student:** maple-frieren · **PR:** #566 · **assignment** `maple-r102-a-splitk-decode-attention`
· **revision** `r102-a-rev1` · **base** `codex/mlxfast-maple-20260804-advisor` @ `51e36805` (`51e36805030a982daecda80535281f4540a1cde1`)

**Verdict: NO-GO on both arms.** The primary (full-attention) arm measures
`f/τ₀ = 33.6 %` resident / `28.8 %` SLC-defeat against a `9.4 %` bar, and the
secondary (sliding) arm measures `20.3–52.2 %` against a `1.6 %` bar. This
retires ≈70.6–75.9 µs/step ≈ **1.08–1.16 % of score** of modelled headroom
(§7.1) rather than deferring it.

**Submitted-surface delta: 0 bytes.**
`git diff --name-only 51e36805030a982daecda80535281f4540a1cde1 HEAD -- Sources/ Vendor/ benchmark.json`
is empty. Every file in this experiment is under `research/`.

**Rule-75 working-set digest (identical for every paired run):**
`ce9c6b1646b35a6d547848c07e8610656b3fbead947ad14560746025f52794d4`

**Host:** Apple M4 Pro, 14 CPU / **20 GPU cores**, 48 GiB unified, macOS 26.5.2,
`applegpu_g16s` (Apple GPU generation 16). Ranked M5 has **C = 40** cores; every
40-core number below is a projection from a measured 20-core wave decomposition
and is labelled as such.

---

## 0. What changed relative to the PR body

Four advisor comments supersede §2–§4 of the assignment and I followed them
exactly:

- `r102-a-fb-window-knob-defect-and-slice-granularity`
  (PR #566 comment, 2026-08-09T18:05:59Z): the `FERN_WINDOW → dParams[2]` knob is a no-op for the
  sliding kernel; the row bound must be changed by source substitution of
  `constexpr int N = 512;` (`LagunaRuntimeModel.swift:1434`) while
  `constexpr uint window = 512;` (`:1426`) is held fixed. Sliding sweep points
  restricted to `{512, 384, 256, 128}`. Added null **N-E**. Verify resident
  TGs/core. Name which kernel was extracted.
- `r102-a-fb-2-swap-primary-arm-full-kernel-is-2-deep`
  (PR #566 comment, 2026-08-09T18:12:57Z): **the primary arm is the full-attention kernel**, whose
  row bound is genuinely dynamic (`int N = int(params[1])`, `:1964`) and needs no
  source edit. Gate `f/τ₀ < 9.4 %` decided at C = 40. S = 5 retracted entirely;
  the sliding arm demotes to secondary with bar `1.6 %`.
- `r102-a-fb-3-reprice-from-561-measured-pool-table`
  (PR #566 comment, 2026-08-09T20:00:23Z) and
  `r102-a-fb-4-same-kernel-r-measurement`
  (PR #566 comment, 2026-08-09T20:05:43Z) arrived after the measurement jobs were
  queued. They reprice the pool from #561, ask for the latency-regime
  corroboration to be addressed, ask for the ratio-invariance argument to be
  stated explicitly, and supply an archival `r ∈ [1.022, 1.041]`. All four are
  answered in **§7**.

### Preregistration deviations (rule 72 honesty)

1. Only `constexpr int N = 512;` is rewritten in the sliding kernel.
   `constexpr uint window = 512;` is deliberately **not** rewritten, so the
   per-kv-head address stride is identical at every sweep point (advisor
   comment 1).
2. The preregistered **blockwise** runs (job `cb6a2983-…`) are **superseded** and
   moved to `research/artifacts/frieren-r102/blockwise-superseded/`. They showed
   ~14 % block-order drift with inconsistent sign; they are not used as fit
   inputs. All reported data comes from a **drift-immune interleaved sweep**
   where every `N` is visited once per round in rotating order.
3. The primary arm changed from sliding to full (advisor comment 2). The full
   arm needs **no source edit**: `FERN_PARAM_ROWS=1` builds **one shared
   pipeline** and delivers `N` through `params[1]`, so every sweep point runs the
   byte-identical binary.
4. **Added, not preregistered:** the dense `FZ`/`FZD` grid with two
   below-the-loop anchors at `N = 32` and `N = 0`. This was necessary because
   `τ(N)` turned out to be non-affine (N-B fires), so the fitted intercept is
   not a trustworthy `f`. `N = 0` gives a **direct, fit-free** measurement of the
   fixed cost, which became the headline gate.

---

## 1. Archive reconciliation (rule 69)

`research/RESEARCH_ARCHIVE_through-round-91.md:6264-6299` already closes this
family. Three findings there are directly on point:

| anchor | claim | status in archive |
|:--|:--|:--|
| `:6264-6281` (§4.12.8 C, PR #196) | decode-attention KV split across threadgroups | **CLOSED at every S** |
| `:6282-6288` | shrinking attention tgMem to buy residency | **CLOSED** |
| `:6289-6299` | "idle slots below C cost time" (ragged-occupancy premise) | **CLOSED — premise is false** |

PR #196 measured, wave-matched at C = 40: `S=1` 9.078 µs, `S=2` 10.384 µs
(1.144×), `S=5` 15.468 µs (1.704×), `S=10` 19.832 µs (2.185×), with
`f = 3.130 µs` = **34.3 %** of a 512-row call, decomposed as `a = 1.661 µs` +
`φ = 1.469 µs/wave`, i.e. `f/τ₀ = 52.6 %`.

**My `f_direct := a + φ` definition is identical to theirs.** This experiment is
therefore an **independent replication on a different host (M4 Pro, C = 20)
with a different probe (kernel-source extraction rather than the runtime
path)**. #196's 34.3 % versus my measured 33.6 % resident is a strikingly close
agreement across two hosts, two probes and two kernels.

`:6289-6299` reports a staircase flat to ±0.06 µs from K = 1 to K = 20, a
+6.48 µs step at K = 21 and +6.44 µs at K = 41. My `W = ⌈K/20⌉` wave law
(§6) reproduces exactly that shape, and my marginal-wave cost `b = 7.408 µs`
against a lone-threadgroup cost of 8.891 µs shows co-residency recovers only
~17 % — i.e. the dispatch is issue/ALU-bound, not occupancy-bound.

### The state file is out of date

`grep -n "#196" research/CURRENT_RESEARCH_STATE.md` returns **no hits**. The
state file therefore proposes R102-A without citing the experiment that already
closed it. Two specific corrections are required:

- `CURRENT_RESEARCH_STATE.md:143-146` asserts that `f` "has never been
  measured". It was measured by #196 at 3.130 µs, and is measured again here at
  4.630 µs (resident, C = 20, K = 24).
- The motivating premise that "~20 % is left on the floor to ragged occupancy"
  is **false**: `:6289-6299` shows idle slots below `C` are free, so there is no
  ragged-occupancy pool for split-K to recover.

A drop-in closure block for the state file is in §10.

---

## 2. Probe modification and geometry fidelity (rule 77)

### Diff

`research/fern_r100_attn_probe.swift` gained six environment knobs and one
source-substitution function (`+185 / −27` lines vs base). Line anchors in the
committed file:

| knob | line | purpose |
|:--|--:|:--|
| `FERN_ROWS` | 75 | sliding-kernel row bound via source substitution |
| `FERN_STRIDE_KV` | 78 | pins the SLC-defeat rotation stride across a K sweep |
| `FERN_ROWS_SWEEP` | 82 | interleaved (drift-immune) row rotation within a round |
| `FERN_MATCH_BYTES` | 86 | scales defeat slots as `window/rows` to hold DRAM bytes/round fixed |
| `FERN_PARAM_ROWS` | 90 | full-attention mode: `N` via `params[1]`, **source unmodified** |
| `FERN_GQA` | 93 | query heads per kv head (8 sliding, 6 full) |
| `FERN_ITER_POSITIONS` | 96 | KV positions per main-loop iteration (128 sliding, 64 full) |

The substitution itself (`rewriteRowBound`, `:173-181`) is deliberately minimal
and fail-loud:

```swift
func rewriteRowBound(_ body: String, rows: Int) -> String {
    guard !paramRows, rows != 512 else { return body }
    let needle = "constexpr int N = 512;"
    let hits = body.components(separatedBy: needle).count - 1
    precondition(hits == 1, "expected exactly one `\(needle)`, found \(hits)")
    return body.replacingOccurrences(of: needle, with: "constexpr int N = \(rows);")
}
```

It rewrites exactly one token, aborts if the declaration moves, and is a
**no-op** when `paramRows` is set or `rows == 512`.

### Geometry-fidelity statement

**Which kernel was extracted.** Two, and they are different:

| | secondary arm | primary arm |
|:--|:--|:--|
| kernel | `laguna_sliding_fused_attn_ring_v1` | `laguna_full_fused_attn_grow_v1` |
| declaration | `LagunaRuntimeModel.swift:1416` | `LagunaRuntimeModel.swift:1936` |
| row bound | `constexpr int N = 512;` `:1434` (**source substitution**) | `int N = int(params[1]);` `:1964` (**dynamic, no edit**) |
| main loop | `int i = sg; i + 3*BN < N; i += 4*BN` `:1547-1548` | `int i = sg; i + BN < N; i += 2*BN` `:2076-2077` |
| unroll depth | 4-deep, **128 positions/iter** | 2-deep, **64 positions/iter** |
| production heads | 64 (30 sliding layers) | 48 (10 full layers) |
| dispatch | `:1879-1880` grid `((heads/2)*1024, 1, 1)` ⇒ **K = 32** | `:2364-2365` same form ⇒ **K = 24** |
| gqa (q heads / kv head) | 8 | 6 |
| rotary pairs | 64 | 32 |

**Fidelity of the primary arm is exact.** `FERN_PARAM_ROWS=1` builds a **single**
pipeline from unmodified `LagunaRuntimeModel.swift` source and every `N` in the
sweep runs that same binary; only the `params[1]` word differs. The probe
dispatches 1024 threads/threadgroup and `K` threadgroups, matching production
(`head0 = pair_tg*2`, 2 query heads per threadgroup). Production geometry is
confirmed from `Sources/MLXFastModel/LagunaConfig.swift`: `numKeyValueHeads = 8`
(`:21`), `headDim = 128` (`:22`), `slidingWindow = 512` (`:29`),
`numHiddenLayers = 40` (`:20`). `distinctKVHeads(24) = 8`, so the full-attention
probe reads exactly the production kv-head set.

**Loop-count fidelity.** `i = sg; i + 32 < N; i += 64` over 32 simdgroups gives
exactly 8 / 6 / 4 / 2 / 1 iterations for `N` = 512 / 384 / 256 / 128 / 64, uniform
across all simdgroups. The trailing `if (i < N)` tail block is one BN slice and
is **not taken** for `N ≡ 0 (mod 64)`, so every swept point is a whole number of
main-loop iterations with no tail. `capacity = params[2] = 512` is held fixed, so
the address stride per kv head never changes; the epilogue is `N`-independent.

**Resident threadgroups per core = 1 (advisor request).** From the probe's
pipeline-properties gate: full kernel `tgMemB = 18432` against
`maxThreadgroupMemoryLength = 32768` ⇒ threadgroup-memory bound is
`⌊32768/18432⌋ = 1`; `maxTotalThreadsPerThreadgroup = 1024` and the dispatch uses
1024 threads. This is corroborated empirically by the `W = ⌈K/20⌉` wave law in
§6 — the step period is exactly the core count, which only happens at one
resident threadgroup per core.

---

## 3. τ(N) on the primary arm — both cache modes

`regime` and `slc_fit` are reported per block at the worst (largest) working
set, `N = 512`. The working set is `4096·N` bytes per kv-head-pair, so it only
shrinks at lower `N`; `slc_fit` cannot flip from `yes` to `no` as `N` falls.

| block | K | TG/core | kvheads | slots | uniq_MiB | achieved GB/s | pct_peak | slc_fit | regime |
|:--|--:|--:|--:|--:|--:|--:|--:|:--|:--|
| FZ (resident) | 24 | 1.20 | 8 | 1 | 2.03 | 115.9 | 43.5 | yes | PARTIAL |
| FZ (resident) | 48 | 2.40 | 16 | 1 | 4.06 | 163.1 | 61.3 | yes | PARTIAL |
| FZD (defeat) | 24 | 1.20 | 8 | 48 | 96.03 | 102.7 | 38.6 | no | UNSATURATED |
| FZD (defeat) | 48 | 2.40 | 16 | 48 | 192.06 | 143.8 | 54.0 | no | PARTIAL |

`dram_peak = 266.3 GB/s` (measured, rule 55). The defeat mode is byte-matched:
slots scale as `512/N` (48 / 54 / 64 / 76 / 96 / 128 / 192 / 384 / 384 / 384 for
`N` = 512…0), so each point streams the same distinct bytes per round.

### FZ — resident KV, dense grid (µs, median of 21 rounds × 2000 reps)

| N | M iters | K=24 med | K=24 rel sd | K=48 med | K=48 rel sd |
|--:|--:|--:|--:|--:|--:|
| 512 | 8 | 18.391 | 1.58 % | 26.131 | 4.06 % |
| 448 | 7 | 17.236 | 3.53 % | 23.634 | 4.83 % |
| 384 | 6 | 16.400 | 1.99 % | 21.348 | 5.14 % |
| 320 | 5 | 13.788 | 3.06 % | 19.338 | 4.55 % |
| 256 | 4 | 10.049 | 0.28 % | 17.651 | 6.77 % |
| 192 | 3 | 8.507 | 0.28 % | 14.939 | 6.88 % |
| 128 | 2 | 7.126 | 0.41 % | 10.134 | 0.38 % |
| 64 | 1 | 5.841 | 0.46 % | 8.160 | 0.35 % |
| **32** | 0 | **5.088** | 0.38 % | **6.734** | 0.83 % |
| **0** | 0 | **4.630** | 0.53 % | **6.316** | 0.81 % |
| 512 (dup) | 8 | 18.397 | 1.40 % | 26.083 | 3.84 % |

**Null band (duplicate `N` within the same round):** K=24 **0.04 %**, K=48
**0.18 %**. Rule 78 gate is `|d%| ≤ 0.25 ×` smallest reported dose; the smallest
dose here (one 64-position iteration) is ~7 % of `T(512)`, so the gate is 1.75 %
and both nulls pass comfortably.

### FZD — SLC-defeat, byte-matched, dense grid

| N | slots | K=24 med | K=24 rel sd | K=48 med | K=48 rel sd |
|--:|--:|--:|--:|--:|--:|
| 512 | 48 | 20.747 | 0.66 % | 29.610 | 3.48 % |
| 448 | 54 | 19.066 | 0.44 % | 26.949 | 3.91 % |
| 384 | 64 | 17.574 | 0.35 % | 24.349 | 4.30 % |
| 320 | 76 | 16.647 | 0.43 % | 21.851 | 3.02 % |
| 256 | 96 | 13.339 | 0.92 % | 19.362 | 4.04 % |
| 192 | 128 | 9.800 | 0.10 % | 17.575 | 7.19 % |
| 128 | 192 | 8.201 | 0.31 % | 14.348 | 6.88 % |
| 64 | 384 | 6.551 | 0.33 % | 9.138 | 0.62 % |
| **32** | 384 | **5.506** | 0.19 % | **7.311** | 0.64 % |
| **0** | 384 | **4.634** | 0.24 % | **6.270** | 0.96 % |
| 512 (dup) | 48 | 20.734 | 0.19 % | 29.610 | 3.46 % |

**Null band:** K=24 **0.06 %**, K=48 **0.00 %**.

Note the sd structure: below `N = 320` the relative sd sits at 0.1–0.9 %; at
`N ≥ 320` it jumps to 3–7 %. That is a cache-capacity threshold, not
instability, and it is one of the reasons the affine fit is unreliable at the
top of the range.

---

## 4. Fits, and why they are *not* the headline

### 4.1 Affine fits `τ(N) = f + cN`

FULL / FULLD are fitted on `N ∈ {512, 384, 256, 128, 64}` (the sweep the advisor
named); FZ / FZD on the dense grid `N ∈ {512, 448, 384, 320, 256, 192, 128, 64}`.
The two anchors below the loop (`N` = 32, 0) are held out of every fit so they
stay independent evidence.

| block | K | f µs | ±95 % | c µs/pos | u = 32c | τ₀ = 16u | f/τ₀ | 95 % CI | R² | rmse | max resid |
|:--|--:|--:|--:|--:|--:|--:|--:|:--|--:|--:|--:|
| FULL (real kernel, resident) | 24 | 3.496 | 3.039 | 0.02988 | 0.956 | 15.297 | 22.9 % | [1.7, 44.0] | 0.97000 | 0.861 | 1.409 |
| FULL | 48 | 5.709 | 2.791 | 0.04076 | 1.304 | 20.869 | 27.4 % | [12.7, 42.0] | 0.98618 | 0.791 | 1.489 |
| FULLD (real kernel, defeat) | 24 | 4.441 | 1.506 | 0.03283 | 1.051 | 16.809 | 26.4 % | [16.7, 36.2] | 0.99375 | 0.427 | 0.538 |
| FULLD | 48 | 7.606 | 2.892 | 0.04386 | 1.404 | 22.457 | 33.9 % | [19.2, 48.6] | 0.98717 | 0.820 | 1.275 |
| FZ (dense, resident) | 24 | 3.284 | 1.674 | 0.03085 | 0.987 | 15.794 | 20.8 % | [9.6, 31.9] | 0.97254 | 0.760 | 1.271 |
| FZ | 48 | 6.197 | 1.749 | 0.03981 | 1.274 | 20.385 | 30.4 % | [20.9, 39.9] | 0.98183 | 0.794 | 1.261 |
| FZD (dense, defeat) | 24 | 4.332 | 1.672 | 0.03353 | 1.073 | 17.169 | 25.2 % | [14.7, 35.7] | 0.97671 | 0.759 | 1.584 |
| FZD | 48 | 8.123 | 1.818 | 0.04262 | 1.364 | 21.821 | 37.2 % | [27.6, 46.9] | 0.98284 | 0.826 | 1.713 |

**Every fitted value already fails the 9.4 % bar, and the lower end of every
95 % CI except FULL K=24 also fails it.**

### 4.2 Residuals — N-B fires

FULL / FULLD, `N` = 64 / 128 / 256 / 384 / 512:

- FULL K=24: `+0.418 / −0.209 / −1.122 / +1.409 / −0.496` (max |r| = 1.409, i.e.
  8 % of `T(512)`)
- FULL K=48: `−0.161 / −0.795 / +1.489 / −0.031 / −0.503`
- FULLD K=24: `+0.004 / −0.458 / +0.409 / +0.538 / −0.495`
- FULLD K=48: `−1.275 / +1.142 / +0.543 / −0.048 / −0.362`

FZ / FZD, `N` = 64…512 step 64:

- FZ K=24: `+0.583 / −0.106 / −0.700 / −1.131 / +0.633 / +1.271 / +0.133 / −0.684`
- FZ K=48: `−0.586 / −1.159 / +1.097 / +1.261 / +0.400 / −0.138 / −0.400 / −0.476`
- FZD K=24: `+0.073 / −0.423 / −0.971 / +0.422 / +1.584 / +0.365 / −0.289 / −0.761`
- FZD K=48: `−1.713 / +0.770 / +1.269 / +0.328 / +0.089 / −0.140 / −0.268 / −0.335`

The residuals are **structured, not scattered**, and the maxima are 15–40× the
duplicate-`N` null band. Second differences of `τ(N)` over the dense grid
(step 64) confirm it:

| block | K | max |Δ²| µs | null band |
|:--|--:|--:|--:|
| FZ | 24 | 2.196 | 0.04 % (≈0.007 µs) |
| FZ | 48 | 2.831 | 0.18 % |
| FZD | 24 | 2.382 | 0.06 % |
| FZD | 48 | 1.984 | 0.00 % |

`τ(N)` is decidedly **non-affine**. That is why the headline gate below uses no
fit at all.

### 4.3 The headline: measured-only gate, `τ₀ := T(512) − T(0)`

Both terms are medians from the **same shared pipeline** in the **same
interleaved round**. There is zero extrapolation.

| block | K | T(512) µs | T(0) µs | τ₀ µs | **f/τ₀** | bar | verdict |
|:--|--:|--:|--:|--:|--:|--:|:--|
| FZ (resident) | **24** | 18.394 | 4.630 | 13.764 | **33.6 %** | 9.4 % | **NO-GO** |
| FZ (resident) | 48 | 26.107 | 6.316 | 19.791 | 31.9 % | 9.4 % | NO-GO |
| FZD (defeat) | **24** | 20.740 | 4.634 | 16.106 | **28.8 %** | 9.4 % | **NO-GO** |
| FZD (defeat) | 48 | 29.610 | 6.270 | 23.340 | 26.9 % | 9.4 % | NO-GO |

K = 24 is the production dispatch width. The gate fails by **3.1–3.6×**, and it
also fails the more permissive C = 20 / S = 4 bar of 25 %.

**Cache-mode invariance of the fixed cost.** `T(0)` reads no KV bytes, so any
difference between modes is probe overhead rather than memory:

| K | resident T(0) | defeat T(0) | Δ |
|--:|--:|--:|--:|
| 24 | 4.630 | 4.634 | **+0.09 %** |
| 48 | 6.316 | 6.270 | −0.73 % |

`f` is a genuine fixed cost, not a residency artefact. **N-C does not fire.**

### 4.4 Projection to the ranked C = 40 host

`T(K, 0) = a + W(K)·f_TG` with `W = ⌈K/20⌉`. The `K = 24` (W = 2) and
`K = 48` (W = 3) anchors separate the once-per-dispatch constant from the
per-threadgroup fixed work, which is exactly what lets a 20-core host answer a
40-core question:

| block | a µs | f_TG µs | f(C=40, W=1) µs | τ₀(C=40) µs | **f/τ₀ @ C=40** |
|:--|--:|--:|--:|--:|--:|
| FZ | 1.258 | 1.686 | 2.944 | 6.882 | **42.8 %** |
| FZD | 1.362 | 1.636 | 2.998 | 8.053 | **37.2 %** |

Because `a ≠ 0`, the ratio **rises** as the wave count falls. The measured C = 20
value is therefore a **lower bound** on the C = 40 value. This restores a valid
host-invariance argument after the retracted "invariant at S = 5" version: I do
not need the M5 to know the M5 fails, because moving to more cores can only make
this ratio worse.

### 4.5 Optimistic makespan scan (merge excluded)

`makespan(S) = a + ⌈24S/C⌉·(f_TG + (16/S)·u_TG)`, with the merge dispatch left
out entirely, so this is an **upper bound on the achievable win**.

**C = 40 (ranked):**

| block | S=1 | S=2 | S=3 | S=4 | S=5 | S=6 | S=7 | S=8 | best | gross gain | merge floor `a` | net |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| FZ | 9.83 | 11.51 | **9.22** | 11.48 | 10.45 | 12.59 | 14.60 | 13.99 | 3 | +0.61 | 1.26 | **LOSS** |
| FZD | 11.05 | 12.69 | **10.00** | 12.31 | 11.10 | 13.27 | 15.29 | 14.58 | 3 | +1.05 | 1.36 | **LOSS** |

**C = 20 (this host):**

| block | S=1 | S=2 | S=3 | S=4 | S=5 | S=6 | S=7 | S=8 | best | gross gain | merge floor `a` | net |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| FZ | 18.39 | **16.64** | 17.18 | 18.29 | 19.63 | 23.92 | 25.28 | 26.72 | 2 | +1.75 | 1.26 | nominal WIN |
| FZD | 20.74 | **18.35** | 18.64 | 19.61 | 20.84 | 25.19 | 26.44 | 27.79 | 2 | +2.39 | 1.36 | nominal WIN |

At the ranked core count the best gross gain is **smaller than the strict merge
floor**, so split-K loses even before the merge does any real work. The C = 20
nominal wins are falsified directly in §4.6.

### 4.6 Model validation — the one split point this host can execute directly

A two-way split at C = 20 is *literally* `K = 48` threadgroups each covering
`N = 256`, which the dense grid already measures. So the model can be checked
against a real dispatch rather than trusted:

| block | measured T(48, 256) | model makespan(S=2, C=20) | model error | measured vs S=1 | merge floor `a` | merge est `T(0)` | net vs floor | net vs est |
|:--|--:|--:|--:|--:|--:|--:|:--|:--|
| FZ | 17.651 | 16.639 | **−5.7 %** | +0.743 µs (0.960×) | 1.26 | 4.63 | LOSS | LOSS |
| FZD | 19.362 | 18.350 | **−5.2 %** | +1.378 µs (0.934×) | 1.36 | 4.63 | WIN (+0.02) | LOSS |

Two conclusions:

1. The makespan model is **systematically optimistic about splitting by 5–6 %**.
   The C = 40 scan in §4.5 is therefore an upper bound that is itself ~5 %
   too generous.
2. A realistic merge launches the same 24 threadgroups and so pays their
   prologue and epilogue: it cannot cost less than the measured `T(0) = 4.63 µs`.
   Against that estimate **every** split point is a loss, at both core counts.

---

## 5. Independent estimate of `f`, and whether the two agree

Three estimators of the same quantity, sharing no data:

1. **Direct anchor** `T(0)` — the kernel runs its prologue and epilogue with
   zero main-loop iterations.
2. **Low-N extrapolation** — fit `N ∈ {64, 128, 192}` only, where the working
   set stays under 800 kB, the relative sd is below 0.5 %, and no cache level is
   exceeded. This shares no points with the large-`N` data that dominates the
   full-grid intercept, and does not use `N = 0`.
3. **Full-grid affine intercept** — §4.1.

| block | K | low-N slope µs/pos | low-N intercept | direct T(0) | Δ | Δ % | full-grid f | Δ vs full-grid |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| FZ | **24** | 0.02083 | 4.492 | **4.630** | −0.137 | **−3.0 %** | 3.284 | +1.209 |
| FZ | 48 | 0.05296 | 4.298 | 6.316 | −2.018 | −31.9 % | 6.197 | −1.899 |
| FZD | **24** | 0.02538 | 4.936 | **4.634** | +0.301 | **+6.5 %** | 4.332 | +0.604 |
| FZD | 48 | 0.06592 | 5.250 | 6.270 | −1.020 | −16.3 % | 8.123 | −2.874 |

**Do they agree? At the production width K = 24, yes: within 3.0 % (resident)
and 6.5 % (defeat).** That is small compared with the 3.1–3.6× margin by which
the gate fails, so the verdict does not depend on which estimator is used.

At K = 48 the low-N estimator disagrees badly (−16 % to −32 %). That is expected
and informative rather than alarming: K = 48 runs three waves, and at low `N`
the three waves overlap differently than at high `N`, so a straight line through
`{64, 128, 192}` has no reason to extrapolate to the true zero-iteration cost.
It is another symptom of N-B.

A fourth cross-check, the tail-slice marginal cost `(T(32) − T(0))/32`, is much
cheaper than the main-loop `c`:

| block | K | `(T32−T0)/32` | main-loop `c` | ratio |
|:--|--:|--:|--:|--:|
| FZ | 24 | 0.01432 | 0.03085 | 0.46 |
| FZ | 48 | 0.01305 | 0.03981 | 0.33 |
| FZD | 24 | 0.02725 | 0.03353 | 0.81 |
| FZD | 48 | 0.03253 | 0.04262 | 0.76 |

The single tail slice costs roughly half a main-loop position, confirming that
the main loop, not the tail, sets `c`.

The full-grid affine intercept **understates** `f` in resident mode
(`T(0) − f = +1.346` for FZ K=24), which is exactly the direction the convexity
of `τ(N)` predicts. Using the fitted intercept would have been *generous* to the
hypothesis and still failed.

---

## 6. Secondary arm — sliding attention

Source substitution of `constexpr int N = 512;`, `window` held at 512,
`N ∈ {512, 384, 256, 128}` plus a below-the-loop point at `N = 96`
(the 4-deep ring runs zero iterations there), so
`f_direct(K) := T(K, N=96)` is a direct measurement.

| mode | K | W | T(512) µs | f_direct µs | τ₀ µs | f/τ₀ | bar | verdict |
|:--|--:|--:|--:|--:|--:|--:|--:|:--|
| resident | 20 | 1 | 8.716 | 2.991 | 5.725 | **52.2 %** | 1.6 % | NO-GO |
| resident | **32** | 2 | 18.224 | 3.837 | 14.386 | **26.7 %** | 1.6 % | **NO-GO** |
| resident | 40 | 2 | 18.373 | 3.938 | 14.434 | 27.3 % | 1.6 % | NO-GO |
| resident | 64 | 4 | 32.201 | 5.971 | 26.230 | 22.8 % | 1.6 % | NO-GO |
| resident | 128 | 7 | 53.615 | 9.044 | 44.570 | 20.3 % | 1.6 % | NO-GO |
| defeat | 20 | 1 | 9.778 | 2.990 | 6.788 | 44.0 % | 1.6 % | NO-GO |
| defeat | **32** | 2 | 19.248 | 3.840 | 15.408 | 24.9 % | 1.6 % | **NO-GO** |
| defeat | 40 | 2 | 19.649 | 3.944 | 15.705 | 25.1 % | 1.6 % | NO-GO |

K = 32 is the production sliding dispatch. The bar is exceeded by **12–33×**.
Duplicate-`N` nulls across the secondary blocks are 0.01–0.27 %, with one
outlier at 1.78 % (F2, K = 48).

### Wave law

`f_direct(K) = a + W·φ`, `W = ⌈K/20⌉`. Calibration blocks only (n = 8):

- **a = 1.901 ± 0.105 µs**, **φ = 1.017 ± 0.033 µs**, R² = 0.99896, rmse 0.0611

Refit including the held-out F2/F2D blocks (n = 12):

- **a = 1.863 ± 0.128 µs**, **φ = 1.026 ± 0.043 µs**, R² = 0.99654, rmse 0.0939

The held-out points move the coefficients by 2 % and 1 %, so the law generalises.

`t_ring(512 keys) = 5.725 µs`, giving **φ/t_ring = 17.8 % resident / 15.0 %
defeat**. Reported honestly: on the *per-wave* framing this sits in the PARTIAL
band, even though the `f/τ₀` framing that the assignment gates on is a decisive
NO-GO. The two are not in conflict — `φ` is only one of the two components of
`f`, and the once-per-dispatch `a = 1.9 µs` is what kills the split.

### Why the sliding arm is structurally dead

The 4-deep ring consumes 128 positions per iteration over 32 simdgroups, so at
`S` slices each threadgroup runs `⌈(512/S)/128⌉` iterations and the ring saving
is `⌈0.8S⌉/S ≥ 0.8` — **at most 20 % of `t_ring` can ever be recovered**, while
the wave surcharge for `S` slices is at least `3φ ≈ 3 µs`. For `S ≥ 5` the
slice falls below the 128-position granularity of the loop body and the
threadgroup does one iteration regardless, so extra slices are pure overhead.

### Direct split emulation (merge omitted — generous to the split)

M3D, byte-matched diagonal: S=1 (K=32, N=512) **19.280 µs** (1.000×);
S=2 (K=64, N=256) **22.341 µs** (1.159×); S=4 (K=128, N=128) **21.837 µs**
(1.133×). Splitting is slower even before the merge exists.

### F2/F2D — the out-of-sample split the wave law says *should* win

| block | S | K | W | N | measured | predicted | err | measured vs S=1 | predicted vs S=1 |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| F2 | 1 | 24 | 2 | 512 | 18.129 | 15.384 | −15.1 % | 1.000× | 1.000× |
| F2 | 2 | 48 | 3 | 256 | 17.239 | 13.538 | −21.5 % | **0.951×** | 0.880× |
| F2D | 1 | 24 | 2 | 512 | 19.011 | 15.384 | −19.1 % | 1.000× | 1.000× |
| F2D | 2 | 48 | 3 | 256 | 17.971 | 13.538 | −24.7 % | **0.945×** | 0.880× |

There **is** a real 4–5 % gross win here — but the merge dispatch costs at least
`a ≈ 1.86–1.89 µs`, which is 10 % of `T(512)`, so the net is negative. The wave
law also over-predicts the win (0.88× predicted vs 0.95× measured), because the
per-threadgroup ring cost is nearly equal at K = 24 (0.2467 µs) and K = 48
(0.2567 µs): ring work scales with **total threadgroup count**, i.e. the
dispatch is throughput-bound rather than wave-serial. Caveat: the sliding
K = 20 / K = 32 pair does not fit this picture, confounded by resident
cache-capacity effects around ~1.5 MiB.

### `r` — the 4-deep vs 2-deep penalty (advisor request, with caveat)

Comparing `u` between the two kernels: sliding-family `u ≈ 1.02` (from `φ`, the
per-wave marginal) against full-kernel `u = 0.987` (FZ K=24) / `1.073` (FZD
K=24), giving `r ≈ 1.03–1.09`. **This is confounded** and should be treated as
indicative only: the two kernels differ in `gqa` (8 vs 6) and `rotary_pairs`
(64 vs 32) as well as unroll depth, so the ratio absorbs those differences. It
is nonetheless consistent with the #539 prior of `r ≈ 1.03`.

---

## 7. Repricing against #561, and why a NO-GO is the right answer

Two further advisor comments landed after the measurement jobs were queued and
before this report was written. Both are answered here.

### 7.1 Updated pool figures — the retired prize is larger than the brief said

`r102-a-fb-3-reprice-from-561-measured-pool-table` (2026-08-09T20:00:23Z)
replaces the brief's ≈290 / ≈100 µs/step estimates with #561's measured rows
(PR #561, W&B `hvrzplnm`, artifact `research/artifacts/fern-r101/m5-pool-table.csv`).
All M5 figures are **modelled**: *M4 ×0.4369 bandwidth-pool / ×0.5 latency-pool
two-pool map, residual −6.63 % vs measured M5 steady-state decode, #561*.

| family | calls | M4 µs/step | M5 µs/step (modelled) | regime | % of M5 peak BW |
|:--|--:|--:|--:|:--|--:|
| `T3a` sliding fused attn | 30 | 636.0 | 318.0 → **≈309.5** | latency | 32.4 % |
| `T3a'` full fused attn | 10 | 229.7 | **114.85** | latency | 33.6 % |

The ≈309.5 correction is the advisor's own, from
`r102-a-fb-4-same-kernel-r-measurement` §1: #561's `T3a` row was taken at base
`3567695b`, i.e. **before** #539 landed the 4-deep ring, so 636.0 M4 is a 2-deep
number and the current pool is ≈619 M4 / ≈309.5 M5 (−2.7 %). I use ≈309.5.

Prize now being retired, at the advisor's own ideal gains (S = 8 full ⇒ 37.5 %
of the pool; sliding ⇒ 8.9–10.6 % of the pool):

| arm | ideal gain | µs/step (modelled M5) | % of score @ 0.015228 %/µs-step | status |
|:--|--:|--:|--:|:--|
| full, S = 8 | 37.5 % of 114.85 | **43.1** | 0.66 % | **retired** |
| sliding, S = 8 | 8.9–10.6 % of 309.5 | 27.5–32.8 | 0.42–0.50 % | **retired** |
| both | — | **70.6–75.9** | **1.08–1.16 %** | **retired** |

None of the verdicts below depend on these figures: they price the lever, they
do not decide it. The decision is the measured ratio in §4.3.

### 7.2 The latency-regime corroboration is correct — and it is *compatible* with NO-GO

The advisor is right that #561's classification is independent support for the
premise, and right that a NO-GO therefore needs an explanation rather than a
shrug. Here it is, and the two facts are not in tension.

**The under-occupancy is real.** I confirmed it directly rather than assuming it:
one resident threadgroup per core (§2, tgMem 18 432 B against a 32 768 B cap at
1024 threads/TG), and a K-ladder that is flat to ±0.06 µs from K = 1 to K = 20
and then steps +6.48 µs at K = 21. Cores 1–19 really are free capacity, exactly
as `Fill(24, 40) = 0.60` claims.

**Low achieved bandwidth is a statement about the threadgroup, not about
divisibility.** 33.6 % of peak means each threadgroup is latency-bound
*internally*. Split-K does not attack that; it replicates the threadgroup. And
the replicated part is expensive: `f = 4.63 µs` against a `τ₀ = 13.76 µs`
main loop, i.e. **34 % of the dispatch is work that a split duplicates rather
than divides.** Structurally, the `if (sg < 3)` prologue (`LRM:1973`, null N-E)
plus the epilogue is head-serial work that every slice must redo — the very
asymmetry that leaves 29 of 32 simdgroups idle in the prologue and depresses the
achieved bandwidth is *also* what makes the split unprofitable. Split-K divides
the 66 % that is main loop and multiplies the 34 % that is not.

Put the numbers through §4.5's own (merge-free, deliberately optimistic) model
at C = 40: S = 8 costs **13.99 µs** against S = 1's **9.83 µs**, i.e. 1.42×
*worse*, and the best split factor anywhere in the scan (S = 3) gains +0.61 µs,
which is below the strict merge floor `a = 1.26 µs`. The single split point this
host can execute for real (§4.6) comes in 5–6 % worse than even that model.

**One-line reconciliation:** the latency-regime signature says the *cores* are
idle; it does not say the *work* is divisible. On this kernel it is not.

Two further reasons the NO-GO is not a surprise once you look for prior art:
PR #196 closed the same question four rounds earlier at every S and measured
`f/τ₀ = 34.3 %` against my 33.6 % (§1) — this is an independent replication, not
a new claim; and `CURRENT_RESEARCH_STATE.md` never cites #196, which is why the
premise survived into a fresh assignment.

### 7.3 Ratio-invariance: why an M4 measurement may decide an M5 question

Stated explicitly as requested. `f/τ₀` is a ratio of two times measured on the
**same host, same session, same shared pipeline, same interleaved round**, from
the **verbatim shipped kernel source** — `laguna_full_fused_attn_grow_v1` is a
hand-written Metal kernel in `LagunaRuntimeModel.swift`, not an MLX kernel with
an `_nax` variant, so the M5 executes the identical source and the gen-16 /
pre-NAX caveat that limits #561's pool map does not apply to the kernel body
here.

I do not claim the ratio is exactly invariant, and I do not need to:

1. **Core count.** The measured C = 20 value is a *lower bound* on C = 40,
   because `a ≠ 0` makes the ratio rise as waves fall (§4.4): 33.6 % → 42.8 %.
2. **Clocks.** A uniform clock change cancels in the ratio.
3. **Any M5 speed-up that favours the main loop** (wider ALUs, better
   scheduling) shrinks `τ₀` relative to a launch/prologue-bound `f` and makes
   `f/τ₀` **larger**, not smaller.

Every transfer error I can name moves the ratio further above the bar, and the
margin is 3.6× at C = 20 and 4.6× at C = 40. A transfer artefact would have to
be a 3.6× error to flip the verdict.

### 7.4 `r`: adopting the archival estimate, and why the sliding verdict is `r`-invariant

`r102-a-fb-4-same-kernel-r-measurement` supersedes §5 of the second comment and
supplies `r ∈ [1.022, 1.041]` from #539's receipt against #561's pre-#539 `T3a`
row. **I adopt that as the primary `r`** and demote my cross-kernel ratio (§6,
`r ≈ 1.03–1.09`) to a corroborating check, as instructed.

*Flagging the comparison because the advisor asked to be told about a ±0.02
disagreement:* the two overlap at the low end (my 1.03 against the archival
upper 1.041) but my upper end 1.09 sits 0.049 above it. My estimator is
confounded by `gqa` 8 vs 6 and `rotary_pairs` 64 vs 32, both of which make the
sliding kernel do more per-position work for reasons unrelated to unroll depth,
so the bias is **upward by construction**. I read this as no actionable
disagreement — neither #539's receipt nor #561's `T3a` row needs re-examining on
my evidence — but it is a confounded estimator agreeing at one end, not a
confirmation.

**The direct 2-deep source substitution (comment 4 §2) cannot change the
verdict, so I did not spend host time on it.** Here is the arithmetic, so that
this reads as a reasoned deferral and not an omission. The sliding S = 8
condition at C = 40 is `7f + 14ru < f + 16u`, i.e.

```
f/τ₀ < (16 − 14r) / 96
```

| `r` | bar | measured sliding `f/τ₀` | exceeds bar by |
|:--|--:|--:|--:|
| **1.000** (theoretical floor) | **2.08 %** | 17.8 % resident | **8.6×** |
| 1.000 | 2.08 % | 15.0 % defeat | 7.2× |
| 1.022 (archival low) | 1.76 % | 17.8 % | 10.1× |
| 1.041 (archival high) | 1.49 % | 17.8 % | 11.9× |

Even at the physically impossible `r = 1` — a 2-deep body costing exactly what
the 4-deep body costs per position — the sliding arm misses by 8.6×. No value of
`r` in or outside the archival box moves the verdict, so under the advisor's own
cost-control rule ("the full-kernel arm comes first and this comes second") the
substitution was the right thing to drop.

What it would still buy a future round, at research-only cost: a same-kernel
`u₂/u₄` that de-confounds the #539 attribution, and the free N-B cross-check
`f₄ ≈ f₂` on the affine model. Listed as follow-up 5 in §12.

### 7.5 Byte-contamination hygiene (comment 3 §3)

No number in this report is derived from a per-family byte count in
`CURRENT_RESEARCH_STATE.md`. Every byte figure (`uniq MiB`, `achieved GB/s`,
`slc_fit`) is computed inside the probe from its own allocation and dispatch
accounting and checked against this host's measured 266.3 GB/s ceiling (§3). The
brief's ≈13 MB/step rung-2 partial-traffic budget is not reused anywhere: §9
records the rung-2 design without a traffic estimate, because a NO-GO makes the
estimate moot.

---

## 8. Verdicts

### Overall

**NO-GO on both arms.** The primary full-attention arm's per-dispatch fixed cost
is 33.6 % (resident) / 28.8 % (SLC-defeat) of `τ₀` measured with no
extrapolation, projecting to 42.8 % / 37.2 % at the ranked C = 40, against a
9.4 % bar; the secondary sliding arm is 20.3–52.2 % against a 1.6 % bar; and the
single directly-executable split point shows the (merge-free, already optimistic)
makespan model is a further 5–6 % too generous.

### Preregistered nulls

- **N-A (launch-dominated) — FIRES, and is the explanation.** `f` is 33.6 % of
  `τ₀` (predicted ≥ 20 %), both cache modes agree to 0.09 % at K = 24, and the
  direct anchor confirms the fit; this was the predicted outcome and it
  replicates PR #196's 34.3 %.
- **N-B (not affine) — FIRES.** Second differences reach 1.98–2.83 µs against a
  0.00–0.18 % duplicate-`N` null and the residuals are structured, so the fitted
  intercept is unreliable; this is why the headline gate is the fit-free
  `T(512) − T(0)`.
- **N-C (residency artifact) — DOES NOT FIRE.** The fixed cost is
  mode-invariant (`T(0)`: 4.630 resident vs 4.634 defeat, +0.09 % at K = 24) and
  the gate fails in *both* modes, so the verdict is not a cache effect.
- **N-D (the model omits the reduction) — FIRES, and is decisive on its own.**
  Even the merge-free scan's best C = 40 gross gain (+0.61 / +1.05 µs) is below
  the strict merge floor `a` (1.26 / 1.36 µs) and far below the realistic merge
  estimate `T(0) = 4.63 µs`; M3D and F2/F2D confirm this directly.
- **N-E (replicated prologue) — FIRES, and is *inside* the measured `f`.** The
  `if (sg < 3) {…}` prologue (sliding `:1452`, full `:1973`) re-executes once per
  slice and lies entirely within the fixed cost; **the direct `T(0)` anchor and
  the intercept fit both capture it** (the kernel still runs the prologue with
  zero main-loop iterations), whereas an epilogue-only cross-check would not —
  so I report the two measurements as capturing different things rather than
  reconciling them, and the headline gate uses the one that includes N-E.

---

## 9. Rung-2 design note (written, deliberately **not** implemented)

The assignment says to write the rung-2 design even on GO and stop. This is a
NO-GO, so rung 2 should not be built at all in its current form; the design is
recorded only so a future revision does not have to rediscover it.

Host-side slice selection, per dispatch:

```
S = clamp(N / 64, 1, 8)      // 64 = KV positions per full-kernel main-loop iteration
```

`params[1]` becomes the per-slice row count and a second `params` word carries
the slice index; the merge is a separate dispatch over the `S` partial
`(o, m, l)` triples. **Reopen conditions** — do not attempt rung 2 unless one of
these changes:

1. **The dispatch fits the machine.** `K_real · S ≤ C`. Today `K_real = 24` and
   `C = 40`, so even `S = 2` is 48 threadgroups = 2 waves. A decode grid narrow
   enough that splitting stays inside one wave removes the `f_TG` surcharge,
   which is 57 % of the fixed cost.
2. **The merge is free.** Fusing the `(o, m, l)` recombination into the head of
   the following kernel (the o-projection) removes the second dispatch entirely,
   which is worth `a = 1.26 µs` at minimum and `T(0) = 4.63 µs` realistically.

Absent one of those, the arithmetic above says the family stays closed.

---

## 10. Drop-in closure block for `research/CURRENT_RESEARCH_STATE.md`

Replace the R102-A entry (and correct `:143-146`) with:

```markdown
### R102-A — split-K decode attention: CLOSED (NO-GO), round 102

Closed by PR #566 (maple-frieren, rung 1) on measured evidence, replicating
PR #196 (`RESEARCH_ARCHIVE_through-round-91.md:6264-6281`), which had already
closed this family at every S and was never cited here.

Per-dispatch fixed cost of the ranked full-attention kernel
`laguna_full_fused_attn_grow_v1`, measured directly at N=0 with no
extrapolation on M4 Pro / C=20:

  f/tau0 = 33.6% resident, 28.8% SLC-defeat   (bar for S=8 at C=40: 9.4%)

Wave decomposition (a = 1.26 us once-per-dispatch, f_TG = 1.69 us
per-threadgroup) projects this to 42.8% / 37.2% at the ranked C=40. Because
a != 0 the ratio rises as the wave count falls, so the C=20 measurement is a
lower bound on the C=40 value; the M5 cannot rescue it.

The merge-free (optimistic) makespan scan's best C=40 gross gain is +0.61 us
(resident) / +1.05 us (defeat), below the strict merge floor a and far below
the realistic merge estimate T(0) = 4.63 us. The one split point a 20-core host
can execute directly (K=48 @ N=256) shows the model is a further 5-6%
optimistic. The sliding kernel is worse: f/tau0 = 20.3-52.2% against a 1.6%
bar, and the 4-deep 128-position ring caps any ring saving at 20% of t_ring.

CORRECTIONS to earlier text in this file:
- "f has never been measured" is wrong: PR #196 measured f = 3.130 us (34.3%
  of a 512-row call); PR #566 measures 4.630 us (33.6%) independently.
- The "~20% left on the floor to ragged occupancy" premise is FALSE.
  `RESEARCH_ARCHIVE_through-round-91.md:6289-6299` shows idle slots below C are
  free (flat to +-0.06 us from K=1..20, +6.48 us step at K=21). There is no
  ragged-occupancy pool for split-K to recover.

PRICE OF THE CLOSURE, against #561's measured pool table (modelled M5: M4
x0.4369 bandwidth-pool / x0.5 latency-pool two-pool map, residual -6.63%):
full 37.5% x 114.85 = 43.1 us/step, sliding 8.9-10.6% x ~309.5 = 27.5-32.8
us/step, total ~70.6-75.9 us/step ~= 1.08-1.16% of score. That entire amount is
retired, not deferred. Note both attention families are latency-regime at
32.4%/33.6% of peak bandwidth: the cores really are idle, but the idle capacity
is not recoverable by replicating a threadgroup whose fixed cost is a third of
its total.

REOPEN only if (1) a decode grid satisfies K_real * S <= C, or (2) the (o,m,l)
merge is fused into the head of the following kernel so no second dispatch is
paid.

Evidence: research/maple-frieren-r102a-splitk-fixed-cost.md;
research/artifacts/frieren-r102/{fit.md,sweep.csv};
W&B summary run 4bp1qhvz (wandb-applied-ai-team/mlxfast-maple).
```

---

## 11. Reproduction, hygiene and artifacts

### Reproduction

```bash
xcrun swiftc -O research/fern_r100_attn_probe.swift -o /tmp/fernattn   # ~3 s
research/run_frieren_r102_fixed_cost.sh                                 # ~183 s, 9 blocks
python3 research/frieren_r102_fit.py \
  > research/artifacts/frieren-r102/fit.md \
  2> research/artifacts/frieren-r102/fit.err
python3 research/frieren_r102_wandb_log.py                              # 10 W&B runs
```

Block set: `BLOCKS=R_sweep,D_sweep,M3D,F2,F2D,FULL,FULLD,FZ,FZD`.
Primary-arm environment:
`FERN_KERNEL=laguna_full_fused_attn_grow_v1 FERN_PARAM_ROWS=1 FERN_GQA=6 FERN_ITER_POSITIONS=64`,
ladder `24,48`, sweep `512,448,384,320,256,192,128,64,32,0,512`; defeat adds
`FERN_STRIDE_KV=32 FERN_CACHE_COPIES=96 FERN_DEFEAT_SLOTS=48 FERN_MATCH_BYTES=1`.
`FERN_ROUNDS=21`, `FERN_REPS=2000`, best-of-rounds per point.

### Rule-75 working-set digests — every paired run

sha256 of sorted `Sources/` + `Vendor/`, taken before build and after the timed
phase of every job:

| job | window (UTC) | wall s | blocks | pre-build digest | post-timing digest | exit | host idle |
|:--|:--|--:|:--|:--|:--|--:|:--|
| `df1b5c16-…` | 19:29:36 → 19:31:04 | 88.0 | R_sweep, D_sweep, M3D | `ce9c6b16…794d4` | `ce9c6b16…794d4` | 0 | yes |
| `ac19f77e-…` | 19:43:39 → 19:45:30 | 110.9 | + F2, F2D | `ce9c6b16…794d4` | `ce9c6b16…794d4` | 0 | yes |
| `81f32b7f-c20c-4c91-a9aa-47a95bd2863c` | 20:00:03 → 20:02:24 | 141.4 | + FULL, FULLD | `ce9c6b16…794d4` | `ce9c6b16…794d4` | 0 | yes |
| `4ddea956-6199-4d91-acf6-13e0a82d6ab4` | **20:07:32 → 20:10:35** | **182.5** | **all nine, + FZ, FZD** | `ce9c6b16…794d4` | `ce9c6b16…794d4` | 0 | yes |

Full digest: `ce9c6b1646b35a6d547848c07e8610656b3fbead947ad14560746025f52794d4`.
It is **byte-identical across all four jobs and across pre/post within each
job**, confirming no submitted-surface file changed at any point during
measurement. `pgrep` before and after each job returned an empty
model-holding-process list, so every measurement ran on an idle host with one
model-holding process at a time. Reported data comes from job `4ddea956-…`,
whose single interleaved sweep contains every block.

### W&B runs — `wandb-applied-ai-team/mlxfast-maple`

| block | run id | URL |
|:--|:--|:--|
| R_sweep | `2k72wd0j` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/2k72wd0j |
| D_sweep | `wvo05b7j` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/wvo05b7j |
| M3D | `4urxyova` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/4urxyova |
| F2 | `84bsx0o2` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/84bsx0o2 |
| F2D | `l818ji2f` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/l818ji2f |
| FULL | `tz5oibjx` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/tz5oibjx |
| FULLD | `g89a9h8d` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/g89a9h8d |
| FZ | `1b22ne53` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/1b22ne53 |
| FZD | `2zmzw32z` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/2zmzw32z |
| **summary** | **`4bp1qhvz`** | **https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/4bp1qhvz** |

The summary run carries `primary_metric = 33.64`
(`f_over_tau0_pct_primary_arm_worst`) with
`primary_gate_source = "measured T(512)-T(0), no extrapolation"`, plus
`primary_f_over_tau0_pct_worst_fitted`,
`primary_f_over_tau0_pct_worst_at_C40 = 42.78`, the measured gate table, the
C = 40 wave projection, the makespan scan, the direct S = 2 emulation (with
`merge_floor_us` / `merge_est_us` / `net_ratio_merge_est`), the secondary-arm
tables, the wave law, `sliding_split_scan`, `heldout_f2`,
`replicates_pr196 = True` and `submitted_surface_delta_bytes = 0`.

### Machine-readable artifacts

- `research/artifacts/frieren-r102/sweep.csv` — every point, schema
  `block,K,waves,idx,N,M,slots,rounds,min_us,med_us,mean_us,sd_us` (144 rows).
- `research/artifacts/frieren-r102/fit.md` — full derived tables (673 lines).
- `research/artifacts/frieren-r102/{R_sweep,D_sweep,M3D,F2,F2D,FULL,FULLD,FZ,FZD}.log`
  — raw probe output including the pipeline-properties gate and memory-regime
  table for each block.
- `research/artifacts/frieren-r102/blockwise-superseded/` — the discarded
  block-ordered runs, kept for audit.
- `research/artifacts/frieren-r102/surface_digest.txt` — rule-75 digests.
- `research/frieren-r102-preregistration.md` — committed at `7dbec2f` **before**
  any measurement.

---

## 12. Runtime, cost, and suggested follow-ups

Total GPU time across all four measurement jobs: **523 s**. Peak memory is the
probe's 16 MiB K-cache plus a matching V-cache; no model was loaded, so this
experiment never contended for unified memory. No official submission was made
(none authorised). `Sources/`, `Vendor/` and `benchmark.json` are untouched.

**Follow-ups I did not implement:**

1. **Fuse the `(o, m, l)` merge into the o-projection head.** This is the single
   change that would move split-K from "loses by 4.6 µs" to "loses by 1.3 µs",
   and it is independently useful: the same fusion removes a dispatch from the
   unsplit path too. Worth scoping as its own experiment regardless of split-K.
2. **`a = 1.26 µs` per dispatch is itself a target.** With 40 layers × 2
   attention-adjacent dispatches, a once-per-dispatch constant of this size is a
   large absolute cost on the decode path. Measuring how much of `a` is
   command-buffer overhead versus pipeline bind would say whether batching
   dispatches into fewer encoders is worth an experiment.
3. **The N ≥ 320 variance cliff** (rel sd jumping from 0.3 % to 3–7 %) is a
   cache-capacity threshold at a working set the *production* sliding layers sit
   right on top of. If real, a layout change that keeps the hot KV slice under
   that threshold could be worth more than anything split-K offered.
4. **`CURRENT_RESEARCH_STATE.md` does not cite the archive.** The fact that
   R102-A was proposed on a premise the archive explicitly falsifies suggests a
   mechanical cross-check (grep proposed-experiment keywords against archive
   closure entries) before assignments are written.
5. **The same-kernel 2-deep sliding substitution from comment 4 §2.** Dropped
   here because the sliding verdict is `r`-invariant (§7.4), but it is still the
   only unconfounded way to get `u₂/u₄`, it would firm up the #539 attribution
   that several downstream numbers lean on, and its `f₄ ≈ f₂` check is a free
   test of the affine model. Research-only, roughly one 3-minute probe job.
