# R108-M Part 2 — integration-freeze custody: the channel, the protocol, the traps

maple-fern · branch `maple-fern/r108-m-bandwidth-probe-and-freeze-custody` · PR #664
Companion to `research/maple-fern-r108m-m5-bandwidth-probe.md` (Part 1, the α bracket).
Decision rule lives in `research/maple-fern-r106j-integration-tree.md` §9. This file is the
*mechanics*: what the submission channel actually does, what the wrapper actually checks,
and the minute-by-minute sequence I will run between 06:00Z and 09:00Z.

Everything below is read from the installed toolchain on this host on 2026-08-10.
**Zero receipts were spent producing it.** I did not invoke `senpai/submit-official.sh`,
and I will not.

---

## 0. Custody statement

I own the freeze. Concretely that means:

* I do not own any kernel. Nothing in §4 changes a byte under `Sources/` or `Vendor/`
  unless a sibling hands me a candidate and it passes §6.
* I do not fire the draw. I produce the certificate that says whether firing is
  *mechanically* safe, and the §9.4 verdict that says whether it is *statistically*
  justified. The advisor decides.
* Everything I add lives under `research/`, which is outside `editablePaths` and outside
  `harnessHash()`. My Part 2 work is byte-free against the Rule 105.14 budget
  (`current=2681206/3000000`, unchanged) and cannot move the score.

---

## 1. Channel forensics — what `mlxfast submit` actually does

Nobody in this campaign has written this down, and several of our working assumptions
about the draw turn out to be wrong. `/usr/local/bin/mlxfast` is a four-line `/bin/sh`
shim:

```
#!/bin/sh
if [ -z "${MLXFAST_API_URL:-}" ]; then export MLXFAST_API_URL='https://api.mlx.fast'; fi
if [ -z "${MLXFAST_BENCHMARK_REF:-}" ]; then export MLXFAST_BENCHMARK_REF='eigenlabs/mlxfast-challenge'; fi
exec /opt/homebrew/bin/bun /usr/local/libexec/mlxfast.js "$@"
```

`mlxfast.js` is a 952,523-byte bundle. Line numbers below are into that file, as
installed on this host today.

### 1.1 The exact call order, and where the receipt is spent

`submitEditablePaths` (`:24200`) runs, in order:

| # | step | line | local or network | can it burn the draw? |
|---|------|------|------------------|-----------------------|
| 1 | `loadBenchmarkManifest(repoPath)` | `:20565` | local | no |
| 2 | `resolveBenchmarkRef(...)` | `:24536` | network (read) | no |
| 3 | `readSubmissionNoteOption(...)` | `:24246` | local | no |
| 4 | `createSubmissionArchive(repoPath, manifest)` | `:24530` | local | no |
| 5 | `drainPendingTracesBeforeSubmit(...)` | `:24231` | network, ≤60 s | no |
| 6 | archive ≤ `SUBMISSION_ARCHIVE_MAX_BYTES` | `:24208` | local | no |
| 7 | **`client.createSubmission({...})`** | `:24212` | network (write) | **YES — this is the draw** |

Steps 1–6 are all fail-fast and all happen **before** step 7. Every mis-configuration in
§1.3–§1.6 therefore costs time, not a receipt. That is a genuinely reassuring result and
it is the first time we have had it on evidence rather than on hope.

The one thing to *not* do is interrupt step 5. It prints
`Pushing traces before submission (up to 60 seconds)...` and is wrapped in a bare
`try { ... } catch {}` — so it cannot fail the submit, but Ctrl-C during that window
lands in an ambiguous place. Budget a full minute of apparent silence.

### 1.2 What is actually uploaded — and it is **not** the commit

```js
async function createSubmissionArchive(repoPath, manifest) {
  const tempDir = await mkdtemp(path12.join(os4.tmpdir(), "yukon-submit-"));
  const archivePath = path12.join(tempDir, "submission.tar.gz");
  await Zn({ gzip: true, file: archivePath, cwd: repoPath, portable: true, noMtime: true },
           manifest.editablePaths);
  return { path: archivePath, tempDir };
}
```

Three consequences, all of which matter:

1. **The payload is exactly `editablePaths`.** Nothing else leaves this machine.
   `research/`, `senpai/`, `Tests/`, `.git/`, the whole rest of the tree — never sent.
2. **The payload is read off the WORKING TREE, not off `HEAD`.** `tar` walks the paths on
   disk. `git` is not consulted at all by the CLI. If you call `mlxfast submit` directly,
   *you ship whatever is currently on disk*, committed or not.
3. **Directory entries are walked recursively.** `Sources/MLXFastModel` is a directory in
   the manifest, so every file under it is packed — **including untracked files and
   including `.gitignore`d files**. A stray `.DS_Store` or `.metallib` under
   `Sources/MLXFastModel` does not merely trip a checker; it is *uploaded*.

Point 2 is the load-bearing one. **The only reason "we ship HEAD" is true is
`senpai/submit-official.sh` predicate 12**, which refuses to run if the working tree is
dirty under the protected paths. Bypass the wrapper and that guarantee evaporates. This
is why §4 never calls `mlxfast` directly and why "just run `mlxfast submit`" must never
appear in anyone's runbook.

Point 3 explains *why* the wrapper passes `--ignored=matching` to `git status`, a flag
that has puzzled us since R106-J. It is not paranoia; it is exactly matched to what `tar`
will pick up.

**Measured payload size on the current advisor tree** (built locally with the same file
list; nothing was sent):

```
$ jq -r '.editablePaths[]' benchmark.json > /tmp/fern_ep.txt   # 97 entries
$ tar czf /tmp/fern_submission_preview.tgz -T /tmp/fern_ep.txt
428038 bytes, 148 archive entries
```

428 KB against a 25 MiB cap = **1.6 % of budget**. The archive cap is a non-issue unless
build residue lands inside an editable directory, at which point it becomes the *only*
symptom you would see.

### 1.3 The note contract — the 5 KiB floor nobody has budgeted for

```js
var SUBMISSION_NOTE_MIN_BYTES = 5 * 1024;      // :23479
var SUBMISSION_NOTE_MAX_BYTES = 100 * 1024;    // :5774
```

`readSubmissionNoteOption` (`:24246`) builds the stored note as

```js
const note = `Model: ${model}\n\n${rawNote}`;
assertSubmissionNoteSize(note);
```

so the 5 KiB is measured **after** prepending `Model: senpai\n\n` (15 bytes) and is
measured in **UTF-8 bytes**, not characters. Practical rules:

* the note file must be **≥ 5,105 bytes** of its own content to clear 5,120 after the
  prefix. Aim for ≥ 6 KiB and stop worrying.
* `--note` and `--note-file` are mutually exclusive; passing both throws.
* an empty-after-`trim()` note throws `submission note is required`.
* **the flag is `--note` / `--note-file`, never `--notes`.** Our own
  `research/r106j/scripts/submit_preconditions.sh` printed `--notes` until I fixed it
  today; `commander` would have rejected the unknown option.

This is a real schedule item. A 5 KiB narrative note is ~15 minutes of writing that
nobody has allocated, and it must exist *before* 08:00Z. §4 puts it at 07:00Z, in
parallel with the build, and it is the one task on the critical path that does not
depend on which candidate wins.

### 1.4 `--model` is required by the CLI and supplied by the wrapper

```js
program2.command("submit")
  .option("--note <markdown>", ...)
  .option("--note-file <path>", ...)
  .requiredOption("--model <name>", 'required AI model used ...')   // :23547
```

`--model` is a **`requiredOption`**: `mlxfast submit` will not run without it. The wrapper's
last line is `exec mlxfast submit --model senpai "$@"`, which supplies it. This resolves
the apparent contradiction between "model attribution is fixed to senpai" and the help
text: both are true, and the *only* correct behaviour for us is to never pass it
(`senpai/submit-official.sh:18-23` exits 2 if we do).

### 1.5 Dedup: an identical archive does not produce a new job — and discards the note

```js
const deduped = result.job === null;                      // :24222
function submitHeading(deduped) {                          // :21202
  return deduped ? "Submission already exists" : "Submission queued";
}
function submitNoteLine(deduped, sentNote, storedNote) {   // :21205
  if (deduped && sentNote !== storedNote)
    return "not stored (existing submission reused; its original note is kept)";
  ...
}
```

`idempotencyKey` is a fresh `randomUUID()` on every invocation, so this dedup is
**content-addressed on the archive**, not request-addressed. Two readings follow:

* If we re-fire a byte-identical surface, we get `Submission already exists`, `job === null`,
  and **the new note is thrown away**. So a "resubmit with a better note" plan does not work.
* I will *not* claim this means a duplicate is free of receipt accounting. The CLI cannot
  see the server's ledger. Treat it as: a duplicate buys us nothing, and must not be
  attempted as a way to "check" whether the channel works.

### 1.6 The remaining caps

| constant | value | line |
|---|---|---|
| `SUBMISSION_ARCHIVE_MAX_BYTES` | 25 MiB compressed | `:5772` |
| `SUBMISSION_ARCHIVE_MAX_EXPANDED_BYTES` | 512 MiB | `:5773` |
| `SUBMISSION_NOTE_MAX_BYTES` | 100 KiB | `:5774` |
| `SUBMISSION_NOTE_MIN_BYTES` | 5 KiB | `:23479` |

### 1.7 What this settles: nezuko's E.3

nezuko's R107-J′ §E.3 flags an untested risk — that a server-side CI content gate might
reject a branch that carries `research/` changes, which every student branch does. §1.2
settles it for the submission channel: **the server never receives `research/`.** The
archive is a tar of `editablePaths` and nothing else, and the CLI never sends a ref, a
branch name, a commit, or a diff. There is no mechanism by which `research/` content can
be gated at submit time.

Two honest limits on that finding. First, it is a statement about *this* CLI build on
*this* host; a server-side change would be invisible to me. Second, it says nothing about
any repo-level CI that runs on our GitHub branches — but the draw does not go through
GitHub, so that CI cannot cost us the draw. **E.3 is downgraded from "live draw risk" to
"not on the draw path".** nezuko should still keep the item open for the PR path.

---

## 2. The twelve predicates, and the six things they do not check

`research/r106j/scripts/submit_preconditions.sh` is a faithful, read-only re-implementation
of every exit condition in `senpai/submit-official.sh`, in wrapper order. You cannot
dry-run the wrapper — if all predicates pass, it submits — so this rehearsal is the only
way to get the pass/fail table without spending the draw.

Run on my HEAD `433c66a8` at 16:12Z: **12 pass, 0 fail**
(`research/artifacts/maple-fern-r108m/preconditions_head_1615Z.txt`).

`protected_paths` = `benchmark.json` + the 97 `editablePaths` entries read from
**`origin/main`'s** `benchmark.json` (`submit-official.sh:69-72`), which is a *different
source* from the manifest the CLI packs from (`§1.2`: the local working-tree
`benchmark.json`). Predicate 10 is what forces the two to agree.

### What the wrapper protects

| # | predicate | wrapper lines | what it really buys |
|---|---|---|---|
| 1 | BASE_SHA is 40/64-char hex | 12-17 | stops a truncated or symbolic ref |
| 2 | no `--model` | 18-23 | attribution stays `senpai` |
| 3 | `git`/`jq`/`mlxfast` on PATH | 24-29 | fails before any network call |
| 4 | inside a git worktree | 31-35 | |
| 5 | BASE_SHA is a local commit | 36-39 | |
| 6 | `git fetch origin main` succeeds | 41-48 | **retryable**: nothing was sent |
| 7 | BASE_SHA is an ancestor of HEAD | 51-54 | the claimed base is really behind us |
| 8 | `origin/main:benchmark.json` has usable `editablePaths` | 56-67 | |
| 9 | `origin/main` == BASE_SHA over protected paths | 74-78 | **the anti-stale-base gate** |
| 10 | `origin/main` == HEAD on `benchmark.json` | 79-82 | we did not widen our own surface |
| 11 | no skip-worktree / assume-unchanged under protected paths | 84-95 | no hidden index tricks |
| 12 | protected paths clean incl. untracked **and ignored** | 97-107 | **the only reason we ship HEAD** (§1.2) |

### What it does **not** check — six gaps

1. **HEAD's content under `editablePaths` is never compared to `origin/main`.** Predicate 9
   compares `main_sha` to `base_sha`; predicate 10 covers only `benchmark.json`. So the
   wrapper has no opinion whatsoever on the diff we are actually shipping. That is
   correct — the diff *is* the submission — but it means no wrapper predicate will ever
   catch a wrong candidate, a bad merge, or a reverted fix.
2. **It does not build.** A tree that does not compile passes all twelve.
3. **It does not run the correctness gate.** `Sources/MLXFastCore/Golden.swift` is not even
   in `editablePaths` — it is harness-side. Token-ID equality (Rule 105.15) is enforced
   server-side, after we have paid.
4. **It does not check the environment.** `DARKBLOOM_QMV_WIDE_CODES` (Rule 102, −0.5363 %)
   and `DARKBLOOM_EXPERT_DOWN_BN` (Rule 103, −0.195 %) being exported in the firing shell
   would silently degrade the submission. I added an explicit advisory block for these to
   `submit_preconditions.sh` today, clearly labelled as *not* a wrapper predicate.
5. **It does not check the note.** The 5 KiB floor of §1.3 is enforced by the CLI, one
   layer further in.
6. **It does not check that the surface fits Rule 105.14.** `senpai/check-editable-budget.sh`
   is a separate, campaign-side script. Current: `current=2681206/3000000 headroom=318794
   growth=-302643/262144 files=142`, largest file
   `Sources/MLXFastModel/LagunaRuntimeModel.swift` 384,245 B of the 524,288 B hard cap.

Gaps 1–3 are the entire reason §4 exists: the wrapper is a *mechanical* gate, and
everything that actually decides whether the draw is worth firing has to be established
before we get to it.

---

## 3. Part 2a — the `BASE_SHA` default fix

The assignment says to fix the `BASE_SHA` default in `senpai/handoff_certificate.sh`, on the
grounds that `senpai/` is in `editablePaths` and the fix must therefore be byte-cheap.
Both halves of that are wrong, and it is worth recording why, because both errors point
the same way — toward being *more* free to fix this, not less.

**Error 1: the file is not at that path.** There is no `senpai/handoff_certificate.sh`.
`senpai/` contains `assignment-template.md, check-editable-budget.sh, competition_notes,
exa_search.py, experiment-runbook.md, infra.md, pre-nax-moe-layout.md, program.md,
quality-eval, quality-evaluation.md, quality_eval, result-template.md, submit-official.sh,
test_submit_official.py, test_watch_submission.py, tools, validate-assignment-scope.sh,
watch-submission.py`. The script I wrote in R106-J and that the assignment is describing is
**`research/r106j/scripts/handoff_certificate.sh`**.

**Error 2: `senpai/` is not in `editablePaths`.** Membership test against
`1bc1c895:benchmark.json` for `senpai`, `senpai/handoff_certificate.sh` and `research`
returns `[]` for all three. The 97 entries are `Sources/MLXFastModel`,
`Sources/MLXFastTransform`, and 95 `Vendor/…` paths — note that even
`Sources/MLXFastCore` is *not* editable. So editing anything under `senpai/` or
`research/` costs **zero** against the Rule 105.14 budget and cannot trip any wrapper
predicate. The fix was free.

**The bug, and why it was the dangerous kind.** The old default was the hardcoded literal
`446fe9875d1f95b1216628b5809a99da844e5c79`. The fork's `origin/main` is now
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`. A stale literal is the worst available failure
mode here because **it fails silently**: with the stale value, predicates 1, 7, 10, 11 and
12 all still pass, and only predicate 9 catches it — at the cost of the draw. A checker
that is green for the wrong reason is worse than no checker.

**The fix** (`research/r106j/scripts/handoff_certificate.sh`): never hardcode. `BASE_SHA`
now defaults to `origin/main` *resolved at run time, after the fetch*, using the wrapper's
own refspec (`+refs/heads/main:refs/remotes/origin/main`) so that `MAIN_SHA` is computed
exactly the way `submit-official.sh:41-49` computes it. An explicit argument still wins,
and the certificate now prints `BASE_SHA source` and shouts if `BASE_SHA != origin/main`,
because in that case predicate 2 of the certificate stops being a tautology and starts
being a real test. A failed fetch now refuses to certify rather than certifying against a
stale ref.

I also fixed the `--notes` → `--note-file` typo in `submit_preconditions.sh` (§1.3) and
added the note/`--model`/DARKBLOOM footnotes to both scripts' final "the exact command"
block. Verified: both scripts run clean on `433c66a8`, artifacts committed under
`research/artifacts/maple-fern-r108m/`.

---

## 4. The freeze protocol

Times are UTC. Every command is copy-pasteable from the repo root
`/Users/…/student-maple-fern/workspace/target`. Every step states its abort condition,
because the default action at every checkpoint is **hold** (Rule 96.2: "no draw" is modal
and acceptable; Rule 101.2: "Hold our tree").

### T−60 · 06:00Z — handoffs due to me

Expected in R106-J §7 style: **frieren** (R108-K, #660, decode dispatch merge) and, if it
lands, whatever tanjiro's R108-L ledger (#663) implies for the pair choice. Each handoff
must give me, at minimum:

* the candidate branch and commit SHA;
* the arm, the measured M4 Δµs/step with a CI, and the number of blocks;
* which conversion regime applies (Rule 105.11/105.12) and therefore which `k`;
* the correctness evidence (Rule 105.15 class; see §8.8.4 of the integration tree);
* whether the change is MSL-literal disjoint from every other candidate (§8.4).

**If a handoff is missing at 06:00Z I do not chase it.** I proceed with what exists. A
candidate that arrives after 07:00Z is not integrated; that is what a freeze means.

### T−0 · 07:00Z — the freeze

```bash
cd <repo root>
git fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'
git rev-parse refs/remotes/origin/main            # expect 1bc1c895…, or record the new value
git log --oneline -1                              # record the frozen HEAD
git status --porcelain                            # MUST be empty
```

Expected: `origin/main = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`, clean tree.
**Abort condition:** if `origin/main` has moved, predicate 9 now requires `BASE_SHA` to be
the *new* main and the whole surface must be re-verified against it — that is a
30-minute-minimum re-run, and if it does not fit before 08:00Z, we hold.

From 07:00Z the surface is closed. Anything landing after this point is documentation.

### T+0 to T+60 · 07:00Z–08:00Z — three tracks in parallel

**Track A — build and measure (the long pole).** Both products, exactly as `benchmark.sh`
builds them (`benchmark.sh:2020,2022`):

```bash
swift build -c release --force-resolved-versions --product mlxfast-swift
swift build -c release --force-resolved-versions --scratch-path .build-worker \
      --product mlxfast-runtime-worker
```

Cold-build cost is being measured today (see §4.1) precisely so this window is budgeted
from evidence rather than guessed. Note that any local timing run also pays
`benchmark.sh`'s **40 °C GPU cool-down gate** before each measured phase
(`COOL_GATE_TEMP_C=40`, poll 10 s, `COOL_GATE_ABORT_SECONDS=180`,
`COOL_GATE_STALL_SECONDS=90`). That is dead time you cannot compress.

**Track B — write the note.** ≥ 5,105 bytes of body (§1.3). This does not depend on which
candidate wins; write the shared 80 % now and paste the arm-specific numbers in at 07:45Z.
Save to `research/artifacts/maple-fern-r108m/draw_note.md` and check the size:

```bash
wc -c research/artifacts/maple-fern-r108m/draw_note.md    # want ≥ 5105
```

**Track C — the certificate.**

```bash
PRECOND_OUT=research/artifacts/maple-fern-r108m/preconditions_freeze.txt \
  bash research/r106j/scripts/submit_preconditions.sh
HANDOFF_OUT=research/artifacts/maple-fern-r108m/handoff_certificate_freeze.txt \
  bash research/r106j/scripts/handoff_certificate.sh
bash senpai/check-editable-budget.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
```

Expected: `summary: 12 pass, 0 fail`; `VERDICT: all 12 predicates pass on this HEAD.`;
budget `headroom` positive and `largest_file_bytes` under 524,288.
**Do not pipe these through `head`** — the scripts `tee` their output and a SIGPIPE
truncates the artifact. (I lost a certificate to exactly this at 16:13Z today; the file
stopped at 184 of 225 lines with no error. Cheap lesson, recorded so nobody re-learns it
at 08:00Z.)

**Abort condition for the window:** any predicate red, any build failure, any correctness
regression. All three mean hold.

### T+60 · 08:00Z — latest sensible draw start

Decision, in this order (integration tree §9.4, and §9's ordering rule):

1. **admissibility** — 12/12 predicates, builds, correctness gate green;
2. **correctness** — Rule 105.15 class per §8.8.4; a class-2 claim is not a bit-exactness claim;
3. **composition** — MSL-literal disjointness (§8.4) if more than one arm is stacked;
4. **argmax de-bias** — Rule 105.10, applied to whichever arm won a selection;
5. **the band**: `< 0.40 %` HOLD · `0.40–0.93 %` HOLD and say why · `0.93–1.25 %` armed,
   advisor's call · `> 1.25 %` TAKE.

If we fire, the command is exactly:

```bash
cd <repo root>
git status --porcelain                                   # empty
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
     --note-file research/artifacts/maple-fern-r108m/draw_note.md
```

with `DARKBLOOM_QMV_WIDE_CODES` and `DARKBLOOM_EXPERT_DOWN_BN` **unset in that shell**,
no `--model`, and no `head`/`tee` on the pipeline. Expect up to 60 s of silence at the
trace-drain step, then `Submission queued`. `Submission already exists` means the archive
was byte-identical to a previous one and **no job was created** (§1.5) — that is a
failure to react to, not a success.

### T+120 · 09:00Z — hard stop

No draw is started after 09:00Z. Deadline is 2026-08-11T10:00Z and a queued job needs
room to finish. After 09:00Z my job is the writeup, not the wire.

### 4.1 Timed dry-run (discretionary)

I am timing a cold release build of `mlxfast-swift` into a scratch path outside the repo
(`--scratch-path /tmp/fern-freeze-build`, so the checkout stays pristine and predicate 12
stays green) to put a real number on Track A. Result and the resulting minute-by-minute
budget are appended to `research/artifacts/maple-fern-r108m/` when it lands.

---

## 5. Trap register

Live traps, each with its detection command. Nothing here is speculative; every item
either bit us or is a direct reading of the code above.

| # | trap | why it bites | detect |
|---|---|---|---|
| T1 | `.DS_Store` under an editable dir | `.gitignore:60` hides it from plain `git status`, but `tar` **uploads** it (§1.2) and predicate 12 uses `--ignored=matching` | `git status --porcelain=v1 -uall --ignored=matching -- Sources Vendor` — currently empty |
| T2 | stray `.metallib` under `Sources/` | same mechanism; MSL dumps belong in `research/artifacts/` only | `find Sources Vendor -name '*.metallib'` — currently none; the three real ones are under `research/msl/`, the rest under `.build*/` |
| T3 | stale hardcoded `BASE_SHA` | fails silently, only predicate 9 catches it (§3) | fixed today; certificate now prints `BASE_SHA source` |
| T4 | note under 5 KiB | CLI throws at step 3 of §1.1 — costs time, not a receipt, but at 08:05Z time *is* the constraint | `wc -c <note>` ≥ 5105 |
| T5 | `--notes` instead of `--note-file` | unknown option; our own script printed it | fixed today |
| T6 | passing `--model` | wrapper exits 2 (`:18-23`) | never pass it |
| T7 | `DARKBLOOM_*` exported in the firing shell | −0.5363 % / −0.195 %, invisible to every predicate | advisory block now printed by `submit_preconditions.sh` |
| T8 | calling `mlxfast submit` directly | ships the **working tree**, not HEAD (§1.2) | only ever go through the wrapper |
| T9 | piping a certificate through `head` | SIGPIPE truncates the `tee`d artifact with exit 0 | redirect to a file, then read the file |
| T10 | `origin/main` moves between 07:00Z and 08:00Z | invalidates predicate 9 and the whole certificate | re-fetch immediately before firing; the certificate re-fetches on every run |
| T11 | prefill numbers from this host | gen-16 GPU, no `_nax` path; decode transfers M4→M5, prefill does not (−43.5 %) | Rule 105.4: prefill deltas do not convert |
| T12 | byte-identical resubmission | dedup discards the new note and creates no job (§1.5) | do not attempt as a channel test |

---

## 6. What I need from frieren and tanjiro, and what I will do with it

From Part 1 (`research/maple-fern-r108m-m5-bandwidth-probe.md`), the measured M4 DRAM read
ceiling on this host is **263.29 GB/s**, range [262.37, 263.49]; the cache-served ceiling
is 1675.96 GB/s (6.37×); and α is bracketed to **[0.4227, 0.4409]** by two independent,
opposite-signed constraints. The campaign value **α = 0.4369 survives**, at the 78th
percentile of the bracket. Two consequences for the freeze:

* **Rule 55's `bytes/266.3 + 3.97` floor is 1.14 % optimistic** and should read
  `bytes/263.29 + 3.97`. Any candidate whose case rests on beating that floor by less than
  1.14 % is not actually resting on anything.
* **Byte-regime savings are priced up to 3.2 % too generously** if α is wrong, and it is
  wrong in the *optimistic* direction if at all. I re-priced both live estimates under the
  bracket in Part 1 §6: **nothing crosses a §9.4 band boundary.** frieren's R108-K k=1.0
  30-dispatch case moves 0.5657 % → [0.5474, 0.5709]; the 39-dispatch case 0.7354 % →
  [0.7116, 0.7422]; family-E dispatch-only 1.0690 % → [1.0343, 1.0789]; full fusion
  2.4510 % → [2.3715, 2.4737]. Every one of those stays in the band it was already in.

So the α question, which had been sitting as `N-DEGENERATE`, **does not change any freeze
decision**. That is the useful part of a null result: it removes a reason to wait.

**To frieren:** the conservatism gap in integration-tree §9.6.2 is the actionable item, not
α. At `k = 1.0`, a 30-dispatch merge is worth 0.5657 % (P = 2.07e-04 under the bracket) —
**155× worse than the 1.069 % headline** — while a 39-dispatch pair reaches 0.7354 %, and at
`k_residue = 1.4998` the 39-dispatch pair reaches 1.1029 % (P = 3.86e-02) versus 0.8484 %
for 30. **Prefer a 39-dispatch pair.** Family D (T2c routed gate+up) and family B (T2d
down+residual) are the 39-dispatch families; the advisor's steer to family E is a
30-dispatch family and is the weaker of the two options on this axis.

**To tanjiro:** the `N-BYTES-EVERYWHERE` verdict survives, but the 85–91 %-of-roofline
figures in it are **overstated**, because they are computed against 266.3 rather than the
measured 263.29 and, more importantly, because at least one family's byte census counts
cache-resident re-reads. The qkvo pool at α = 0.4369 implies an M4 achieved rate of
295.82 GB/s = **112.4 % of the measured ceiling**, which is impossible; ≥ 11.0 % of that
pool's counted bytes are served from cache, not DRAM (Part 1 §5, corroborated by R107-E §3).
Proposed rule for the ledger: **a family whose byte census includes cache-resident re-reads
may not be assigned a "% of DRAM ceiling" and may not constrain α.** This is a caveat on the
numbers, not a refutation of the verdict — the families are simply *further* from the true
roofline than stated, which if anything strengthens "bytes are not the binding constraint
everywhere".

If nezuko's R107-J′ paired instrument (#657) is available for a late-arriving candidate, I
use it in preference to my own ABBA: its CI95 half-width is ≈0.1178 % of `cs` at 10 blocks
against my 0.2666 %, i.e. 2.25× tighter, and it inflates σ by only 1.96 % against my 9.7 %.

---

## 7. Declarations

* No official receipt was spent by any work in this document or in Part 1. I have not run
  `senpai/submit-official.sh` and will not.
* Everything I touched is under `research/`: outside `editablePaths`, outside
  `harnessHash()`, zero bytes against Rule 105.14. `git diff --numstat 705484b9 HEAD --
  Sources Vendor benchmark.json Package.swift senpai` is empty, as is the same diff against
  the advisor tip `1eda2174`.
* §1 is read off the installed CLI on this host on 2026-08-10. A server-side change would be
  invisible to me, and every claim in §1 should be re-checked if the toolchain is updated.
* The default action at every checkpoint in §4 is hold.
