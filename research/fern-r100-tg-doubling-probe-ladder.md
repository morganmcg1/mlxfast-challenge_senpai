# r100-A — probe fidelity, and the threadgroup-doubling cost ladder

Student: maple-fern · PR #553 · branch `maple-fern/r100-tg-doubling-probe-ladder`
Base: `d90f854d4687605880b0baf99e93b4a0b786100e` (`codex/mlxfast-maple-20260804-advisor`)
Host: Apple M4 Pro, 20 GPU cores, `applegpu_g16s` (Apple GPU gen 16), macOS 26.5.2, 48 GiB
Predictions registered before measurement: `research/fern-r100-preregistration.md`

## Reply

Two questions were assigned. Both are answered, and both answers are negative
for the route they were testing — but the second one produced a reusable
structural result that I think is the more valuable output of the round.

**1. Probe fidelity (P1). r99's QMV template probe overstates its own effect by
8.01×, from two independent defects that I measured separately.**

- *Rung selection (1.59×).* r99's headline "−14 %" is the `TG=1024` rung. I
  proved from the kernel's own indexing that full coverage of the SwiGLU
  intermediate requires **exactly** `TG=2048` (`activated[expert_slot*512 +
  logical_row]` with `output_width=512`), and confirmed it against the
  equivalence gate's write counts: `TG=1024` writes 4096 B, half of the 8192 B
  that 8 experts × 512 rows × 2 B require. Every rung below 2048 is a
  partial-coverage dispatch that corresponds to no real unit of work. At the one
  faithful rung the dose is **−9.167 %**, not −14.613 %.
- *Cache residency (5.02×).* At `TG=2048` the probe's 8.51 MiB working set is
  re-read 500× per round and is served at **246.7–253.0 GB/s = 92.7–95.0 % of
  this host's measured 266.3 GB/s DRAM ceiling** — so it is not riding a free
  cache, but it *is* reading a resident 8.51 MiB window rather than the
  312 MiB/step (39 layers × 8 MiB) a real decode step must stream. Rotating the
  binding across 64 slots (274.14 MiB unique, `slc_fit=no`) shrinks the dose
  from −9.167 % to **−1.825 %**. I registered "≥2× shrink, best estimate −4 %,
  interval [−8 %, −1 %]" beforehand; the measured −1.825 % lands just inside
  that interval and the shrink is 2.5× larger than my best estimate.

Priced on the recorded pool (`T2c_routed_qmv`, marginal 1183.81 ± 8.44 µs/step):
**21.6 µs/step marginal (28.6 µs/step census) = 0.330 % score = 31 % of the
68.7 µs/step record bar.** The template route does not clear on its own. The
uncorrected −14.6 % would have promised 173 µs/step = 2.64 %.

**2. The "≈70× overstatement" in the brief is an arithmetic artifact, and r99's
in-situ leg never had the power to establish it.** 70 ≈ 14 % ÷ 0.196 %, which
divides a *kernel-relative* dose by a *step-relative* measurement. I registered
this reading before measuring. r99's in-situ leg measured −25.5 µs/tok against a
same-arm base spread of 137.2 µs/tok, i.e. SE(diff) ≈ 85 µs/tok and a 95 %
interval of **[−193, +142] µs/tok** — it could not have distinguished the
uncorrected prediction from zero. What the corrections do is close the gap:
21.6 µs/step (21.6–34.6 µs/tok across a 1.0–1.6 step↔token factor) sits within
**0.11 σ** of the measured −25.5 µs/tok, while the uncorrected 173 µs/step sits
**1.7–3.0 σ** away. The two defects fully account for the discrepancy.

**3. The threadgroup ladder (E1) is a clean staircase with risers at exactly
K = 21, 41, 61 on this 20-core host, and it survives cache-residency defeat
unchanged** (φ(32) = 1.8008 resident vs 1.8040 defeated). So it is a scheduling
effect, not a memory effect.

**4. I have to correct my own preregistered inference.** I registered "stepped φ
⇒ the M4 kill does not transfer, φ_M5 ≈ 1.0". That was wrong, and the error was
mine: I wrote it believing 64 threadgroups still fit M5's first tread, but
64 > 40, so M5 pays a second round too. The correct statement is that the
32 → 64 doubling **doubles the round count on both hosts** (M4: 2 → 4 at 20
cores; M5: 1 → 2 at 40 cores), so it is not an M4 artifact at all.

**5. Route A ("one query head per threadgroup") is dead, host-independently, and
for a sharper reason than kernel time.** Define
`Fill(K) = K / (cores · ceil(K / cores))`. On the ranked 40-core M5,
`Fill(32) = 32/40 = 0.80` and `Fill(64) = 64/80 = 0.80` — **the doubling is
exactly fill-neutral** while doubling the requested K/V window traffic (8
threadgroups per kv-head instead of 4, at `gqa = 8`). The same holds on M4
(0.80 → 0.80). In general `Fill(2K)/Fill(K) = 2·ceil(K/C)/ceil(2K/C)`, which for
K = 32 equals 1 for **every** core count C < 64 and only reaches 2 at C ≥ 64.
M5 Max has 40 cores. Route A therefore buys nothing anywhere in the plausible
core-count range and costs extra traffic. It should not be built.

I also closed the obvious escape hatch before concluding this. E1b sweeps a
synthetic kernel over threads/TG × threadgroup bytes: at 1024 threads the
risers stay at 21/41/61/81 for **every** threadgroup allocation from 256 B to
32768 B (a 128× range), and at 512 threads too. Shrinking the kernel's 18432 B
threadgroup footprint — which the 6b Route A variant would have done — cannot
raise concurrency. There is no occupancy lever here.

**6. The constructive result.** The mechanism is threadgroup-count/core-count
quantization, and the way to capture it is *finer, balanced* granularity rather
than a 2× head split: splitting the 512-position KV window 16 ways gives 512
threadgroups and `Fill = 0.985` on both hosts, i.e. it recovers
`1 − 0.80/0.985 = 18.8 %` of the sliding-attention kernel time. On M5 that is
**≈54.5 µs/step ⇒ 0.83 % score, 79 % of the bar**, before paying for the
cross-slice softmax reduction. This independently reproduces rule 67's
starvation ceiling (its 0.1836 sliding-starvation fraction vs my 0.188) and
supplies the missing mechanism and geometry for it. I did not implement it —
flagging it as the follow-up that the ladder actually points at.

**Recommendation:** close Route A on this evidence; do not spend an assignment
on the 6b threadgroup-memory variant either. Re-price the QMV template route at
21.6 µs/step before considering it further. If the advisor wants the attention
dispatch attacked, the split-K/flash-decoding geometry is the arm with a real
ceiling, and it needs an M5 measurement because the payoff is entirely a
core-count effect.

Scope note: **no scored file was touched** (`git diff --stat` against base is
confined to `research/`), submitted-surface growth is **0 bytes**, and
`run_upstream_equivalence.sh` is therefore not applicable — no scored-path
numerics, representation, dispatch, or layout changed. Both probes compile the
kernel text out of `Sources/MLXFastModel/LagunaRuntimeModel.swift` read-only.

---

## 0. What ran

| Artifact | Contents |
| --- | --- |
| `research/fern_r99_qmv_probe.swift` | QMV template probe, extended with the P1.1 regime block, P1.2 residency defeat, `t_paired`, and a coverage model |
| `research/fern_r100_attn_probe.swift` | new attention threadgroup ladder: NULL control, regime block, residency defeat, absolute `t(K)`/`t/K`/`φ(K)` |
| `research/fern_r100_occupancy_probe.swift` | new synthetic occupancy probe: threads × threadgroup-bytes sweep, riser detection |
| `research/artifacts/fern-r100/p1_qmv_null_resident.log` | QMV NULL bias floor, resident |
| `research/artifacts/fern-r100/p1_qmv_null_defeat.log` | QMV NULL bias floor, 64-slot defeat |
| `research/artifacts/fern-r100/p1_qmv_dose_resident.log` | 4-variant dose ladder, resident |
| `research/artifacts/fern-r100/p1_qmv_dose_defeat.log` | 4-variant dose ladder, 64-slot defeat |
| `research/artifacts/fern-r100/p2_attn_e1_resident.log` | E1 ladder, resident |
| `research/artifacts/fern-r100/p2_attn_e1_defeat.log` | E1 ladder, 64-slot / 12-copy defeat |
| `research/artifacts/fern-r100/p2_occupancy_e1b.log` | E1b occupancy sweep |

Reproduction:

```bash
xcrun swiftc -O research/fern_r99_qmv_probe.swift -o /tmp/fernqmv
xcrun swiftc -O research/fern_r100_attn_probe.swift -o /tmp/fernattn
xcrun swiftc -O research/fern_r100_occupancy_probe.swift -o /tmp/fernocc

# P1: NULL control (reference path repeated) then the 4-variant dose ladder.
# The .metal arms are the tracked r99 variants.
V=research/artifacts/fern-r99
FERN_ROUNDS=21 FERN_REPS=100 FERN_DEFEAT_SLOTS=1  /tmp/fernqmv $V/depth1_shipped.metal
FERN_ROUNDS=21 FERN_REPS=100 FERN_DEFEAT_SLOTS=64 /tmp/fernqmv $V/depth1_shipped.metal
FERN_ROUNDS=21 FERN_REPS=100 FERN_DEFEAT_SLOTS=1  /tmp/fernqmv $V/depth1_shipped.metal \
  $V/tmpl_s1.metal $V/tmpl_s2.metal $V/tmpl_s4.metal $V/stage4_cand.metal
FERN_ROUNDS=21 FERN_REPS=100 FERN_DEFEAT_SLOTS=64 /tmp/fernqmv $V/depth1_shipped.metal \
  $V/tmpl_s1.metal $V/tmpl_s2.metal $V/tmpl_s4.metal $V/stage4_cand.metal

# E1: resident, then residency-defeated
FERN_ROUNDS=21 FERN_REPS=200 /tmp/fernattn Sources/MLXFastModel/LagunaRuntimeModel.swift
FERN_ROUNDS=21 FERN_REPS=200 FERN_DEFEAT_SLOTS=64 FERN_CACHE_COPIES=12 \
  /tmp/fernattn Sources/MLXFastModel/LagunaRuntimeModel.swift

# E1b: occupancy limiter
FERN_TGMEM_LIST=256,8192,16384,18432,32768 FERN_THREADS_LIST=1024,512,256,128 \
  FERN_K_MAX=200 FERN_ITERS=800 FERN_ROUNDS=3 FERN_REPS=30 /tmp/fernocc
```

Zero benchmark receipts, as assigned. No official submission.

---

## 1. P1.1 — which side of the roofline the QMV probe lives on

The probe re-reads its bound window `reps` times per round, so read
amplification is `reps` while a real decode step reads each expert once. The
regime block makes that explicit instead of assuming it. Requested bytes per
dispatch come from the kernel's own constants (`fused_row_bytes = 1024`,
`scale_tile_bytes = 512`, `routed_experts = 8`, `rows = (TG/8)·2`); unique bytes
come from an interval merge over the rotated bindings.

Resident, `FERN_REPS=100`:

| TG | rows | uniq MiB | req MiB/round | amplif | base µs | achieved GB/s | % of 266.3 peak | slc_fit | regime |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 128 | 32 | 0.54 | 266.28 | 500 | 4.56 | 123.0 | 46.2 | yes | PARTIAL |
| 256 | 64 | 1.07 | 532.55 | 500 | 6.82 | 164.0 | 61.5 | yes | PARTIAL |
| 512 | 128 | 2.13 | 1064.85 | 500 | 10.72 | 209.0 | 78.0 | yes | PARTIAL |
| 1024 | 256 | 4.26 | 2128.45 | 500 | 19.94 | 224.0 | 84.0 | yes | SATURATED |
| **2048** | **512** | **8.51** | **4256.41** | **500** | **35.28–36.18** | **246.7–253.0** | **92.7–95.0** | yes | **SATURATED** |

Two things follow. First, the probe is *not* getting a free cache ride: at the
faithful rung it runs within 5–7 % of the measured DRAM ceiling even though its
working set nominally fits the ≈24 MiB SLC. Second, that is still the wrong
regime: in situ, 39 layers × 8 MiB = 312 MiB/step must come from DRAM with
amplification ≈ 1, so a 500× re-read of one resident window rewards
instruction-count reductions that DRAM latency would otherwise hide.

Defeated (64 slots, weight buffer 335544320 B, scale buffer 20910208 B, routed
winners `[39, 88, 99, 110, 114, 184, 216, 239]`):

| TG | uniq MiB | amplif | base µs | achieved GB/s | % peak | slc_fit | regime |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2048 | 274.14 | 15.5 | 38.95 | 229.2 | 86.1 | **no** | SATURATED |

I deliberately keep `slc_fit` (capacity) and `regime` (bandwidth saturation) as
separate columns, because the resident `TG=2048` row is the case where they
disagree and that disagreement is the whole point.

**Instrument bug found and fixed.** The regime block originally ran *before* the
warm-up loops, so its `ref_us` was a cold measurement — 22.05 µs at `TG=128`
against a true 4.56 µs, a 4.8× error that would have mislabelled every rung's
regime. Warm-up now precedes the block and regime timing is min-of-3.

## 2. P1.2 — the NULL bias floor, and an honest verdict on my own gate

Passing one source path runs BASE against itself, so the true difference is
exactly zero and whatever the probe reports is its own bias.

| arm | rung | d_mean µs | d % of ref | t | verdict vs registered gate |
| --- | --- | --- | --- | --- | --- |
| resident | 2048 | −0.182 | **−0.534** | −1.86 | passes both clauses |
| resident | 128/512/1024 | — | ≤ 0.47 in magnitude | 6.7–7.9 | **fails the \|t\| < 3.0 clause** |
| defeat | 2048 | −0.020 | **−0.051** | −0.92 | passes both clauses |

I registered the null gate as `|d_mean| ≤ 0.5 %` **and** `|t| < 3.0`, with
"failure ⇒ instrument broken, report immediately". Reporting as promised: the
`|t|` clause fails at three resident rungs. My reading is that the gate, not the
instrument, is at fault. The bias is real but is −0.02…−0.04 µs — the
second-measured arm is consistently a hair faster — and it is only resolvable
because `d_sd` is minute. A `t`-statistic has no upper bound as precision
improves, so pairing a precision-free percentage clause with a `t` clause was a
design error on my part. The decision-relevant quantity is bias relative to
effect: ≤ 0.53 % of reference against doses of 9.2 % and 1.8 %, i.e. **≥ 17×
smaller than the smallest dose I report, and 36× smaller in the defeated arm
that carries the headline number.** I am flagging the failure rather than
quietly re-deriving the gate, and I would replace the `t` clause with
`|d%| ≤ 0.25 × |smallest reported dose|` next time.

## 3. P1.3 — the dose ladder, and why only one rung is real

Four template variants (`tmpl_s1`, `tmpl_s2`, `tmpl_s4`, `stage4_cand`), all
**bitwise identical to the reference at every rung**.

| TG | coverage | resident d %_ref | defeat d %_ref |
| --- | --- | --- | --- |
| 128 | 1/16 | ≈ −4.9 | ≈ −13.9 |
| 256 | 1/8 | ≈ −8.9 | ≈ −12.0 |
| 512 | 1/4 | ≈ −11.35 | ≈ −25.5 |
| 1024 | **1/2 — r99's headline rung** | −9.80\*, −14.45, −14.63, −14.76 → **−14.613** (3 converged) | ≈ −3.4 |
| **2048** | **full** | −9.568, −8.969, −9.061, −9.069 → **−9.167** | −1.826, −1.976, −1.775, −1.722 → **−1.825** |

\* `tmpl_s1` is an outlier at the 1024 rung; the partial rungs are also
variant-unstable and non-monotone in the defeated arm, which is what a
measurement of a meaningless work unit looks like.

Coverage is not a judgement call. `research/artifacts/fern-r99/depth1_shipped.metal`
L156-168 and L266 give `output_width = 512` and
`activated[expert_slot*output_width + logical_row]`, with
`logical_row = (TG/8)·2 − 1` at most; full coverage of 8 experts × 512 rows
therefore requires exactly `TG = 2048`. The equivalence gate's write counts
confirm it: 4096 B at `TG=1024` versus 8192 B at `TG=2048`.

### The correction and its price

| step | factor | dose |
| --- | --- | --- |
| r99 headline (`TG=1024`, resident) | — | −14.613 % |
| → faithful rung (`TG=2048`, resident) | **1.59×** | −9.167 % |
| → residency defeated (`TG=2048`) | **5.02×** | −1.825 % |
| combined | **8.01×** | |

| quantity | uncorrected | corrected |
| --- | --- | --- |
| marginal µs/step (× 1183.81) | 173.0 | **21.6** |
| census µs/step (× 1569.8) | 229.4 | 28.6 |
| score % (× 0.015280 %/µs) | 2.643 | **0.330** |
| fraction of the 68.7 µs/step bar | 252 % | **31 %** |

### Reconciliation with r99's in-situ leg

r99 measured **−25.5 µs/tok** in situ, with a same-arm base spread of
137.2 µs/tok ⇒ σ ≈ 60 µs/arm, SE(diff) ≈ 85 µs/tok, 95 % interval
**[−193, +142] µs/tok**.

| prediction | µs/tok (step↔token factor 1.0–1.6) | distance from −25.5 |
| --- | --- | --- |
| uncorrected 173 µs/step | 173–277 | **1.7–3.0 σ** |
| **corrected 21.6 µs/step** | **21.6–34.6** | **0.05–0.11 σ** |

The corrected prediction is a bull's-eye and the uncorrected one is excluded.
The two defects account for the whole probe/in-situ gap, so no third mechanism
needs to be invoked — and, symmetrically, the in-situ leg on its own never had
the resolution to prove anything, which is why the brief's "≈70×" could not have
been a measurement.

---

## 4. E1 — the absolute threadgroup cost ladder

Kernel `laguna_sliding_fused_attn_ring_v1`, wrapper geometry
`grid((heads/2)·1024, 1, 1)`, `TG (1024, 1, 1)`, `heads = 64` ⇒ **32
threadgroups** (`Sources/MLXFastModel/LagunaRuntimeModel.swift` L1778, L1808-1809,
sole call site L6019). Pipeline properties identical for both arms:
srcLines 285, **staticThreadgroupMemoryLength 18432 B**,
maxTotalThreadsPerThreadgroup 1024, threadExecutionWidth 32.

Best of 21 rounds of 200 dispatches:

| K | TG/core | resident µs | resident t/K | defeat µs | defeat t/K |
| --- | --- | --- | --- | --- | --- |
| 8 | 0.40 | 9.01 | 1.126 | 9.33 | 1.166 |
| 16 | 0.80 | 9.05 | 0.566 | 9.59 | 0.599 |
| 20 | 1.00 | 9.06 | 0.453 | 9.90 | 0.495 |
| **21** | 1.05 | **17.79** | 0.847 | **20.02** | 0.954 |
| 24 | 1.20 | 18.01 | 0.750 | 19.07 | 0.795 |
| **32** | 1.60 | **18.31** | 0.572 | **19.12** | 0.597 |
| 40 | 2.00 | 18.05 | 0.451 | 20.21 | 0.505 |
| **41** | 2.05 | **25.04** | 0.611 | **28.08** | 0.685 |
| 48 | 2.40 | 25.37 | 0.529 | 27.37 | 0.570 |
| 56 | 2.80 | 25.34 | 0.453 | 27.80 | 0.496 |
| 60 | 3.00 | 25.10 | 0.418 | 28.03 | 0.467 |
| **61** | 3.05 | **32.87** | 0.539 | **35.40** | 0.580 |
| **64** | 3.20 | **32.97** | 0.515 | **34.48** | 0.539 |
| 80 | 4.00 | 34.37 | 0.430 | 35.49 | 0.444 |
| 96 | 4.80 | 42.01 | 0.438 | 43.22 | 0.450 |

Risers sit at **K = 21, 41, 61** — exactly `20n + 1` for this host's 20 cores —
and `t/K` falls monotonically *within* each tread while jumping at each riser.
Fitting `t = a + b·ceil(K/20)` to the tread means gives
`t ≈ 0.80 + 8.24·W` resident and `t ≈ 1.21 + 8.40·W` defeated.

φ at the operating point: **φ_resident(32) = 1.8008, φ_defeat(32) = 1.8040.**
Residency defeat (12 cache copies ⇒ 384.12 MiB unique at K = 96, `slc_fit=no` at
every rung) raises absolute times by 4–5 % and leaves the riser positions and φ
**unchanged to three digits**. The staircase is scheduling, not memory.

Consistent with that, the regime block shows attention is not bandwidth-bound
on either arm: 21.5–58.5 % of the 266.3 GB/s peak resident, 30.1–55.3 %
defeated, i.e. `UNSATURATED`/`PARTIAL` throughout.

NULL bias floor for this probe: `|d%| ≤ 0.37` for K ≤ 60 resident and `≤ 0.69`
defeated, so the detection floor is ≈ 1.5 % of kernel time. Note that nezuko's
known K = 32 base-vs-base artifact of +1.4–1.6 % **did not reproduce** here
(d% = −0.266, t = −1.28).

## 5. E1b — is there an occupancy lever? No.

If the ladder's quantum could be made smaller than one threadgroup per core,
a doubling variant could hide its extra rounds. The synthetic probe sweeps
threads/TG × threadgroup bytes and reads concurrency off the first riser.

| threads | tgmem B | risers (K) | C | TG/core |
| --- | --- | --- | --- | --- |
| 1024 | 256 | 21, 41, 61, 81 | 20 | 1.00 |
| 1024 | 8192 | 21, 41, 61, 81 | 20 | 1.00 |
| 1024 | 16384 | 21, 41, 61, 81 | 20 | 1.00 |
| 1024 | **18432** (the real kernel's) | 21, 41, 61, 81 | 20 | 1.00 |
| 1024 | 32768 (per-core max) | 21, 41, 61, 81 | 20 | 1.00 |
| 512 | 256 … 32768 | 21, 41, 61 | 20 | 1.00 |
| 256 | 16384, 18432 | 41 | 40 | 2.00 |
| 128 | 18432 | none ≤ 200 | > 200 | — |

`device.maxThreadgroupMemoryLength = 32768 B`, and every configuration was
admitted at the requested thread count (no `maxTotalThreadsPerThreadgroup`
clamping), so this is a clean sweep.

The 1024-thread rows are flat at `TG/core = 1.00` across a **128× range** of
threadgroup allocation, including 256 B. Threadgroup memory is therefore not
what quantizes the ladder, and the 6b Route A variant's plan to shrink
`outputs[4*BN*BDP]` to `outputs[2*BN*BDP]` (18432 B → ≈9984 B) cannot buy
concurrency. The 512-thread rows are also flat at 1.00, which rules out the
other candidate lever (halving threads/TG alongside heads/TG).

Honest limit of this sub-experiment: the 128- and 256-thread rows are internally
inconsistent (C reads 20, 40, 60, 80 or ">200" depending on `tgmem`) because
`t(1)` floors at ≈16–17 µs regardless of thread count — at low thread counts the
synthetic kernel becomes latency-bound on its dependent-FMA chain, so a 21st
threadgroup is partly hidden and the 1.18 riser threshold misses. I therefore do
not claim a residency number from those rows. I also cannot fully separate
"one threadgroup slot per core" from "co-resident threadgroups share ALUs, so
residency is irrelevant" — both produce `wall = a + b·ceil(K/cores)`, which is
what the real kernel measurably does. That ambiguity does not affect any
decision below, because both mechanisms give the same `Fill` arithmetic.

## 6. The corrected transfer argument, and why Route A is dead

Route A was "one query head per threadgroup": 64 threadgroups × 1 head instead
of 32 × 2, bit-exact per head, same total work.

I registered "stepped φ ⇒ the M4 kill does not transfer, φ_M5 ≈ 1.0". **That
inference was wrong.** I wrote it believing 64 threadgroups remain inside M5's
first tread, but M5 Max has 40 cores and 64 > 40, so M5 pays a second round as
well. Round counts:

| host | cores | base 32 TG | Route A 64 TG |
| --- | --- | --- | --- |
| M4 Pro (measured) | 20 | ceil(32/20) = 2 | ceil(64/20) = 4 |
| M5 Max (ranked) | 40 | ceil(32/40) = 1 | ceil(64/40) = 2 |

Both hosts double. With per-threadgroup times τ₂ (two heads) and τ₁ (one head),
Route A wins iff `4τ₁ < 2τ₂` on M4 and `2τ₁ < τ₂` on M5 — **the same condition,
τ₁ < 0.5·τ₂.** It cannot be met: going from two query heads to one halves the
QK/AV arithmetic but leaves the K/V window read and the fixed per-threadgroup
cost intact, so `τ₁ ≈ 0.5·compute + kv + fixed` and break-even would require
`0.5·(kv + fixed) < 0`.

The cleaner way to say the same thing, which also makes the result
core-count-robust, is fill. With `Fill(K) = K / (cores · ceil(K/cores))`:

| cores | Fill(32) | Fill(64) | Route A fill gain |
| --- | --- | --- | --- |
| 20 (this host) | 0.800 | 0.800 | **1.00×** |
| 32 | 1.000 | 1.000 | 1.00× |
| **40 (M5 Max)** | **0.800** | **0.800** | **1.00×** |
| 48 | 0.667 | 0.667 | 1.00× |
| 64 | 0.500 | 1.000 | 2.00× |
| 80 | 0.400 | 0.800 | 2.00× |

`Fill(2K)/Fill(K) = 2·ceil(K/C)/ceil(2K/C)`, which at K = 32 equals 1 for every
`C < 64`. Route A is fill-neutral on every plausible Apple Silicon core count
and only pays at ≥ 64 cores. It also doubles requested K/V traffic, since at
`gqa = 8` each kv-head would be read by 8 threadgroups instead of 4 — affordable
in bandwidth terms (§4 shows ≤ 58.5 % of peak) but strictly negative. **Route A
should not be built.** Note this is a stronger conclusion than "the M4 says no":
it does not depend on the M4 measurement transferring.

For completeness: no test constrains this geometry. `grep` over `Tests/` finds no
assertion on the sliding-fused-attention threadgroup shape, so the gate on any
geometry change is purely numerical.

## 7. Where the ladder does point

The same arithmetic that kills Route A prices the opposite move. Sliding
attention runs at `Fill = 0.80` on M5 — 8 of 40 cores idle in its single round —
and the fix is finer, *balanced* granularity, i.e. split-K/flash-decoding over
the 512-position KV window with a cross-slice softmax reduction:

| geometry | TGs | Fill on M5 (40) | Fill on M4 (20) |
| --- | --- | --- | --- |
| base: 32 pairs | 32 | 0.800 | 0.800 |
| Route A: 64 heads | 64 | 0.800 | 0.800 |
| 32 pairs × 4 slices | 128 | 0.800 | 0.914 |
| 32 pairs × 8 slices | 256 | 0.914 | 0.985 |
| **32 pairs × 16 slices** | **512** | **0.985** | 0.985 |

At 16 slices the recoverable fraction is `1 − 0.80/0.985 = 18.8 %` of the
sliding kernel. On M5 (sliding ≈ 290 µs/step) that is **≈54.5 µs/step ⇒ 0.83 %
score, 79 % of the 68.7 µs/step bar**, before the reduction's own cost. Full
attention (≈100 µs/step on M5) adds more.

This independently reproduces rule 67's starvation ceiling — its sliding
starvation fraction of 0.1836 against my 0.188, from a completely different
measurement — and supplies what rule 67 lacked: the mechanism (threadgroup-count
versus core-count quantization) and a concrete geometry that captures it. It
also explains why the ceiling is real rather than a bookkeeping artifact.

Two caveats I would not hide from whoever picks this up. The payoff is entirely
a core-count effect, so it must be measured on M5; on this 20-core host the
same change scores `0.800 → 0.985` too, but for different riser positions, and a
positive M4 result would be weak evidence. And 512 threadgroups × 18432 B of
threadgroup memory is fine (allocation is per resident threadgroup, and E1b
shows concurrency is 1/core regardless), but the reduction across 16 partial
softmaxes per head-pair is the part that decides whether 0.83 % survives.

## 8. What I did not do

- No Route A implementation, and no timing of one. E1/E1b answer the question
  the implementation was meant to answer, negatively and host-independently, so
  building it would have spent an assignment to confirm a fill-neutral change.
- No E2 uniqueness fold (`kv_head = (head0/gqa) % 8`). It was scoped as a
  contingency on Route A being viable.
- No split-K implementation. It is a real kernel change with a correctness
  surface (partial-softmax reduction) and belongs in its own assignment with an
  M5 measurement.
- No benchmark receipts and no official submission, as assigned.
- No scored file touched; `Sources/` is untouched, so #539 and #548 are
  unaffected.

## 9. Registered-prediction scorecard

| registered claim | outcome |
| --- | --- |
| "≈70×" is `14 % ÷ 0.196 %`, kernel-relative ÷ step-relative, not a measurement | **confirmed** |
| in-situ band `[−193, +142]` µs/tok ⇒ r99 in-situ had no power to establish an overstatement | **confirmed** |
| resident reproduces −14 % ± 3 % | **confirmed** at the 1024 rung (−14.613 %) |
| defeat shrinks the dose ≥ 2×; best estimate −4 %, interval [−8 %, −1 %] | **confirmed**, 5.02× shrink to −1.825 %, inside the interval |
| null gate `\|d_mean\| ≤ 0.5 %` **and** `\|t\| < 3.0` | **failed at 3 resident rungs**; reported in §2, gate design was mine and is wrong |
| stepped φ ⇒ M4 kill does not transfer, φ_M5 ≈ 1.0 | **wrong, and retracted** — 64 > 40 cores, so M5 doubles rounds too (§6) |
| E1 discriminates smooth vs stepped | **confirmed stepped**, risers at exactly 20n+1, robust to residency defeat |
