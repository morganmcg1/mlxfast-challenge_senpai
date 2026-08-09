# R97-A Stage 2 result — layer-0 dense-MLP block-exponent compaction

Assignment `maple-r97-a-dense-mlp-stage2`, revision `r97-a-rev1`, PR #525.
Base `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.
Preregistration: `research/fern-r97-stage2-preregistration.md`, committed as
`1e683e5` before any timing datum was collected.

Host: M4 Pro, 48 GiB, low-memory startup profile. **Directional only.** The M4
Pro reports Apple GPU generation 16 and does not select the `_nax` prefill
kernels the ranked M5 uses; every number below is a decode-side measurement on
the shipped dense-MLP path, which is the same kernel family on both machines,
but the official M5 remains authoritative.

## 1. What shipped

Three submitted files:

| path | role |
|---|---|
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | `LagunaDenseBlockExponentBank`, packer, bit-exactness certificate |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | two block-exponent kernels, their wrappers, the two selection flags |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` | bank construction at load time and the dispatch preference |

Both banks are built once outside the scored hot path and are installed only
after a certificate rebuilds every BF16 pattern of the plane bit-for-bit; a
plane that fails the certificate is declined and the stock path runs.

## 2. Timed states

| state | gate/up plane | down plane |
|---|---|---|
| base | stock BF16 | stock BF16 |
| S2a | block-exponent `B=128, d=4`, escapes allowed | stock BF16 |
| S2b | block-exponent `B=128, d=4`, escapes allowed | block-exponent `B=row(8192), d=6`, no escapes |

<!-- RESULTS -->

## 3. Escape census, confirmed at load time

The packer prints one census line per plane. Observed with
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`:

```
block-exponent B128 d4 escaped 1735/262144: dense gate/up
block-exponent B8192 d6 escaped 0/2048: dense down
```

Both match the preregistration exactly. The preregistration predicted 1735
escaped gate/up blocks (858 gate + 877 up) out of 262,144 and zero escaped
down rows out of 2,048; the bytes/step arithmetic in §5 of the preregistration
was computed from those counts, so the byte predictions carry no census risk.
Both certificates passed, so neither plane was declined.

## 3b. Rung-control verification

Before any timed comparison the instrument itself was checked. The ladder
patch replaces the two `*Active()` predicates with a read of a shared mmap
control word, so a silent mmap failure would fall back to the static default
(rung 2) and dispatch both kernels in every process — an instrument that
reports "no effect" for the wrong reason. Three single-rung processes were run
with `SCHEDULE="const:0;const:1;const:2"` and dispatch logging on:

| process | rung | `block-exponent kernel:` notes | token-stream hash | teacher-forced mismatches |
|---|---|---|---|---|
| p00 | 0 (base) | none | `004d82089b71b300` | 0 |
| p01 | 1 (S2a) | `dense gate/up` | `004d82089b71b300` | 0 |
| p02 | 2 (S2b) | `dense gate/up`, `dense down` | `004d82089b71b300` | 0 |

The control word is therefore read live, each rung selects exactly the intended
kernel set, and all three rungs produce the identical token stream.

## 3c. Unpack-ALU audit: added integer ops per byte removed

The preregistration priced a removed byte at ~266 GB/s **assuming zero ALU
cost**, and flagged that assumption as the optimistic bound. Counting the
integer ops actually emitted by the two shipped kernels turns that assumption
into a number that can be checked before a change is built.

Counted from the kernel bodies in `LagunaRuntimeModel.swift`, per 4 elements
handled by one thread for one weight row:

| term | gate/up (`bexp128d4`) | down (`bexp_row_d6`) |
|---|---|---|
| delta load addressing | 3 | 4 (two delta streams) |
| escape-base compare | 1 | 0 (no escapes) |
| payload load addressing | 2 | 2 |
| base shift | 1 | 0 (hoisted, row-invariant) |
| delta extract + assemble, 4 elem | 16 | 32 |
| rotate back to BF16, 4 elem | 12 | 12 |
| **total per 4 elements** | **35** | **50** |
| **per element** | **8.75** | **12.5** |

Cross-check against the preregistered per-thread figures: gate/up handles
`4 rows x 2 planes x 4 elements = 32` elements per K-iteration, giving 280 ops
against the preregistered "≈240"; down handles `4 rows x 4 elements = 16`,
giving 200 against "≈160". The audit is 15-25% **higher** than the
preregistered estimate in both cases, i.e. the preregistration understated the
ALU cost. That is recorded as a deviation in §8.

Converting to the quantity that generalises:

| plane | elements | added int ops | bytes removed | **ops per byte removed** |
|---|---|---|---|---|
| gate/up (S2a) | 33,554,432 | 293.6 M | 16,070,912 | **18.3** |
| down (S2b − S2a, marginal) | 16,777,216 | 209.7 M | 4,192,256 | **50.0** |
| S2b combined | — | 503.3 M | 20,263,168 | **24.8** |

The obvious quantity to compare against is the machine's integer-throughput to
DRAM-bandwidth ratio. On this M4 Pro, ~20 cores x 128 lanes x ~1.5 GHz gives
roughly 3.8-4.0 T simple-int-ops/s against a measured 260.2 GB/s ceiling, i.e.
a nominal break-even near **15 added integer ops per byte removed**. Before any
timing this audit therefore predicted that both planes were unprofitable, with
gate/up (18.3) marginal and down (50.0) roughly 3x over.

**The measurement in §2 refutes that ordering, and I am recording the refutation
rather than the rule.** The plane the audit called 3x-hopeless (down, 50.0
ops/byte) is the one that converted, and the plane the audit called marginal
(gate/up, 18.3 ops/byte) is the one that lost far more time than its bytes could
ever have been worth. A scalar ops-per-byte screen does not rank these two
kernels, so §9 does not promote it to a standing rule. §2 develops what does
separate them; the audit survives only as an accounting of what the unpack
actually costs, not as a predictor.

## 4. Equivalence and correctness

<!-- CORRECTNESS -->

## 5. Byte budget

`senpai/check-editable-budget.sh b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`:

| | current | headroom | growth | files |
|---|---|---|---|---|
| base | 2,899,476 | 100,524 | 0 | 141 |
| this branch | 2,925,859 | 74,141 | **26,383** | 141 |

Growth is 26,383 B against the assignment's 60,000 B cap and the contract's
262,144 B per-review cap. No file was added or removed, and no submitted file
approaches the 524,288 B per-file cap.

## 6. W&B evidence

<!-- WANDB -->

## 7. Reproduction

All research tooling lives under `research/` and is not part of the submitted
surface. The submitted surface is the three files in §1.

Build the three-rung worker and run the blocked randomised ladder:

```bash
bash research/fern_r97_ladder_session.sh OUT=/tmp/r97/ladder MODE=block
```

`MODE=block` expands to `P=12 R=9 S=248 SCHEDULE=rand:0,1,2 PLACEBO_EVERY=8
WARMUP_RUNS=1 GATE_C=40 SEED=97`. The driver applies
`research/fern-r97-rung-ladder.patch` on top of the pristine-Sources commit
`55edbc77b2441c6fa84d6930503c9cc7518b8ec8`, builds
`mlxfast-runtime-worker` into `.build-worker`, restores the worktree, then
delegates to `research/fern_r93_nested_session.sh`. Re-apply the patch by hand
with:

```bash
git checkout 55edbc77b2441c6fa84d6930503c9cc7518b8ec8 -- \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
git apply research/fern-r97-rung-ladder.patch
```

The patch replaces the bodies of `lagunaDenseBlockExponentGateUpActive()` and
`...DownActive()` with a read of a shared `mmap` control word named by
`DARKBLOOM_R97_RUNG_MAP`, so all three states are one binary and one process
image. Gate/up is active at rung >= 1, down at rung >= 2. §3b is the evidence
that the control word is genuinely read per step.

The per-run companion reuses that binary:

```bash
bash research/fern_r97_ladder_session.sh OUT=/tmp/r97/perrun MODE=perrun \
  SKIP_BUILD=1
```

Analysis:

```bash
python3 research/fern_r93_ladder.py '/tmp/r97/ladder/p*.json' \
  --block 6 --drop-steps 24 --mad-mult 8 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/ladder.json
python3 research/fern_r97_decompose.py '/tmp/r97/ladder/p*.json' \
  --drop-steps 24 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/decompose.json
python3 research/fern_r93_perrun.py '/tmp/r97/perrun/p*.json' \
  --drop-steps 24 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/perrun/perrun.json
```

Smoke check of the three states plus the escape census (48 steps):

```bash
OUT=/tmp/r97/smoke STEPS=48 bash research/fern_r97_smoke.sh
```

`NARROW_LOG=1` turns on per-dispatch logging. It takes a lock per dispatch and
was off for every timed run reported here.

## 8. Deviations from the preregistration

<!-- DEVIATIONS -->

## 9. Verdict against the go/no-go bar

<!-- VERDICT -->
