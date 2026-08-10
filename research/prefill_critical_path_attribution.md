# 512-token prefill critical-path attribution

## R2 terminal result

**Calibrated measurement GO; successor assignment NO-GO.** A same-binary,
empty-fence-subtracted measurement resolved the common full-attention fused Q/K
normalization + YaRN H1 family at **2.726245 ms/pass**, with a stratified
bootstrap 95% interval of **[2.694376, 2.743162] ms/pass** and conservative
half-width **0.031869 ms/pass**. The lower bound clears the advisor's decisive
**2.33 ms/pass** headroom gate. Complete-prefill perturbation stayed below 1%
in both A-B-B-A and reverse B-A-A-B orderings.

This is a calibrated completion/critical-path interval, not a pure GPU kernel
duration. Inputs were materialized before timing, outputs were materialized at
the end, and the same-binary empty completion fence was subtracted. That method
addresses the synchronization inflation identified in the R1 global trace and
in analogous decode work, while the whole-pass perturbation gate limits graph
and scheduling distortion.

The measurement does **not** justify a new optimization assignment. The exact
family clears the latency gate, but its known optimization mechanisms overlap
active #641's Q/K raw-BF16 reuse or the exhausted Q/K/RoPE arithmetic and
geometry space. I found no materially distinct, unassigned <=8 KiB production
patch with a defensible byte/launch seam. No successor was nominated merely to
satisfy the hypothesis.

W&B is not applicable to this measurement-only hardware experiment. No official
submission was made.

## Identity, host, and scope

- Assignment base: `23a84d0e668eaf50b3f1cfbaf5bdfcb3b0694b25`.
- R2 instrumented/tested SHA: `3ca6b1eb05c160cb132260140aeb248a7dd07092`.
- Assignment revision:
  `cedar-nezuko-prefill-critical-path-attribution-20260810-r2-differential-fence-calibration`.
- Host: Mac mini, Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB unified
  memory; Apple GPU generation 16 (`applegpu_g16s`).
- Worker SHA-256:
  `140f3e288edb68f95faed57a282315eae2f3d938cdc562c180932ec2d5570eba`.
- Fixture: `longcopy-gate-english-512`, exactly 512 prompt tokens, expected
  first token 5991.
- Fixture SHA-256:
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.
- Compact prompt SHA-256:
  `6340be0422a338354777310f5ab3d8c5dd4ff8b60f7e47539d08739166423f`.

The M4 and ranked M5 both reach this common fused full-attention source family;
this is not an M5-only `_nax` prefill kernel. Absolute M4 timing and threadgroup
sign remain host-specific, so the M5 inference is directional rather than a
ranked timing claim.

## Exact measured seam and census

The temporary selector was active only for length-512 prefill in
`LagunaAttention.__callAsFunction`. The family branch was
`usePrefillFusedFullQKNormYaRN`, calling `lagunaPrefillFullQKNormYaRN` at the
default `lagunaPrefillQKHeadsPerGroup=1` setting.

- Input boundary: materialize `[queries, keys]` before starting the interval.
- Empty control: repeat materialization of those already-materialized inputs.
- Family completion: materialize `[outQueries, outKeys]` after the fused call.
- Exact census per pass: 10 sites, 10 completed sites, 10 dispatches, 5,120 Q
  rows, 5,120 K rows, heads-per-group 1.
- Output control: every arm and request returned token 5991; every census field
  was constant and exact.

The selector and fence records were temporary research instrumentation. They
were removed after measurement. `Sources/` and `Vendor/` are tree-identical to
the assigned base.

## Calibrated results and gates

Each phase used eight fresh-worker arms, one warmup and four measured prefills
per arm, ordered A-B-B-A then B-A-A-B. Together the phases contain 64 warmed
measured prefills. Estimates use arm medians and a 20,000-iteration bootstrap
stratified by mirrored block/order with within-arm request resampling.

| Phase / metric | Balanced baseline | Balanced candidate | Delta | ABBA delta | BAAB delta | 95% interval | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| off -> empty control, wall | 546.061141 | 547.210453 | +1.149312 ms (+0.2105%) | +1.119521 ms | +1.179104 ms | [0.939664, 2.399617] ms | <=1% pass |
| off -> empty control, completion | 0 | 0.034927 | +0.034927 ms | +0.035812 ms | +0.034042 ms | [0.032619, 0.036204] ms | 0.002308 ms half-width |
| control -> full-QK-H1, wall | 547.279000 | 548.097365 | +0.818365 ms (+0.1495%) | +0.996136 ms | +0.640594 ms | [-4.355112, 4.530449] ms | <=1% pass |
| control -> full-QK-H1, completion | 0.032671 | 2.758917 | **+2.726245 ms** | +2.720876 ms | +2.731615 ms | **[2.694376, 2.743162] ms** | 0.031869 ms half-width; lower >2.33 ms |

Ordering-specific wall perturbations were about 0.1821% (ABBA) and 0.1170%
(BAAB). Even the wall-delta interval's +4.530449 ms upper endpoint is 0.828% of
the 547.279000 ms control pass. Thus both the point estimates and the
conservative upper perturbation stay below 1%.

The family phase's input-boundary interval moved from 500.102131 to 498.853912
ms (delta -1.248219 ms, 95% interval [-1.451880, -1.017321] ms). This boundary
is upstream materialization, not family work, and is why the result is reported
as an empty-fence-calibrated completion interval rather than a decomposition of
whole-pass wall time.

## Raw R2 samples

Each cell lists the four measured values for one fresh-worker arm. `wall` is
complete request latency; `fence` is the completion interval. Units are ms.
The JSON artifacts retain every request timestamp, boundary interval, token,
census field, command, child artifact hash, stderr hash, and cooling record.

### Phase 1: off / empty-control calibration

| Arm | Mode | wall | fence |
|---:|---|---|---|
| 0 | off | 546.185416, 546.230542, 545.901625, 545.943875 | 0, 0, 0, 0 |
| 1 | control | 547.071166, 547.144125, 547.170334, 546.966500 | 0.039083, 0.043168, 0.033040, 0.041123 |
| 2 | control | 546.872125, 547.058667, 547.637125, 547.232916 | 0.033375, 0.029667, 0.034542, 0.026624 |
| 3 | off | 546.017917, 546.549583, 545.881583, 545.752583 | 0, 0, 0, 0 |
| 4 | control | 552.282042, 547.371834, 546.956667, 547.439667 | 0.036459, 0.030458, 0.033211, 0.034334 |
| 5 | off | 545.367791, 546.351625, 546.133833, 546.661000 | 0, 0, 0, 0 |
| 6 | off | 546.084959, 545.889917, 546.138500, 545.119958 | 0, 0, 0, 0 |
| 7 | control | 547.376500, 547.014791, 547.132833, 547.232416 | 0.034126, 0.035209, 0.031333, 0.034499 |

### Phase 2: empty control / full-QK-H1

| Arm | Mode | wall | fence |
|---:|---|---|---|
| 0 | control | 547.019125, 547.005666, 546.823000, 547.463167 | 0.037541, 0.027415, 0.032084, 0.026752 |
| 1 | full-QK-H1 | 548.144167, 548.004667, 548.230917, 547.778708 | 2.755250, 2.746708, 2.753750, 2.721498 |
| 2 | full-QK-H1 | 548.794292, 548.197250, 548.078292, 547.704417 | 2.784457, 2.810749, 2.728334, 2.729209 |
| 3 | control | 547.792791, 547.090167, 546.898541, 547.324875 | 0.038580, 0.041249, 0.028668, 0.032542 |
| 4 | full-QK-H1 | 562.948792, 548.095333, 548.198708, 547.926792 | 2.771958, 2.753249, 2.772377, 2.662791 |
| 5 | control | 563.996458, 547.541375, 547.656833, 547.059834 | 0.041627, 0.032374, 0.031626, 0.031543 |
| 6 | control | 567.775417, 546.960208, 547.443792, 547.150166 | 0.034459, 0.031748, 0.037374, 0.032291 |
| 7 | full-QK-H1 | 560.623500, 548.125125, 547.799166, 547.935375 | 2.805210, 2.745417, 2.697040, 2.786585 |

The isolated wall outliers are absorbed by per-arm medians and mirrored-block
resampling; the fence samples remain stable. This is also why raw requests are
reported rather than only aggregate point estimates.

## Amdahl projection and successor decision

The calibrated point estimate is 0.4981% of the 547.279000 ms control pass; the
95% lower bound is 0.4923%. If the entire measured interval were removable with
no regressions, the point projection is 1.005006x prefill and 1.001249x weighted
score at neutral decode. The lower-bound projection is 1.004948x prefill and
1.001235x weighted score.

Those are upper-bound opportunity projections, not candidate speedups. No
production optimization was implemented or timed. The family has enough
critical-path mass to merit optimization in isolation, but the currently known
seams are not still-unassigned:

- raw Q/K vector lifetime and reuse overlaps active #641;
- fused Q/K normalization, YaRN arithmetic, and H1 geometry are in the exhausted
  Q/K/RoPE arithmetic/geometry space; and
- adding or removing a measurement fence is not a production optimization.

Therefore the terminal recommendation is **no successor from R2**. A future
assignment would need a new, concrete seam that removes bytes or launches
without duplicating those mechanisms, plus an exact M5-reachable dispatch
census and correctness plan.

## Reproduction and artifacts

Artifact root:

```bash
ART=/Users/ec2-user/.senpai/native/mlxfast-cedar-20260804/roles/student-cedar-nezuko/experiment_artifacts/prefill-attribution/r2-differential-fence
```

Phase 1 command:

```bash
/Users/ec2-user/.senpai/venv/bin/python research/prefill_attribution_driver.py \
  --worker .build-worker/release/mlxfast-runtime-worker --weights weights \
  --fixture correctness_prompts/public_longcopy_gate_english_512_256.json \
  --output "$ART/r2-control-pilot.json" --label pr646-r2-control-pilot \
  --warmups 1 --repeats 4 --required-samples 4 \
  --expected-prompt-tokens 512 --expected-token 5991 \
  --bootstrap-samples 20000 --bootstrap-seed 646 \
  --matrix-order off,control,control,off,control,off,off,control \
  --cool-gate ./benchmark.sh
```

Phase 2 command:

```bash
/Users/ec2-user/.senpai/venv/bin/python research/prefill_attribution_driver.py \
  --worker .build-worker/release/mlxfast-runtime-worker --weights weights \
  --fixture correctness_prompts/public_longcopy_gate_english_512_256.json \
  --output "$ART/r2-full-qk-h1-pilot.json" \
  --label pr646-r2-full-qk-h1-pilot \
  --warmups 1 --repeats 4 --required-samples 4 \
  --expected-prompt-tokens 512 --expected-token 5991 \
  --bootstrap-samples 20000 --bootstrap-seed 646 \
  --matrix-order control,full-qk-h1,full-qk-h1,control,full-qk-h1,control,control,full-qk-h1 \
  --cool-gate ./benchmark.sh
```

- `r2-control-pilot.json` SHA-256:
  `d97eeabf646d9ece27d77df646780ca586ccede6830d4132f8a2190d8b96d1a6`.
- `r2-full-qk-h1-pilot.json` SHA-256:
  `dc5cc2642cdd14d5264168d0ca9c5827177c33478d5c017e252ac77e33c345b5`.
- Phase 1 supervised job: `74af3556-6070-4f25-adf3-581016894feb`, exit 0.
- Phase 2 supervised job: `cbad60fc-f81b-4c2c-b8fa-bcac66b62797`, exit 0,
  639.984 s.

## Correctness and final cleanup

The R1 untouched-base and post-measurement upstream-equivalence runs had the
same known M4-only floating signature: prefill max absolute logit error 0.125,
mean error 0.011933609, exact argmax 5991, and exact decode steps 0-7. The
positive corruption control required token 5992 and failed closed on observed
5991.

After R2 measurement, the temporary selector was removed and this proof passed:

```bash
git diff --exit-code 23a84d0e668eaf50b3f1cfbaf5bdfcb3b0694b25 -- Sources Vendor
```

The final post-removal check tested clean production SHA
`11563a137c372d93a59195136f2388b09b83ae01` with:

```bash
/usr/bin/env MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1 \
  research/run_upstream_equivalence.sh
```

Supervised job `62bb9af2-57a5-4d42-95d9-3270f94dd75c` ran 57.831 s and exited
1 after executing exactly one Swift Testing test. This is the expected recorded
M4-only drift rather than a claimed pass: prefill max absolute error 0.125,
mean error 0.011933609, exact runtime/upstream prefill token 5991, exact decode
steps 0-7, and `EQUIVALENCE_EXACT_STEPS=8`. The allow-drift setting preserves
and reports the failure; it does not relax the official correctness gate. This
exactly matches the untouched-base signature above. The 102-line, 5,366-byte
log is
`/Users/ec2-user/.senpai/native/mlxfast-cedar-20260804/roles/student-cedar-nezuko/state/openhands_state/training/62bb9af2-57a5-4d42-95d9-3270f94dd75c.log`
with SHA-256
`6f20ae92591e1312c844da19375a23f119e7d5173adae875b556462379e08e5b`.

The historical R1 evidence follows for auditability; its global-trace NO-GO is
superseded by the R2 differential-fence calibration.

# Appendix: R1 global-trace evidence (superseded)

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
