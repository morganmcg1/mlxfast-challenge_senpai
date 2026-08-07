# Cold-Duplicate Rotation: T2c Routed QMV Result (Revision r2)

## Terminal result

**Result: clean negative.** On this M4 Pro host, rotating routed gate/up QMV to
virtually disjoint expert rows did not materially increase marginal decode cost
relative to duplicating the selected rows. The aggregate cold/warm slope ratio
was **1.0026340123**, with paired block-bootstrap 95% confidence interval
**[0.9820025506, 1.0101507719]**. The interval includes 1.0 and is entirely
below the preregistered 1.10 threshold. The preregistered decision is therefore
`stop_after_t2c`; T2d was not eligible and was not run.

This is the current r2 result. The earlier r1 result is invalid and superseded:
r1 did not give warm and cold the same source-level arithmetic DAG, and its
fault proof exercised only the warm arm. No r1 metric is used here.

This was an evidence-only assignment. The instrument was removed after
measurement, the final `Sources/` and `Vendor/` diff against required base
`32d18cb3604af18e259793df2ea0e0f25787acec` is empty, and no official M5
submission was dispatched.

## Required decisions

1. **Does warm duplication materially discount routed QMV marginal cost?** No.
   Cold rotation was not measurably more expensive than warm duplication.
2. **Is the effect large and stable enough to change the next solver
   mechanism?** No. The point estimate is near 1.0, its confidence interval
   crosses 1.0, and the three blocks do not show a stable positive cold penalty.
3. **Which mechanism should follow?** Neither routed-weight byte elimination
   nor an expert layout/locality project is justified by this probe. Continue
   prioritizing mechanisms with independent end-to-end evidence; this result is
   not causal support for a layout project.

## Primary result

Primary metric: `decode/cold_to_warm_routed_qmv_slope_ratio` (maximize; null
baseline 1.0).

| Quantity | Estimate | 95% confidence interval |
| --- | ---: | ---: |
| Warm marginal slope | 770.070438 us/step/duplicate | [764.328500, 771.781292] |
| Cold marginal slope | 772.098812 us/step/duplicate | [754.485566, 775.619812] |
| Cold/warm slope ratio | 1.0026340123 | [0.9820025506, 1.0101507719] |

Candidate-minus-null change for the primary metric is **+0.0026340123**.
Each arm summary is the median retained step time. Each block slope is the
four-point Theil-Sen slope over K = {1, 2, 3, 5}; the aggregate slope is the
median of the three block slopes. Confidence bounds use a paired,
non-overlapping 30-step block bootstrap with 10,000 retained replicates and
seed 252.

### Block slopes

| Block | Warm slope (us/step/duplicate) | Cold slope (us/step/duplicate) |
| --- | ---: | ---: |
| 1 | 770.070438 | 772.098812 |
| 2 | 758.737896 | 741.684750 |
| 3 | 773.070438 | 776.453375 |

The palindromic/interleaved schedule balanced mode and K within all three
blocks. Block 2 moves opposite blocks 1 and 3, supporting the null rather than
a stable cold penalty.

## Measurement protocol

- Family: routed gate/up QMV (`T2c`).
- Warm route: `(indices + 256) % 256`.
- Cold route: `(indices + 8) % 256`.
- Duplicate counts: K = {1, 2, 3, 5}.
- Blocks: three independent palindromic/interleaved blocks.
- Arms: 24 total (3 blocks x 2 modes x 4 K values).
- Steps: 1,216 per arm; first 16 discarded; 1,200 retained.
- Raw rows: 29,184; the `.csv` artifact is tab-delimited.
- Clock: `CLOCK_UPTIME_RAW`.
- Exact duplicate dispatches: 39*K per decode step: 39, 78, 117, and 195.
- Every step advanced logical and physical KV position exactly one and left no
  pending duplicate roots.
- Matrix artifact wall time: 409.487 seconds; supervised tool elapsed time:
  409.567 seconds.

## Causal-control evidence and limits

Warm and cold used the same source-level add-then-remainder construction,
graph construction order, K order, duplicate count, scratch-root order,
evaluation order, and synchronization. Only the integer addend differed: 256
for warm and 8 for cold. This establishes source-level graph parity only. No
Metal capture or hardware trace was collected, so no claim is made about
post-compilation kernel identity.

The instrument also established the following before interpreting timing:

- Checked all 39 sparse layers and complete weight/scale backing ranges.
- Verified all 78 routed-bank **virtual address ranges** were pairwise
  non-overlapping and expert-first contiguous; distinct expert rows were
  therefore virtually disjoint.
- Eagerly evaluated both banks before measurement.
- Symmetrically pre-touched each complete bank at page stride outside the timed
  region; the blocking checksum was `47e8a018fe07ce34`.
- Armed measurement only after constructor and weight-cache-library warmup.
- Evaluated duplicate scratch roots before the logits root.
- Ran isolated fault sessions for both warm and cold at K=1. Each session
  materialized exactly 39 roots, observed exactly 39 duplicate dispatches, and
  intentionally returned the expected code -5 at the injected root fault.
- K=0 created no rotated tensor, root, asynchronous evaluation, or blocking
  duplicate probe.

These controls prove virtual-range separation, not physical independence.
Cache-set mapping, physical-page placement, DRAM traffic, and cache residency
were uncontrolled and unmeasured. No physical-page or cache-set claim is made.

## Correctness and serial-track integrity

Supervised correctness run `787e2d38-bb76-4cb0-9410-a650a8544c2f` completed in
13.25 seconds and passed all instrumentation gates:

- Zero greedy-token divergence across warm, cold, and every K value.
- Full dense bfloat16 logits were bitwise identical for warm, cold, and K=0:
  FNV digest `956add317e7211aa`, 200,704 bytes, shape `[1, 1, 100352]`.
- Logical and physical KV position each advanced exactly one per supplied token.
- No pending future token, logits, KV state, or duplicate root crossed calls.
- The matrix repeated zero token divergence, exact KV +1, zero pending roots,
  and exact expected dispatch counts for every arm and step.

Symmetric fault run `9cc499dc-8f4d-4ec9-9e22-0fdffa3fcd31` completed in 85.837
seconds with exit 0. Both isolated child sessions produced their expected -5
return and 39/39 materialization/dispatch evidence. The earlier asymmetric run
`408427d5-d3ad-41a0-a89d-07bfc5c61100` is superseded and is not evidence for
this result.

### Restored upstream equivalence

After removing the instrument, `research/run_upstream_equivalence.sh` ran under
supervised ID `15756b08-82cf-4401-9101-4debbbea2535` at restored-source commit
`43a8eaa`. It built successfully, executed exactly one enabled Swift Testing
equivalence test, and reported matching runtime/upstream greedy tokens for one
512-token prefill and eight decode steps. All eight decode logits were bitwise
identical. The wrapper returned exit 1 after 64.496 seconds because the
unchanged restored M4 baseline's prefill logits had maximum absolute error
0.125 and mean absolute error 0.011933609 while the strict tolerance was 0.0.
It recorded `EQUIVALENCE_EXACT_STEPS=8` and `EQUIVALENCE_EXIT=1`.

This is not an experiment-induced submitted-source regression: the terminal
`Sources/` and `Vendor/` trees match the required assignment base. No tolerance
relaxation or local golden override was used. The official M5 remains
authoritative for the known cross-generation prefill difference.

## Expert-set overlap

Warm and cold recorded the same overlap distribution:

- Observations per mode: 561,600.
- Mean original/rotated top-8 overlap: 0.1963247863 experts.
- Median: 0; p95: 1; maximum: 3.
- Zero-overlap fraction: 0.8135897436.

The fixed +8 cold offset was not changed after observing results.

## Modeled traffic interpretation

The selected expert gate/up tensors contain 1,179,648 modeled bytes per
expert-layer use. Across 39 sparse layers, eight selected experts, and one
instrument duplicate, the model assigns 368,050,176 bytes per duplicate decode
step.

| Mode | Modeled effective bandwidth |
| --- | ---: |
| Warm | 477.9435 GB/s |
| Cold | 476.6879 GB/s |

These are modeled bytes divided by measured marginal time. They are not
measured DRAM traffic and do not prove cache residency. They support only the
null timing conclusion.

## Environment and resource accounting

- Hardware: Apple M4 Pro (`Mac16,11`), 48 GiB unified memory.
- Apple GPU generation: 16; low-memory startup profile active.
- OS: macOS 26.5.2.
- Swift: 6.3.3.
- Driver: CPython 3.13.14.
- Worker: `.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker`.
- Correctness: 13.25 seconds.
- Symmetric fault proof: 85.837 seconds.
- Matrix: 409.487 artifact seconds / 409.567 supervised seconds.
- Restored equivalence: 64.496 seconds.
- Peak process memory was not captured; no peak-memory value is claimed.

This M4 result is directional only. It does not exercise M5 `_nax` prefill
kernels and makes no ranked performance claim.

## W&B and official submission

No W&B integration or run was required for this probe, and the assignment
prohibited building a new integration. There is no W&B run ID or URL. No
official M5 submission was dispatched. Repository artifacts provide the full
measurement record.

## Reproduction

All model/GPU commands must be launched through the supervised `run_training`
interface in this environment.

```bash
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
senpai/check-editable-budget.sh 32d18cb3604af18e259793df2ea0e0f25787acec
senpai/check-editable-budget.sh 6d32b6c7581b5e1dadaa0df3b391809bcf17ac76
```

## Preserved artifacts and provenance

- Instrument patch: `research/cedar-nezuko-cold-duplicate-rotation.patch`.
- Driver: `research/cedar_nezuko_cold_duplicate_rotation.py`.
- Correctness: `research/cedar-nezuko-cold-duplicate-correctness.json`.
- Symmetric fault proof: `research/cedar-nezuko-cold-duplicate-fault.json`.
- Raw matrix: `research/cedar-nezuko-cold-duplicate-matrix.csv`.
- Metadata: `research/cedar-nezuko-cold-duplicate-matrix-metadata.json`.
- Analysis: `research/cedar-nezuko-cold-duplicate-analysis.json`.

Required base: `32d18cb3604af18e259793df2ea0e0f25787acec`.

Commit chain:

- `cabf8fe6fd327977db308c75a5cde9d69a1338ff`: exact r2 measurement implementation.
- `a4705ca1c861b43e4b808a8dbd2067ef7b8bd62d`: correctness evidence.
- `22e505db96cdaf72e0a4059fefd0ae57eaaf9a2f`: driver orchestration.
- `ad3ae61deeba8a93d24ee0c3b5821812ffeacdb0`: symmetric fault evidence and matrix source HEAD.
- `7edc556`: corrected raw matrix outputs.
- `43a8eaa`: restored runtime, corrected T2c analysis, and regenerated patch.

Supervised execution IDs:

- Build: `3cb26bdd-d591-43a0-9da4-5134653199ea`.
- Correctness: `787e2d38-bb76-4cb0-9410-a650a8544c2f`.
- Symmetric fault: `9cc499dc-8f4d-4ec9-9e22-0fdffa3fcd31`.
- T2c matrix: `004d2854-cc1c-4668-8cf3-1bf00f548df0`.
- Restored equivalence: `15756b08-82cf-4401-9101-4debbbea2535`.

## Suggested follow-ups not implemented

- Do not run T2d for this assignment; its preregistered gate failed.
- Do not begin an expert layout/locality project based on this probe.
- If a later mechanism independently removes routed bytes and wins end to end,
  evaluate it directly on matched hardware instead of inferring value from
  synthetic duplication.
- If exact equivalence evidence is needed for promotion, rerun the restored
  baseline wrapper on authoritative M5 hardware rather than relaxing the M4
  test.
