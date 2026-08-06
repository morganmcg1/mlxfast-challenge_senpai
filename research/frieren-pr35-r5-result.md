SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"ranked_ns_delta_vs_0c21dc18_pct","available":true,"value":1.0512},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

**No W&B runs exist for this result, by construction.** This track has no
training loop and no W&B project traffic: the scored artifact is a Swift
inference binary timed by `./benchmark.sh` and by the official `mlxfast`
service. Evidence is therefore ranked submission-receipt IDs plus committed
`research/*.md` and `research/*.log` paths. `wandb_run_ids` is `[]` because
zero runs were created, not because they were omitted.

- Student / PR: `maple-frieren` / PR #35, assignment
  `maple-2026-08-04j-scale-code-width`, revision **r5**
- Hypothesis and target cost: **r5-A** — the shipped correctness gate is not a
  certificate for the 4-bit lane-major NVFP4 scale-bank *representation*
  change (advisor RULE 20), so bit-identity must be established by a
  standalone bitwise oracle that carries a must-flag power control. **r5-B** —
  the already-verified lane-major stack is worth one ranked receipt; dispatch
  it and read the result against a pre-registered table. Target cost: the
  attention decode scale-plane read, 89.1 MB/step of QKV scale bytes reduced
  to a 4-bit row-base plane.
- Decision: **Mechanism confirmed on the ranked M5; promotion blocked by
  baseline-pairing noise, not by this candidate.** The bitwise oracle passed
  (1782 pairs, max ULP 0, two must-flag power controls firing 33/33), the
  ranked receipt passed all three gates, and the normalized speed measure `ns`
  came in at **+1.05 %** over the paired reference — roughly 3.8× the
  single-receipt minimum detectable effect and above the pre-registered
  strong-confirmation band. The receipt is nevertheless stamped `rejected`,
  because `officialScore` is computed against a *same-session* baseline whose
  prefill axis carries ~1.9 % run-to-run spread. This receipt drew a fast
  baseline prefill, so a genuinely faster candidate scored below the standing
  record. I am **not** resubmitting the unchanged surface to chase a better
  draw; see the recommendation at the end.
- `BASE_SHA` / candidate commit: assignment base
  `1849b376d73f69f9a6b9018619ac665ae4bceb33`; accepted advanced base
  **`20f1fb68f9b41b847c0f75c9822a10afba9aad97`** — the fifth advance across this
  assignment span, cleared in advance in PR comment 19 (2026-08-06T00:45:35Z),
  superseding the `d08ddd7b2c33e9421c7c1d894c8b00071507fd31` clearance in
  comment 18. Both clearances say **do not rebase**, so I did not. I verified the
  latest advance independently rather than trusting the commit subject:
  `git diff --name-only d08ddd7b 20f1fb68` lists exactly one file,
  `research/CURRENT_RESEARCH_STATE.md`, which is not in `editablePaths`, so the
  submitted surface is byte-identical across the advance and nothing measured
  here is invalidated. Because the advisor tree has moved on independently
  (tanjiro's `DARKBLOOM_INJECT_EMPTY_CHAIN` hunk), the surface diff against the
  newest base reads `601 insertions(+), 38 deletions(-)` rather than the
  `585 insertions(+), 17 deletions(-)` measured against my own assignment base;
  that difference is other students' work, not mine, and is exactly what the
  no-rebase contract preserves;
  candidate commit is the head of `maple-frieren/scale-code-width` at
  submission. Byte-budget checks use the fixed base
  `768bb9d4adfc2baac7d74c0008afc92d010329da`.

  The submitted surface is byte-identical to what the ranked upload actually
  carried. `HEAD` at upload time was `97457fc`; every commit added since
  (`03b2c04`, `80b4301`, `d0c1fbec`, and the commit that adds this file) touches
  only `research/`, and `git diff --stat 97457fc d0c1fbec -- Sources/ Vendor/`
  is empty. The inject-guard grep below is pasted at `d0c1fbec`; the only later
  commit adds `research/frieren-pr35-r5-result.md`, this report. The
  receipt reports its own `submissionCommitSha 4bdeaae6a85a5269951edc3b2338ba0ff6d07adf`,
  which is **not** a commit in this repository — the service synthesizes a
  commit from the uploaded file set — so no local SHA should be claimed to
  "be" the submitted commit.
- Submitted candidate files (2, both in `editablePaths`):
  - `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  - `Sources/MLXFastModel/LagunaRuntimeWeights.swift`

  `git diff --stat 1849b376 HEAD -- Sources/ Vendor/` → `2 files changed, 585
  insertions(+), 17 deletions(-)`. The surface has not moved since r4:
  `git diff --stat b3319dfb 03b2c04 -- Sources/ Vendor/` is **empty**. All r5
  work cost **zero submitted bytes** (`research/` is not in `editablePaths`).
- Supporting test or documentation files (research-only, unsubmitted):
  `research/frieren-pr35-r5a-certificate.md`,
  `research/frieren-pr35-r5a-bitwise.log`,
  `research/frieren_pr35_lanemajor_bitwise.swift`,
  `research/r5a_kernels/{lanemajor,wide}_h{48,64}.metal`,
  `research/frieren_pr35_r5a_bitwise_run.sh`,
  `research/frieren_pr35_r5a_split_gen.py`,
  `research/frieren_pr35_r5a_dump.sh`, `research/frieren-pr35-r5a-dump.patch`,
  `research/frieren-pr35-receipt-note.md`,
  `research/frieren-pr35-r4-gate-blindness.md` (erratum added).
- Assignment-scope preflight: `senpai/validate-assignment-scope.sh` clean for
  the two submitted paths; every r5 artifact is research-only.
- Editable bytes / headroom / growth (verbatim, base `768bb9d4…`):

  ```text
  editable budget OK: current=2966629/3000000 bytes headroom=33371 growth=-33355/262144 files=142 (file count is diagnostic only; base=142)
  ```

  `wc -c Sources/MLXFastModel/LagunaRuntimeModel.swift` → **521566** B, under
  the 523,000 B advisor cap and 2,722 B under the 524,288 B hard cap.
- Inject-guard grep re-run on the shipped commit, both required lines pasted
  verbatim (`git grep -n -E 'DARKBLOOM_INJECT_(DECODE_EMPTY|PREFILL_EMPTY|EMPTY_TG)'
  d0c1fbec -- Sources/MLXFastModel/LagunaRuntimeModel.swift`):

  ```text
  d0c1fbec:Sources/MLXFastModel/LagunaRuntimeModel.swift:11342:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
  d0c1fbec:Sources/MLXFastModel/LagunaRuntimeModel.swift:11345:    "DARKBLOOM_INJECT_PREFILL_EMPTY", 0)
  d0c1fbec:Sources/MLXFastModel/LagunaRuntimeModel.swift:11354:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
  ```

  Also `0`/`1` respectively for `DARKBLOOM_INJECT_DECODE_SWEEPS` (`:11332`),
  `DARKBLOOM_INJECT_SWEEP_PASSES` (`:11336`, `1`),
  `DARKBLOOM_INJECT_PREFILL_MATMULS` (`:11339`, `0`) and
  `DARKBLOOM_INJECT_EMPTY_SPREAD` (`:11350`, `1`) — the #27 instrument block is
  inert under shipped defaults.
- Dispatch compliance: `mlxfast submit --model "senpai"` verbatim, as
  specified. **The literal model value `senpai` was accepted**
  (`mlxfast submission-note` echoes `Model: senpai`), so the single permitted
  provider/model fallback was **not** used and the public note carries no
  fallback disclosure.
- Scored-path reachability evidence: the lane-major plane is read inside the
  scored decode QKV projection.
  `LagunaRuntimeModel.swift:4902` defines `lagunaDecodeNVFP4QKVR1`; its body
  branches at `:4921` (`if let lane = bank.laneMajorScales,` →
  lane-major dispatch `:4930`) before the narrow arm at `:4936` and the wide
  fallback; the **sole** call site is `:5858`, inside the decode attention
  projection reached from `prepareFusedRuntimeWeights()` (`:11211`) ←
  `LagunaRuntimeWeights.swift:637` ← `:620` `loadLibraryModel(`. The plane is
  manufactured off the hot path by `prepareNativeAffineQKVWeight()`
  (`:5592`, writes `fused.laneMajorScales` at `:5664`, sole caller `:11216`)
  and is fail-closed by the reproduction certificate
  `lagunaLaneMajorScaleBankReproducesScales` (`LagunaRuntimeWeights.swift:898-920`)
  which reverts to the wide path on any mismatch. The instrumented r5-A dump
  confirmed live traffic: 122 captured artifacts across 40 attention layers,
  8,192 rows for the 10 full-attention (h48) layers and 10,240 rows for the 30
  sliding (h64) layers, 389,120 rows total.

### Evidence

- Host, memory profile, toolchain, and thermal policy:
  `ip-10-231-2-150.ec2.internal`, `Mac16,11`, Apple **M4 Pro**, arm64, 20 GPU
  cores, **48 GiB** unified memory, macOS 26.5.2 (25F84), Apple GPU generation
  **16** (so **no `_nax` kernel selection** — the ranked M5 does select
  `_nax`). Sub-64 GiB ⇒ the low-memory startup profile is active (allocator
  management only, not a ranked code path). The 40 C thermal gate was honoured
  and never bypassed; both cooldown gates in the preflight opened at exactly
  **40.0 C** after 90 s and 100 s. All `swift` invocations passed
  `--force-resolved-versions` with `git checkout -- Package.resolved`
  afterwards.
- Exact baseline and candidate commands:

  ```bash
  # r5-A standalone bitwise oracle (five planes + three power controls)
  research/frieren_pr35_r5a_bitwise_run.sh            # -> research/frieren-pr35-r5a-bitwise.log

  # r5-A plane capture that fed the oracle (instrumented tree, reverted)
  git apply research/frieren-pr35-r5a-dump.patch
  research/frieren_pr35_r5a_dump.sh                    # -> /tmp/pr35_r5a (122 files, 72 MB)
  python3 research/frieren_pr35_r5a_split_gen.py /tmp/pr35_r5a research/r5a_kernels
  git checkout -- Sources/

  # shipped-tree preflight (paired baseline + candidate, same session)
  ./benchmark.sh --local-submit

  # ranked dispatch
  mlxfast submit --model "senpai" --note-file research/frieren-pr35-receipt-note.md
  ```

  Supervised launches: `run_training` `9b57e616-9773-4920-b859-94da9fea62fc`
  (r5-A oracle, exit 0, **2.525 s**), `8ca86fe1-57cf-4747-9c49-7ae23d5ca547`
  (plane dump, exit 0, 46.1 s, `peak_ram_gb 20.79`, `mlx_peak_gb 36.43`,
  0 divergences), `68123fbc-21f5-4f31-8f7e-035332a979ee`
  (`--local-submit`, exit 0, **428.867 s**),
  `fc5f65d4-daa1-4089-a460-3328c521147a` (first r5-A attempt, failed on a
  harness defect — see below).
- Tests and risk-based checks run, including selected-test count:
  - **r5-A standalone bitwise oracle**, 33 passes per height (1 dense +
    32 lane-isolated) × 2 kernel heights, **1,782 pairs compared**, five
    synthetic scale planes:

    | plane | construction | escaped rows (h48 / h64) | max ULP diff |
    | --- | --- | ---: | ---: |
    | P0 real | captured live planes | 14–208 / 10–187 | **0** |
    | P1 | `base(r) + ((b+l) mod 16)` | 0 / 0 | **0** |
    | P1H | one-hot spike at `l==r%32 && b==(r/32)%4` | 0 / 0 | **0** |
    | P2 | `base(r) + ((12l+7b) mod 16)` | 0 / 0 | **0** |
    | P3 | escaped rows `8 + ((7g) mod 239)` on `r%7==3` | 1170 / 1463 | **0** |

    `base(r) = 8 + (r % 190)` keeps every plane byte inside the
    representable `[8,247]` window that `laguna_tail_nvfp4_scale` requires
    (it builds a half from `bits << 7`). P1/P2 deliberately vary in **both**
    `b` and `l` rather than in `g` alone: the kernel reads `g = b*32 + l` and
    `32 ≡ 0 (mod 16)`, so a plane that is constant in `b` cannot discriminate
    a `b`-displacement — exactly the unsatisfiable-precondition class that
    voided the r4 fault ladder.
  - **Must-flag power controls** (all three fired, so the oracle is proven
    sensitive rather than merely quiet):

    | control | passes flagged | rows differing | max ULP |
    | --- | ---: | ---: | ---: |
    | P4a rotate nibbles | **33 / 33** | 267,529 (99.0 %) / 334,492 (99.0 %) | 38,828 / 38,713 |
    | P4b flip a base bit | **33 / 33** | 65 / 66 | 198 / 168 |
    | P4c single nibble | **2 / 33** (exactly the lanes that touch it) | 2 / 2 | 4 / 3 |

  - Instrument fidelity asserted against the live call site: pipelines
    reported `staticThreadgroupMemoryLength=0`,
    `maxTotalThreadsPerThreadgroup=1024`, `threadExecutionWidth=32`; geometry
    `grid ((rows/2)*64,1,1)`, `threadGroup (64,1,1)`; compile options
    `mathMode=safe`, `languageVersion=262144`, 47,412 B `metal::utils()`
    preamble — matching MLX's own
    `backend/metal/device.cpp:622-638` and `custom_kernel.cpp:71`.
  - The h48 and h64 kernel texts are byte-identical apart from the generated
    kernel name (`diff` differs only on line 54), so the second height is a
    **replication**, not independent coverage. Reported as such.
  - **`./benchmark.sh --local-submit`** on the shipped tree: full correctness
    gate, `checked_tokens=1025`, `decode_steps=1023`, `repeats=1`,
    `first_failing_case/layer/step` all null, `error ""`. Hashes
    `golden_hash f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`,
    `harness_hash 047449cbdb985609e54da6c883c3d584595d718147dc0b1253eab26669cbbd41`,
    `weights_hash aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`
    (9 files, 21,568,891,382 B).
- Correctness and serial-protocol verdict: `passed_correctness true`,
  `passed_decode_speedup_floor true`, `passed true`. The change is a pure
  **weight-representation** change prepared before the timed window; it adds
  no cache keyed on input tokens, computes logits and KV rows only for the
  tokens supplied in each invocation, advances KV by exactly the supplied
  input length, and leaves no pending future token, logits, or KV state. The
  serial non-speculative rule is satisfied by construction.
- Divergent tokens or failure category, if any: **none.** 0 divergences in the
  instrumented dump; 0 mismatches and 0 silent power controls in the r5-A
  oracle; no failing case in `--local-submit`.

  **Honest disclosure of one harness defect.** The first r5-A attempt
  (`fc5f65d4-daa1-4089-a460-3328c521147a`) *failed*, and the failure was
  mine, not the kernel's: the coverage check filled the output buffer with an
  `0xCD` sentinel and treated any surviving sentinel as an unwritten row. But
  `0xCDCD` is a legitimate bf16 value, so real outputs false-positived as
  uncovered. I replaced the single-sentinel test with a **two-fill**
  (`0xCD` then `0x37`) coverage-plus-determinism check: a row is covered iff
  both fills produce the same output. Reported `uncovered rows: 0`. The
  bit-identity result was never affected — only the coverage bookkeeping was.
- Peak RAM or generated-weight size, if relevant: `--local-submit`
  `peak_ram_gb: 21` (summary 20.728); plane dump `peak_ram_gb 20.79`,
  `mlx_peak_gb 36.43`; generated weights 21,568,891,382 B over 9 files
  (unchanged — this change alters an in-memory derived layout, not the
  checkpoint).
- Official ranking status versus correctness/floor status, if submitted:
  **All three gates PASS; ranking status `rejected` for score only.** Ranked
  submission `0d123661-66d8-4b8c-962d-28dac448fa21` (short `0d12366`),
  `createdAt 2026-08-06T00:11:58Z`, `updatedAt 2026-08-06T00:33:29Z`
  (~21.5 min on the official M5 Max).

  ```text
  status                             rejected
  rejectionReason                    score did not improve current best
  improved                           False
  officialScore                      2.52045366445076
  passed_correctness                 True
  passed_prefill_speedup_floor       True
  passed_decode_speedup_floor        True
  error                              ''
  first_failing_case/layer/step      None / None / None
  decode_seconds_per_token           0.005011932296875
  prefill_seconds_per_token          0.000191656169921875
  baseline_decode_seconds_per_token  0.013843359703125
  baseline_prefill_seconds_per_token 0.000367052978515625
  peak_ram_gb                        21
  submissionCommitSha                4bdeaae6a85a5269951edc3b2338ba0ff6d07adf
  golden_hash   be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71
  harness_hash  9d8f03583db140897adc2d247556f1dd3980bf9217303e6b8ae0fd5baab28c33
  weights_hash  aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
  ```

  Reproduce with
  `python3 research/frieren_pr35_receipt_read.py /tmp/subs_r5_final.json 0d123661`
  after refreshing the feed (`curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN"
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"`).
  Note that `officialMetrics` arrives as a JSON-encoded *string*, and the
  aggregate `passed` key is absent from it, so the three specific flags above
  are the correctness/floor evidence.

  `rejected` here is **not** a correctness failure. `rejectionReason` is
  literally "score did not improve current best". `officialScore` reproduces
  exactly from the four timing fields,
  `(0.013843359703125 / 0.005011932296875)^0.75 *
  (0.000367052978515625 / 0.000191656169921875)^0.25 = 2.52045366445076`
  (decode speedup 2.762080, prefill speedup 1.915164), which confirms it is a
  *same-session paired* score rather than a normalized one.

**Ranked M5 metrics (the evidence that counts).** Baseline column is the
pre-registered reference receipt `0c21dc18`, itself an all-gates-pass receipt of
the unchanged base tree; `ns`, `S` and `T` are the pre-registered normalized
measures defined in "M5 transfer risk" below.

| Ranked metric | Baseline `0c21dc18` | Candidate `0d123661` | Delta |
| --- | ---: | ---: | ---: |
| **`ns` (primary)** | 2.529734002 | **2.556325618** | **+1.0512 %** |
| `T` decode-step, ms | 4.3181484 | 4.2453076 | **−1.6869 %** |
| `S` prefill, ms | 98.029375 | 98.127960 | +0.1006 % |
| decode seconds/token | 0.0050840029 | 0.0050119323 | — |
| prefill seconds/token | 0.00019146362 | 0.00019165617 | — |
| `officialScore` (paired, noisy) | 2.49232051 | 2.52045366 | +1.129 % |
| `passed_correctness` | True | True | — |
| `passed_decode_speedup_floor` | True | True | — |
| `passed_prefill_speedup_floor` | True | True | — |

The pre-registered decision band was: ≥ +0.60 % on `ns` is strong confirmation.
Observed **+1.0512 %** is ~3.8× the single-receipt minimum detectable effect of
±0.278 % and above the priced range of +0.58 %…+0.67 %. `T` moved in the
predicted direction and by more than predicted; `S` is flat, as designed
(nothing in this change touches prefill).

| Local research metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.013856 | 0.009211 | 1.504x |
| prefill seconds/token | 0.000368 | 0.001140 | 0.322x |
| same-host paired estimate | — | 1.023522878707341 | — |

The paired estimate is a same-host research metric, not an official M5 score.

**Read the local prefill ratio as an artifact, not as evidence.**
`passed_prefill_speedup_floor` is `false` locally. The local "baseline"
`prefill_seconds_per_token=0.000368` and `decode_seconds_per_token=0.013856`
are pinned **official-M5 constants**, not a measurement from this 48 GiB M4
Pro; this host runs the low-memory startup profile and selects **no `_nax`
prefill kernel** at all. The assignment is explicit: *"Ignore local prefill
entirely."* The corresponding inflation of the local decode ratio (1.504×) is
the same artifact with the opposite sign and is likewise not ranked evidence.
The ranked receipt below is the only prefill and decode evidence that counts.

### Conclusion

- What happened and why: **The hypothesis held on both axes it was asked
  about — bit-identity and ranked decode speed — and the submission was still
  turned away for a reason that has nothing to do with the candidate.**

  r5-A certified the lane-major 4-bit row-base scale plane as bit-identical to
  the wide `uint8` plane: 1,782 kernel-output pairs across five plane families,
  max ULP difference 0, zero uncovered rows, and two independent must-flag
  power controls that fired on 33/33 lane-isolated passes. That closes the
  RULE 20 objection which voided r4 — the shipped correctness gate is not a
  certificate for a representation change, so a standalone oracle with a
  proven-sensitive control had to supply it.

  r5-B then spent one ranked receipt. Receipt `0d123661` passed correctness and
  both speedup floors, and moved the pre-registered normalized measure `ns`
  from 2.529734 to 2.556326, **+1.0512 %**. The decode-step component `T` fell
  1.6869 % while prefill `S` stayed flat at +0.1006 %. Both signs and both
  magnitudes are what the mechanism predicts: the change removes scale-plane
  bytes from the attention decode read and touches nothing on the prefill path.

  **Why it was rejected anyway.** `officialScore` divides candidate timings by a
  baseline measured in the same session, and those two baseline axes have very
  different noise:

  | baseline axis | stdev/mean | max/min spread | score weight | score-noise contribution |
  | --- | ---: | ---: | ---: | ---: |
  | `baseline_decode_seconds_per_token` | 0.247 % | +1.921 % | 0.75 | 0.185 % |
  | `baseline_prefill_seconds_per_token` | **1.933 %** | **+9.290 %** | 0.25 | **0.483 %** |

  So the low-weight prefill axis contributes ~2.6× more score noise than the
  high-weight decode axis. Holding this candidate's own four timings fixed and
  re-scoring it against each of the 1,046 observed gate-passing baseline
  **pairs** gives: min 2.506896, p10 2.515864, median 2.527385, p90 2.549877,
  max 2.584802. It clears the standing record of 2.552308 in **72 of 1,046
  draws (6.9 %)**. This receipt drew a fast baseline prefill
  (0.000367053, against a median of 0.000368493 and a p90 of 0.000382858), so a
  faster candidate scored low. The separation is sharp: 4/4 promotions in the
  slow-prefill tail (n=4, mean 0.000394668, +6.012 % above the cut) versus
  68/1,042 in the main mass.

  On the normalized plane, which removes the baseline draw entirely, this
  candidate is **rank 1 of 1,046** gate-passing receipts: `ns` 2.556326 against
  a next-best 2.547641 (`b6032aeb`), a margin of +0.3409 % over the whole field.
  The receipt that currently *defines* the `officialScore` record (`46eeccf0`,
  officialScore 2.552308) has `ns` of only 2.524190 — this candidate is
  **+1.27 %** faster than the record holder on the plane that does not depend on
  which baseline the session happened to draw.

  **A recorded error of my own.** My first pass at this analysis varied only
  `baseline_decode` and concluded that 0 of 1,046 draws could have promoted the
  receipt. That was wrong, and wrong in an instructive way: I resampled the
  *low-noise* axis alone and mistook its narrowness for the whole picture. The
  joint resampling above supersedes it. I have deliberately kept the flawed
  script (`research/frieren_pr35_baseline_drift.py`) in the tree rather than
  deleting it, so the mistake stays visible next to its correction.

  **Two honest consequences.** First, at ~6.9 % per attempt, resubmitting this
  identical surface until a slow-prefill baseline turns up would be
  noise-mining, not science; I have not done it and I am not going to without an
  explicit advisor decision. Second, and more importantly for the programme: the
  standing record is partly a favourable-baseline artifact, so ranking our own
  internal work by `officialScore` will systematically mis-order candidates.
- Evidence for or against the mechanism:
  - **r5-A settled the representation question.** The lane-major 4-bit
    row-base scale plane reproduces the wide `uint8` plane **bit-for-bit**
    across 1,782 kernel-output comparisons on five plane families, including
    the captured live planes and three adversarial synthetic families that
    vary in both nibble index and block index. Max ULP difference is 0
    everywhere. Because all three power controls fired — and P4c fired on
    *exactly* the 2 of 33 lanes that read the perturbed nibble — the zero is
    a measurement, not an artifact of a dead instrument. This closes the
    blind spot that RULE 20 identified and that voided r4.
  - **The shipped gate is genuinely blind to this class of change, and I can
    now say why more precisely than in r4.** A coherent scale fault of the
    right magnitude *does* flag (faults flag at decode steps 3/2/1), but
    128/128 pure **displacement** probes were silent, and a matched-magnitude
    *incoherent* control was silent 64/64 while producing an identical golden
    hash. My r4 explanation ("coherence, not magnitude") is therefore
    **retracted** in the erratum: the discriminating variable is neither
    magnitude alone nor coherence alone. A separate 5,765 s sweep did fault
    72.1–75.4 % of 389,120 rows at mean relative error 0.2311 / RMS 0.3266 /
    max 16.6× on 64 odd `L` values without changing the checked tokens. The
    gate is not a representation certificate; the standalone oracle is.
  - **The timing mechanism was screened before dispatch, not assumed.** The
    r3/r4 full-stack screen measured STACK 8.5576 vs STOCK 8.6555 ms/step
    (−97.9 µs/step, ratio 1.0114), with **deliverable B alone worth
    −28.4 µs/step**, and 0 divergences across 24 passes. The ranked receipt
    tests whether that survives on the M5.
  - **Five citations in the r4 note were mis-transcribed and are corrected in
    place** (`:5907`→`:5858`, `:11302`→`:11211`, `:5683`→`:5592`,
    `:5755`→`:5664`, `:5003`→`:4921`). I verified this was transcription
    error, not commit drift, and recorded an Erratum block rather than
    silently rewriting history.
  - **Programme-level disclosure that I owed the advisor:** the upstream
    equivalence oracle
    (`LagunaUpstreamEquivalence.swift:41` `compare`, `:74`
    `LagunaRuntimeModel(runtimeConfig)`, `:88` `eval(runtime)`, `:91`
    `newCache`) has **never** covered a single derived/fused runtime layout on
    this track. Every such layout is manufactured behind the single-caller
    chain `prepareFusedRuntimeWeights()` (`:11211`) ←
    `LagunaRuntimeWeights.swift:637` ← `:620`, which the oracle does not
    enter. That affects sibling preparers too
    (`prepareFusedSharedGateUp` `:8048`, `prepareFusedDenseGateUp` `:8086`,
    `prepareFusedRoutedGateUp` `:9740`, `prepareRoPEAngleAtlases` `:10578`,
    `prepareNativeAffineOProjWeight` `:5291`, `prepareLastPrefillProjectionWeights`
    `:5415`, `LagunaLmHeadPruner` `:10916-10958`). The advisor **withdrew**
    the one-line oracle repair, so I did not implement it; the gap is
    documented, not patched.
- Uncertainty or M5 transfer risk:
  - **Architecture.** This is an M4 Pro at Apple GPU generation 16. It does
    not select the `_nax` kernels the ranked M5 uses, so no local prefill
    number transfers, and threadgroup geometry can change sign across core
    counts. The r5-A bit-identity result is architecture-independent in the
    sense that it is a *representation* proof against the same kernel text,
    but a near-tie argmax elsewhere in the model could still differ on
    another Apple Silicon generation.
  - **Single-receipt resolution.** The minimum detectable effect for one
    receipt is **±0.278 %** on `ns`, against a priced expectation of
    **+0.58 % to +0.67 %**. A result inside ±0.28 % is noise, not a
    refutation.
  - **Pre-registered read rule** (binding, set before dispatch; `ns`, `S`, `T`
    computed from the receipt's own `decode_seconds_per_token` and
    `prefill_seconds_per_token`, never from any `*_speedup` field and never
    ranked by `officialScore`):

    ```text
    ns = (0.013890/decode_spt)^0.75 * (0.0003845/prefill_spt)^0.25
    S  = 512000 * prefill_spt                 (ms)
    T  = 1000 * decode_spt - S/128            (ms)
    ```

    Baseline frontier receipt **`0c21dc18`: T 4.3181 ms, S 98.029 ms,
    ns 2.52973**. Elasticities `d ln score/d ln T = 0.638`,
    `d ln S = 0.362`.

    | observed Δ`ns` vs `0c21dc18` | reading |
    | --- | --- |
    | ≥ +0.60 % | strong confirmation |
    | +0.15 % … +0.60 % | report only; do **not** resubmit |
    | −0.28 % … +0.15 % | inside single-receipt noise |
    | < −0.28 % | report immediately |

  - **Byte headroom is the binding constraint on any follow-up**, not compute:
    33,371 B of surface headroom remain and
    `LagunaRuntimeModel.swift` is 2,722 B under the hard per-file cap.
- Smallest useful next action: **merge this surface and start the queued 4-bit
  arm.** The read against the table above is settled — Δ`ns` = **+1.0512 %**,
  which is in the strong-confirmation band, so no replicate of this measurement
  is warranted. The single cheapest thing that would change the programme's
  decisions is to switch internal ranking from `officialScore` to `ns`; that
  costs one script that is already in the tree
  (`research/frieren_pr35_ns_leaderboard.py`) and no GPU time.
- Recommendation: **Merge the surface on the strength of the normalized result;
  do not resubmit it unchanged; and stop ranking our own work by
  `officialScore`.**

  1. **Merge.** The mechanism is certified bit-identical by a standalone oracle
     with proven-sensitive power controls, and it is the fastest gate-passing
     receipt of 1,046 on the normalized plane. `rejected` in this case means
     only "did not beat the current best score", and the score it lost to is
     itself 1.27 % *slower* on `ns`. Waiting for an `accepted` stamp before
     merging would gate a confirmed win on a coin flip.
  2. **Do not resubmit unchanged.** ~6.9 % promotion probability per attempt
     from baseline draw alone. Repeated identical submissions to catch a
     slow-prefill baseline is noise-mining, and I am explicitly leaving that as
     an advisor decision rather than taking it.
  3. **Rank internally by `ns`, not `officialScore`.** This is the finding with
     the broadest reach beyond my own PR. The baseline prefill axis carries
     1.93 % spread at 0.25 weight, which is ~2.6× the score noise of the 0.75
     weight decode axis. Any internal comparison that uses `officialScore`
     across sessions is reading baseline luck as candidate merit — and the
     current record holder is a live example. If a candidate must be judged by
     `officialScore`, judge it by the *distribution* over observed baseline
     pairs (`research/frieren_pr35_baseline_modes.py`), not by the one draw it
     happened to get.
  4. **Spend the next receipt on the 4-bit arm, not on this one.** It is
     structural rather than empirical, roughly 6× this effect size, and byte
     headroom (33,371 B) rather than compute is what will constrain it.

### Suggested follow-ups (not implemented)

1. **Group-32 pairwise-constancy 4-bit scale arm** — the largest remaining
   item I found, and it is *structural*, not empirical.
   `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h:2186-2205`
   (`fp_quantize`, `group_size == 16`) predicates lines `2192-2194` on
   `tidx.x`, the **global grid x index**, under a 1-D dispatch
   (`quantized.cpp:2455-2478`, `per_thread=1`, `grid_dims=(nthreads,1,1)`).
   Therefore `scale[2k] == scale[2k+1]` bit-exactly for *any* weights — this
   is a property of MLX's quantizer, not of this checkpoint. The JIT twins
   agree (`mlx-generated/fp_quantized.cpp:2349-2351`,
   `mlx-generated/metal/fp_quantized.h:1850-1852`) and there is **no `_nax`
   override of `fp_quantize`**, so the M5 sees the same structure. Exploiting
   it would take the attention scale-plane read from 89.1 MB/step to
   ~23.1 MB/step, about **3.7 % of the decode budget** — roughly 6× the
   effect this receipt is testing. The one hazard is real and must be
   reproduced bit-exactly: **89 exceptions at `g=0`**, which are a first-span
   exception replicated across 120 independent q/k/v dispatches. Supporting
   census facts: constant-quadruple fraction 537,269/12,373,312 = 4.3422 %;
   80.31 % of plane codes are E4M3 subnormals (1..7); the transform never
   computes scales (`Sources/MLXFastTransform/Transform.swift:69`,
   `LagunaCheckpointValidation.swift:33`). I deliberately kept the mechanism
   out of the public submission note and hold the derivation in
   `research/` only, since the same structure implies an optimization that is
   queued as separate work.
2. **`o_proj` 256-entry float LUT as an instruction-issue discriminator** —
   held as Ask 2 from r4; would separate a bandwidth-bound from an
   issue-bound reading of the remaining attention decode cost.
3. **Oracle coverage for derived runtime layouts** — the gap documented above
   is programme-wide, not specific to PR #35. The advisor withdrew the
   one-line repair, but every future representation or layout change on this
   track will need its own standalone certificate until something covers
   `prepareFusedRuntimeWeights()`.

I did **not** spend time on the routed-expert scale census: another student
owns it.
