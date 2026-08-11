# Cedar C2 frozen contingency dispatch packet

> **SUPERSEDED — NEVER DISPATCH THIS OLD-BASE CANDIDATE.** The promoted `cdcd091` / `4ea72c3b` frontier is now the mandatory base. C2 remains immutable historical evidence only; no gate, queue state, or authorization can reactivate the commands preserved below.

## Mandatory promoted-frontier hold

This packet was made dispatch-ready against frozen base `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`, then superseded on 2026-08-11 by:

| Mandatory frontier item | Exact value |
|---|---|
| Promoted receipt | `cdcd0918-0002-45b0-a14b-81f34c40a398` |
| Organizer commit | `4ea72c3b28873fca23b12b6f33193a2eeb5042f8` |
| Research-fork snapshot | `f52be6aa9cefabc74f0f369d29d54e0686284aac` |
| Research-fork tree | `8a82e90dc7f0332aabbdee4b4c050a0cfa90b059` |
| Official score | `2.6195531094824` |
| Official decode | `203.93695 tok/s` |
| Official prefill | `5314.29504 tok/s` |

The promoted archive is executable-identical to rejected receipt `41c1b5d` except for a comment. Its official draw moved prefill about `+3.27%` and decode about `-0.31%`; therefore the full promotion margin is not causal evidence for N1. The mandatory snapshot nevertheless owns the current submitted surface. Its M5/NAX-specific behavior also means an M4 no-effect observation would not reject a future composition.

All old-base C2 correctness evidence below remains valid evidence about the exact frozen C2 tree. Any old-base timing, gate, budget-headroom interpretation, or composition claim is **stale relative to organizer commit `4ea72c3b`** and cannot authorize a draw. The old static budget remains historical only; a future candidate needs a fresh budget against the updated advisor base.

### Seven-file overlap audit

The promoted `27cb47b..f52be6aa` delta changes these exact submitted files: `LagunaRuntimeModel.swift`, `LagunaRuntimeWeights.swift`, `SwitchLayers.swift`, `fp_quantized_nax.cpp`, `jit_kernels.cpp`, `fp_quantized_nax.h`, and `quantized.cpp`. C2 also changes `LagunaRuntimeModel.swift`, so treating the old Runtime blob as current would overwrite promoted behavior even though the LM-head row-32 mechanism itself is separate.

| Required audit region | Mandatory `f52be6aa` behavior | C2 disposition |
|---|---|---|
| Route-sort | `SwitchLayers.swift` has the fused sorter publish one exact 257-entry expert-prefix table. | Preserve exactly; C2 must not add another producer or restore the pre-N1 sorter. |
| Expert index / carrier | The sorter returns the dedicated offset-64, zero-stride `UInt32` carrier while retaining its contiguous backing payload. | Preserve exact marker, flags, capacity, and fallback semantics; do not normalize or imitate it. |
| Pairwise scales | Runtime admission and `quantized.cpp` require the certified gate/up and down pairwise-scale layouts. | Preserve the promoted guards and carriers; row-32 has no license to alter them. |
| Gather geometry | `quantized.cpp` makes EG256 the no-override expert gather geometry. | Preserve EG256; do not evaluate C2 against the historical geometry as if it were current. |
| Warmup | `LagunaRuntimeWeights.swift` warms admitted 512-token EB1 and a declined 129-token EB0 shape before decode warmup. | Preserve both identities and the declined-shape warmup. |
| Gather-QMM bounds | Backend dispatch validates the exact sidecar contract and keys distinct `_eb_0` / `_eb_1` pipelines. | Preserve the validation and identities; do not create a parallel bounds path. |
| Lower-bound work | Both generated and header NAX consumers reuse the sorter prefixes, avoiding repeated lower-bound searches and barriers. | **Do not duplicate N1**, reintroduce those searches, or claim their removal as C2 work. |

### Only permitted future path

A future composition requires a **fresh advisor-owned assignment after the updated advisor-base merge**. It must begin from the exact promoted submitted snapshot, independently rederive any row-32 experiment from its reviewed source, preserve N1 across a source-level three-way audit, produce a new commit/tree/manifest, pass fresh scope and editable-budget checks, and obtain fresh correctness plus current-base M5 composition evidence. Do not rebase, amend, cherry-pick, reconstruct, or copy this held candidate. Until a new packet names that new identity and the advisor authorizes it, there is no supported invocation.

## Frozen identity

| Item | Frozen value |
|---|---|
| Candidate PR | [#721](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/721) |
| Candidate commit | `5b5e73a469a636f28f37a8857b3f58c3bc27f620` |
| Candidate tree | `e266fb28a3db32af72ea0e8a27784d1e2988c18d` |
| Tree-identical tested commit | `f45d5bb2587551dbc203f5ee12e8c7b10a89f776` |
| Frozen official base | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| Frozen official-base tree | `99cd398dc28b424c1e2bb766d210affa58f17d54` |
| Advisor acceptance base | `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4` |
| Current leader at packet preparation | receipt `cc6ddc1`, score `2.61650354381456` |

The exact objects above were independently read from the candidate and frozen-base Git objects. The candidate descends from the frozen official base. Relative to that frozen base, exactly the following submitted files change:

| Submitted file | Git blob | SHA-256 | Bytes |
|---|---|---:|---:|
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | `7738d670b5570159284aae626b5a5b63c08f371e` | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | 60,069 |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | 511,892 |

Independent exact-object budget verification passed: `2,997,654 / 3,000,000` submitted bytes, `2,346` bytes headroom, and `13,805 / 262,144` bytes growth. The 142-file count is diagnostic only.

## Intended mechanism and established deterministic evidence

C2 is the exact e27 runtime with production shared-R1 plus the organizer's exact row-32 LM-head implementation from `0101733e2d3c2629a04d86c24f236a43ef38bc33`. It adds no prompt specialization, speculative work, or cross-request state.

Established evidence attached to PR #721:

- Exact-C2 and unchanged-current-base upstream-equivalence controls used `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh` on the same 48-GiB M4.
- Both controls produced prefill runtime/upstream token `5991/5991`, max absolute logit error `0.125`, and mean absolute error `0.011933609`; candidate-minus-control mean delta was exactly zero.
- Both controls produced decode tokens `509, 902, 5991, 509, 902, 5991, 509, 902`; every decode step had max/mean error `0/0`. This classified the nonzero prefill value as matched non-M5 host/frontier drift, not a C2 delta.
- The row-32 fixture job passed one real test suite and five full-shape dense, zero-candidate, sparse-boundary, refined-reference, and survivor-reject cases.
- `./benchmark.sh --local-submit` exited zero with `passed=true`, `passed_correctness=true`, `1,025` checked steps, `max_abs_diff=0`, and peak RAM `21 GB`.
- Scope, ancestry, exact two-file diff, static budget, `Package.resolved`, and worktree cleanliness passed. The final candidate tree is identical to the tested commit tree.
- M4 timing diagnostics are not an authoritative M5 primary comparison. C2 has no official paired M5 metric and no W&B run; W&B is N/A for deterministic Swift/Metal preflight.

## Retired historical release predicate

The clauses below explain the packet's former contingency routing. They are retained for provenance only and can no longer authorize this old-base commit. Even complete historical gate, queue, and authorization evidence means **do not dispatch** after the mandatory frontier move.

1. C1 Gate B explicitly selects the row-32 contingency represented by exact commit `5b5e73a469a636f28f37a8857b3f58c3bc27f620`. The release evidence must name this exact commit; do not infer selection from a generic “C2” message.
2. PR #723 records the shared official queue as idle immediately before dispatch.
3. The advisor explicitly authorizes one official draw of this exact commit after seeing the Gate B and queue evidence.
4. The candidate, frozen-base snapshot, note option, and submitted hashes pass every check below.

Record the immutable release evidence before running any submission command:

| Required authority evidence | Value to record |
|---|---|
| Gate B source URL / receipt | `<REQUIRED>` |
| Gate B observed value and verdict | `<REQUIRED>` |
| Exact candidate named by release | `5b5e73a469a636f28f37a8857b3f58c3bc27f620` |
| PR #723 queue-idle evidence URL | `<REQUIRED>` |
| Queue-idle observation timestamp UTC | `<REQUIRED>` |
| Advisor authorization URL | `<REQUIRED>` |
| Advisor authorization timestamp UTC | `<REQUIRED>` |
| Authorized dispatcher | `<REQUIRED>` |

## Preservation rule

Preserve the immutable commit, tree, manifest, and completed evidence above without modification. **Never dispatch, rebase, amend, reconstruct, cherry-pick, squash, merge new content into, or copy these candidate changes onto a fresh commit.** The mandatory-base move permanently retires this identity from submission. A future experiment needs a new advisor assignment and a separately derived current-base identity; this packet cannot authorize it.

## Archived pre-dispatch checklist — do not execute

This checklist records the verification contract that applied before `cdcd091` became mandatory. Do not perform it as a prelude to submission: its frozen-base checks must now fail the current-frontier guard, and no historical pass can overcome that mismatch.

- [ ] `git rev-parse HEAD` is exactly `5b5e73a469a636f28f37a8857b3f58c3bc27f620`.
- [ ] `git rev-parse 'HEAD^{tree}'` is exactly `e266fb28a3db32af72ea0e8a27784d1e2988c18d`.
- [ ] `git merge-base --is-ancestor 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 HEAD` exits zero.
- [ ] `git diff --quiet` and `git diff --cached --quiet` exit zero. No submitted path is dirty, untracked, ignored, `skip-worktree`, or `assume-unchanged`.
- [ ] `git diff --name-only 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 HEAD` intersects the submitted surface in exactly the two manifest paths above.
- [ ] `git show HEAD:Sources/MLXFastModel/LagunaRuntimeModel.swift | shasum -a 256` equals the manifest hash.
- [ ] `git show HEAD:Sources/MLXFastModel/LagunaLmHeadPrune.swift | shasum -a 256` equals the manifest hash.
- [ ] `senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` reproduces a passing budget. Any value above a cap stops dispatch.
- [ ] `bash -n senpai/submit-official.sh` exits zero.
- [ ] The current `mlxfast` skill/help still recognizes `--note-file`; the note is valid public Markdown between 5 KiB and 100 KiB. An absent or renamed option stops dispatch rather than silently dropping the note.
- [ ] The filled note contains no `<REQUIRED>` placeholders and records the exact identity, checks, gate, queue state, authorization, and mechanism.
- [ ] Gate B evidence names this exact commit and satisfies the release predicate.
- [ ] PR #723 queue-idle evidence is current; any contention or concurrent official run stops dispatch.
- [ ] Explicit advisor authorization for this exact commit and one draw is present. Generic campaign approval is insufficient.
- [ ] The wrapper's refresh of `origin/main` must confirm that the frozen base's `benchmark.json` and submitted snapshot still match current `origin/main`. A mismatch stops dispatch; never bypass the wrapper.
- [ ] No `--model` argument is present. The wrapper owns the `senpai` campaign attribution.
- [ ] The dispatcher has reviewed the no-retry rule below before the single invocation.

## Archived public note-file template — do not use

This block is retained only as the historical old-base note contract. Do not copy, fill, publish, or submit it. Any future current-base experiment requires a fresh advisor-owned assignment and a newly derived note.

```markdown
# Cedar C2 official M5 submission note

> **SUPERSEDED OLD-BASE DRAFT — NEVER SUBMIT.** This candidate predates mandatory leader receipt `cdcd0918-0002-45b0-a14b-81f34c40a398` and cannot be authorized by completing placeholders.

## Status and provenance

- Dispatch status: superseded; official submission prohibited
- Candidate label: Cedar C2 — e27 + production shared-R1 + exact organizer row-32 LM head
- Candidate PR: https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/721
- Candidate commit: `5b5e73a469a636f28f37a8857b3f58c3bc27f620`
- Candidate tree: `e266fb28a3db32af72ea0e8a27784d1e2988c18d`
- Tree-identical tested commit: `f45d5bb2587551dbc203f5ee12e8c7b10a89f776`
- Frozen official base: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
- Frozen official-base tree: `99cd398dc28b424c1e2bb766d210affa58f17d54`
- Ranked leader observed before dispatch: receipt `cc6ddc1`, score `2.61650354381456`
- Dispatch UTC: `<REQUIRED>`
- Authorized dispatcher: `<REQUIRED>`

This is the previously audited immutable C2 candidate. It was not rebased, amended, reconstructed, squashed, or copied to a fresh commit for dispatch. The campaign wrapper supplies model attribution `senpai`; no `--model` option was passed by the operator.

## Intended mechanism

The candidate composes the e27 runtime, production shared-R1, and the organizer's exact row-32 LM-head packing implementation from commit `0101733e2d3c2629a04d86c24f236a43ef38bc33`. Row-32 retains the audited exact-tail arithmetic and ownership geometry. The mechanism is input-independent kernel/layout work; it does not hardcode prompts, tokens, fixtures, or answers, and it does not add speculative tokens, cross-request prediction, or memoization.

## Immutable submitted manifest

| Submitted file | Git blob | SHA-256 | Bytes |
|---|---|---|---:|
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | `7738d670b5570159284aae626b5a5b63c08f371e` | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | 60,069 |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | 511,892 |

Independent dispatch-time verification:

- Observed `HEAD`: `<REQUIRED; MUST EQUAL 5b5e73a469a636f28f37a8857b3f58c3bc27f620>`
- Observed tree: `<REQUIRED; MUST EQUAL e266fb28a3db32af72ea0e8a27784d1e2988c18d>`
- Frozen-base ancestry: `<REQUIRED: PASS>`
- Exact submitted diff paths: `<REQUIRED: PASS; LIST BOTH>`
- Runtime SHA-256: `<REQUIRED; MUST MATCH ABOVE>`
- LM-head SHA-256: `<REQUIRED; MUST MATCH ABOVE>`
- Submitted surface clean: `<REQUIRED: PASS>`
- `Package.resolved` clean: `<REQUIRED: PASS>`

## Static contract and budget

Independent packet preparation measured `2,997,654 / 3,000,000` submitted bytes, `2,346` bytes headroom, and `13,805 / 262,144` bytes growth. The candidate changed exactly the two manifest files relative to the frozen official base. The dispatch-time budget command reported: `<REQUIRED; PASTE PASSING SUMMARY>`. The wrapper's refreshed-base snapshot check reported: `<REQUIRED: PASS>`. Any differing or failing value would have stopped dispatch.

## Established deterministic correctness evidence

PR #721 records these completed checks for the immutable tree:

1. A row-32 fixture suite ran one real test and passed five full-shape cases: dense, zero-candidate, sparse boundaries, refined exact reference, and refined survivor reject.
2. Same-host unchanged-base and exact-C2 controls used `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh`. Both produced prefill token `5991/5991`, max absolute error `0.125`, and mean absolute error `0.011933609`. C2-minus-base mean delta was exactly zero. Both produced decode tokens `509, 902, 5991, 509, 902, 5991, 509, 902`, with max/mean error `0/0` at every step. The matched prefill discrepancy was classified as non-M5 host/frontier drift rather than candidate-induced divergence.
3. `./benchmark.sh --local-submit` exited zero with `passed=true`, `passed_correctness=true`, `1,025` checked steps, `max_abs_diff=0`, and peak RAM `21 GB`.
4. Exact two-path scope, ancestry, budget, clean `Package.resolved`, and clean worktree passed. Final commit `5b5e73a` is tree-identical to tested commit `f45d5bb`.

These are deterministic preflight facts, not an official performance claim. The M4 low-memory timing diagnostics are not used as an authoritative M5 primary comparison. C2 had no official paired M5 metric before this draw. Deterministic Swift/Metal work has W&B: N/A. Contextual ranked runs, not candidate evidence: https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq and https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ut3wdjct .

## Gate, queue, and authorization

- Release predicate: C1 Gate B explicitly selected the row-32 contingency represented by exact commit `5b5e73a469a636f28f37a8857b3f58c3bc27f620`.
- Gate B evidence URL / receipt: `<REQUIRED>`
- Gate B observed value and explicit verdict: `<REQUIRED>`
- Exact candidate named by gate routing: `<REQUIRED; MUST MATCH COMMIT>`
- PR #723 queue-idle evidence URL: `<REQUIRED>`
- Queue-idle observation UTC: `<REQUIRED>`
- Advisor authorization URL: `<REQUIRED>`
- Advisor authorization UTC: `<REQUIRED>`
- Authorization scope: `<REQUIRED; MUST SAY ONE DRAW OF THIS EXACT COMMIT>`

## Archived dispatch record — no invocation permitted

The historical command text was `senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c2-submission-note.md`. It is recorded only to identify this retired packet and must never be run. Mandatory leader receipt `cdcd0918-0002-45b0-a14b-81f34c40a398` makes the frozen base invalid, so the wrapper must reject it and must not be bypassed.

- Dispatch outcome: `N/A — prohibited; no invocation`
- Unsupported-`senpai` fallback: `N/A — no first invocation and no fallback`

## Archived expected receipt schema

No receipt should exist for this old-base candidate. The historical fields below remain unfilled evidence of the former contract; they cannot authorize monitoring, adjudication, retry, or submission. A future experiment must establish same-session paired M5 evidence under a fresh current-base assignment.

_This archived note was generated by an AI agent (OpenHands) on behalf of the research team._
```

## Archived unsupported invocation — do not run

The following text identifies the retired packet only; it is not a supported command:

```text
senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c2-submission-note.md
```

Running it is prohibited. The base predates mandatory promoted snapshot `f52be6aa9cefabc74f0f369d29d54e0686284aac`, and the wrapper should reject it. Do not bypass the wrapper or add any model override.

## Archived no-retry rule

There must be no first invocation of this packet, therefore no retry or fallback can be authorized. Any future experiment requires a fresh advisor-owned assignment on the current base.

## Archived receipt adjudication schema — do not populate

No old-base receipt should exist. The blank table is retained only to preserve the former evidence contract; it must not be monitored, completed, or used for a disposition.

| Receipt field | Recorded value | Source / calculation | Verdict |
|---|---|---|---|
| Submission ID and URL | `N/A` | Submission prohibited | — |
| Immutable candidate commit/tree | `5b5e73a469a636f28f37a8857b3f58c3bc27f620` / `e266fb28a3db32af72ea0e8a27784d1e2988c18d` | Historical manifest | stale |
| Candidate raw decode (ms/token) | `N/A` | No official draw | — |
| Candidate raw prefill (ms/token) | `N/A` | No official draw | — |
| Paired baseline decode (ms/token) | `N/A` | No official draw | — |
| Paired baseline prefill (ms/token) | `N/A` | No official draw | — |
| Decode speedup | `N/A` | No official draw | — |
| Decode component floor | `N/A` | No official draw | — |
| Prefill speedup | `N/A` | No official draw | — |
| Prefill component floor | `N/A` | No official draw | — |
| Correctness | historical local evidence only | PR #721 | non-authorizing |
| Error | `N/A` | No official draw | — |
| Weighted score | `N/A` | No official draw | — |
| Promoted frontier before draw | `f52be6aa9cefabc74f0f369d29d54e0686284aac` | Mandatory leader snapshot | blocks draw |
| Promoted frontier after draw | `N/A` | No official draw | — |
| Ranking status | `N/A` | No official draw | — |
| Final disposition | retired old-base evidence | Mandatory frontier mismatch | never dispatch |

These fixed archival values document that no adjudication occurred.
