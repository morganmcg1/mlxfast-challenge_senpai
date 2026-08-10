# PR #645 decode critical-path attribution: definitive measurement NO-GO

## Decision

**Terminal result: calibrated measurement NO-GO.**

The r2 same-binary family-fence experiment completed the requested persistent-worker,
ABBA and reverse-BAAB protocol for all seven decode families. None of the seven
selectors met the authoritative whole-token perturbation limit of at most 1% in
both orders. The family estimates therefore diagnose fence-induced serialization;
they are not valid production attribution, recoverable latency, or optimization
rankings. Although the LM-head estimate alone met the +/-5 us/token precision
criterion, its empty control fence perturbed whole-token latency by 1.576%-1.828%
and its family fence by 2.923%-3.265%, so it is also non-actionable.

The gate order is calibration (`<=1%` perturbation in both orders), precision
(`+/-5 us/token`), then novelty (conservative lower bound `>=18 us/token`). Since
calibration failed first for every family, the novelty gate was not reached. No
successor optimization is proposed, no production or vendor source remains changed,
and no official submission was made.

## Scope and environment

- Advisor base: `f7cf412e910a8f937f13b25828ca9b952ecf20f6`
  (advanced through research documentation only; production source unchanged)
- Production-source base: `16d3730253eeb9809d306dda8b4777cbcb68e1da`
- Final restoration commit: `e0b931bbffadfec680d5e08ae937978da5684687`
- Instrumented measurement commit: `89f1d76084b18b6074129c1dd8322ef3bff8e49d`
- Branch: `cedar-thorfinn/decode-critical-path-attribution`
- Host: Mac mini `Mac16,11`, Apple M4 Pro, 20-core GPU, 48 GB unified memory
- Apple GPU generation: 16; this host does not establish M5 `_nax` behavior
- W&B: N/A. This was a local systems-attribution experiment and generated no
  W&B run.

Final production restoration was verified by:

```bash
git diff --exit-code 16d3730253eeb9809d306dda8b4777cbcb68e1da -- Sources Vendor
```

The command exited zero. Restored source hashes are:

```text
Sources/MLXFastModel/LagunaRuntimeModel.swift
  ed084a8aa840f651449b8c9f344c2cd40786de9eccee2c291bde419716022ccb
Sources/MLXFastHarness/LagunaRuntimeWorker.swift
  c5e31430578440c067dd751d711abe243f5605437a0e7319ac399274707cecbe
```

## Clean baseline

Supervised job `90921b79-a2a7-4c08-a28f-5bdd81d95e38` ran:

```bash
./benchmark.sh --local-iterate
```

The unchanged route passed correctness (`checked_steps=130`, `max_abs_diff=0`)
in 184.138 seconds with 21 GB peak RAM.

| Metric | Result |
|---|---:|
| Decode | 0.0129538343046875 s/token = **12,953.834 us/token** |
| M4 prefill diagnostic | 0.001111484375 s/token |
| Pinned calibration decode | 0.01385621216015625 s/token |
| Score JSON | `/tmp/pr645-baseline-a1.json` |
| Score SHA-256 | `be435a861e3d0bddc4c55592a229a61afa22231f21ba722036a3bb33b44ed936` |

The M4 prefill value is diagnostic only and is not evidence for the ranked M5
prefill route.

## R2 protocol

Instrumented worker build job `cb939fbb-89bd-4880-8fb6-ea469f1e68e5` passed.
Supervised measurement job `ea58e4ca-244f-4e8a-8469-edca0456a398` exited zero
after 287.149 seconds (273.359 seconds recorded by the driver) with:

```bash
python3 research/pr645_decode_probe.py \
  --worker .build-worker/release/mlxfast-runtime-worker \
  --weights weights \
  --output /tmp/pr645-r2-decode-probes.json
```

The temporary selector was research-only and selected exactly one family per
trajectory. The worker and loaded model stayed persistent and warm. Each family
ran six blocks in each order under both complete ABBA and reverse BAAB schedules.
Each selector/order combination retained 128 steady one-token samples after a
64-step warm trajectory, for 84 blocks and 10,752 measured samples total.

The timestamp boundaries were:

- Control: `asyncEval(inputs)`, GPU synchronize, timestamp, empty GPU synchronize.
- Family: `asyncEval(inputs)`, GPU synchronize, timestamp, `asyncEval(output)`,
  GPU synchronize.

Each block validated identical supplied input tokens, teacher-forced expected
tokens, logical cache progression, physical cache progression, and runtime
census. For all 128 measured decode steps, the route manifest recorded the
exact eight selected expert `UInt32` IDs and eight `Float32` weight bit patterns
for every one of the 39 sparse layers. All 128 per-step route-manifest hashes
were unique. Representative hashes:

```text
step 0:   e4950ed9892d3b68d8363c4ea39eb4f3d1202a624949ccc7a9c4e451fcf35f91
step 127: bcacc1e8843f37c3e3c5a1e697d488b1fd14af8b2b6ef7154cd8c5a578d5f1cf
```

The aggregate validator reported:

```json
{"blocks":84,"ok":true,"route_steps":128,"samples":10752}
```

A positive corruption control modified the census and correctly failed with
`block 0 census step 0; block 0 census total`. This establishes that the census
validator would reject a silent route mismatch rather than merely accepting the
recorded schema.

## Calibrated family results

All durations below are us/token. `Diagnostic bound` is the same-binary
family-minus-control estimate produced by the completed protocol. `CI hull` is
the union of the two order-specific confidence intervals; `half-width` is its
conservative uncertainty radius. Perturbation columns are whole-token 95% CIs
relative to the unfenced path. These diagnostic timing estimates must not be
interpreted as production family costs because their corresponding perturbation
checks failed.

| Family | Diagnostic bound | CI hull | Half-width | ABBA control / family perturbation | BAAB control / family perturbation | +/-5 us | <=1% both orders | Actionable |
|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| Sliding attention | 8,625.549 | [5,427.071, 12,277.947] | 3,425.438 | [164.077, 200.416]% / [518.278, 576.778]% | [115.820, 133.351]% / [204.704, 239.402]% | No | No | No |
| Full attention | 1,412.586 | [1,402.843, 1,422.064] | 9.610 | [28.269, 28.587]% / [42.835, 43.138]% | [28.248, 28.529]% / [43.076, 43.422]% | No | No | No |
| OProj | 5,968.799 | [5,953.692, 5,985.287] | 15.797 | [84.818, 85.518]% / [129.859, 130.641]% | [86.006, 86.591]% / [131.231, 132.000]% | No | No | No |
| Routed gate/up | 5,850.939 | [5,826.310, 5,880.357] | 27.024 | [83.553, 84.066]% / [128.865, 129.290]% | [84.332, 84.789]% / [129.171, 129.762]% | No | No | No |
| Shared gate/up | 8,996.943 | [7,452.311, 11,545.340] | 2,046.514 | [149.970, 174.938]% / [411.820, 432.529]% | [158.160, 162.830]% / [413.355, 522.688]% | No | No | No |
| Down/residual | 5,373.793 | [5,352.117, 5,396.187] | 22.035 | [81.136, 81.786]% / [128.871, 129.368]% | [83.197, 83.811]% / [129.730, 130.183]% | No | No | No |
| LM head | 627.193 | [625.073, 630.483] | 2.705 | [1.576, 1.823]% / [3.075, 3.265]% | [1.624, 1.828]% / [2.923, 3.167]% | Yes | No | No |

Order effects were also too large for several families: sliding attention
`5,888.501` us/token, full attention `-9.086`, OProj `-9.795`, routed gate/up
`-30.124`, shared gate/up `-2,858.817`, down/residual `-23.818`, and LM head
`-1.539`.

### Gate interpretation

1. **Perturbation gate:** failed for all seven families. Even the empty LM-head
   control fence exceeded 1% in both orders.
2. **Precision gate:** LM head alone met +/-5 us/token; the other six did not.
3. **Novel lower-bound gate:** not reached for any family because a family must
   first pass calibration and precision. No claim of `>=18 us/token`
   conservatively recoverable latency is supported.

The synchronization boundaries serialize or de-overlap asynchronous GPU work.
That explains why several diagnostic differences occupy implausibly large
fractions of the 12,953.834 us/token baseline and why control-only fences cause
large whole-token slowdowns. More repetitions cannot repair this systematic
perturbation.

## Correctness and restoration

After deleting the temporary driver and restoring both modified Swift files,
cleanup commit `e0b931bbffadfec680d5e08ae937978da5684687` returned the complete
`Sources/` and `Vendor/` production tree byte-for-byte to production-source base
`16d3730253eeb9809d306dda8b4777cbcb68e1da`.

Final upstream-equivalence job `2718fa80-72e3-437a-a137-99f7272bb155` ran:

```bash
research/run_upstream_equivalence.sh
```

The wrapper executed exactly one Swift Testing test and exited 1 for the known
unchanged-base M4 prefill tolerance drift:

- Prefill maximum absolute logit error: `0.125`
- Prefill mean absolute logit error: `0.011933609`
- Prefill runtime/upstream token: `5991` / `5991`
- Decode steps 0-7: maximum and mean absolute error `0`
- Exact decode tokens: `509, 902, 5991, 509, 902, 5991, 509, 902`
- Wrapper evidence: `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`

This is the same M4-only prefill drift observed on the unchanged base, not a
regression. Production equality to the base provides the stronger final
restoration proof; the official M5 remains authoritative for prefill numerics.

## Artifact and revision checksums

```text
Measurement JSON: /tmp/pr645-r2-decode-probes.json
  size: 8,807,791 bytes
  SHA-256: 6d31be0d991bc764547aff4b4409cb60d9561205b6ececcc45328423986f519f
Instrumented worker binary:
  SHA-256: 2cc275691d6354bec963da51839089e1e19fd018e4451492235384601640f6b2
Fixture: longcopy-gate-english-512
  SHA-256: b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
Temporary driver at measurement commit:
  SHA-256: 9ce8dcabd0901ad124d88498c89b235e4ba0c19a8297faa0bb5d30c52a5898d0
Instrumented LagunaRuntimeModel.swift:
  SHA-256: 6a4822bad56b4641903fc2233bac13973b56918fcad310049cf7beb4eaaabe84
Instrumented LagunaRuntimeWorker.swift:
  SHA-256: ebcb43842c169a4a912fa50ea1b267cbd94934595aa8ac44c5cacba9103feb00
```

Temporary instrumentation history:

```text
0ad90300a8ddeea482fae7b7717932bd2fa8cc6f  Instrument decode family completion probes
cb5d1742124c6a68ee4e6861759bff5d8487f061  Record exact decode route manifests
6221718197c99ee6b05e70b77dd701023b560408  Handle absent first-step attention census
89f1d76084b18b6074129c1dd8322ef3bff8e49d  Aggregate omitted zero-count census keys
e0b931bbffadfec680d5e08ae937978da5684687  Restore production after decode attribution probes
```

## R1 historical context

The initial r1 Metal System Trace was stale: it ended before scored decode and
captured no MLXFast process, command buffer, or encoder. Its source-derived
census and corruption control were useful controls but did not attribute time.
R2 supersedes that incomplete result with an exact-route, same-binary calibrated
measurement. R2 still concludes NO-GO, now definitively because the required
fences fail the perturbation contract rather than because samples are missing.

## Conclusion and suggested follow-up

The experiment completed every requested family and both orders with exact
route, token, cache, and census validation. The result is a definitive
measurement NO-GO: all seven family fences violate the <=1% whole-token
perturbation gate, so none can support a production critical-path claim or a
novel successor target. A future attribution assignment would need an
advisor-approved lower-perturbation timestamp or hardware-counter method before
repeating these families. That follow-up was not implemented here.

_This report was prepared by an AI agent (OpenHands) on behalf of the student._
