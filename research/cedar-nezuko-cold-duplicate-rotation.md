# Cold-Duplicate Rotation: T2c Routed QMV Result

## Terminal result

**Result: clean negative.** Warm duplication does not materially discount the
marginal cost of routed gate/up QMV on this M4 Pro host. The aggregate cold to
warm slope ratio is **0.9947885860**, with paired block-bootstrap 95% confidence
interval **[0.9791274205, 1.0024836717]**. The ratio is below the preregistered
1.10 threshold and its confidence interval includes 1.0, so the stopping rule
requires stopping after T2c. T2d was not run.

This was an evidence-only assignment. No ranked solver change remains under
`Sources/` or `Vendor/`, and no official M5 submission was dispatched.

## Required decisions

1. **Does warm duplication materially discount routed QMV marginal cost?** No.
   Cold rotation is not measurably more expensive than warm duplication in this
   experiment.
2. **Is the effect large and stable enough to change the next solver
   mechanism?** No. The point estimate is slightly below 1.0, the confidence
   interval crosses 1.0, and the three block ratios do not support a positive
   cache-discount effect.
3. **Which exact mechanism should follow?** **Neither** routed-weight byte
   elimination nor an expert layout/locality project is justified by this
   probe. Continue prioritizing mechanisms using independent end-to-end
   evidence; do not use this experiment as causal support for a layout project.

## Primary result

Primary metric: `decode/cold_to_warm_routed_qmv_slope_ratio` (maximize; null
baseline 1.0).

| Quantity | Estimate | 95% confidence interval |
| --- | ---: | ---: |
| Warm marginal slope | 773.062750 us/step/duplicate | [768.8802188, 779.4220141] |
| Cold marginal slope | 769.034000 us/step/duplicate | [760.0155000, 773.0387812] |
| Cold/warm slope ratio | 0.9947885860 | [0.9791274205, 1.0024836717] |

Candidate-minus-null change for the primary metric is -0.0052114140.

The per-arm summary is the median retained step time. Each block slope is the
four-point Theil-Sen slope over K = {1, 2, 3, 5}. The aggregate slope is the
median of the three block slopes. Confidence bounds use a paired,
non-overlapping 30-step block bootstrap with 10,000 retained replicates and
seed 252.

## Block-level slopes and residuals

| Block | Warm slope (us) | Cold slope (us) | Warm MAD residual (us) | Warm p95 abs residual (us) | Cold MAD residual (us) | Cold p95 abs residual (us) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 779.6032083 | 764.0026250 | 4.0321 | 8.2042 | 6.5861 | 59.4331 |
| 2 | 773.0627500 | 770.8749375 | 6.3120 | 20.0336 | 12.5833 | 15.2523 |
| 3 | 770.0999583 | 769.0340000 | 2.2935 | 14.7736 | 2.3363 | 30.6397 |

The cold residual tails are noisier in blocks 1 and 3, but they do not produce
a positive aggregate cold penalty. The palindromic/interleaved schedule kept
mode and K balanced within all three blocks.

## Measurement protocol

- Family: routed gate/up QMV (`T2c`).
- Modes: selected experts (warm) and `(expert + 8) % 256` (cold).
- Duplicate counts: K = {1, 2, 3, 5}.
- Blocks: three independent palindromic/interleaved blocks.
- Arms: 24 total (3 blocks x 2 modes x 4 K values).
- Steps: 1,216 per arm; first 16 discarded; 1,200 retained.
- Raw rows: 29,184. The `.csv` artifact is tab-delimited.
- Clock: `CLOCK_UPTIME_RAW`.
- Exact duplicate dispatches: 39*K per decode step: 39, 78, 117, and 195.
- Every retained and discarded step advanced logical and physical KV position
  by exactly one and left zero pending duplicate roots.
- Matrix wall time: 408.2482 seconds.

## Causal-control evidence

The instrument established the advisor-requested physical and graph controls
before interpreting the slope:

- Checked all 39 sparse layers and all weight/scale backing ranges.
- Verified 78 warm/cold backing ranges were pairwise non-overlapping, with
  expected shape, strides, and row-byte layout.
- Eagerly evaluated duplicate banks before measurement.
- Symmetrically pre-touched each bank at page stride outside the timed region;
  the blocking pre-touch checksum was `47e8a018fe07ce34`.
- Armed measurement only after constructor and weight-cache-library warmup.
- Used the same graph construction, evaluation order, K order, duplicate count,
  scratch-root order, and synchronization in warm and cold modes. Only selected
  expert addresses differed.
- Evaluated duplicate scratch roots before the logits root.
- Fault injection with K=1/warm materialized exactly 39 roots, observed 39
  duplicate dispatches, then intentionally terminated at the injected root
  fault. This proves every sparse-layer duplicate root was evaluated.
- K=0 created no rotated tensor, root, asynchronous evaluation, or blocking
  duplicate probe.

The remaining limitation is intentional and explicit: cache-set mapping and
physical page placement were not controlled, and no hardware counter directly
measured DRAM or cache residency. The storage, eager-materialization, and
pre-touch controls make the warm/cold address comparison interpretable, but
cannot eliminate that residual cache-set/page-placement confound.

## Correctness and serial-track integrity

The dedicated correctness run passed all instrumentation gates:

- Zero greedy-token divergence across warm, cold, and every K value.
- Full dense bfloat16 logits were bitwise identical for warm, cold, and K=0:
  FNV digest `956add317e7211aa`, 200,704 bytes, shape `[1, 1, 100352]`.
- Logical KV position advanced by exactly one per supplied decode token.
- Physical KV position advanced by exactly one per supplied decode token.
- No pending future token, logits, KV state, or duplicate root crossed calls.
- Warm/cold command-graph metadata and evaluation order were identical.
- The matrix repeated zero token divergence, exact KV +1, zero pending roots,
  and exact expected dispatch counts for every arm and step.

### Restored upstream equivalence

`research/run_upstream_equivalence.sh` was run after restoring the submitted
surface. It executed exactly one enabled equivalence test and all nine reported
runtime/upstream greedy tokens matched: one 512-token prefill and eight decode
steps. All eight decode logits were bitwise identical. The strict test still
returned exit 1 on this M4 Pro because the unchanged restored baseline's
prefill logits had maximum absolute error 0.125 and mean absolute error
0.011933609 while the test tolerance was 0.0.

This is not an experiment-induced submitted-source regression: the terminal
`Sources/` and `Vendor/` trees are identical to assignment head
`88bab7caa7b11e607a2681449f0ee0a1e45161c1`. No tolerance relaxation or local
golden override was used. The official M5 remains authoritative for this
baseline numerical difference. Supervised run
`328d6808-68cd-400a-bffc-eab494dccfbd` recorded
`EQUIVALENCE_EXACT_STEPS=8` and `EQUIVALENCE_EXIT=1` in 63.752 seconds.

## Expert-set overlap

Warm and cold modes recorded identical overlap-observation counts:

- Observations per mode: 561,600.
- Mean original/rotated top-8 overlap: 0.1963248 experts.
- Median overlap: 0.
- 95th percentile overlap: 1.
- Maximum overlap: 3.
- Zero-overlap fraction: 0.8135897.

The fixed +8 offset was not changed after observing results.

## Modeled traffic interpretation

The selected expert gate/up tensors contain 1,179,648 modeled bytes per
expert-layer use. Across 39 sparse layers, eight selected experts, and the
instrument's duplicate operation, the analysis models 368,050,176 bytes per
duplicate decode step.

| Mode | Modeled effective bandwidth |
| --- | ---: |
| Warm | 476.0935 GB/s |
| Cold | 478.5877 GB/s |

These values are model-implied bytes divided by measured marginal time. They
are not measured DRAM traffic and must not be read as proof of cache residency.
They reinforce only the null timing result: cold rotation did not expose a
material hidden weight-traffic penalty.

## Environment and resource accounting

- Hardware: Apple M4 Pro, 48 GiB unified memory, Apple GPU generation 16.
- OS: macOS 26.5.2.
- Swift: 6.3.3.
- Driver: CPython 3.13.
- Worker: `.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker`.
- Matrix wall time: 408.2482 seconds.
- Correctness run wall time: 53.174 seconds.
- Restored equivalence wall time: 63.752 seconds.
- Peak process memory was not captured; only the 48 GiB physical host memory is
  known, so no peak-memory value is claimed.

This M4 result is directional evidence only. The experiment does not touch M5
`_nax` prefill kernels and makes no ranked performance claim.

## W&B

No existing W&B integration or run was available for this probe, and the
assignment explicitly prohibited building a new integration. Therefore there
is no W&B run ID or direct URL. Raw step data, metadata, correctness output,
fault output, and analysis JSON are preserved in the repository instead.

## Reproduction

All model/GPU commands below must be launched through the supervised
`run_training` interface in this environment.

```bash
./setup.sh
swift build -c release --force-resolved-versions \
  --build-path .build-worker \
  --product mlxfast-runtime-worker

python3 research/cedar_nezuko_cold_duplicate_rotation.py correctness \
  --worker .build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker \
  --output research/cedar-nezuko-cold-duplicate-correctness.json

python3 research/cedar_nezuko_cold_duplicate_rotation.py fault \
  --worker .build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker \
  --output research/cedar-nezuko-cold-duplicate-fault.json

python3 research/cedar_nezuko_cold_duplicate_rotation.py matrix \
  --worker .build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker \
  --raw-output research/cedar-nezuko-cold-duplicate-matrix.csv \
  --metadata-output research/cedar-nezuko-cold-duplicate-matrix-metadata.json \
  --timed-steps 1200 \
  --discard-steps 16

python3 research/cedar_nezuko_cold_duplicate_rotation.py analyze \
  --raw research/cedar-nezuko-cold-duplicate-matrix.csv \
  --metadata research/cedar-nezuko-cold-duplicate-matrix-metadata.json \
  --output research/cedar-nezuko-cold-duplicate-analysis.json \
  --bootstrap-replicates 10000 \
  --bootstrap-block-size 30 \
  --bootstrap-seed 252

bash research/run_upstream_equivalence.sh
senpai/check-editable-budget.sh 6d32b6c7581b5e1dadaa0df3b391809bcf17ac76
```

## Preserved artifacts and provenance

- Instrument patch: `research/cedar-nezuko-cold-duplicate-rotation.patch`.
- Driver: `research/cedar_nezuko_cold_duplicate_rotation.py`.
- Correctness: `research/cedar-nezuko-cold-duplicate-correctness.json`.
- Fault proof: `research/cedar-nezuko-cold-duplicate-fault.json`.
- Raw matrix: `research/cedar-nezuko-cold-duplicate-matrix.csv`.
- Matrix metadata: `research/cedar-nezuko-cold-duplicate-matrix-metadata.json`.
- Analysis: `research/cedar-nezuko-cold-duplicate-analysis.json`.

Commit chain:

- `2f9d304d7f78063cba88fcbd2aac9b981fea72b0`: exact measurement implementation.
- `9c3b6b42f177f38711793902b61e44e24a43cf29`: correctness/storage evidence.
- `67873f1b85882f8d706e6d569119cafd59bb1ff2`: all-root fault evidence.
- `21cad6c`: preserved raw timing matrix and metadata.
- `638a6a1`: restored runtime and recorded terminal analysis.

Supervised execution IDs:

- Setup: `04193ef8-5624-412a-9992-2ecad8768725`.
- Correctness: `76752145-31c5-44fd-9e87-44dba97b2627`.
- Fault: `e20b36e8-2220-4443-818c-a8a093bd3e7a`.
- T2c matrix: `c95b0872-7875-493d-aed4-11e0d80fb1f1`.
- Restored equivalence: `328d6808-68cd-400a-bffc-eab494dccfbd`.

## Suggested follow-ups not implemented

- Do not run T2d for this assignment; the preregistered eligibility gate failed.
- Do not begin an expert layout/locality project on the basis of this probe.
- If a later mechanism independently removes routed bytes and wins end to end,
  evaluate it directly on matched hardware rather than inferring its value from
  synthetic duplication.
- If exact equivalence evidence is needed for promotion, rerun the restored
  baseline wrapper on the authoritative M5 rather than relaxing the M4 test.
