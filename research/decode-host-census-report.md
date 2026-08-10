# Decode host-graph attribution census: measurement NO-GO

## Verdict

**Status: inconclusive measurement NO-GO. No successor experiment is nominated.**

The bounded host-path census could not enter its first warmed timing window because this M4 Pro host never satisfied the unchanged strict `<= 40C` GPU cool-down gate. The instrumented run stopped after 190 seconds at `40.6C`, its minimum observed temperature. Two unchanged-baseline attempts had already failed the same gate, with the closest minimum at approximately `40.1C`.

No per-family latency, perturbation, order effect, uncertainty interval, removable lower bound, or speedup is reported. Zeros in the failing benchmark JSON are sentinel values produced before timing and are not measurements. Disabling or weakening the gate would make the result non-comparable, so the assignment's stopping rule requires a NO-GO rather than false precision.

## Identity and environment

- PR: `#650`
- Branch: `cedar-askeladd/decode-host-graph-attribution`
- Assignment start: `9f5bbf3ac0ed5f1c14fecfc8b2ba38d351db68f7`
- Experiment base: `b9d75bbc51c96f619915389abfe476742434df65`
- Exact temporary instrumentation: `922de16b035e037686dec820eee7426d1311b4e7`
- Exact attempted runner: `5d5e2a78111c2e8cb0ff684d370075210aff5b63`
- Host: `Mac16,11`, Apple M4 Pro, 48 GiB, `arm64`
- OS: macOS `26.5.2`
- GPU generation reported by the runtime: 16; M5-only `_nax` prefill kernels were not selected
- Weights: `21,568,891,382` bytes across 9 files, SHA-256 `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`
- Harness SHA-256: `71855979692718e4f0a70570f24fec3f22225e044475eb580242308cbf72a045`
- W&B: not applicable; this was a local inference attribution measurement, and no timing window ran

## Intended measurement design

The temporary probes were intentionally same-binary and release-built. They preserved GPU waits as separate families and selected one host family at a time:

1. model dispatch
2. layer dispatch
3. attention/cache bookkeeping
4. kernel configuration
5. MoE wrapper work
6. graph/view construction
7. asynchronous submission
8. blocking evaluation
9. LM head
10. greedy-token wait

The worker was configured to perform an empty-probe calibration over 200,000 iterations, one warm 128-step decode, token/checksum/cache-offset corruption controls, and five repetitions of both ABBA and BAAB orders. A complete run would therefore have produced 400 warmed 128-step family/control windows. The predeclared gates were:

- both orderings represented by at least 64 windows per ordering or uncertainty no greater than `5 us/token`;
- instrumentation perturbation no greater than 1% in both orders;
- GPU waits reported separately from host work; and
- a successor only for a novel common M4/M5 host optimization with a conservative removable lower bound of at least `18 us/token`.

The thermal stop occurred before the warm decode. Consequently, empty-probe calibration, controls, timing orders, perturbation, uncertainty, and lower-bound gates were not evaluated.

## Static scored-path census

These are deterministic call counts from the instrumented control flow, not elapsed-time estimates:

| Boundary | Calls/token | Calls/128-step window |
|---|---:|---:|
| `MLXFastKernel` dispatches | 323 | 41,344 |
| model layers | 40 | 5,120 |
| attention/cache boundaries | 120 | 15,360 |
| sparse MoE kernel boundaries | 195 | 24,960 |
| dense/shared expert boundaries | 3 | 384 |
| LM-head boundaries | 4 | 512 |
| embedding boundary | 1 | 128 |
| asynchronous eval entries | 8 | 1,024 |
| blocking eval API entries | 3 | 384 |
| approximate submission opportunities | 9 | 1,152 |

Cache bookkeeping across the requested window had 5,120 update attempts and 5,110 advances: 3,840 sliding-window operations and 1,280 full-cache attempts, including 1,270 full-cache advances. This flow is shared between M4 and M5 decode. The M5-only `_nax` distinction applies to prefill and does not make this decode host census architecture-specific.

## Thermal failure evidence

Reproduction command:

```bash
/bin/bash research/run_host_census.sh
```

The runner expands to:

```bash
MLXFAST_HOST_CENSUS=1 MLXFAST_HOST_CENSUS_ROUNDS=5 ./benchmark.sh --local-iterate
```

Supervised job `f46ab0a9-52ef-479c-b68c-d14fe498887b` exited 1 after 373.997 seconds. Build and 38-second weight preflight succeeded. The benchmark then waited 190 seconds for `<= 40C` and failed at `40.6C`, also the minimum observed temperature. Its structured failure was emitted at `2026-08-10T15:27:09Z` with `timed_benchmark_seconds=0`, `case_count=0`, and error `local GPU cool-down gate failed for host-census with status 1`.

The attempt used a verified 80% fan hold only to improve cooling; the benchmark correctly detected that manual controller. Immediately afterward, the fan was restored and verified as `auto`. A process inspection found no model, Metal, Swift, benchmark, or runtime worker competing for the GPU. A single idle `macmon` sample reported GPU temperature `40.8559C`, CPU temperature `40.3212C`, and GPU active fraction approximately `0.0113`, consistent with this host idling above the strict threshold rather than an orphaned model process.

Raw supervised output is retained in `research/decode-host-census-thermal-failure.log` (SHA-256 `76084d655e38e033c6c51f5b2ed1119f1a09521f1a5a8c74f43676905c2e9675`).

## Baseline comparison

The trusted harness's pinned reference constants were:

- prefill: `0.00036751938916015626 s/token`
- decode: `0.01385621216015625 s/token`

An earlier local diagnostic recorded approximately `0.001112 s/token` prefill and `0.012897 s/token` decode with legacy score `0.8`, but it was not a fresh paired measurement for this assignment. The required unchanged and instrumented paired windows both failed the strict thermal gate, so there is no valid candidate-minus-baseline comparison and no primary metric.

## Novelty audit and successor decision

The static census did not reveal an unassigned, submission-eligible common-host family that could independently satisfy the `18 us/token` threshold without timing evidence:

- metadata/descriptor paths were negative in PRs `#340`, `#354`, `#559`, and `#621`;
- wrapper boundaries were covered by `#344`, `#354`, and `#633`;
- enqueue/synchronization work was covered by `#189` and `#632`, with a retired projection-launch estimate of only about `0.1-0.17 us/token`;
- cache paths were covered by `#195`, `#227`, `#580`, and `#604`;
- router/MoE paths were covered by `#327`, `#341`, `#480`, and `#614`;
- LM-head work is represented by merged PR `#336`, while `#474`, `#479`, `#577`, and `#624` were negative; and
- C-bridge/eval internals and the trusted token loop are not submission-editable.

A delegated frontier review produced no usable advisory result because its descendants did not return a collected terminal synthesis. It is therefore not used as evidence.

Because no timing family passed perturbation, order, uncertainty, and lower-bound gates, nominating any successor would violate the assignment contract. The appropriate follow-up is operational: rerun the exact committed instrumentation on a host that can satisfy the unchanged thermal gate, preferably matched M5 hardware. No implementation or official submission was attempted.

## Correctness and restoration

Before instrumentation, `research/run_upstream_equivalence.sh` completed its checks but exited 1 with the known M4 public-fixture near-tie signature: prefill runtime/upstream token `5991`, maximum absolute logit difference `0.125`, mean absolute difference `0.011933609`, and all 8 decode steps exact. This is baseline-equivalent diagnostic behavior, not an introduced decode mismatch.

All temporary `Sources/` and `Vendor/` changes were restored from the assignment start. The final production tree is byte-identical to base `b9d75bbc51c96f619915389abfe476742434df65`; only research evidence and the local runner remain. Post-restoration supervised job `40a035fb-fa54-4941-a683-eff08c270801` ran `research/run_upstream_equivalence.sh` in 57.677 seconds and exited 1 with the same known M4 signature: prefill runtime/upstream token `5991`, maximum absolute difference `0.125`, mean absolute difference `0.011933609`, and all 8 decode steps exact (`EQUIVALENCE_EXACT_STEPS=8`).

---

_This report was prepared by the OpenHands AI agent on behalf of the assigned student role._
