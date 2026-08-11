# Cedar C2 frozen contingency dispatch packet

> **HELD — THIS DOCUMENT IS NOT DISPATCH AUTHORIZATION.** Use this packet only after the exact C2 release predicate is evidenced, PR #723 shows the shared official queue is idle, and the advisor explicitly authorizes this exact commit. Do not poll the queue from this lane.

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

## Release predicate

All clauses are conjunctive. Any missing or ambiguous clause means **do not dispatch**.

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

While held, **never rebase, amend, reconstruct, cherry-pick, squash, merge new content into, or copy these candidate changes onto a fresh commit**. Dispatch only the immutable commit and tree above. A moved branch head is not equivalent even if a textual diff appears similar. If the head moved, stop and ask the advisor to issue a new packet.

## Fail-closed pre-dispatch checklist

An authorized dispatcher performs these checks from a checkout whose `HEAD` is already the immutable candidate. These are verification commands, not permission to reconstruct the candidate.

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

## Public note-file template

Copy the complete block below to `/tmp/cedar-c2-submission-note.md`, replace every `<REQUIRED>` value, and leave factual `N/A` entries explicit. Do not shorten away evidence. Run `wc -c /tmp/cedar-c2-submission-note.md`; it must be from 5,120 through 102,400 bytes. The note is public.

```markdown
# Cedar C2 official M5 submission note

## Status and provenance

- Dispatch status: gate-authorized single official draw
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

## Dispatch command and retry policy

The operator invoked exactly:

`senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c2-submission-note.md`

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
senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file /tmp/cedar-c2-submission-note.md
```

Do not add `--model`. The wrapper refreshes `origin/main`, validates the frozen snapshot and submitted cleanliness, then injects `--model senpai` itself.

## No-retry rule

Do not retry a timeout, network error, validation failure, delayed response, or unrelated error. The first invocation may already have created a submission. Only an explicit API rejection saying that `senpai` is an invalid or unsupported model value permits one fallback attempt:

```bash
mlxfast submit --model "<actual-provider/model>" --note-file /tmp/cedar-c2-submission-note.md
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
