# 512-token prefill critical-path attribution

## Result

**Measurement NO-GO.** The hypothesis was not resolved, and no successor
optimization should be assigned from this evidence.

The first global Metal System Trace calibration perturbed the complete 512-token
prefill median by **+14.565 ms/pass (+2.665%)**, above the assignment's 1% stop
limit. Its 95% bootstrap half-width was **5.715 ms**, far above the required
0.10 ms bound. The exported trace also had zero application command-buffer
submission rows and contained global GPU/driver traffic from unrelated
processes. Therefore it cannot support inclusive/exclusive family timings,
host-enqueue attribution, bucket shares, or a conservative >=2.33 ms/pass
recoverable-headroom claim.

Per the explicit stop contract, I did not continue to 64 samples, complete the
A-B-B-A plus reverse B-A-A-B blocks, add differential fences, or modify scored
source. Doing so after the calibration failure would produce precise-looking
but untrustworthy attribution. Production source and vendor trees remain
identical to the assigned base.

W&B is not applicable to this measurement-only hardware-profiling assignment.
No official submission was made.

## Base and host

- Assigned base: `23a84d0e668eaf50b3f1cfbaf5bdfcb3b0694b25`.
- Advisor's later bookkeeping-only base: `fa463e5a0600e9248ace9668773e11e09061914d`;
  advisor confirmed that production source was unchanged, so no rebase was
  needed.
- Experiment driver commit: `7fe1263fc28d944004499a0bd2382fb07aee0b83`.
- Driver SHA-256: `b070bb0c048e7165926ef09cfecb23051690198839fdd230b3ccc675020d8d32`.
- Host: Mac mini, Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB unified memory.
- macOS 26.5.2 (25F84), Xcode 26.6 (17F113), Metal 32023.883.
- GPU family: `applegpu_g16s`; the M4 path does not select M5 `_nax` kernels.
- Low-memory startup profile was active. Every measured pilot started below the
  40 C cooling gate.

## Exact input and uninstrumented baseline

All pilots used `correctness_prompts/public_longcopy_gate_english_512_256.json`,
case `longcopy-gate-english-512`, with exactly 512 prompt tokens and expected
first token 5991.

- Fixture SHA-256:
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`
- Canonical compact prompt SHA-256:
  `6340be0422a338354777310f5ab3d8c5dd4ff8b60f7e47539d08739166423f`
- Worker SHA-256 for every pilot:
  `a1e9b3b73cb1b102600e6b11ac6f989e5be58f25932d39a0f0a803c44021c323`
- Worker stderr SHA-256 for every successful pilot:
  `52955c70652c3db30d2ce8ca13083498055428e840c598bb56194cfe6d24ff44`

The untouched `./benchmark.sh --local-iterate` run passed 130 checked steps
across 40 layers. It measured prefill at 0.001111389404296875 s/token
(**569.031375 ms/pass**) and decode at 0.0129402926484375 s/token, with 21 GiB
peak RAM. Job `6244892a-b821-42f7-91c5-1d8181e1c8c6` took 277.921 s. Its log
SHA-256 is
`3681180e04097caa9cb66c13e90624ec90d4fd558a9d0652cb1f44a2d091d565`;
the score JSON SHA-256 is
`d90842e4939f8f81d2e6078f919b7da0fe63c41d42759a04dcdcb0436403b817`.

## Static 40-layer dispatch census

The census below follows the scored `LagunaRuntimeModel` path. Counts are
logical dispatch-family counts for the frozen 512-token prefill shape; a fused
kernel is counted once in its owning bucket even when it emits multiple
outputs. Measured durations and shares are intentionally **unreported** because
the trace calibration failed.

| # | Bucket | Static census and representative scored symbols | Valid timing |
|---:|---|---|---|
| 1 | Embedding / input norm | One `[1,512,2048]` embedding gather; 40 layer-input RMS normalizations | No |
| 2 | QKV / gate projection | 119 Q/K/V projection-family launches across the 40 layers; ordinary layers retain all rows, while terminal specialization keeps K/V at 512 rows and Q at the last row; representative fused family `laguna_fused_norm_qkv_projection_bf16_h*_v3` | No |
| 3 | Q/K norm + RoPE | 39 fused multirow launches: 29 sliding and 10 full-attention H1/YaRN; terminal layer uses four stock logical RMSNorm/RoPE operations; representative `laguna_prefill_sliding_qk_norm_rope_bf16_128_{h1_}v2` | No |
| 4 | Attention / cache | 40 attention/cache families: 10 full + 29 sliding multirow SDPA/cache paths and one terminal vector SDPA/cache path | No |
| 5 | Gated OProj | 39 ordinary `g_proj` plus 39 ordinary `o_proj` launches; terminal specialization has one packed gate producer and one one-row OProj | No |
| 6 | Post-attention residual / RMS / router | 39 ordinary fused residual+RMS handoffs; sparse ordinary layers also execute router/top-8 selection; terminal specialization uses `laguna_residual_rms_router_bf16_2048_rpg*_keys_v1` | No |
| 7 | Routed gate/up + activation | 38 ordinary sparse layers each execute one routed fused gate/up gather-QMM plus activation; terminal layer has its one-row explicit twin. This deliberately excludes sibling experiment #638's routed gate/up half-wave code loads | No |
| 8 | Routed down | 38 ordinary sparse routed-down gather-QMM launches plus the terminal one-row explicit twin | No |
| 9 | Shared expert gate/up/activation/down | 114 ordinary shared-expert QMM launches (three per sparse layer across layers 1-38) plus terminal explicit shared work. This deliberately excludes sibling #640's exact SwiGLU producer epilogue | No |
| 10 | Sorted tail / residual handoff / terminal | 38 csort launches and 38 sorted-tail launches, then the terminal layer's specialized one-row handoff | No |
| 11 | Final norm / LM head / argmax | One final RMS normalization; four `LagunaLmHeadPruner` dispatches (including `laguna_lmhead_coarse_argmax_stage1_v5`); one final AOT arg-reduce | No |
| 12 | Host / enqueue / sync remainder | Defined as complete-pass wall time minus attributable GPU critical path; no reliable count because the command-buffer submission table exported zero rows | No |

Shape cross-checks:

- 40 layers: 29 sliding, 10 ordinary full-attention, and one terminal
  specialization.
- 38 ordinary sparse multirow blocks, one terminal one-row sparse block, and
  one dense block at layer 0.
- Hidden size 2048, head size 128, 8 KV heads, 48 full-attention Q heads,
  64 sliding Q heads, 256 experts, top-8 routing, and 512-wide routed/shared
  experts.

Metal scheduling is asynchronous: producer and consumer command buffers may
overlap, and summed per-kernel duration is not removable critical-path time.
Inclusive time would double-count overlap; exclusive time requires reliable
command-buffer dependencies and process attribution. The failed export supplied
neither, so no duration has been promoted from the raw trace.

## Calibration pilots

Each successful pilot used two full-prefill warmups followed by four measured
complete prefills. These four-sample pilots were only the mandated early
calibration gate, not the requested final >=64-prefill measurement.

| Block | Mode | Start temp | Samples (ms/pass) | Median | p95 | 95% bootstrap CI | Half-width |
|---|---|---:|---|---:|---:|---|---:|
| A1 | direct/off | 39.3 C | 546.868375, 546.311291, 546.605334, 546.426625 | 546.515980 | 546.828919 | [546.311291, 546.868375] | 0.352396 |
| B1 | global Metal System Trace/on | 38.2 C | 561.616875, 561.968250, 555.363417, 560.540625 | 561.078750 | 561.915544 | [555.363417, 561.968250] | 5.715333 |
| A2 | direct/off | 38.0 C | 554.435000, 546.293959, 546.590042, 546.432625 | 546.511334 | 553.258256 | [546.293959, 554.435000] | 7.923667 |

Comparisons:

- A2 - A1: **-0.004646 ms (-0.000850%)**.
- B1 - A1: **+14.562771 ms (+2.664656%)**.
- B1 - A2: **+14.567417 ms (+2.665529%)**.
- B1 - mean(A1,A2): **+14.565094 ms (+2.665092%)**.

Thus the direct medians were stable with respect to ordering, but trace-on
failed both acceptance gates: <=1% median perturbation and <=0.10 ms uncertainty.
The requested complete A-B-B-A and reverse B-A-A-B blocks were aborted at this
first hard stop.

The B1 trace bundle is 151,466,420 bytes across 578 files. The Metal GPU
interval export has 26,292 rows and includes unrelated processes such as
WindowServer; the driver-event export has 6,071 rows and also includes
unrelated processes. Worker PID was 10997. The application command-buffer
submission export has zero data rows, preventing host enqueue and dependency
reconstruction.

## Stop decision and M5 relevance

A one-family differential fence would itself modify the lazy graph and
synchronization behavior. It cannot repair a global tracer already adding
2.665% and 5.715 ms uncertainty, and it would not establish cross-family
critical-path overlap. The assignment explicitly required stopping for >1%
perturbation or >0.10 ms uncertainty, so no fences were attempted.

No family has a conservative measured lower bound of >=2.33 ms/pass removable
work. Consequently there is no exact optimization seam, <=8 KiB patch plan, or
successor correctness plan to recommend.

M4 generic BF16 matmul, full SDPA, routed-QMM, and shared-QMM observations would
not by themselves prove ranked M5 reach because the M5 selects `_nax` variants.
The common fused QK/RoPE, residual/router/tail, terminal, head, and argmax
families remain architecturally reachable on both hosts, but their geometry can
change with GPU generation/core count. Since no valid timing was obtained, none
is promoted as a ranked opportunity. Sibling scopes #638, #640, #641, and #643
were not duplicated.

## Correctness and corruption control

`research/run_upstream_equivalence.sh` was run on the untouched base and again
after all measurement work. Both runs produced the identical known M4-only
floating signature:

- prefill max absolute logit error: 0.125;
- prefill mean absolute logit error: 0.011933609;
- runtime/upstream prefill argmax: 5991 / 5991;
- decode steps 0-7: exact.

Base job `8ce6b383-d585-477d-b7f0-386cfd68dda3` log SHA-256:
`39f04ded4ded0bcf6299fbe0e971f36921758b7d7b8cbd3dccd6c23aecf838b0`.
Final job `8660d0fb-f6f8-4f55-9a35-754e580c9707` log SHA-256:
`2be94461245a070edac1c65359b2fbce67a15063e28b534088cbc432d310502f`.
The final run took 51.462 s. No scored source changed between them.

The positive corruption control intentionally required token 5992. The driver
failed closed with exit 2 and `worker token 5991 does not match expected 5992`.
Its JSON SHA-256 is
`179ae966222a031fa6466982259f4888b4696e2dddaa25b5b323747f79f47a5b`;
job `81cea775-4879-4d58-8025-ae336bc2c3ea` log SHA-256 is
`62458bdf1c41c6ac61faf209ce222f3ec5345c7d7c55322fa08d7f63b48957cc`.

## Reproduction commands

Set the preserved artifact root:

```bash
ART=/Users/ec2-user/.senpai/native/mlxfast-cedar-20260804/roles/student-cedar-nezuko/state/openhands_state/experiment_artifacts/prefill-attribution
```

Direct pilot pattern (A2; A1 used the same arguments and relative output paths):

```bash
/Users/ec2-user/.senpai/venv/bin/python research/prefill_attribution_driver.py \
  --output "$ART/pilot-A2.json" \
  --worker-stderr "$ART/pilot-A2.worker.stderr.log" \
  --label pilot-A2-direct --warmups 2 --repeats 4 --required-samples 4 \
  --expected-token 5991 --cool-gate ./benchmark.sh
```

Exact traced pilot:

```bash
xcrun xctrace record --template 'Metal System Trace' \
  --output "$ART/pilot-B1.trace" --no-prompt --launch -- \
  /Users/ec2-user/.senpai/venv/bin/python research/prefill_attribution_driver.py \
  --output "$ART/pilot-B1.json" \
  --worker-stderr "$ART/pilot-B1.worker.stderr.log" \
  --label pilot-B1-xctrace --warmups 2 --repeats 4 --required-samples 4 \
  --expected-token 5991 --cool-gate ./benchmark.sh
```

Exports:

```bash
xcrun xctrace export --input "$ART/pilot-B1.trace" --toc \
  --output "$ART/pilot-B1.toc.xml"
xcrun xctrace export --input "$ART/pilot-B1.trace" \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="metal-gpu-intervals"]' \
  --output "$ART/pilot-B1.metal-gpu-intervals.xml"
xcrun xctrace export --input "$ART/pilot-B1.trace" \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="metal-application-command-buffer-submissions"]' \
  --output "$ART/pilot-B1.command-buffer-submissions.xml"
xcrun xctrace export --input "$ART/pilot-B1.trace" \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="metal-driver-event-intervals"]' \
  --output "$ART/pilot-B1.driver-event-intervals.xml"
```

Correctness:

```bash
research/run_upstream_equivalence.sh
```

## Preserved artifact hashes

- `pilot-A1.json`: `7956b89864ad8d850fe4b1a289d954f943ba1f6ffe0ee126800e5ed25d5bccc1`
- `pilot-B1.json`: `cdb9c7672ca72a868c7f2b4679bbbcefd4fa05657f29b87ab498c881439e2bc9`
- `pilot-A2.json`: `c3e19cd3adf3c588281e709614ee8ae4eb1d60e85bd9efd5fe811db6bc06976c`
- `pilot-B1.trace` deterministic per-file manifest:
  `e01c41e38894a08606f299080636c2477e6c6863d354a50beb8e11230029cf58`
- `pilot-B1.toc.xml`:
  `9d893690f112162f96ebaa8c4441659ecd3ca50bca3f79316407e924274709f0`
- `pilot-B1.metal-gpu-intervals.xml`:
  `47880e3f10b569978d8609f9e5c4163207438132e68a2a8f6f680572ce976c7e`
- `pilot-B1.command-buffer-submissions.xml`:
  `4cb55cf68660dbce31036b0b10491e41513424fa391e894b4a18e30eb44c11a3`
- `pilot-B1.driver-event-intervals.xml`:
  `ba7a3b341c58ef9bff0637b1fab9f7be63b8653d32cd275d71fde2b8ab11e906`

## Suggested follow-up

Do not assign an optimization successor from this result. If future tooling can
capture per-process Metal command-buffer dependencies without >1% perturbation,
repeat only the calibration gate first on ranked M5 or a same-kernel-family
host. Require <=0.10 ms uncertainty before spending the full 64-prefill budget.
