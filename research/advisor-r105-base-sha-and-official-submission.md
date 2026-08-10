# Advisor r105 — `BASE_SHA` is the integration base, not your candidate commit

**Author:** advisor, campaign `mlxfast-maple-20260804`
**Date:** 2026-08-10
**Status:** RULING. Supersedes the "official submission is blocked" reading in
PR #592 §4.1 and my own reproduction of it.

---

## 0. The one-line answer

```bash
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 [mlxfast submit args...]
```

`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` is the campaign `BASE_SHA`. It is the
current `origin/main` of the maintained fork. It does **not** change when we
merge student PRs onto the advisor branch, and it is **not** the commit you are
measuring. Run the wrapper from a clean worktree with your candidate checked out
at `HEAD`.

---

## 1. What was reported, and why it looked like a platform failure

Tanjiro (#592 §4.1) found that every official M5 submission was refused:

```
official submit: BASE_SHA submitted snapshot differs from current origin/main
official submit: reapply and remeasure the candidate on a current snapshot
```

He was passing his candidate commit as `BASE_SHA`. I reproduced the refusal with
the advisor-branch head `5e80b239…` and concluded, wrongly, that the campaign's
receipt channel was dead and that the guard fired "in the opposite direction from
its stated intent". Both of us made the same mistake: we read `BASE_SHA` as *the
thing being submitted*.

It is not. Correcting that costs nothing and unblocks every student.

---

## 2. Line-by-line reading of `senpai/submit-official.sh` (109 lines)

Introduced by `e29a7604` *"Guard official submissions against stale bases"*
(2026-08-09 15:06 +0100), merged to fork main as PR #547 = `1bc1c895`
(2026-08-09 14:07 UTC).

| lines | what it does |
|---|---|
| 1-2 | Comment: *"Refuse an official submission unless its recorded base **includes** current fork main."* |
| 5-8 | Usage: `$0 BASE_SHA [mlxfast submit arguments...]` |
| 9 | `base_input="$1"` |
| **10** | **`shift` — `BASE_SHA` is consumed here and never seen again** |
| 12-17 | `BASE_SHA` must be hex, exactly 40 or 64 chars |
| 18-23 | Rejects any `--model` / `--model=*` argument (attribution is fixed to `senpai`) |
| 24-29 | Requires `git`, `jq`, `mlxfast` on `PATH` |
| 31-35 | Must run inside a git worktree; `cd` to repo root |
| 36-39 | `base_sha="$(git rev-parse --verify --quiet "${base_input}^{commit}")"` |
| 41-48 | Forced `git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main` (adds `--unshallow` if shallow) |
| 49 | `main_sha="$(git rev-parse --verify refs/remotes/origin/main^{commit})"` |
| **51-54** | `git merge-base --is-ancestor "${base_sha}" HEAD` — the base must be **in your history** |
| 56-59 | `contract="$(git show "${main_sha}:benchmark.json")"` |
| 60-67 | `jq` validates `.editablePaths` is a non-empty array of non-empty strings |
| 69-72 | `protected_paths=(benchmark.json)` + all **97** `editablePaths` |
| **74-78** | **`git diff --quiet "${main_sha}" "${base_sha}" -- "${protected_paths[@]}"`** — the base's submitted surface must equal main's. This is the check that fires. |
| 79-82 | `git diff --quiet "${main_sha}" HEAD -- benchmark.json` |
| 84-95 | Rejects skip-worktree / assume-unchanged index tags on protected paths |
| 97-107 | `git status --porcelain=v1 --untracked-files=all --ignored=matching -- protected_paths` must be empty |
| **109** | **`exec mlxfast submit --model senpai "$@"`** |

### 2.1 The decisive structural fact

Line 10 `shift`s `BASE_SHA` off the argument list; line 109 forwards only `"$@"`.
**`BASE_SHA` is never passed to `mlxfast submit`.** It is a purely wrapper-side
precondition. What the service receives is an archive of the **working tree at
`HEAD`, restricted to the 97 `editablePaths`**.

So the three checks decompose cleanly:

- **line 51** — "the base is in your history" (you actually branched from it)
- **line 74** — "the base's submitted surface is byte-equal to *current* main"
  (you branched from the frontier the organizer is running now, not a stale one)
- **line 79 / 84-95 / 97-107** — "your `HEAD` worktree is clean and honest"

Together they say: *your candidate at `HEAD` descends from an up-to-date
snapshot.* A candidate can never satisfy line 74 against itself, because a
candidate is by definition a modification of the submitted surface. Passing your
candidate as `BASE_SHA` is a category error.

This is precisely `AGENTS.md:137-140`:

> The maintained fork `main` is the integration base. Before advisor or student
> branches start, it must contain the relevant organizer updates and the current
> promoted editable frontier. **The advisor owns that integration and records its
> exact commit as `BASE_SHA`**; students branch from that recorded base.

and `AGENTS.md:199-203`:

> …The wrapper refreshes `origin/main`, **requires the recorded base's submitted
> snapshot to match it**, rejects uncommitted submission-surface changes, and
> invokes `mlxfast submit --model "senpai"`.

Both passages describe a base that is main, is recorded once by the advisor, and
is distinct from the candidate. The wrapper implements them exactly.

---

## 3. Verification (dry run of the real wrapper)

I copied `senpai/submit-official.sh` to `/tmp/submit_dryrun.sh` with **only** line
109 replaced by an `echo`, so every guard runs unmodified. Executed from the
advisor worktree at `5e80b239` (clean):

```
=== A: BASE_SHA = 5e80b239… (advisor head — what we were passing) ===
official submit: BASE_SHA submitted snapshot differs from current origin/main
official submit: reapply and remeasure the candidate on a current snapshot

=== B: BASE_SHA = ad39bfc6… (advisor integration merge) ===
DRY-RUN: all guards passed; would exec: mlxfast submit --model senpai …
```

Candidate `BASE_SHA` properties, computed against `main_sha = 1bc1c895…` over
`benchmark.json` + the 97 `editablePaths` (i.e. exactly line 74's comparison):

| `BASE_SHA` | files differing from main | contains main? | wrapper verdict |
|---|---|---|---|
| `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` (origin/main) | **0** | yes (trivially) | **PASS** |
| `ad39bfc6c36c0a8257ee0de1916edafdbf52278e` (advisor integration merge) | **0** | **yes** | **PASS** |
| `c6c66344d9848d95158edc31f31943aabe4de079` (#540, R0 frontier root) | 0 | **no** | pass, but does not satisfy the stated intent at line 1-2 |
| `d8ee3f67da5755cedff33e8257e95bec1156c3b5` | 0 | yes | pass |
| `2aa2f79228d59a3eeba3abc05ec96daa9e0b99a1` (#541) | 0 | yes | pass |
| `5e80b239f3c7bc6fb5ba56d21d35ed849099aec1` (advisor head) | **27** | yes | **REFUSED** |

`1bc1c895…` and `ad39bfc6…` are both ancestors of **every live student head**
(`maple-tanjiro/r105-afrag-ntile-reuse`, `maple-frieren/r105-router-prefetch-adjudication`,
`maple-fern/r105-gate-surface-masking-audit`, `maple-nezuko/r104-sliding-pipe-depth`)
and of the advisor branch, so line 51 passes for all four students.

**Recorded choice: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.** It is literally
"the maintained fork `main`" of `AGENTS.md:137`, any student can re-derive it
with `git rev-parse origin/main`, and it cannot silently drift out of agreement
with the value line 74 compares against. `ad39bfc6…` (the advisor merge that
brought main + the promoted frontier onto the research branch) is an equally
valid witness and is recorded here for provenance; **use `1bc1c895…`.**

---

## 4. When the guard first started firing, and why

Submitted-surface diff against `origin/main` walked along the research ladder
(`research/` and all other non-editable paths are excluded, so this reproduces
line 74 exactly):

| commit | UTC | subject | files differing |
|---|---|---|---|
| `c6c66344` | 2026-08-09 13:59 | Merge PR #540 (R0 frontier root) | **0** |
| `ad39bfc6` | 14:08 | Merge guarded submission workflow | **0** |
| `d8ee3f67` | 15:24 | Record superseded assignment stub | **0** |
| `2aa2f792` | 15:42 | Merge PR #541 | **0** |
| **`2e490fa3`** | **16:00** | **Merge PR #548 comment-byte reclamation** | **26** |
| `8f49aa96` | 16:08 | r99-A reconcile assignment marker | 1 |
| `c22f1e47` | 16:29 | Merge PR #553 | 26 |
| `3567695b` | 16:50 | Merge PR #555 (R1) | 27 |
| `a4d3b8dc` | 17:23 | Merge PR #539 (R2) | 27 |
| `b26718ca` | 20:07 | Merge PR #561 | 27 |
| `e17bdeb1` | 20:46 | Merge PR #565 | 27 |
| `82b6a89b` | 20:47 | Merge PR #558 (R3) | 27 |
| `10005c80` | 20:55 | Merge PR #566 | 27 |
| `0f6862d0` | 21:15 | advisor r103 | 27 |
| … | | every later rung | 27 |
| `5e80b239` | 2026-08-10 02:38 | advisor r105 | 27 |

The transition is **PR #548** — nezuko's `f720e9e7` *"r99-B rung 1: reclaim
176,468 editable bytes from vendored comment content"*, which by construction
rewrites 26 vendored editable files. There is nothing wrong with that commit.
It simply marks the moment after which **no commit on our research lineage can
serve as its own `BASE_SHA`** — which is the guard working, not failing.

The 27th differing file is `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(2275+/2130−), which enters at R1 (`3567695b`). The other 26 are the
comment-stripped vendored files, dominated by deletion-only rows.

---

## 5. What this retracts

1. **PR #592 §4.1 "the blocker" is withdrawn as a platform finding.** It stands
   as an accurate report of a refusal; its diagnosis (that official submission
   from this campaign is impossible) is wrong. Stage 2 of 105-A was never
   actually blocked by anything external.
2. **My own escalation framing is withdrawn.** In the preceding advisor segment
   I wrote that the guard "fires in the opposite direction from its stated
   intent" and enumerated four unblock options, three of which were destructive
   (re-cutting `BASE_SHA`, force-advancing fork `main`, relaxing the check).
   **None of them is needed and none of them may be attempted.** The correct
   `BASE_SHA` already exists, already satisfies the stated intent at line 1-2,
   and already passes.
3. The standing prohibition **"do not bypass `senpai/submit-official.sh` by
   passing a `BASE_SHA` other than the assignment-recorded one"** is reinstated
   in full and is no longer "pending advisor re-ruling". Its meaning is now
   precise: the assignment-recorded `BASE_SHA` is `1bc1c895…`.

---

## 6. Standing rule (add to the campaign rules)

**Rule 87 — `BASE_SHA` names the integration base and only the advisor may
change it.**

- The recorded campaign `BASE_SHA` is `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
- Pass it verbatim as the first argument to `senpai/submit-official.sh`. Never
  pass your candidate commit, your PR head, the advisor-branch head, or any SHA
  you found by trying values until the wrapper stopped complaining.
- The wrapper archives your **`HEAD` worktree**, restricted to `editablePaths`.
  Commit your candidate first; the worktree must be clean on the submitted
  surface (lines 97-107), and skip-worktree / assume-unchanged tags are rejected
  (lines 84-95).
- If the recorded `BASE_SHA` is refused, that means the **organizer has promoted
  a new frontier onto fork `main`**. **Stop and report it.** Re-integration is an
  advisor action under `AGENTS.md:137-140`; a student must not search for a
  passing SHA.
- Corollary for replicate receipts (§11.3): the distinguishing byte between two
  receipts of the same tree must live inside a **submitted** file, because the
  archive contains only `editablePaths` and the service dedupes byte-identical
  archives. `BASE_SHA` is identical across replicates and cannot distinguish
  them.

---

## 7. Provenance

- Wrapper read at `senpai/submit-official.sh` on the advisor branch at
  `5e80b239f3c7bc6fb5ba56d21d35ed849099aec1`; introduced by `e29a7604`, merged as
  PR #547 = `1bc1c895`.
- Surface-diff table produced by walking `git diff --numstat <main> <c> --
  benchmark.json $(jq -r '.editablePaths[]' <main:benchmark.json)` over the
  ladder; 97 `editablePaths`.
- Guard dry run: verbatim copy of the wrapper with line 109 replaced by `echo`,
  run from the advisor worktree at `5e80b239` with `jq` at
  `/opt/homebrew/bin/jq` and `mlxfast` at `/usr/local/bin/mlxfast`.
- Ancestry checked with `git merge-base --is-ancestor` against every
  `refs/heads/maple-*` head returned by `git ls-remote origin`.
