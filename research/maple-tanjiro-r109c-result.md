# R109-C result — routed gate/up extract-round elimination is REFUTED

Student: maple-tanjiro. PR #683. `assignment_id maple-r109-c-gateup-extract-round-elimination`,
`revision_id r109-c-rev1`. Base `1a6761bf46c282fcabd0577b618f0c1206757e6c`.
Host: M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s` (gen 16, pre-NAX), macOS 26.5.2.

**Verdict: FAILED. Banked negative `N-INDS-DEPENDENCY-BARRIER`.**

The hypothesis was that the routed gate/up QMV kernel recomputes the top-8
expert order statistic every dispatch (`laguna_router_top8_extract_round`), that
the decode router already publishes that exact order statistic as `inds`, and
that passing `inds` in would remove the recompute for free.

Two of the three claims are true. **The recompute removal is real** (−49.6
us/step measured end to end). **The order statistics are provably identical**
(proof in `research/maple-tanjiro-r109c-stage0.md`). But the third claim — that
consuming `inds` is free — is false: *binding* the extra input costs
**+102.0 us/step even when the kernel never reads it**, because MLX must insert
an encoder-global memory barrier for the new RAW hazard. The candidate is a
**+52.4 us/step regression**.

---

## 1. Headline numbers

End-to-end paired ABBA. `research/maple-frieren-r103a-abba.sh`, 3-arm rotate
design, `STEPS=250`, `REPS=6` (1 warm-up rep discarded → 5 usable), 36 slots,
1551.9 s wall. Estimator = per-slot median us/step; drift-cancelled contrasts.

Per-arm level (median us/step, across-rep sd):

| arm | `DARKBLOOM_GATEUP_INDS` | median us/step | sd |
| --- | --- | --- | --- |
| base | 0 (shipped) | **8263.0** | 5.25 |
| p1 | 1 (bind `indices`, never read) | **8365.0** | 12.81 |
| p2 | 2 (read `indices`, skip extract rounds) | **8315.4** | 8.90 |

Drift-cancelled contrasts:

| contrast | K | mean us/step | 95% hw | lo | hi | sign |
| --- | --- | --- | --- | --- | --- | --- |
| base→p1 | 5 | **+102.00** | 17.19 | +84.80 | +119.19 | 5/0 |
| base→p2 (ranked claim) | 5 | **+52.38** | 8.91 | +43.47 | +61.29 | 5/0 |
| p1→p2 | 5 | **−49.62** | 22.05 | −71.67 | −27.57 | 0/5 |

`base→p2` is the ranked contrast: **+52.38 us/step, a loss**, sign-consistent in
5 of 5 reps, and its 95% interval excludes zero with margin.

## 2. Mechanism, fully attributed

The three-arm design was chosen precisely so that the effect could be split, and
it separates cleanly:

* **`p1→p2` = −49.62 us/step** is the extract-round elimination in isolation of
  the plumbing. The isolated single-kernel probe predicted
  −1.505 us/dispatch × 40 layers = **−60.2 us/step**; measurement recovers 82%
  of that. So **busy-time additivity holds** for this kernel — it is
  execution-dominated and fully exposed on the critical path (see
  `research/maple-tanjiro-r109d-stage0.md` §4.3b-ii: the routed gate/up family is
  0.00% nested).
* **`base→p1` = +102.00 us/step = +2.55 us/layer** is the price of the
  *dependency edge alone*. Arm p1 compiles the identical kernel body as base and
  discards the new buffer; the only difference is that `indices` appears in the
  MLX `inputs` list. `inds` is produced by `laguna_router_top8_ordinal` in the
  same command encoder, so:
  - `set_input_array` (`Vendor/mlx-swift/.../metal/device.cpp:315-328`) records a
    RAW hazard against that output;
  - `maybeInsertBarrier` (`device.cpp:363-373`), called from
    `dispatch_threadgroups` (`:378-384`), emits
    `memoryBarrier(BarrierScopeBuffers)` — which is **encoder-global**, not
    pairwise, on the single `MTLDispatchTypeConcurrent` encoder
    (`device.cpp:545-549`);
  - every dispatch already in flight in that encoder is therefore serialized at
    that point, 40 times per step.

So the mechanism that would pay for the win is the same mechanism that destroys
it. `+102.00 − 49.62 = +52.38`, consistent with the directly measured
`base→p2`.

## 3. Correctness

Bit-exactness was a hard precondition and it passed everywhere:

* Harness token-stream check: `distinct token-stream checksums: 1 (must be 1)`,
  0 divergences in all 36 slots.
* Rule-75 tree digest: `PASS(rule 75): Sources+Vendor unchanged`,
  `digest_after=01755283d415f82eb84de9b4e4a4e6636caf1ab261808738359c8d020923bcbc`
  (all three arms are the *same* binary; they differ only by env var, which is
  why `ASSERT_SAME=s:s` is set and `ASSERT_DIFFER` is disabled with a single
  space).
* Isolated probe gate before implementation: 0 of 65536 differing bytes at
  TG=1024 and TG=2048.
* Order-statistic equality proof (not just sampling): the decode `inds` producer
  performs a full 256-element bitonic sort under the strict total order
  `laguna_router_ordinal_before` (LRM:9431-9442); the gate/up prologue
  (`lagunaRouterTop8PrecomputedPrelude` LRM:7879-7890 +
  `laguna_router_top8_extract_round` LRM:7846-7875) runs masked-argmin rounds
  over identically constructed keys. Same order statistic **including ties**.

Because the candidate lost, `research/run_upstream_equivalence.sh` was not spent
on it; the token-stream identity above plus the identical-binary digest are
sufficient for a negative result.

## 4. Honest caveats

I am reporting these because they weaken, but do not overturn, the conclusion.

1. **Harness guardrail N-2 fires**: "drift comparable to a contrast: YES". Rep-to-rep
   drift on this host is of the same order as the contrasts being measured. The
   rotate design cancels linear drift, and the 5/0 sign consistency is the main
   defence.
2. **Precision check MISS**: worst half-width 22.05 us/step versus the harness
   target `< 8.00`. `base→p2` (hw 8.91) is close to target; `p1→p2` (hw 22.05) is
   the loose one, so the *decomposition* is noisier than the *verdict*.
3. **Largest identical-code null bound** on this instrument (rule-79 pooled
   sep-3): `[−14.25, +32.09]`. `base→p1` (+102.0) clears it by 3×;
   `base→p2` (+52.4) clears it with less margin. `p1→p2` (−49.6) clears the
   lower edge.
4. **Joint Bonferroni over m=3 contrasts**: no pair is resolvable at
   > 26.9 us/step M4 (≈16.8 M5-equivalent under the R1 transfer). All three
   contrasts exceed that.
5. **TOST against the campaign's 32.4 M4-equivalent "missing microseconds"
   margin fails for every contrast**, i.e. I cannot claim any contrast is
   *equivalent to zero*; I claim `base→p2` is positive, which is the opposite
   direction and is supported.
6. **M5 transfer.** M5-equivalent half-width for `base→p2` under four transfer
   models: fixed 8.9 / R1 5.5 / proportional 4.5 / bandwidth 3.9. Sign is robust
   under all four. This is a decode-path change; no `_nax` prefill kernel is
   touched, so the usual M4 prefill caveat does not apply.
7. **Estimator agreement.** Median and the official analog (`mean_first128`)
   agree in sign and roughly in magnitude for all three contrasts:
   +102.00/+113.37, +52.38/+54.02, −49.62/−59.36.
8. **Step-0 contrasts** (+2069.6 / +129.1 / −1940.5 us) are much larger than the
   steady-state ones and are excluded from the estimator, as designed; they show
   the barrier cost is worst on the first, coldest step.
9. Diagnostics: step0 9415.12 / 11484.77 / 9544.22; `mean_first128` 8259.35 /
   8372.72 / 8313.37; `tail_excess` 4.34 / 2.16 / 5.31; `spike_count`
   0 / 0.40 / 0.40. QC rejected 0 slots and voided 0 reps.

## 5. What this means for other work

* **For fern's B×C composition:** the R109-C mechanism **cannot be composed**.
  Any consumer that imports `inds` from the router pays the encoder-global
  barrier. If a future arm wants the extract-round saving, it must obtain the
  order statistic *without creating a cross-kernel dependency* — e.g. by fusing
  the ordinal producer into the consumer, or by having the consumer compute it
  once into threadgroup memory and reuse it across its own rounds.
* **Reusable positive finding:** on the shipped decode path `inds` carries a
  full-slot **ORDER** dependency, not just a set dependency. Its 8 winners in
  index order are `[39,88,99,110,114,184,216,239]` and in slot order
  `[184,239,110,88,99,216,39,114]`; consumers that assume index order will be
  wrong. Neither nezuko nor I may change the `inds`/`weights` layout
  unilaterally.
* **Second banked negative from this arm's stage 0**,
  `N-SG0-BROADCAST-NULL-AT-OCCUPANCY`: moving the gate/up prologue into
  simdgroup 0 plus a threadgroup-memory broadcast is worth −2.850 us (−23.2%) at
  TG=512 but **−0.017 us / −0.045% / t = −0.62 (NULL)** at the shipped TG=2048.
  Prologue-cost optimisations measured at small TG do not transfer to this
  kernel's shipped geometry.
* **Corroboration for the §6333 retraction** (see
  `research/maple-tanjiro-r109d-stage0.md` §4.3c): if decode dispatches were
  already fully serialized, adding one dependency edge could not cost
  +102 us/step. They are not.

## 6. Preregistered kill, and why it fired

The stage-0 gate preregistered the barrier as the single ranked risk: *"the
ranked risk is the one MLX barrier that the extra `indices` input inserts in
front of the 38 us kernel."* The p1 arm existed only to price that risk. It came
in at +102 us/step against a −60 us/step upside, so the arm is killed by its own
preregistered criterion rather than by post-hoc reinterpretation.

## 7. Reproduction

```bash
# implementation is commit b2431493 on maple-tanjiro/r109-gateup-extract-round-elimination
# snapshot dir must contain BOTH mlxfast-runtime-worker and mlx.metallib
ls /tmp/maple-r109c-snap/s/          # worker sha256 ab3a6cc6a5bd0c0e...

SNAP=/tmp/maple-r109c-snap OUT=/tmp/maple-r109c/rung1 REPS=6 WARMUP_REPS=1 \
  STEPS=250 DESIGN=rotate ASSERT_DIFFER=" " ASSERT_SAME=s:s \
  ARMS="base:s p1:s:DARKBLOOM_GATEUP_INDS=1 p2:s:DARKBLOOM_GATEUP_INDS=2" \
  research/maple-frieren-r103a-abba.sh

python3 research/maple-frieren-r103a-analyze-multi.py /tmp/maple-r109c/rung1
# -> /tmp/maple-r109c/rung1/analysis-multi.json

# isolated single-kernel ladder (seconds, no model load)
xcrun swiftc -O research/maple_tanjiro_r109c_gateup_probe.swift -o /tmp/tanjirogu
/tmp/tanjirogu
```

Runtime: 1551.9 s for the ABBA (job `a6418230-0d15-44b7-9c9e-a94bb4a73e15`,
exit 0), plus seconds for each isolated probe. No W&B runs: this is Metal kernel
timing, not training, and the harness publishes to files.

## 8. Suggested follow-ups (not implemented)

1. **Price the barrier once, campaign-wide.** `base→p1` is a clean,
   reusable measurement of "one added RAW edge in the decode encoder" =
   +2.55 us/layer on this host. A tiny generic probe that varies the *number* of
   added edges would tell every future arm whether a proposed input is
   affordable before anyone implements it. This is probably the highest-value
   thing in this PR.
2. **Fuse the ordinal producer into the gate/up kernel** instead of passing its
   output. That removes the recompute *and* the edge, and it is the only version
   of R109-C that can win. It is a much bigger change (the producer does a
   256-element bitonic sort) and needs its own assignment.
3. **Re-audit any arm whose price came from busy-time additivity** against
   `research/maple-tanjiro-r109d-overlap.py --all`. Additivity is sound for most
   decode kernels but is off by 28× for `laguna_gate_sp`.
