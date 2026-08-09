# r96-b Stage 1 — certified lossless low-precision router screen: **NO-GO**

- Student / PR: `maple-frieren` / #512
- Hypothesis and target cost: a low-precision screen over the BF16 MoE router
  plane (`[256, 2048]` per sparse layer, 39 layers) can certify the top-8
  selection for most decode steps and refetch only ambiguous rows, cutting the
  40.9 MB/step router traffic enough to buy 0.31–0.47 % score at the realised
  price 0.015224 % per MB/step.
- Decision: **dead hypothesis** for the deterministic-certificate family.
- `BASE_SHA` / candidate commit: `43036cd39dd3c795b117b099f0fe52767fbedbca` /
  see PR head.
- Submitted candidate files: **none**. `Sources/` on this branch is
  byte-identical to the assignment base (`git diff ae62e87 -- Sources/ Vendor/`
  is empty). Stage 1 was pre-registered as a measurement stage with no kernel.
- Supporting files (research only, not submitted):
  `research/frieren-r96b-preregistration.md`,
  `research/frieren-r96b-router-dump.patch`,
  `research/frieren_r96b_screen.py`,
  `research/frieren_r96b_wandb.py`,
  `research/frieren-r96b-stage1-results.json`.
- Official submission `--model` value: not applicable, nothing to submit.
- Assignment-scope preflight: passed at assignment time; the final surface is
  empty, so editable growth is **0 bytes** against the 104,610-byte headroom.
- Scored-path reachability evidence: the instrument was placed inside the fused
  decode branch that feeds the scored call site
  (`LagunaRuntimeLayers.swift:2345-2362`) and produced 201 records for each of
  the 39 sparse layers per 200-step decode run, confirming the measured tensors
  are the ones the scored path consumes. The second, terminal-prefill-row call
  site (`:2441-2459`) was deliberately left uninstrumented.

## Verdict against the pre-registered bar

The bar was fixed in `research/frieren-r96b-preregistration.md` (commit
`682e100`) before any of this data existed: a config passes only if net traffic
is **≤ 629,146 B** per layer-step (60 % of the 1,048,576 B BF16 plane) **and**
ambiguous experts `A` satisfy `p99 ≤ 16` **and** `max ≤ 64`.

**No pre-registered config passes either gate.** Of 40 pre-registered
configurations (`{pot, affine} × b ∈ {8,6,5,4,3} × G ∈ {32,64,128,2048}`):

| config | net B/layer-step | net % | save MB/step | A mean | A p99 | A max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| affine b=8 G=64 (best bytes) | 752,597 | 71.8 % | 11.54 | 15.8 | 45 | 108 |
| affine b=8 G=32 (best ambiguity) | 760,141 | 72.5 % | 11.23 | 12.8 | 37 | 81 |
| pot b=8 G=32 | 861,257 | 82.1 % | 7.33 | 31.0 | 69 | 155 |
| affine b=6 G=32 | 1,338,229 | 127.6 % | −11.28 | 99.2 | 149 | 208 |
| affine b=4 G=32 | 2,326,754 | 221.9 % | −49.86 | 236.0 | 248 | 248 |

Every `b ≤ 6` configuration is **worse than the BF16 baseline**: the certificate
leaves ~99–248 of the 256 experts ambiguous, so the screen refetches nearly the
whole plane at 4 KB per row *on top of* the screen plane it already read.

The minimum over all 64 configurations tested (including post-hoc diagnostic
widths) is **71.8 %** of baseline. The 60 % bar is never approached.

## Which pre-declared failure mode fired

The preregistration named two candidate failure modes. The data cleanly
selects one and **excludes** the other.

- *Mode A — "ρ, the BF16 output-rounding term, dominates the interval":*
  **excluded.** `rho_share ≤ 0.008` at every pre-registered width (≤ 0.18 even
  at 14 bits). Even forcing ρ → 0 leaves every `b ≤ 6` config above 100 % net.
- *Mode B — "margins routinely fall below 2ε":* **confirmed.** The median ratio
  of certified interval width to the top-8/9 decision margin is 13.9 at the
  best pre-registered config, 12–35 across `b = 8`, and 47–206 for `b ≤ 6`.

## Root cause: provability-limited, not precision-limited

Two diagnostics added after the grid pass make the mechanism unambiguous:

- `real_half_over_gap_median = 0.268` at affine b=8 G=64. The error the 8-bit
  screen **actually makes** is ~3.7× *smaller* than the decision margin. An
  oracle-tight certificate at 8 bits would certify the large majority of
  decisions and the hypothesis would work.
- `bound_looseness_median = 41.7×` at the same config (38–59× across `b = 8`).
  The deterministic certificate over-estimates the realised error by that
  factor.

That factor is not tuning slack — it is √2048 ≈ 45.3. The binding term is
`E2 = ‖x‖₂ · ‖Δw_i‖₂` (Cauchy–Schwarz), while the realised error of a
2048-term dot product with incoherent rounding residuals concentrates at
`≈ ‖x‖₂‖Δw_i‖₂ / √2048`. The alternative term
`E1 = Σ_g (Σ_{j∈g} |x_j|) · max_{j∈g}|Δw_ij|` never helps:
`e1_wins_frac ≈ 0` at every configuration, so E2 governs throughout and the
√n penalty is intrinsic to this bound family.

Closing a 45× deterministic-bound gap is not a parameter-search problem, and a
probabilistic bound is not admissible: the correctness gate requires every
checked greedy token to match, so the screen must be certified for **all**
steps, not 99.9 % of them.

## Independent structural blocker: 6.8 % of routing decisions are exact ties

While measuring the margin distribution I found a property of the routing
problem that constrains *any* interval-based screen, independent of precision:

- The router correction bias `e_score_correction_bias` is **identically zero in
  all 39 sparse layers** of this checkpoint.
- Selection therefore ranks on `sigmoid(L) + 0`, which is order-equivalent to
  the raw **BF16** logit `L`.
- BF16 carries only ~256 distinct values per binade while 256 experts are
  ranked, so logit collisions are frequent. Measured over 7,839 decode routing
  decisions: **6.77 % have an exact tie at the top-8/9 boundary**
  (margin p01 = p05 = 0, p10 = 8.2e−4, median 4.8e−3).

No interval certificate can ever separate a tie, so ≥1 ambiguous expert is
structurally unavoidable in ~7 % of decisions, and any screen must additionally
reproduce the reference tie-break bit-exactly.

**The current runtime is correct here** and this is not a latent bug: ties are
broken deterministically by ascending expert index in the shared comparator
(`LagunaRuntimeLayers.swift:604-612`), and both selections per decode layer —
the tournament gate kernel and the re-derivation inside
`lagunaRoutedSwiGLUQMVPackedTop8` — use that same comparator. The finding is a
constraint on *future* work: any change to router ranking (a different sort,
reduction order, or vectorised top-k) that alters tie-break order will silently
change expert selection on ~7 % of decisions and surface as rare token drift.

## Byte frontier: the two feasible sets do not intersect

- **Ambiguity-feasible** (`A p99 ≤ 16`, `max ≤ 64`) requires `b ≥ 10`. Best:
  affine b=10 G=2048 (p99 16, max 27) at 72.7 % net, 11.17 MB/step; pot b=10
  G=32 (p99 13, max 22) at 73.4 %, 10.86 MB/step.
- **Byte-feasible** (≤ 60 % net) is reached by **no** configuration at the 4 KB
  refetch price; the global minimum is 71.8 %.

The best point in either set saves 11.54 MB/step. The pre-registered 60 % bar
corresponds to 20.4 MB/step, and the assignment's target band of 0.31–0.47 %
score at the realised price 0.015224 % per MB/step corresponds to 20.4–30.9
MB/step. At that price the best configuration is worth **0.176 %** — short of
the band by 1.8–2.7×.

*Second accounting, for honesty.* An idealised perfectly-bandwidth-bound view
gives a larger number: 11.54 MB against the ~1.58 GB/step decode budget is a
0.73 % byte reduction, worth ≈0.55 % score at weight 0.75. I do not lead with
this because the target band and the price come from the same assignment
contract and are internally consistent, whereas the realised price is
calibrated on promoted wins and already absorbs kernel overhead. But even
taking the idealised figure, it is delivered only by affine b=8 G=64, which
fails the ambiguity gate by 3× (p99 45 vs bar 16, max 108 vs bar 64); the best
ambiguity-passing config saves 11.17 MB/step and needs `b = 10`, which was not
pre-registered. Neither accounting produces a fundable Stage 2.

Worse, under this host's byte-time model (`t = 3.97 µs + bytes / 266.3 GB/s`)
the best configuration saves **43.3 µs/step** (308.4 → 265.1 µs/step across the
39 sparse layers) against a measured **8,237 µs/step** decode — a 0.53 % step
saving, and the whole baseline router plane is only 3.7 % of the step. 43.3 µs
is below the ~80 µs/step detection bar, so even ignoring its ambiguity failure
and all kernel overhead, the winning configuration could not be reliably timed
on this host.

## Optimistic residual-plane sensitivity (post-hoc, unproven)

If a candidate could refetch only the `(16 − b)` bits the screen plane does not
already carry, instead of a full 4 KB BF16 row:

- best net falls to 57.8 % (affine b=8 G=64, 17.25 MB/step ≈ 0.263 % score) —
  but that config fails ambiguity by 3×;
- the best config that *also* passes ambiguity is pot b=10 G=32 at 65.9 %
  (13.96 MB/step ≈ 0.213 %), still above the 60 % bar and still below the
  target band.

**Caveat: this row is an upper bound on an unbuilt representation, not a
result.** It assumes an exact bit split at `b` bits exists. It does not for
either scheme tested — `pot` uses a per-group e8m0 scale and `affine` a
per-group min/scale, and neither is a bit-slice of BF16. Naive BF16 bit-slicing
measured ~137× worse error at equal bits, and an exact fixed-point split needs
~15–17 bits because of intra-group exponent spread. So even the optimistic
frontier does not clear the bar.

## Two bound tightenings, declared

Both were applied uniformly to **every** configuration including the
pre-registered ones, before the verdict was read. Both are strict tightenings,
so they can only ever move a config toward GO:

1. **η (FP32 accumulation).** Now `2^-17 · (|x| @ max(|w|, |ŵ|)ᵀ)`,
   over-bounding `2 · 21 · 2^-24` for the chunked accumulation of both the
   reference and the screen kernel.
2. **ρ (output rounding).** Replaced the pre-registered `± ulp/2` with the
   exact monotone BF16 interval: because BF16 rounding is monotone, the
   reference logit lies in
   `[bf16(nextafter(l̂ − err, −∞)), bf16(nextafter(l̂ + err, +∞))]`.

Neither changed the verdict.

## Evidence

- Host, memory profile, toolchain, thermal policy: Apple **M4 Pro**, 48 GiB
  unified memory (low-memory startup profile, < 64 GiB), macOS 26.5.2. No
  `_nax` kernels are selected on this host. No thermal gate is involved because
  no ranked timing was taken.
- Exact commands:
  ```bash
  # build the scored worker
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
  # capture router activations (instrument applied, then reverted)
  DARKBLOOM_R96B_DUMP_DIR=/tmp/r96b python3 research/decode_probe.py --steps 200
  # grid analysis and go/no-go decision
  python3 research/frieren_r96b_screen.py --dir /tmp/r96b --records 200 \
    --out research/frieren-r96b-stage1-results.json
  ```
- Sample size: 39 sparse layers × 200 decode records = **7,839 routing
  decisions**, 64 configurations each.
- Pipeline validation (pre-registered gate, `frac ≥ 0.999` and `≤ 1` ulp):
  **1,996,790 / 1,996,800** dumped BF16 logits reproduced bit-exactly offline
  (**99.9995 %**), max bit-pattern gap **1 ulp**. The offline model of the
  fused kernel is faithful, so the grid numbers are trustworthy.
- Correctness and serial-protocol verdict: the instrumented run produced **0
  divergent tokens** against the reference, confirming the instrument was
  observational. No screen kernel was built, so there is no candidate to gate.
  Nothing in Stage 1 touches the serial non-speculative rules.
- Peak RAM / artifacts: 157 MB of activation dumps in `/tmp/r96b` (78 files),
  not committed.

| Metric | Baseline | Candidate (best of 64) | Ratio / delta |
| --- | ---: | ---: | ---: |
| router bytes / layer-step | 1,048,576 | 752,597 | 0.718× |
| router µs / step (modelled, 39 layers) | 308.4 | 265.1 | −43.3 µs |
| ambiguous experts p99 | 0 | 45 | bar ≤ 16 |
| top-8/9 margin p01 | — | 0.0 (exact tie) | — |
| projected score | — | 0.176 % | target 0.31–0.47 % |

No paired benchmark timing was taken: Stage 1 carries no kernel, so there is
nothing to time. `router_us_per_step` is **modelled**, not measured.

## Conclusion

- **What happened and why:** the screen is provability-limited, not
  precision-limited. At 8 bits the realised error is already 3.7× below the
  decision margin, but every cheap deterministic certificate over a 2048-term
  dot product is ~√2048 ≈ 45× looser than the realised error, and the measured
  looseness is 41.7×. The certificate, not the arithmetic, leaves 16–45 experts
  ambiguous, which forces refetching and pushes net traffic back above the bar.
- **Evidence for or against the mechanism:** the two competing bound terms were
  separated (`e1_wins_frac ≈ 0`, so E2/Cauchy–Schwarz governs); the rounding
  term was excluded (`rho_share ≤ 0.008`); and the oracle-tight counterfactual
  was measured (`real/gap = 0.268`). These three together isolate bound
  looseness as the single cause.
- **Uncertainty and M5 transfer risk:** low for the verdict. The result is an
  arithmetic/statistical property of the checkpoint's router weights and decode
  activations, not a kernel-timing property, so it does not depend on M4 vs M5
  kernel selection. The byte accounting is hardware-independent; only the
  µs conversion is M4-specific, and it is not load-bearing for the NO-GO.
- **Smallest useful next action:** none in this direction. Do not fund Stage 2
  and do not fund a re-tuned variant of this bound family — the gap is 45×, not
  10–20 %.
- **Recommendation: close.**

## Suggested follow-ups (not implemented)

1. **Redundant router sigmoids.** With bias identically zero in this
   checkpoint, ranking is order-equivalent to the raw BF16 logit, yet sigmoid
   is evaluated over all 256 experts **twice** per decode layer — in the fused
   producer (`LagunaRuntimeModel.swift:963-965`) and again in the selector
   (`LagunaRuntimeLayers.swift:1180-1183`) — where only the 8 winners' values
   are needed as gate weights. An arm that computes only the 8 already exists
   and is off by default (`DARKBLOOM_ROUTER_ORDINAL_SCORE_TABLE=0`,
   `LagunaRuntimeLayers.swift:512-516`, gated at `655-658`). This is ALU, not
   bandwidth, on a bandwidth-bound decode, so I would expect it to be small —
   but it is nearly free to measure given the arm exists. Note the zero bias is
   a property of *this checkpoint*; the runtime should keep reading the tensor.
2. **Tie-break as a correctness invariant.** Given 6.8 % exact ties, it is
   worth adding an explicit regression test pinning ascending-index tie-break
   across both selection paths, so a future top-k rewrite cannot silently
   change routing.
3. **Where the router bytes could still go.** The router plane is only 2.6 % of
   the decode byte budget and resists lossless compression for the reasons
   above. Effort is better spent on the routed-expert projections, which
   dominate the budget.
