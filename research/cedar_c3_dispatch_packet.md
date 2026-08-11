# Cedar C3 frozen contingency dispatch packet

> **HELD — THIS DOCUMENT IS NOT DISPATCH AUTHORIZATION.** Use this packet only after an authoritative Maple Gate A pass, a current PR #723 queue-idle record, and explicit advisor authorization for this exact commit. Do not poll the queue or infer Gate A in this lane.

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

## Release predicate

All clauses are conjunctive. Any missing or ambiguous clause means **do not dispatch**.

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

While held, **never rebase, amend, reconstruct, cherry-pick, squash, merge new content into, or copy these candidate changes onto a fresh commit**. Dispatch only the immutable commit and tree above. Do not repeat comment reclaim or reapply the o_proj patch. A moved branch head is not equivalent even if hashes from selected files seem familiar. If the head moved, stop and ask the advisor to issue a new packet.

## Fail-closed pre-dispatch checklist

An authorized dispatcher performs these checks from a checkout whose `HEAD` is already the immutable candidate. These are verification commands, not permission to reconstruct the candidate.

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

## Public note-file template

Copy the complete block below to `/tmp/cedar-c3-submission-note.md`, replace every `<REQUIRED>` value, and leave factual `N/A` entries explicit. Do not shorten away evidence. Run `wc -c /tmp/cedar-c3-submission-note.md`; it must be from 5,120 through 102,400 bytes. The note is public.

```markdown
# Cedar C3 official M5 submission note

## Status and provenance

- Dispatch status: Gate-A-authorized single official draw
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

## Dispatch command and retry policy

The operator invoked exactly:

`senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c3-submission-note.md`

The operator did not pass `--model`; `senpai/submit-official.sh` injected campaign attribution. The first invocation outcome was: `<REQUIRED>`.

There is no retry for timeout, network error, validation failure, delayed response, or any unrelated error, because the first submission may already exist. A one-time fallback is permitted only if the submission API explicitly rejects `senpai` as an invalid or unsupported model value. If and only if that occurs, record the exact rejection and the one fallback invocation here; otherwise leave both fields `N/A` and do not place any provider/model identity elsewhere in campaign metadata.

- Explicit unsupported-`senpai` rejection: `<REQUIRED: N/A OR EXACT ERROR/RECEIPT>`
- One-time provider/model fallback invocation and outcome: `<REQUIRED: N/A UNLESS TRIGGERED>`

## Expected receipt adjudication

The official result will be judged from same-session paired M5 evidence. Record submission ID/URL, candidate raw decode and prefill, paired baseline decode and prefill, correctness, error, decode floor, prefill floor, score, promoted frontier, and final disposition. A `rejected` ranking status alone does not imply correctness failure. Both component speedups must be at least `0.95`; correctness must pass and error must be absent before score/rank interpretation.

_This public submission note was generated by an AI agent (OpenHands) on behalf of the research team and completed by the authorized dispatcher._
```

## Exact supported invocation

After every checkbox passes and the filled note is within size limits, run exactly once:

```bash
senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c3-submission-note.md
```

Do not add `--model`. The wrapper refreshes `origin/main`, validates the frozen snapshot and submitted cleanliness, then injects `--model senpai` itself.

## No-retry rule

Do not retry a timeout, network error, validation failure, delayed response, or unrelated error. The first invocation may already have created a submission. Only an explicit API rejection saying that `senpai` is an invalid or unsupported model value permits one fallback attempt:

```bash
mlxfast submit --model "<actual-provider/model>" --note-file /tmp/cedar-c3-submission-note.md
```

That exception is one-time, must use the same immutable candidate, and must be recorded with the explicit rejection in the public note. Do not use the fallback for any other failure and do not otherwise publish the underlying provider/model in campaign metadata.

## Receipt adjudication table

PR #723 owns monitoring. Populate this table only from the terminal official receipt; do not infer missing values.

| Receipt field | Recorded value | Source / calculation | Verdict |
|---|---|---|---|
| Submission ID and URL | `<REQUIRED>` | Official receipt | — |
| Immutable candidate commit/tree | `<REQUIRED>` | Receipt plus manifest | exact / mismatch |
| Candidate raw decode (ms/token) | `<REQUIRED>` | Candidate leg | — |
| Candidate raw prefill (ms/token) | `<REQUIRED>` | Candidate leg | — |
| Paired baseline decode (ms/token) | `<REQUIRED>` | Same session | — |
| Paired baseline prefill (ms/token) | `<REQUIRED>` | Same session | — |
| Decode speedup | `<baseline decode / candidate decode>` | Calculate from raw legs | — |
| Decode component floor | `<REQUIRED>` | speedup `>= 0.95` | pass / fail |
| Prefill speedup | `<baseline prefill / candidate prefill>` | Calculate from raw legs | — |
| Prefill component floor | `<REQUIRED>` | speedup `>= 0.95` | pass / fail |
| Correctness | `<REQUIRED>` | Official hidden/public gates | pass / fail |
| Error | `<REQUIRED; NONE OR EXACT ERROR>` | Official receipt | clear / failed |
| Weighted score | `<REQUIRED>` | Official receipt | — |
| Promoted frontier before draw | `<REQUIRED>` | Queue/leader record | — |
| Promoted frontier after draw | `<REQUIRED>` | Official promotion state | candidate / unchanged / other |
| Ranking status | `<REQUIRED>` | Official receipt | accepted / rejected / other |
| Final disposition | `<REQUIRED>` | Correctness + error + both floors + score/frontier | promote / retain evidence / terminal negative / inconclusive |

A final disposition requires all fields. Inspect correctness, error, and both floors separately from ranking status.
