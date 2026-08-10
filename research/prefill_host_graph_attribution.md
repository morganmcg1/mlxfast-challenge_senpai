# Prefill host-graph attribution

## Result

**Terminal measurement NO-GO.** The empty control passed, but the first broad
host family (`ordinary_layers`) exceeded the assignment's `0.10 ms/pass`
uncertainty ceiling in both traversal orders. Its conservative lower bound was
also only `1.693217 ms/pass`, below the `2.33 ms/pass` successor threshold.
Per the mandatory stop rule, later families were not measured and no successor
optimization is proposed.

This was a measurement-only experiment. All temporary runtime, worker, and
runner instrumentation was removed after measurement; the final branch retains
only this report and the machine-readable raw CSV.

## Provenance and host

- Assignment base: `1237c647f7229ccd997d43f7005d485ea9f3ac90`
- Temporary instrumentation commit: `d72590dab7a86f37221b83327cb2bbbf94b4faec`
- Measurement job: `3881ba67-c42f-4243-a439-7b35e60b40dd`, exit `2`
  (intentional stop-gate exit), `614.93 s`
- Build job: `a326c3e1-94de-4cfb-8ec2-d2fd50335e7c`, exit `0`, `10.437 s`
- Smoke job: `2c0b5ad2-7173-4553-bee5-b08f7824e637`, exit `0`, `80.498 s`
- Host: Mac mini `Mac16,11`, M4 Pro, 48 GB unified memory, Apple GPU
  generation 16, macOS 26.5.2, Metal 32023.883, low-memory startup profile
- Ranked relevance: this M4 does not select the M5 `_nax` prefill kernels.
  Common Swift/MLX host construction is directional evidence; `_nax` selector
  conclusions are not.
- Peak diagnostics: process RAM `20.7076 GiB`; MLX active/cache/peak
  `35.4507/1.2207/38.7711 GB`.
- W&B: not applicable; this local inference timing assignment produced no W&B
  run.

Exact measurement command, run from the instrumentation commit:

```bash
python3 research/prefill_host_graph_attribution.py \
  --worker .build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker \
  --raw research/prefill_host_graph_attribution_raw.csv \
  --summary research/prefill_host_graph_attribution_summary.json \
  --quartets 32 --warmups 8
```

## Method and validity

The release worker remained resident. Each comparison used the same binary and
512-token public long-copy fixture. A selector-plus-empty pair isolated one
family at a time: mode `off` was compared with an empty timing branch for the
empty control, then empty timing was compared with active timing for each
family. Timers used `mach_continuous_time` and did not evaluate an MLX array.
The worker's pre-existing `eval(logits)` was separately timed, so the claimed
host intervals contain no added GPU synchronization.

Each order used 8 warmups and 32 quartets, yielding 64 steady samples per arm
per order. Both ABBA and reverse BAAB traversals were run. Confidence intervals
are 95% block-bootstrap intervals with 5,000 resamples. Family estimates below
are active-minus-empty timer durations; the lower bound is the minimum lower
CI endpoint across orders. Wall perturbation compares the complete prefill
request, including existing evaluation and worker protocol.

The profiler asserted exact counter multiplicities and expected token `5991`
on every response. A synthetic `count + 1` response was rejected, providing a
positive counter-corruption control. Active timing only observed existing calls:
it did not change graph construction, dispatch selection, cache state, or token
selection. All measured wall perturbations remained below 1% in both orders.

## Measurements

| Family / control | Calls/pass | Order | Estimate (ms/pass) | 95% CI (ms) | Half-width (ms) | Whole-prefill perturbation | Valid |
|---|---:|---|---:|---:|---:|---:|---|
| Empty control | 0 | ABBA | -0.407875 wall | [-1.533478, 0.427705] wall | 0.980592 | -0.07447% | yes |
| Empty control | 0 | BAAB | -0.307231 wall | [-1.129044, 0.378352] wall | 0.753698 | -0.05608% | yes |
| Cache construction | 1 | ABBA | 0.003014 | [0.002307, 0.003949] | 0.000821 | +0.01699% | yes |
| Cache construction | 1 | BAAB | 0.002042 | [0.001898, 0.002232] | 0.000167 | -0.01739% | yes |
| Input setup | 1 aggregate | ABBA | 0.010827 | [0.008743, 0.013454] | 0.002355 | -0.01483% | yes |
| Input setup | 1 aggregate | BAAB | 0.008364 | [0.007713, 0.009055] | 0.000671 | +0.01948% | yes |
| Ordinary layers | 39 | ABBA | 1.849350 | [1.693217, 2.061162] | **0.183972** | -0.08607% | **no** |
| Ordinary layers | 39 | BAAB | 1.996274 | [1.786997, 2.289740] | **0.251372** | +0.01464% | **no** |

The timer sign was positive in both orders for every measured real family.
`ordinary_layers` failed solely on precision; even its largest upper CI endpoint
(`2.289740 ms`) remained below the `2.33 ms` successor threshold. The run
therefore stopped before `terminal_layer`, `final_norm_head`, or
`async_enqueue`. The latter was deliberately kept separate: an `asyncEval`
interval can include GPU execution, backpressure, or waits and cannot support a
removable host-only lower bound.

Raw evidence:

- File: `research/prefill_host_graph_attribution_raw.csv`
- Committed LF-normalized SHA-256:
  `2ee8404ac4f6cfa8776beac89219bfc343583a78cad2a92f9517be82a9550f29`
- Original capture CRLF SHA-256:
  `c2fbccf817e11ca3be7d21f7d2ce415b14b3850cf7fa1f6d11dc951c64fd09d8`
- Shape: 1 header + 1,024 observations
- Blocks: 256 empty-control observations and 256 observations for each of
  cache construction, input setup, and ordinary layers
- Invariants: token set `{5991}`; active counts cache `{1}`, input `{1}`,
  ordinary `{39}`; empty counts `{0}`; request IDs `11...1040`

## Full static host census

Counts are per 512-token prefill pass on the scored runtime path. “Common” means
the Swift/MLX host wrapper is reached on both this M4 and ranked M5. M4 fallback
and M5-dependent rows identify selector-specific kernel construction and must
not be generalized across architectures.

| Host-side family | Exact calls/pass | Reachability classification | Measurement disposition |
|---|---:|---|---|
| Cache construction | 1 aggregate: 40 caches (10 standard, 30 rotating) | Common host | Measured; LB `0.001898 ms` |
| Embedding and mask/input setup | embedding 1; mask templates 2 | Common host | Measured aggregate; LB `0.007713 ms` |
| Attention input RMSNorm | 40 | Common host | Included in ordinary/terminal census |
| Q/K/V/G projections | logical Q 40, K 40, V 40, G 40; ordinary physical groups: fused QKV 39 + gate 39; terminal packed banks 2 | Common wrapper/graph construction | Ordinary subset measured only inside broad timer |
| QK norm and RoPE | 40 | Common host | Ordinary subset measured only inside broad timer |
| Attention/cache update | 40: full 10, sliding 30 | Common host; architecture-specific kernels beneath wrapper | Ordinary subset measured only inside broad timer |
| Attention output projection | 40 | Common host | Ordinary subset measured only inside broad timer |
| Post-attention residual and RMSNorm | 40 | Common host | Ordinary subset measured only inside broad timer |
| Dense layer-0 MLP | gate/up 1; down 1 | Common host | Included in 39 ordinary layer calls |
| Sparse routers | 39 | Common host | Included in ordinary/terminal layer calls |
| Routed expert gate/up and down | gate/up 39; down 39 | Common wrapper; M4 observed generic fallback, ranked M5 selector-dependent aligned-gather/pairwise `_nax` route | No narrower timer after mandatory stop |
| Shared expert gate/up and down | gate/up 39; down 39 | Common host | No narrower timer after mandatory stop |
| Sparse sort/tail wrapper | sort 39; tail 39 | Common wrapper; pairwise/aligned implementation M5-selector-dependent | No narrower timer after mandatory stop |
| Ordinary decoder calls | 39 | Common host | Measured; invalid precision, LB `1.693217 ms` |
| Terminal decoder call | 1 | Common specialized last-row host path | Not measured after stop |
| Final norm and language head | norm 1; head 1 | Common host | Not measured after stop |
| Existing async submission | `asyncEval` 39 | Common API call, but elapsed time may include GPU backpressure/waits | Ineligible as host-only attribution; not measured after stop |
| Existing terminal materialization | worker `eval(logits)` 1 | Common API call and GPU synchronization | Kept outside all claimed host timers |
| Research worker protocol | request/response 1 | Research-only; not submitted or ranked | Wall diagnostic only |

The configuration has 40 layers: dense MLP at layer 0 and sparse MLP at layers
1–39. Full attention occurs at indices `0,4,...,36` (10 layers); the other 30
are sliding-window layers. The scored prefill path builds one cache stack and
two mask templates, executes 39 ordinary decoder calls, then a specialized
layer-39 terminal call, final RMSNorm/head, and one worker evaluation. The
prefill async ladder has stride 1 and reaches 39 ordinary calls; the terminal
branch does not enter it. Routed top-8 selection uses 256 experts plus a shared
expert. Current defaults reach QK norm/RoPE, terminal projection banks,
terminal fusion, residual-RMS prefill, fused routed gate/up, MoE tail, and
sorted MoE tail. The router-top8 shortcut is off. On GPU generation 16 the
aligned `_nax` path is not selected, so no M5-specific timing claim is made.

## Correctness and cleanup

Baseline upstream-equivalence job
`983b30d5-610b-4f13-a9a0-80371da46ae8` ran 76.425 s. It reproduced the known
unchanged-base M4 numerical divergence: prefill max/mean absolute logit error
`0.125/0.011933609`, while runtime and upstream tokens both equaled `5991`;
decode logits were exact for steps 0–7 and all 9 greedy decode tokens matched.
The strict zero-tolerance wrapper therefore exited `1`. Post-cleanup job
`0517f618-93b9-41b5-a05f-0320391c43b8` ran 50.469 s and reproduced those exact
prefill errors, tokens, and exact decode steps before the same expected exit
`1`, confirming that the scored source was restored to the assignment base.

## Novelty audit and follow-up

No successor meets the assignment gates. Related work already tested shared
prefill SwiGLU producer epilogues (#640, about `0.357 ms` over 38 calls), found
routed-down ownership infeasible with a `2.217510 ms` traffic lower bound
(#649), and showed synchronization contamination in completion-fence tracing
(#645/#646). The current broad ordinary-family upper confidence bound is itself
below `2.33 ms`, and M5 `_nax` relevance is unproven on this host. The focused
follow-up is therefore to stop rather than spend implementation or official-M5
budget on this attribution path.
