# R97-B receipt 2 — P2/P2b reverted after a measured regression, P4 GEMM swizzle depth alone

Arm `maple-r97-b-prefill-tg-count` (PR #527), branch
`maple-tanjiro/r97-prefill-tg-count`, base
`b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`. Receipt 2 of a 6-receipt budget.

## 1. Context and goal

The arm's goal is to reduce M5 prefill time by attacking the
`steel_gemm_bf16` dispatch pool with sequenced, never-summed mechanisms: one
mechanism per receipt wherever possible, so that every official measurement is
attributable. Prefill carries 25 % of the score weight
(`score = decode_speedup^0.75 * prefill_speedup^0.25`), and at our operating
point of ~96 ms candidate prefill, one millisecond of prefill is worth about
0.26 % of score. Our promoted best is 2.58883 and the leader is 2.61650, a gap
of 1.05 %.

## 2. Environment

Development host is an Apple M4 Pro, 20 GPU cores, 48 GiB unified memory,
macOS 26.5.2. This host reports Apple GPU generation 16. The `_nax` kernel
family used by the ranked M5 requires macOS >= 26.2 **and** GPU generation >= 17
(`device.cpp:913-930`), so this host never selects `_nax`. That single fact
shapes the whole arm: any change confined to the `_nax` path is
**unmeasurable locally** and can only be measured by an official receipt.
Local runs remain valid for correctness, dispatch censuses, and decode timing.

Build path is `./benchmark.sh --local-iterate` / `--local-submit`, which use the
`.build-worker` scratch directory. Because `matmul.cpp` sits inside the
`VendoredMetalFingerprint` subtree, `./setup.sh` was re-run after the edit to
regenerate the metallib and the worker binary.

## 3. Prior work in this arm and what receipt 1 measured

Receipt 1 (`b3b6457f`, commit `a4d7450`, 2026-08-09T11:24Z) carried two
prefill-only mechanisms:

- **P2** — replace the three separate BF16 GEMMs per attention layer
  (Wq: M=512, N=8192, K=2048; Wk and Wv: N=1024) with one row-concatenated
  `[Wq;Wk;Wv]` weight bank of N=10240, built once outside the timed window and
  gated on sequence length > 1 so decode never touches it.
- **P2b** — the four fused prefill QK-norm/RoPE custom kernels declare
  `ensureRowContiguous = true`, so feeding them non-contiguous column slices of
  that bank forced 78 general strided copies per request. P2b adds an
  `int32[4]` layout descriptor letting those kernels address the slices
  directly, removing the copies.

Receipt 1 passed every gate: `passed_correctness = true`, `max_abs_diff = 0`,
1344 checked steps, both speedup floors, semantic GPQA 9/9, TTFT 9/9,
`peak_ram_gb = 21`, empty error string. Its `rejectionReason` was
`score did not improve current best` — a pure ranking rejection with no gate
failure. Reported score 2.55811, with baseline prefill 187.976 ms, candidate
prefill 96.797 ms, baseline decode 13.8089 ms/token, candidate decode
4.92433 ms/token.

## 4. The instrument correction — the most important finding so far

The CLI's `submissions` table truncates the metrics column at about 75
characters, which hides every per-axis number. I wrote
`research/tanjiro_r97_fetch_submission.py`, which reads the local
`~/.config/mlxfast/config.json` and GETs `/api/submissions/<id>` and
`/api/benchmarks/<id>/submissions`, exposing the `officialMetrics` payload.
That made the following visible.

The **same-session baseline** prefill is wildly unstable across 15
contemporaneous scored receipts: 186.821 to 196.395 ms, a spread of 9.6 ms or
about 5 %. Since `prefill_speedup = baseline / candidate`, the published
prefill speedup and hence the published score are dominated by which baseline
draw a session happened to get, not by the candidate. Comparing score to score
across sessions is therefore close to useless at the sub-percent scale we work
at.

The **candidate** prefill axis, by contrast, is quiet. Across the 13
contemporaneous scored receipts on this account between the promoted frontier
and R1, candidate prefill was 96.278, 96.055, 96.070, 96.120, 96.198, 96.193,
96.328, 96.316, 95.870, 96.253, 96.184, 95.953, 96.236 ms — mean **96.158**,
sd **0.139**, n = 13. That is the instrument this arm now uses.

## 5. Reading receipt 1 against that instrument

R1's candidate prefill of 96.797 ms sits **+0.639 ms** above the population
mean. Because R1 is a single new observation rather than a mean, the correct
denominator is the prediction standard error `s*sqrt(1 + 1/n) = 0.1441`, giving
prediction-t = **4.43** on 12 dof and a 95 % effect CI of
**[+0.325, +0.953] ms**. The 95 % prediction interval for one healthy new
receipt is [95.844, 96.472] ms, and R1 is outside it. A distribution-free
reading that assumes nothing about the population shape — R1 being the largest
of 14 exchangeable draws — bounds the p-value only at 1/14 = 0.071. I report
the effect as **+0.64 ms [+0.33, +0.95], prediction-t 4.43, distribution-free
p <= 0.07**, and I have withdrawn an earlier, wrong "+4.6 sigma" phrasing that
divided by the population sd instead of the prediction sd.

Three audits back this up, in `research/tanjiro_r97_control_audit.py`:

- **Drift.** R1 ran 10.4 h after the first control. OLS of candidate prefill on
  time gives slope -0.0059 ms/h (se 0.0218, t = -0.27, 11 dof): no drift, and
  the sign points the wrong way. Drift-adjusted, R1 still reads t = +3.18.
- **Prefill-code homogeneity.** I cannot read other students' branches, so this
  is tested by signature. Four of the 13 controls have visibly broken decode
  (5.08-6.78 ms/token against a 4.914 frontier). Their prefill nonetheless sits
  in the same tight cluster: decode-damaged mean 96.087, decode-healthy mean
  96.189, both far below R1. Arms that demonstrably changed decode left prefill
  undisturbed, which is what one expects if the prefill path is untouched.
- **Bookkeeping.** The 15 scored receipts decompose as 13 controls + `25b0b722`
  + R1. `25b0b722` is excluded because it predates the promoted frontier and
  sits 1.6 ms — 11 sd — off the cluster, i.e. a different prefill code base.

Candidate decode for R1 was 4.9243 ms/token against a healthy-subset population
of 4.9140 +/- 0.0176 (n = 10), i.e. +0.59 prediction-sd, statistically
unchanged. The mechanism stayed prefill-only exactly as designed. That is a
genuine positive: the gating worked.

Correct score attribution: at the population prefill, the same session would
have scored `2.804213^0.75 * (187.976/96.158)^0.25 = 2.56238` against the
observed 2.55811, so the regression cost **-0.166 %**, not the -1.19 % that a
naive score-to-score comparison implies. The remainder of the gap to our
promoted best is baseline-draw noise.

## 6. Course correction

The preregistered read-out table said `> +0.3 ms` means an unmodelled
regression: revert and report negative. That bar is crossed under both the
parametric and the distribution-free reading, so the decision does not depend
on the statistical choice. **P2 and P2b are reverted** by checking out the base
version of the single Swift file that held them.

Why the fusion lost time on M5, despite provably identical tile geometry
(`bm=64, bn=128, bk=256, wm=2, wn=4, swizzle_log=2`) and an identical total
threadgroup count of 640 either way, is not settled and no receipt will be spent
settling it. The leading hypotheses are (a) an SLC capacity crossing, since the
fused 41.94 MB bank exceeds the 33.55 MB Wq under two-band swizzle streaming and
forces a band-2 refetch, which fits the observed magnitude, and (b) loss of
inter-dispatch overlap, since the backend uses one encoder per command buffer
with `MTL::DispatchTypeConcurrent` and never hazard-tracks read-after-read
(`device.cpp:547-548`), leaving the three baseline GEMMs free to overlap. The
large local M4 gain (-11.2 ms, 4/4 paired ABBA) was already known not to
transfer, because on M4 the Wk/Wv projections route to a split-K path that P2
eliminates, while on M5 they stay on the regular path.

## 7. What this candidate contains

The diff against the base is now **6 lines in one file**,
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp:302-311`, inside
`steel_matmul_regular_axpby_nax`:

```cpp
int swizzle_log = tm <= 3 ? 0 : 1;
if (devc == 's' || devc == 'c' || devc == 'd') {
  swizzle_log = (tm >= 8 && (tm % 8) == 0) ? 3 : 2;
}
```

**P4** raises the grid swizzle depth from 2 to 3 when the row-tile count is a
multiple of 8, so all 8 row-tiles sharing one B column slab are dispatched
adjacently instead of split across two grid rows, letting that slab be fetched
once rather than twice. It changes dispatch *order* only: tile geometry,
threadgroup count, accumulation order and every arithmetic operation are
untouched, so bit-exactness is a property of the construction rather than
something to be hoped for. On M5 every regular-`_nax` prefill class has
`tiles_m = 8` — Wq N=8192, Wk/Wv N=1024, dense-0 gate/up N=8192, layer-39
`[K;V]` N=2048 — so with P2 reverted P4 now applies to more GEMMs than it would
have alongside P2.

Registered prediction: **-0.4 ms**, 80 % interval `[-1.5, +0.2]`, with **null
called as the single most likely outcome**. The honest reason for that
pessimism is arithmetic intensity: the Wq GEMM has AI ~ 221 FLOP/B against a
machine balance of roughly 55-125, so it is compute-bound and halved B traffic
largely hides under compute. A real -0.4 ms would have to arrive through
second-order cache-residency or DVFS effects.

This receipt does double duty as the control confirming the revert restored
base prefill: a healthy result should land inside [95.844, 96.472] ms. That
confound — "revert restored base" versus "P4 exactly cancels a revert error" —
is real in principle but not in practice, since the revert is a literal
`git checkout` of the base file and `git diff` against the base now reports
only the 6 lines above.

## 8. Exact commands

```bash
git checkout b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e -- \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
./setup.sh
./benchmark.sh --local-submit
python3 research/tanjiro_r97_control_audit.py
senpai/check-editable-budget.sh b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e
mlxfast submit --model "senpai" --note-file research/tanjiro-r97-r2-note.md
```

## 9. Local verification and its limits

`./benchmark.sh --local-submit` on this exact tree: `passed = true`,
`passed_correctness = true`, `max_abs_diff = 0`, `checked_steps = 1025`,
`peak_ram_gb = 21`, decode floor passed at 1.549x.

The local prefill floor line reads `false` (0.327x) on this host. This is a
known host artifact, not a property of the candidate: `--local-submit` compares
against a pinned M5-class constant of 0.000368 s/token, and the byte-identical
base misses it by the same margin on this machine. The same disclosure was made
for receipt 1.

Editable budget after this change: current 2,899,882 of 3,000,000 bytes,
headroom 100,118, growth 406 of 262,144, 141 files — all inside contract.

## 10. Caveats

P4 is not measurable on the development host at all, because generation-16
hardware never selects `_nax`; the local run is purely a correctness and
regression check. The control population is drawn from different candidates
rather than byte-identical reruns, so its sd of 0.139 ms is an *upper* bound on
true measurement noise, which makes the R1 test conservative but leaves
prefill-code homogeneity as the weakest link in the chain. The mechanism behind
R1's regression remains a hypothesis.

## 11. Learning and next steps

The transferable lesson is methodological: on this benchmark the published
score is a noisy instrument because the same-session baseline swings ~5 %, and
the candidate per-axis millisecond is roughly 35x quieter. Any sub-percent
mechanism should be judged on the candidate axis against a contemporaneous
population, never on score deltas between sessions.

If R2 lands inside the prediction interval, the prefill dispatch-count and
tile-geometry family is exhausted for this arm and I will report the negative
and recommend the decode axis, where 75 % of the score weight sits and where
closing the gap to the leader needs -0.069 ms/token against a -4.0 ms prefill
equivalent.

Preregistration and read-out bars, written before each run, are in
`research/tanjiro-r97-prefill-tg-preregistration.md`: §14 holds the R1 read-out
and the R2 bars, §15 the control audit.

---

## Erratum (added after submission `048674e9`, not part of the uploaded note)

The text above, as uploaded with R2, prices R1's `+0.639 ms` prefill regression
at **-0.166 %**. That is wrong and is corrected to **-0.242 %**.

The uploaded counterfactual held `decode_speedup` fixed while moving prefill.
It cannot be: the 512-token seed forward runs inside the decode timer
(`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift`, timer opened at
line 966, `beginDecode(seedTokens:)` at 968, closed at 1010, with the harness
itself printing `includes_seed_prefill=true` at 967). Prefill is therefore paid
twice: once on its own axis and again as `4·CP` inside every decode step.

Re-priced from R1's own JSON: `CP = 189.057 us/token`, `CD = 4924.33 us/step`,
`f = 4·CP/CD = 0.153570`, forward exponent `0.25 + 0.75f = 0.365178`, so one
millisecond of prefill is worth `0.3773 %`. The exact counterfactual that also
propagates the mandatory `+4.99 us/step` out of decode gives `2.564298` against
the observed `2.558109`, i.e. **-0.242 %**.

This makes the reported regression larger, so it strictly reinforces the
NO-GO already recorded in the note. No measurement and no GO/NO-GO bar changes;
the bars are stated in milliseconds. Full derivation in Amendment 7 (section 16)
of `research/tanjiro-r97-prefill-tg-preregistration.md`.

