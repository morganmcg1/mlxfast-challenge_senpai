# Cedar C3 frozen contingency dispatch packet

> **SUPERSEDED — NEVER DISPATCH THIS OLD-BASE CANDIDATE.** The promoted `cdcd091` / `4ea72c3b` frontier is now the mandatory base. C3 remains immutable historical evidence only; no gate, queue state, or authorization can reactivate the commands preserved below.

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

All old-base C3 correctness evidence below remains valid evidence about the exact frozen C3 tree. Any old-base timing, Gate A, budget-headroom interpretation, or composition claim is **stale relative to organizer commit `4ea72c3b`** and cannot authorize a draw. In particular, the historical 75-byte headroom is not evidence that a current-base composition fits.

### Seven-file overlap audit

The promoted `27cb47b..f52be6aa` delta changes these exact submitted files: `LagunaRuntimeModel.swift`, `LagunaRuntimeWeights.swift`, `SwitchLayers.swift`, `fp_quantized_nax.cpp`, `jit_kernels.cpp`, `fp_quantized_nax.h`, and `quantized.cpp`. C3 also changes `LagunaRuntimeModel.swift`, so treating the old Runtime blob as current would overwrite promoted behavior. Its separate `o_proj` `rps=2` geometry must not be confused with N1's expert-gather geometry.

| Required audit region | Mandatory `f52be6aa` behavior | C3 disposition |
|---|---|---|
| Route-sort | `SwitchLayers.swift` has the fused sorter publish one exact 257-entry expert-prefix table. | Preserve exactly; C3 must not add another producer or restore the pre-N1 sorter. |
| Expert index / carrier | The sorter returns the dedicated offset-64, zero-stride `UInt32` carrier while retaining its contiguous backing payload. | Preserve exact marker, flags, capacity, and fallback semantics; do not normalize or imitate it. |
| Pairwise scales | Runtime admission and `quantized.cpp` require the certified gate/up and down pairwise-scale layouts. | Preserve the promoted guards and carriers; neither row-32 nor `o_proj` may alter them. |
| Gather geometry | `quantized.cpp` makes EG256 the no-override expert gather geometry. | Preserve EG256. C3's `o_proj` `rps=2` is an attention output-projection geometry, not an expert gather control. |
| Warmup | `LagunaRuntimeWeights.swift` warms admitted 512-token EB1 and a declined 129-token EB0 shape before decode warmup. | Preserve both identities and the declined-shape warmup. |
| Gather-QMM bounds | Backend dispatch validates the exact sidecar contract and keys distinct `_eb_0` / `_eb_1` pipelines. | Preserve the validation and identities; do not create a parallel bounds path. |
| Lower-bound work | Both generated and header NAX consumers reuse the sorter prefixes, avoiding repeated lower-bound searches and barriers. | **Do not duplicate N1**, reintroduce those searches, or claim their removal as C3 work. |

### Only permitted future path

A future composition requires a **fresh advisor-owned assignment after the updated advisor-base merge**. It must begin from the exact promoted submitted snapshot, independently rederive any row-32 and `o_proj` experiment from reviewed sources, preserve N1 across a source-level three-way audit, produce a new commit/tree/manifest, pass fresh scope and editable-budget checks, and obtain fresh correctness plus current-base M5 composition evidence. Do not rebase, amend, cherry-pick, reconstruct, repeat comment reclaim from, or copy this held candidate. Until a new packet names that new identity and the advisor authorizes it, there is no supported invocation.

## Frozen identity

| Item | Frozen value |
|---|---|
| Candidate PR | [#722](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/722) |
| Candidate commit | `fb8b4194d669e9122bf93f2d985439001abb31dc` |
| Candidate tree | `a453d532f6d8b46d384a442b7cd89135e4e62c59` |
| Tree-identical tested commit | `68e19ccfdedc6ba161fe41e1a29dea586e5ea8bd` |
| Frozen official base | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| Frozen official-base tree | `99cd398dc28b424c1e2bb766d210affa58f17d54` |
| Advisor acceptance base | `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4` |
| Current leader at packet preparation | receipt `cc6ddc1`, score `2.61650354381456` |

The exact objects above were independently read from the candidate and frozen-base Git objects. The candidate descends from the frozen official base. Relative to that frozen base, exactly the following submitted files change:

| Submitted file | Git blob | SHA-256 | Bytes |
|---|---|---:|---:|
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | `7738d670b5570159284aae626b5a5b63c08f371e` | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | 60,069 |
| `Sources/MLXFastModel/LagunaOProjGeometry.swift` | `ae47f9911a7d8372cd14eecaaaaf58425fb32ea2` | `6145acfbfd3c08aed9850ef0d87327d80875467a8bee33cfcb5d0140cf8bfadb` | 7,035 |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | `33e0dcc678e6bae69bcb16d56c4090015c7a44c7` | `8dcd63ed8cca09b6cd2846617fc468d7aab763546a0de05f4fdffa4bea9afc77` | 507,128 |

Independent exact-object budget verification passed: `2,999,925 / 3,000,000` submitted bytes, only `75` bytes headroom, and `16,076 / 262,144` bytes growth. The 143-file count is diagnostic only. This arm is especially fail-closed: any byte drift can invalidate the static limit.

## Intended mechanism and established deterministic evidence

C3 is exact C2 plus only Maple PR #707's exact `o_proj` `rps=2` port from `e5acc163b31d7ead7392e0f0ef010a79be6084e2`. It excludes `gate_sp` and every other Maple mechanism. Static room was recovered only by removing proven comments: 5,310 Runtime bytes total, including the 2,892-byte nonce ledger and 2,418 bytes from 30 catalogued comment ranges, while preserving newline count and executable content.

Established evidence attached to PR #722:

- Source-hash reconstruction and a three-way audit confirmed exact C2 plus exact `rps=2` o_proj. Shared-R1 and o_proj Runtime hunks are disjoint; row-32 is separate; o_proj symbols reach scored kernel construction, dispatch, and grid geometry.
- The row-32 fixture job passed one real test suite and five full-shape dense, zero-candidate, sparse-boundary, refined-reference, and survivor-reject cases.
- `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh` ran one nonzero test. All eight decode steps matched tokens and logits exactly with max/mean `0/0`; prefill token matched with M4 max `0.125` and mean `0.011933609`, identical to the fresh same-host unchanged-base control from PR #721.
- `./benchmark.sh --local-submit` reported `passed=true`, correctness `1,025/1,025`, `max_abs_diff=0`, runtime `115.396s`, and peak RAM `21 GB`.
- Scope, official/advisor/assignment ancestry, exact three-file diff, budget, `Package.resolved`, and clean worktree passed. Final candidate and tested commit are tree-identical.
- M4 timing diagnostics do not adjudicate this M5 geometry class. C3 has no official Gate A receipt, no paired M5 primary metric, and no W&B run; W&B is N/A for deterministic staging.

## Retired historical release predicate

The clauses below explain the packet's former contingency routing. They are retained for provenance only and can no longer authorize this old-base commit. Even complete historical gate, queue, and authorization evidence means **do not dispatch** after the mandatory frontier move.

1. An authoritative Maple r122 Gate A receipt reports the candidate raw decode leg at or below `4.905 ms/token`, with correctness and required receipt health intact.
2. Gate routing explicitly selects exact C3 commit `fb8b4194d669e9122bf93f2d985439001abb31dc`; do not infer selection from a generic o_proj message.
3. PR #723 records the shared official queue as idle immediately before dispatch.
4. The advisor explicitly authorizes one official draw of this exact commit after seeing Gate A and queue evidence.
5. The candidate, frozen-base snapshot, note option, and submitted hashes pass every check below.

Record the immutable release evidence before running any submission command:

| Required authority evidence | Value to record |
|---|---|
| Maple r122 Gate A receipt URL / ID | `<REQUIRED>` |
| Raw candidate decode (ms/token) | `<REQUIRED; MUST BE <= 4.905>` |
| Gate receipt correctness / error / floors | `<REQUIRED>` |
| Gate A explicit verdict | `<REQUIRED: PASS>` |
| Exact candidate named by release | `fb8b4194d669e9122bf93f2d985439001abb31dc` |
| PR #723 queue-idle evidence URL | `<REQUIRED>` |
| Queue-idle observation timestamp UTC | `<REQUIRED>` |
| Advisor authorization URL | `<REQUIRED>` |
| Advisor authorization timestamp UTC | `<REQUIRED>` |
| Authorized dispatcher | `<REQUIRED>` |

## Preservation rule

Preserve the immutable commit, tree, manifest, and completed evidence above without modification. **Never dispatch, rebase, amend, reconstruct, cherry-pick, squash, merge new content into, repeat comment reclaim from, reapply, or copy these candidate changes onto a fresh commit.** The mandatory-base move permanently retires this identity from submission. A future experiment needs a new advisor assignment and a separately derived current-base identity; this packet cannot authorize it.

## Archived pre-dispatch checklist — do not execute

This checklist records the verification contract that applied before `cdcd091` became mandatory. Do not perform it as a prelude to submission: its frozen-base checks must now fail the current-frontier guard, and no historical pass can overcome that mismatch.

- [ ] `git rev-parse HEAD` is exactly `fb8b4194d669e9122bf93f2d985439001abb31dc`.
- [ ] `git rev-parse 'HEAD^{tree}'` is exactly `a453d532f6d8b46d384a442b7cd89135e4e62c59`.
- [ ] `git merge-base --is-ancestor 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 HEAD` exits zero.
- [ ] `git diff --quiet` and `git diff --cached --quiet` exit zero. No submitted path is dirty, untracked, ignored, `skip-worktree`, or `assume-unchanged`.
- [ ] `git diff --name-only 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 HEAD` intersects the submitted surface in exactly the three manifest paths above.
- [ ] `git show HEAD:Sources/MLXFastModel/LagunaRuntimeModel.swift | shasum -a 256` equals the manifest hash.
- [ ] `git show HEAD:Sources/MLXFastModel/LagunaLmHeadPrune.swift | shasum -a 256` equals the manifest hash.
- [ ] `git show HEAD:Sources/MLXFastModel/LagunaOProjGeometry.swift | shasum -a 256` equals the manifest hash.
- [ ] `senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` reproduces a passing budget with exactly 75 bytes headroom. Any drift or failure stops dispatch.
- [ ] `bash -n senpai/submit-official.sh` exits zero.
- [ ] The current `mlxfast` skill/help still recognizes `--note-file`; the note is valid public Markdown between 5 KiB and 100 KiB. An absent or renamed option stops dispatch rather than silently dropping the note.
- [ ] The filled note contains no `<REQUIRED>` placeholders and records exact identity, checks, gate, queue state, authorization, comment-only reclaim, and mechanism.
- [ ] Gate A evidence is authoritative, has raw candidate decode `<= 4.905 ms/token`, and explicitly selects this exact commit.
- [ ] PR #723 queue-idle evidence is current; any contention or concurrent official run stops dispatch.
- [ ] Explicit advisor authorization for this exact commit and one draw is present. Generic campaign approval is insufficient.
- [ ] The wrapper's refresh of `origin/main` must confirm that the frozen base's `benchmark.json` and submitted snapshot still match current `origin/main`. A mismatch stops dispatch; never bypass the wrapper.
- [ ] No `--model` argument is present. The wrapper owns the `senpai` campaign attribution.
- [ ] The dispatcher has reviewed the no-retry rule below before the single invocation.

## Archived public note-file template — do not use

This block is retained only as the historical old-base note contract. Do not copy, fill, publish, or submit it. Any future current-base experiment requires a fresh advisor-owned assignment and a newly derived note.

```markdown
# Cedar C3 official M5 submission note

> **SUPERSEDED OLD-BASE DRAFT — NEVER SUBMIT.** This candidate predates mandatory leader receipt `cdcd0918-0002-45b0-a14b-81f34c40a398` and cannot be authorized by completing placeholders.

## Status and provenance

- Dispatch status: superseded; official submission prohibited
- Candidate label: Cedar C3 — exact C2 + Maple o_proj rps=2 + comment-only byte reclaim
- Candidate PR: https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/722
- Candidate commit: `fb8b4194d669e9122bf93f2d985439001abb31dc`
- Candidate tree: `a453d532f6d8b46d384a442b7cd89135e4e62c59`
- Tree-identical tested commit: `68e19ccfdedc6ba161fe41e1a29dea586e5ea8bd`
- Frozen official base: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
- Frozen official-base tree: `99cd398dc28b424c1e2bb766d210affa58f17d54`
- Ranked leader observed before dispatch: receipt `cc6ddc1`, score `2.61650354381456`
- Dispatch UTC: `<REQUIRED>`
- Authorized dispatcher: `<REQUIRED>`

This is the previously staged and audited immutable C3 candidate. It was not rebased, amended, reconstructed, squashed, comment-reclaimed again, or copied to a fresh commit for dispatch. The campaign wrapper supplies model attribution `senpai`; no `--model` option was passed by the operator.

## Intended mechanism

The candidate is exact C2 — e27, production shared-R1, and exact organizer row-32 LM head — plus only Maple PR #707's exact o_proj `rps=2` port from `e5acc163b31d7ead7392e0f0ef010a79be6084e2`. It excludes `gate_sp` and all other Maple-head mechanisms. The o_proj port changes the scored kernel construction/dispatch/grid geometry. Static headroom was recovered only by deleting audited comments, with executable source and string-literal content preserved. The mechanism is input-independent kernel/layout work; it does not hardcode prompts, tokens, fixtures, or answers, and it does not add speculative tokens, cross-request prediction, or memoization.

## Immutable submitted manifest

| Submitted file | Git blob | SHA-256 | Bytes |
|---|---|---|---:|
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | `7738d670b5570159284aae626b5a5b63c08f371e` | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | 60,069 |
| `Sources/MLXFastModel/LagunaOProjGeometry.swift` | `ae47f9911a7d8372cd14eecaaaaf58425fb32ea2` | `6145acfbfd3c08aed9850ef0d87327d80875467a8bee33cfcb5d0140cf8bfadb` | 7,035 |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | `33e0dcc678e6bae69bcb16d56c4090015c7a44c7` | `8dcd63ed8cca09b6cd2846617fc468d7aab763546a0de05f4fdffa4bea9afc77` | 507,128 |

Independent dispatch-time verification:

- Observed `HEAD`: `<REQUIRED; MUST EQUAL fb8b4194d669e9122bf93f2d985439001abb31dc>`
- Observed tree: `<REQUIRED; MUST EQUAL a453d532f6d8b46d384a442b7cd89135e4e62c59>`
- Frozen-base ancestry: `<REQUIRED: PASS>`
- Exact submitted diff paths: `<REQUIRED: PASS; LIST ALL THREE>`
- Runtime SHA-256: `<REQUIRED; MUST MATCH ABOVE>`
- LM-head SHA-256: `<REQUIRED; MUST MATCH ABOVE>`
- OProj SHA-256: `<REQUIRED; MUST MATCH ABOVE>`
- Submitted surface clean: `<REQUIRED: PASS>`
- `Package.resolved` clean: `<REQUIRED: PASS>`

## Static contract, comment reclaim, and budget

The staged candidate recovered 5,310 Runtime bytes only from proven comments: a 38-line, 2,892-byte nonce ledger plus 2,418 bytes from 30 catalogued comment ranges. Newline count was preserved, and the source audit found no executable collision. Independent packet preparation measured `2,999,925 / 3,000,000` submitted bytes, only `75` bytes headroom, and `16,076 / 262,144` bytes growth. The candidate changed exactly the three manifest files relative to the frozen official base. The dispatch-time budget command reported: `<REQUIRED; PASTE PASSING SUMMARY SHOWING 75-BYTE HEADROOM>`. The wrapper's refreshed-base snapshot check reported: `<REQUIRED: PASS>`. Any differing or failing value would have stopped dispatch.

## Established deterministic correctness evidence

PR #722 records these completed checks for the immutable tree:

1. Source-hash reconstruction and three-way audit confirmed exact C2 plus exact Maple PR #707 o_proj `rps=2`. Shared-R1 and o_proj Runtime hunks are disjoint, row-32 is a separate file, and o_proj symbols reach scored kernel construction, dispatch, and grid geometry.
2. The row-32 fixture suite ran one real test and passed five full-shape cases: dense, zero-candidate, sparse boundaries, refined exact reference, and refined survivor reject.
3. `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh` ran one nonzero test. All eight decode steps matched tokens and logits exactly with max/mean error `0/0`; prefill token matched with max `0.125` and mean `0.011933609`, identical to the fresh same-host unchanged-base control from PR #721. This was classified as non-M5 host/frontier drift rather than candidate-induced divergence.
4. `./benchmark.sh --local-submit` returned `passed=true`, correctness `1,025/1,025`, `max_abs_diff=0`, runtime `115.396s`, and peak RAM `21 GB`.
5. Exact three-path scope, all required ancestry, budget, clean `Package.resolved`, and clean worktree passed. Final commit `fb8b419` is tree-identical to tested commit `68e19cc`.

These are deterministic staging facts, not an official performance claim. The M4 low-memory timing diagnostics are not used to adjudicate this M5 geometry class. C3 had no official paired M5 metric before this draw. Deterministic Swift/Metal work has W&B: N/A. Contextual ranked runs, not candidate evidence: https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq and https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ut3wdjct .

## Gate, queue, and authorization

- Release predicate: authoritative Maple r122 Gate A raw candidate decode is `<= 4.905 ms/token`, and routing explicitly selected exact commit `fb8b4194d669e9122bf93f2d985439001abb31dc`.
- Gate A receipt URL / submission ID: `<REQUIRED>`
- Gate A candidate raw decode: `<REQUIRED; MUST BE <= 4.905 MS/TOKEN>`
- Gate receipt correctness: `<REQUIRED>`
- Gate receipt error: `<REQUIRED>`
- Gate receipt decode/prefill floor verdicts: `<REQUIRED>`
- Gate A explicit verdict and routing statement: `<REQUIRED>`
- PR #723 queue-idle evidence URL: `<REQUIRED>`
- Queue-idle observation UTC: `<REQUIRED>`
- Advisor authorization URL: `<REQUIRED>`
- Advisor authorization UTC: `<REQUIRED>`
- Authorization scope: `<REQUIRED; MUST SAY ONE DRAW OF THIS EXACT COMMIT>`

## Archived dispatch record — no invocation permitted

The historical command text was `senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c3-submission-note.md`. It is recorded only to identify this retired packet and must never be run. Mandatory leader receipt `cdcd0918-0002-45b0-a14b-81f34c40a398` makes the frozen base invalid, so the wrapper must reject it and must not be bypassed.

- Dispatch outcome: `N/A — prohibited; no invocation`
- Unsupported-`senpai` fallback: `N/A — no first invocation and no fallback`

## Archived expected receipt schema

No receipt should exist for this old-base candidate. The historical fields below remain unfilled evidence of the former contract; they cannot authorize monitoring, adjudication, retry, or submission. A future experiment must establish same-session paired M5 evidence under a fresh current-base assignment.

_This archived note was generated by an AI agent (OpenHands) on behalf of the research team._
```

## Archived unsupported invocation — do not run

The following text identifies the retired packet only; it is not a supported command:

```text
senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c3-submission-note.md
```

Running it is prohibited. The base predates mandatory promoted snapshot `f52be6aa9cefabc74f0f369d29d54e0686284aac`, and the wrapper should reject it. Do not bypass the wrapper or add any model override.

## Archived no-retry rule

There must be no first invocation of this packet, therefore no retry or fallback can be authorized. Any future experiment requires a fresh advisor-owned assignment on the current base.

## Archived receipt adjudication schema — do not populate

No old-base receipt should exist. The blank table is retained only to preserve the former evidence contract; it must not be monitored, completed, or used for a disposition.

| Receipt field | Recorded value | Source / calculation | Verdict |
|---|---|---|---|
| Submission ID and URL | `N/A` | Submission prohibited | — |
| Immutable candidate commit/tree | `fb8b4194d669e9122bf93f2d985439001abb31dc` / `a453d532f6d8b46d384a442b7cd89135e4e62c59` | Historical manifest | stale |
| Candidate raw decode (ms/token) | `N/A` | No official draw | — |
| Candidate raw prefill (ms/token) | `N/A` | No official draw | — |
| Paired baseline decode (ms/token) | `N/A` | No official draw | — |
| Paired baseline prefill (ms/token) | `N/A` | No official draw | — |
| Decode speedup | `N/A` | No official draw | — |
| Decode component floor | `N/A` | No official draw | — |
| Prefill speedup | `N/A` | No official draw | — |
| Prefill component floor | `N/A` | No official draw | — |
| Correctness | historical local evidence only | PR #722 | non-authorizing |
| Error | `N/A` | No official draw | — |
| Weighted score | `N/A` | No official draw | — |
| Promoted frontier before draw | `f52be6aa9cefabc74f0f369d29d54e0686284aac` | Mandatory leader snapshot | blocks draw |
| Promoted frontier after draw | `N/A` | No official draw | — |
| Ranking status | `N/A` | No official draw | — |
| Final disposition | retired old-base evidence | Mandatory frontier mismatch | never dispatch |

These fixed archival values document that no adjudication occurred.
