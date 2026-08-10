# Decode host attribution completion: HOST_ATTRIBUTION_INCONCLUSIVE

## Verdict

The sole permitted acquisition completed the full scientific stream: 400 non-warm windows covering 10 families, 5 rounds, both ABBA and BAAB orders, and all 4 positions. Its process exit code was 1 only because the frozen worker intentionally throws `host census complete` after emitting `HOST_CENSUS complete windows=400 passed=true`.

The attribution remains inconclusive. Seven families failed mirrored-sign agreement and five exceeded the predeclared `5 us/token` uncertainty half-width. The only family satisfying all formal measurement gates, `moe_wrapper`, encloses required sparse-MoE graph construction rather than isolated removable host overhead. No successor experiment is nominated.

## Identity and acquisition

- PR: `#672`
- Assignment: `cedar-thorfinn-decode-host-attribution-completion-20260810-r1`
- Required base: `6149100f9d65d2d1cff9c3378caab0a57698b09e`
- Production base: `b9d75bbc51c96f619915389abfe476742434df65`
- Frozen instrumentation source: `922de16b035e037686dec820eee7426d1311b4e7`
- Local instrumentation commit: `b9fac0ff9be8133363ca71b4cf9ed314d4c0c761`
- Declared whole nine-path binary diff SHA-256: `dad4a979721960cbbacebe22ebb1c8c68b3abec41d0cfd291a02f7fbe62b7fcd`
- Host: Apple M4 Pro, 48 GiB, `arm64`; GPU generation 16
- OS / Metal / Swift: macOS `26.5.2 (25F84)` / `32023.883` / `6.3.3`
- W&B: not applicable; this is a local inference attribution measurement

Exact reproduction command:

```bash
MLXFAST_LOCAL_FAN_PROMPT=0 \
MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1 \
MLXFAST_HOST_CENSUS=1 \
MLXFAST_HOST_CENSUS_ROUNDS=5 \
./benchmark.sh --local-iterate
```

Supervised job `583206df-e77d-4d1d-8925-31600618ba1e` ran once, with no retry, and ended after 694.032 seconds. The strict persistent telemetry gate passed after 20 seconds using five 1 Hz samples and a final GPU temperature of `39.3C`. A preceding 606.100-second idle trace contained 600 valid changing samples: GPU temperature `36.697365/38.471031/39.270184C` minimum/mean/maximum and fan speed `993/1000.033/1008 RPM` minimum/mean/maximum.

The separately persisted environment receipts establish fan mode `auto`, no competing process, a clean worktree, and exact frozen blobs immediately before acquisition; immediately afterward they establish fan mode `auto`, the acquisition PID absent, no named runtime/build process remaining, and a clean worktree. There is no independent continuous fan-mode trace for the acquisition interval. The immutable results artifact's legacy `fan_mode_before_during_after` field is therefore marked unverified and is not relied on for validity.

The trusted binary was 12,683,712 bytes with SHA-256 `8ea677c663e8118d9333d21959ba0511169f625377c7a9c99724ae63718848f7`. The worker was 49,213,704 bytes with SHA-256 `e34df5a62cad50e8ae077afdc676b3a0c583c121c2ec21f08ae1b2f20c3ce085`.

The structured receipt `score.local-iterate.json` has SHA-256 `b6b810682b3a91c8d4b487d9acbbfcad71d9890c0d9603a637ec9d3ce1f62fd2`. It records 690 benchmark wall seconds, 7.1 preflight seconds, harness SHA-256 `88672ebfbda8dfaa75c88d974896d223acd123120f61b847ec2c39b94175f753`, and the intentional `host census complete` sentinel. Its `0.85 GB` process-resident-memory field is a post-run diagnostic, not model peak memory; peak memory was unavailable.

## Method

The frozen same-binary instrumentation selected one family at a time. Each family had 20 measured and 20 control windows, with 128 decode steps per window. Empty timer calibration was finite at `2,758,821 ns` over 200,000 calls, or `13.794105 ns/call`. The injected corruption control was observed exactly once and passed.

Probe duration is the selected family's summed dispatch intervals minus calibrated timer cost, divided by 128 tokens. The 95% interval is a deterministic 20,000-resample nonparametric bootstrap interval for the median of 20 measured windows. Whole-wall perturbation uses nearest measured-control pairs within each order and round. These probe regions are nested: broad family durations include useful graph construction and dependency exposure and therefore are not additive removable costs.

## Frozen census and dynamic scope reconciliation

The frozen static census populated a family-call vector with `334 calls/token` (`42,752 calls/window`): `323` custom-instrumentation calls, `8` async submissions, and `3` blocking APIs. The custom subtotal is independently decomposed as `120` attention-cache calls, `195` sparse-MoE calls, `3` dense/shared-MoE calls, `4` LM-head calls, and `1` embedding call. Model dispatch (`1`), layer dispatch (`40`), and approximately `9` submissions are separate non-vector structural counts and are not added to the populated vector.

The dynamic family counts were model `1`, layer `40`, attention `40`, kernel `363`, MoE `39`, graph `1`, async `8`, blocking `2`, LM head `1`, and greedy wait `1` call/token. Their explicit mapping explains the wrapper overlap: kernel `363 = 323 custom + 40 layer`; attention `40 x 3 = 120` custom sites; MoE `39 x 5 = 195` custom sites; LM head `1 x 4 = 4` custom sites; and async `8` matches exactly. These are nested scope relationships, not quantities that may be added together.

The blocking control did not reconcile: the static census expected `3` calls/token but the dynamic family observed `2`. The checker deliberately rejects any claim that this coverage is validated. Consequently, `334` remains the populated static-vector scope rather than a validated dynamic invocation total, and this unresolved coverage strengthens rather than relaxes the inconclusive verdict. `research/decode-host-census-scope.json` records the reconciliation, while the evidence checker includes negative mutation controls for the custom subtotal, attention multiplier, and false blocking validation.

## Results

All durations and wall effects below are `us/token`. Perturbation percentages use complete-window wall time.

| Family | Calls/window | Probe median | Probe p95 | 95% CI | CI half-width | ABBA wall effect | BAAB wall effect | ABBA / BAAB perturbation | Signs agree | All gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| `model_dispatch` | 128 | 5624.698 | 5723.570 | [5622.940, 5634.666] | 5.863 | -2.082 | 2.242 | -0.025% / 0.027% | no | no |
| `layer_dispatch` | 5120 | 1111.157 | 1206.472 | [1101.735, 1127.109] | 12.687 | 7.705 | -6.716 | 0.093% / -0.081% | no | no |
| `attention_cache` | 5120 | 571.438 | 627.061 | [561.781, 610.091] | 24.155 | 17.686 | 7.773 | 0.213% / 0.094% | yes | no |
| `kernel_config` | 46464 | 715.226 | 768.401 | [710.035, 720.113] | 5.039 | -12.359 | -4.417 | -0.149% / -0.053% | yes | no |
| `moe_wrapper` | 4992 | 344.213 | 376.215 | [343.596, 348.614] | 2.509 | -4.019 | -0.721 | -0.048% / -0.009% | yes | yes |
| `graph_views` | 128 | 0.831 | 0.992 | [0.812, 0.886] | 0.037 | 4.506 | -19.619 | 0.054% / -0.236% | no | no |
| `async_submission` | 1024 | 4521.482 | 4534.357 | [4518.077, 4526.230] | 4.076 | -28.109 | 1.815 | -0.338% / 0.022% | no | no |
| `blocking_eval` | 256 | 2622.303 | 2628.324 | [2621.822, 2624.348] | 1.263 | -32.600 | 0.616 | -0.391% / 0.007% | no | no |
| `lm_head` | 128 | 12.540 | 13.530 | [12.338, 13.007] | 0.335 | 3.770 | -1.538 | 0.045% / -0.019% | no | no |
| `greedy_wait` | 128 | 2600.660 | 2627.411 | [2585.879, 2624.106] | 19.113 | 1.007 | -5.832 | 0.012% / -0.070% | no | no |

Every family passed the 1% perturbation ceiling in each order. Mirrored signs disagreed for `model_dispatch`, `layer_dispatch`, `graph_views`, `async_submission`, `blocking_eval`, `lm_head`, and `greedy_wait`. Uncertainty exceeded `5 us/token` for `model_dispatch`, `layer_dispatch`, `attention_cache`, `kernel_config`, and `greedy_wait`.

The families also separate host work from waits rather than treating all observed duration as removable:

- `graph_views` and `lm_head` are the narrow host-only boundaries, and their measured medians are below the required `18 us/token` successor threshold.
- `kernel_config` encloses configuration/build closures and narrowly misses the uncertainty gate.
- `async_submission` includes dependency/backpressure exposure.
- `blocking_eval` and `greedy_wait` are explicit GPU/read dependency waits.
- `model_dispatch`, `layer_dispatch`, `attention_cache`, and `moe_wrapper` enclose required model graph work. In particular, the passing `moe_wrapper` duration is not an isolated removable lower bound.

This evidence does not establish a novel common M4/M5 submission-eligible host optimization with a conservative removable lower bound of at least `18 us/token`. The M4 measurements remain directional; official M5 behavior is authoritative.

## Integrity, restoration, and correctness

The completion marker reported exactly 400 non-warm windows. Every measured and control window preserved 128 tokens, identical checksum `426215939139894599`, 40 cache offsets all equal to 640, and exact wall decomposition. Immediately afterward the fan remained `auto`, the acquisition PID was absent, and no runtime worker, trusted binary, Swift compiler, or Metal compiler process remained.

All eight production/vendor probe files and `research/run_host_census.sh` were restored from the required assignment base and committed at `c418078664c6bd99f02dcb76d4f4ed69256e7884`. The current `Sources/` and `Vendor/` tree manifest is byte-identical to the required base, with canonical SHA-256 `039454963f131b9b113e635a87b646dd0904fc33397298c5be427205e6eacb97`; the runner is also byte-identical.

Post-restoration supervised upstream-equivalence job `08c1103b-8375-41de-8906-992f749982d3` completed in 58.071 seconds. It produced only the accepted M4 public-fixture near-tie signature: prefill runtime/upstream token `5991`, maximum absolute logit difference `0.125`, mean absolute difference `0.011933609`, and all 8 decode steps exact (`EQUIVALENCE_EXACT_STEPS=8`). Its log SHA-256 is `fce1364f59e1cd263d75144771434bfb8a2639ee38568b66fc42923b55f13e70`.

## Artifacts and successor

`research/decode-host-census-results.json` is immutable and retains every one of the 400 non-warm windows, the warm window, complete summaries, validity decisions, environment, binary identities, and restoration evidence. Its SHA-256 is `daaaaba11288b47a8917bfc7ae94efd6eaa23faf0f20827ba3f515af1a4dbbb2`.

The compact raw receipt bundle preserves independently hash-checked evidence:

- `research/decode-host-census-acquisition-8d22dfb70ff95326f4171640d0b67ba7bc148d39464854ed7b44d49d8e5cc4c4.log.gz`: the sole acquisition log; uncompressed 493 lines, 172,307 bytes, SHA-256 `8d22dfb70ff95326f4171640d0b67ba7bc148d39464854ed7b44d49d8e5cc4c4`.
- `research/decode-host-census-idle-cdfde761adfa32b0e0d1a99ff17cfe03bbecde29059c1d53a43ec0afaa5098c6.jsonl.gz`: the preceding idle telemetry; uncompressed 600 lines, 1,327,593 bytes, SHA-256 `cdfde761adfa32b0e0d1a99ff17cfe03bbecde29059c1d53a43ec0afaa5098c6`.
- `research/decode-host-census-equivalence-fce1364f59e1cd263d75144771434bfb8a2639ee38568b66fc42923b55f13e70.log.gz`: the post-restoration equivalence log; uncompressed 113 lines, 5,876 bytes, SHA-256 `fce1364f59e1cd263d75144771434bfb8a2639ee38568b66fc42923b55f13e70`.

`research/decode-host-census-environment-receipt.json` records exact pre/post commands, stdout, event hashes, strict-gate markers, and the continuous-fan evidence limitation. `research/decode-host-census-scope.json` records the static/dynamic reconciliation. `research/decode-host-census-evidence-manifest.json` binds every compressed and raw receipt identity to the immutable result. Run the standard-library-only integrity and consistency check with:

```bash
python3 research/check_decode_host_census_evidence.py
```

A passing check reports all 400 windows, all three receipts, the `334`-call populated static vector, three negative mutation controls, and `HOST_ATTRIBUTION_INCONCLUSIVE`. No successor experiment or official submission was attempted.

---

_This report was prepared by the OpenHands AI agent on behalf of the assigned student role._
