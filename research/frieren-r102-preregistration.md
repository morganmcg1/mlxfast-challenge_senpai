# R102-A preregistration — the per-threadgroup fixed cost of decode attention

**Student:** maple-frieren · **PR:** #566 · **Base:** `51e36805030a982daecda80535281f4540a1cde1`
**Host:** M4 Pro, `applegpu_g16s` gen 16, 20 GPU cores, 48 GiB, macOS 26.5.2
**Committed before any measurement commit.** Rung 1 has a zero submitted-surface delta.

---

## 1. The question

Does a 5-way KV split of the decode attention kernels pay? The assignment's §2
reduces this to one measurable ratio: the split-invariant per-threadgroup fixed
cost `f` as a fraction of the split-divisible work `τ₀` at window 512.

## 2. Advisor algebra — checked, and it holds

Under the assignment's model `makespan = w·(f + τ₀/S)` with `w = ceil(K·S/C)`:

| kernel / host | K | w(S=1) | w(S=5) | inequality | threshold |
|---|---:|---:|---:|---|---:|
| sliding, M5 C=40 | 32 | 1 | 4 | `4(f+τ₀/5) < f+τ₀` ⇒ `3f < 0.2τ₀` | `f/τ₀ < 6.667 %` |
| sliding, M4 C=20 | 32 | 2 | 8 | `8(f+τ₀/5) < 2(f+τ₀)` ⇒ `6f < 0.4τ₀` | `f/τ₀ < 6.667 %` |
| full, M5 C=40 | 24 | 1 | 3 | `3(f+τ₀/5) < f+τ₀` ⇒ `2f < 0.4τ₀` | `f/τ₀ < 20 %` |
| full, M4 C=20 | 24 | 2 | 6 | `6(f+τ₀/5) < 2(f+τ₀)` ⇒ `4f < 0.8τ₀` | `f/τ₀ < 20 %` |

**The algebra is correct and the host-invariance claim is correct**, because the
wave counts at S=5 and S=1 scale by the same integer factor (4 and 8 against 1
and 2; 3 and 6 against 1 and 2) on both core counts. An M4 measurement of the
*ratio* therefore legitimately decides the M5 case. This is preregistered as
agreed before measuring.

## 3. Prior art (rule 69) — this lever was measured and closed in round ~91

`research/RESEARCH_ARCHIVE_through-round-91.md`:

- `:6264-6280` — "**The decode-attention KV-split-across-threadgroups family, at
  EVERY S — CLOSED by PR #196.**" A prior S=5 relative-makespan proposal,
  structurally identical to this assignment's, was retracted. Measured
  wave-matched at C=40: **S=1 9.078 µs, S=2 10.384 (1.144×), S=5 15.468
  (1.704×), S=10 19.832 (2.185×)**. Reported **`f = 3.130 µs`, 34.3 % of a full
  512-row call**; replacement law `T = a + W·φ + work`, `a = 1.661 µs`,
  `φ = 1.469 µs/wave`.
- `:3814-3838` — the same result in full, plus `g = 0.7483 µs/KV-iter` and the
  direct C=20 measurement `18.333 / 20.309 / 27.296 / 34.875 µs` for
  S = 1/2/5/10.
- `:6289-6299` — "**Idle slots below C cost time' as a pricing model — CLOSED.**"
  The unit-resolution staircase is **flat to ±0.06 µs from K=1 to K=20**, then
  steps +6.48 µs at K=21 and +6.44 µs at K=41.
- `:6256-6262` — the head-axis repartition variant, closed separately.

This host's own round-100 ladder (`research/artifacts/fern-r100/p2_attn_e1_resident.log`)
independently reproduces that staircase on the *current* kernel: 9.01/9.05/9.06 µs
at K=8/16/20, then 17.79 at K=21, flat to 18.05 at K=40, 25.04 at K=41, flat to
25.10 at K=60, 32.87 at K=61. `W = ceil(K/20)` exactly, with nothing in between.

**Consequence I must state up front:** the assignment's framing that we are
"leaving 20 % of the sliding pool on the floor to ragged occupancy" is already
falsified on this host. At K=32 the dispatch costs what K=40 costs; the idle
slots are free. The real cost of K=32 is that it needs `W=2` on C=20 and `W=1`
on C=40 — and at S=1 on the ranked M5 it is already a single wave.

## 4. Preregistered prediction

From #196's decomposition, `f = 3.130 µs` and `τ₀ = 9.078 − 3.130 = 5.948 µs`, so

```
f/τ₀ = 3.130 / 5.948 = 52.6 %      (vs 6.667 % sliding gate, 20 % full gate)
φ/τ₀ = 1.469 / 5.948 = 24.7 %      (vs the same gates, most generous reading)
```

**I predict NO-GO, by roughly 8× on the sliding gate and 2.6× on the full gate.**
I preregister this so that a confirming measurement cannot be read as a fit to a
convenient answer, and so that a *disconfirming* measurement — which would mean
#539's 4-deep ring rewrite materially changed `f` — is the reportable surprise.

## 5. The gate (verbatim from the assignment §4)

- **GO:** `f/τ₀ < 6.67 %` (sliding) with the upper 95 % bound also under
  threshold, in SLC-defeat mode, null band ≥4× smaller than the margin.
- **PARTIAL:** `6.67 % ≤ f/τ₀ < 20 %` ⇒ sliding split dead, full split may pay.
- **NO-GO:** `f/τ₀ ≥ 20 %` ⇒ stop, write the closure, hand back the slot.

**Amendment I preregister now:** the assignment's `f` conflates two costs that
#196 separates — `a`, paid once per *call*, and `φ`, paid once per *wave*. Only
`φ` is re-paid by a split. `φ/τ₀` is therefore the correct and *more generous*
gate quantity, and `f/τ₀ = (a+φ)/τ₀` is conservative. **I will report both and
apply the gate to whichever is more favourable to GO** (i.e. `φ/τ₀`). If they
straddle a gate boundary I will report PARTIAL and say so explicitly rather than
choosing.

## 6. Method — three measurements, one instrument

`research/fern_r100_attn_probe.swift` extended with a `FERN_WINDOW` knob that
rewrites the kernel's `constexpr uint window` and `constexpr int N` together.
Verified beforehand that these two constants are the *only* window-dependent
text in the kernel body (`window` at 4 cache-addressing sites, `N` at the single
loop bound `for (; i + 3*BN < N; i += 4*BN)`), so the substitution is exact and
preserves dispatch geometry (rule 77).

The main loop starts at `i = sg` and strides `4·BN = 128`, so for `N = 128·M`
every simdgroup executes exactly `M` iterations. The admissible sweep is
therefore `N ∈ {512, 384, 256, 128}` ⇒ `M ∈ {4, 3, 2, 1}`, plus **`N = 96` ⇒
`M = 0`**, which executes prologue + merge + epilogue and no KV work at all.

- **M1 — intercept fit.** `K = 32` (shipped sliding geometry), `N ∈ {512, 384,
  256, 128}`. Fit `τ(N) = f + c·N`. Report `f`, `c`, `τ₀ = 512c`, `f/τ₀`, R²,
  residuals, 95 % CI on `f/τ₀`.
- **M2 — direct measurement of `f` at zero KV iterations.** `N = 96`. This is a
  *measurement* of the intercept rather than an extrapolation, and is my
  independent second estimate. I preregister it in place of the assignment's
  partial-write-epilogue variant because it isolates the same quantity without
  editing kernel semantics, and because a partial-write variant would change the
  epilogue's store pattern and therefore measure a different `f`. **Declared
  risk:** with `M = 0` the merge consumes `pair_max = lowest()` and `pair_sum =
  0`; if Metal takes a slow path on the resulting infinities this over-states
  `f`, which biases *against* GO. I will flag it if M1 and M2 disagree.
- **M3 — direct split emulation (work-conserving).** The decisive test, needing
  no wave model: `S=1 → (K=32, N=512)`, `S=2 → (K=64, N=256)`, `S=4 → (K=128,
  N=128)`. Each arm does the same total KV work over `S×` the threadgroups.
  This is a **lower bound** on a real split's cost: it omits the partial `(o,m,l)`
  write, the atomic counter, and the recombination pass. If `t(S) > t(1)` here,
  the family is dead a fortiori.
  I additionally fit `a` and `φ` separately via `K ∈ {20, 40}` at each window:
  `T(40,N) − T(20,N) = φ + c·N`, whose intercept is `φ`.

### Hygiene (standing rules)

- **Rule 71:** every sweep in both cache modes — resident binding, and
  `FERN_DEFEAT_SLOTS` rotation. Report `regime` (from `achieved_GB_s`) and
  `slc_fit` (from capacity) as two independent columns. The rotation *slot
  stride* is pinned to the 512-window footprint at every `N` so the address
  spread is identical across the sweep; only the bytes actually read shrink.
- **Warm-up:** first leg discarded (probe already warms at `k=32, reps=40` then
  runs the base arm over the whole ladder).
- **Null control:** BASE against itself at every `(K, N)` point. **Rule 78:**
  gate is `|d%| ≤ 0.25 × smallest reported dose`.
- **Rule 77:** geometry fidelity stated explicitly — 1024 threads/TG, K
  threadgroups, `FERN_KERNEL=laguna_sliding_fused_attn_ring_v1`, confirmed to be
  the shipped name at base (`LagunaRuntimeModel.swift:1417`), full-attention twin
  `laguna_full_fused_attn_grow_v1` at `:1937`.
- **Rule 75:** sha256 of sorted `Sources/` + `Vendor/` before build and after the
  timed phase, every paired run.
- Counts: `FERN_ROUNDS ≥ 21`, `FERN_REPS = 200`, best-of-rounds per point.

## 7. Preregistered null explanations (rule 72)

- **N-A (launch-dominated).** `f` ≥ 20 % of `τ₀` at the 512-window, dominated by
  prologue/merge/launch. *Signature:* large intercept, both cache modes agree,
  M2 confirms M1. **This is my predicted outcome.**
- **N-B (not affine).** `τ(N)` is a staircase or has a knee. *Signature:* poor
  R², structured residuals, M1/M2 disagreement. Because the loop is exactly
  `M = N/128` iterations, a knee would have to come from cache-line or tile
  granularity, and I will report its shape rather than force a line.
- **N-C (residency artifact).** `f/τ₀` passes resident, fails under SLC-defeat,
  because small `N` shrinks the working set into cache. *Signature:*
  mode-dependent intercept. Guarded by pinning the rotation stride and by
  reporting `uniq_MiB`/`slc_fit` per point.
- **N-D (the model omits the reduction).** Even at `f/τ₀ = 0` the split must pay
  for recombination. The §2 thresholds ignore it, so a GO on the intercept could
  still be a loss at rung 2. Mitigated by demanding margin, and by M3, which
  measures a split lower bound directly.

## 8. Stop rule

Report immediately on NO-GO or PARTIAL. On GO, write the rung-2 design and stop;
no rung-2 implementation without a fresh revision. No official submission is
authorised by this assignment. Do not touch `Sources/` at rung 1.
