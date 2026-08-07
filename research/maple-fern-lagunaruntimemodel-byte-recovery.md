# LagunaRuntimeModel.swift byte recovery — measured ceiling is 9,362 B, below the stop threshold

- Assignment `maple-2026-08-07s-lagunaruntimemodel-byte-recovery` r1, PR #320
- Branch `maple-fern/lagunaruntimemodel-byte-recovery`, BASE_SHA `5c491cf0634699e9969c8909cb4403c3f465cfe3`
- Pure byte experiment. Zero semantic change intended, **no timing claim made**.
- W&B: [`vnv9q9x7`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/vnv9q9x7)
  (`research/fern_partB_wave1_wandb.py`) — byte metrics, policy attribution, and
  gate verdicts only; no timing axis.

## Verdict: the stopping rule fired, nothing was applied

The assignment set a success bar of **≥ 18,000 B net** and an explicit stop:
*"if net < ~10,000 B, stop and submit the analysis as a terminal result instead."*

After applying all five mandatory corrections, wave 1 nets **9,362 B**. That is
below 10,000, so I did **not** touch `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
The scored file is byte-identical to base in this branch. Realised recovery is
**0 B**; 9,362 B is the measured *available* ceiling under a policy I am willing
to defend.

Supporting reason the remaining bytes are not worth the risk: per-file headroom
is already **55,952 B** (the file is at 89.3% of the 524,288 B cap) and total
editable headroom is **150,223 B** with **0 / 262,144** growth used. Recovering
9.4 KB buys headroom that is not currently scarce, in exchange for touching
11,765 bytes of prose in the single most correctness-sensitive file on the
scored path.

### Gates 6, 7 and 8 are vacuous and were skipped

`./benchmark.sh --local-iterate`, the 64-step drift tripwire, and
`research/run_upstream_equivalence.sh` all verify that a source change preserved
behaviour. There is no source change. Running them would burn an M-series
allocation to confirm that base equals base. I skipped them deliberately and say
so rather than reporting a green tick that carries no information.

`./setup.sh` (gate 9) was already run for this branch in an earlier session:
exit 0 in 26 s, log at `research/partB-wave1-logs/setup.log`.

## Where the bytes went

Whole-file comment pool, all-in: **120,626 B** — 120,254 B in 254 comment blocks
plus 372 B in 5 comment lines that sit *inside* `"""` kernel-source literals
(lines 4587-4591). Those 5 lines are Metal code, not comments; they were never a
candidate in any plan and phase 1 of the dry run asserts no planned block covers
them.

Of the 120,254 B block pool, **82,899 B (69%) is hard-kept.** The plan reaches
62 blocks / 12,910 B gross.

### Attribution: each correction's cost, measured

| # | configuration | blocks | moved B |
|---|---|---|---|
| A | base (leaky) policy: `must match` in HARD_KEEP, ABSTRACT_HARD_LINES=3 | 94 | 28,643 |
| B | + rule-idiom recognition (relocate prose only) | 81 | 18,167 |
| C | + `DARKBLOOM_`-only declaration lookahead | 69 | 15,130 |
| D | + full HARD_KEEP declaration lookahead | 69 | 15,130 |
| E | + ABSTRACT_HARD_LINES=8 (my over-correction, reverted) | 22 | 5,299 |
| G | C + ABSTRACT_HARD_LINES=4 | 50 | 11,078 |
| **final** | C + `bit-exact` / bare `pin those` idioms, ABSTRACT_HARD_LINES=3 | **62** | **12,910** |

The original 86-block / 27,196 B plan was **not** a real 27 KB. Correction 1
alone (recognising bit-exactness idioms as prose that must stay) removed
10,476 B, and the declaration lookahead removed another 3,037 B. Row D shows the
full lookahead adds nothing over the `DARKBLOOM_`-only version on this file —
worth recording as a negative.

### Final planner output

```
comment pool          120254 B (25.7% of the file)
  literal-interior    5 line(s), 372 B at 4587..4591  (never a block; 0 in any plan)
  hard-keep           82899 B
planned blocks        62  (54 immediate, 8 fenced)
moved bytes           12910
pointer bytes added   2659
NET recovery          10251
projected size        458085 B  (87.4% of the 524288 B cap)

wave 1 (apply immediately): 54 blocks, 11765 B moved, 2403 B pointers, net 9362 B
wave 1 projected size   458974 B  (headroom 65314 B)
wave 2 (apply after fence): 8 blocks, 1145 B
    overlaps #301: 3 blocks, 308 B
    overlaps #308: 3 blocks, 414 B
    overlaps #309: 3 blocks, 498 B
    of which gutter-only (>=1 fence within 3 lines, none overlapping): 3 blocks, 258 B
      761-762    121 B  #309  lagunaNormReductionTail
      4034-4034   62 B  #308  lagunaGatedAffineOProjNVFP4Source
      6800-6800   75 B  #301,#308  lagunaSharedSwiGLUQMVRows1Kernel
```

Pointer overhead is **20.4% of gross** (2,659 of 12,910), a direct consequence of
correction 3 dropping the pointer floor from 500 B to 120 B. That is the right
trade — an unreachable note is worse than a smaller win — but it is why 12.9 KB
gross becomes 10.3 KB net.

## The five mandatory corrections

### 1. HARD_KEEP leaked bit-exactness rules

`HARD_KEEP` matched `must match`, which made "this must match upstream" prose
*hard-kept* for the wrong reason and, worse, left every other bit-exactness
idiom relocatable. Split into two concerns:

```python
HARD_KEEP  = DARKBLOOM_|Copyright|MARK:|Ported from|upstream        # (re.I)
RULE_IDIOM_CS = r"\bMUST\b|NOT knobs|Exactness"
RULE_IDIOM_CI = r"must be|must not|must match|load-bearing|
                 bit-(?:identical|exact)|keep .* in sync|pin(?:s|ned)? those"
```

`hard_keep()` now ORs `rule_bearing()`. Two genuine gaps found and closed while
auditing the advisor's own six pins: `bit-exact` (only `bit-identical` matched)
and bare `pin those` (only `pins`/`pinned those` matched). Both were required by
blocks 8488-8493 and 10017-10029. **I did not tune these to recover bytes** —
every edit to the idiom set lost bytes.

12 blocks / 12,085 B are hard-kept by rule-idiom recognition *alone*, largest
first: 3395-3428 (2,289 B, `Exactness`), 2312-2336 (1,671 B), 1226-1246
(1,408 B, `Exactness` + `load-bearing`), 8960-8979 (1,348 B), 9580-9599
(1,296 B), 3681-3699 (1,283 B, `bit-identical`), 2497-2510 (885 B), 1073-1079
(509 B, `NOT knobs` + `load-bearing`), 10968-10973 (453 B), 986-990 (367 B),
174-177 (296 B), 3740-3743 (280 B). The single token `Exactness` accounts for
~7,489 B and catches one of the advisor's six on its own.

### 2. DocC detach checker ignored argv

`research/fern_vendor_docc_detach_check.py` had the five MLXLMCommon paths
hardcoded, so passing it the scored file checked the vendor files instead. Now
`DEFAULT_FILES` + `FILES = sys.argv[1:] or DEFAULT_FILES`, accepting
repo-relative or absolute paths. Both invocations verified below.

### 3. Pointer coverage floor was too high

`POINTER_MIN_BYTES` 500 → **120**, and a rule-bearing block emits a pointer
regardless of size: `rb >= POINTER_MIN_BYTES or rule_bearing(rest)`. The planner
now reports both escape hatches explicitly (`0 rule-bearing blocks under 120 B,
pointed anyway`; `0 blocks dropped, pointer>=mv`).

### 4. Fence gutter was zero

Overlap with in-flight #301/#308/#309 was tested by strict intersection, so a
block one line from a fence looked safe. `FENCE_GUTTER = 3`; the spec records
both `fences` and `fences_strict`, and the planner names the 3 gutter-only
deferrals (258 B) separately so the advisor can see what a ±3 gutter actually
costs.

### 5. Planner and applier disagreed by 50 B — now machine-asserted

Root cause was never diagnosed before, only observed. Specs now carry a
`projection` block written by a shared `build()` helper, and dry-run phase 3c
asserts planner `size_before`/`size_after`/`moved_bytes` equal the applier's
actual values **to the byte**. That assertion immediately caught a second,
unrelated bug:

> **char-vs-byte accounting.** The Part B planner counted UTF-8 bytes; the Part A
> planner and my extractor counted characters. Exactly three Part B blocks
> differ — `(692,693)` 143 vs 141, `(6125,6142)` 1220 vs 1216, `(10418,10419)`
> 95 vs 93 — total delta 8 B. The **byte** count is correct: the caps in
> `benchmark.json` are byte caps. Added a shared `nbytes()` and routed every
> counting site through it.

## Two defects found in already-applied Part A work

Both are out of scope for this assignment; I fixed only what was needed to keep
the tooling self-consistent and am reporting the rest as follow-ups.

1. **Part A's reported byte totals were character counts.** 18 lines inside its
   relocated blocks contain non-ASCII (em-dashes), so its published `movedB`
   figures under-report the real bytes. The *applied* result is unaffected —
   file sizes were measured, not projected.
2. **One Part A policy decision was flipped by the same confusion.**
   `BatchKVCache.swift:708-714` measures 499 characters but **503 bytes**,
   straddling the 500 B pointer threshold. Under char counting it got
   `pointer=False`; byte counting at the same threshold would have emitted a
   pointer. Severity is low: the block is pure design narrative
   (`rule_bearing=False`), so this is a discoverability nit, not a lost pin.

To keep `--regenerate` honest I added `POINTER_MIN_BYTES_APPLIED = 500` and
pinned Part A's `plan()` to it. Without that, the corrected live value of 120
would silently re-decide **28 of Part A's 54 blocks**, overwriting the record of
what was actually applied.

## Finding the advisor should see: mid-sentence abstracts are systemic

The advisor cited 2 blocks where `keep_count` truncates an abstract mid-sentence.
Measured at `ABSTRACT_HARD_LINES=3`, it is **50 of the 62 planned blocks** —
essentially the whole plan, not an edge case
(`research/fern_partB_abstract_slack_cost.py`):

```
planned blocks: 62
mid-sentence cuts at ABSTRACT_HARD_LINES=3: 50
byte cost to finish the sentence, slack=1: 3560
byte cost to finish the sentence, slack=5: 8531
```

Finishing every sentence costs 3,560 B at 1 line of slack or 8,531 B at 5 —
i.e. 38% to 91% of the entire 9,362 B wave-1 win. **I left the valve at 3 and
report the cost rather than paying it**, because a plan whose net win is mostly
spent un-truncating its own prose is not a byte-recovery win. If the advisor
prefers readable abstracts over bytes, that is a policy call, and it is another
independent reason this experiment is not worth applying.

(These numbers supersede an earlier 56 blocks / 4,052 B / 9,831 B measurement I
took before the `bit-exact` and `pin those` idiom fixes moved 6 blocks into
hard-keep. The figures above are freshly measured against the final policy.)

## Correctness evidence

### All six advisor-flagged pins stay in the scored file

`research/fern_partB_pin_audit.py` resolves each pin to its enclosing block and
fails if the plan releases it:

```
ok    L1240  block 1226-1246  hard_keep=True  rule_bearing=True  relocated=False
ok    L2502  block 2497-2510  hard_keep=True  rule_bearing=True  relocated=False
ok    L3696  block 3681-3699  hard_keep=True  rule_bearing=True  relocated=False
ok    L4469  block 4461-4471  hard_keep=True  rule_bearing=True  relocated=False
ok    L8491  block 8488-8493  hard_keep=True  rule_bearing=True  relocated=False
ok    L10023  block 10017-10029  hard_keep=True  rule_bearing=True  relocated=False

pins released by the plan: 0
```

### Dry run: 4 arms, all behaving

`research/fern_partB_dry_run.sh [SPEC]`, phases 1-4, with
`MLXFAST_DRY_RUN_INJECT=rule|bytes|size` to prove each assertion can fail.

| arm | exit | outcome |
|---|---|---|
| clean, full spec (62 blocks) | 0 | PASS |
| clean, wave-1 spec (54 blocks) | 0 | PASS |
| `INJECT=rule` | 1 | FAIL, 3 assertions fired |
| `INJECT=bytes` | 1 | FAIL, 54 blocks failed to land |
| `INJECT=size` | 1 | FAIL, 50 B projection delta caught |

Wave-1 clean run, verbatim excerpt (full log
`research/partB-wave1-logs/dryrun-wave1.log`):

```
relocated lines            172
rule-bearing among them    0 (all behind a pointer)
blocks in spec             54
blocks that did not land   0
planner size_after         458974
actual  size_after         458974
planner net_bytes          9362
ok    projection and actual agree to the byte
phase 3 failures: 0
RESULT: PASS (dry run only; Sources/MLXFastModel/LagunaRuntimeModel.swift untouched in this checkout)
```

Fault injection, verbatim:

```
inject=rule exit=1
INJECT rule: block now covers 8488-8493 with pointer=False
FAIL  8488-8493 pointer=False lagunaNativeAffineOnlyLayer
FAIL  8488-8493 diverges at note line 11
FAIL  moved_bytes planner 11765 != extracted 12144
phase 3 failures: 3
RESULT: FAIL (phase 3/4 assertion fired under injected fault rule)

inject=bytes exit=1
INJECT bytes: dropped every section provenance line from the note
FAIL  324-324 diverges at note line 11
...
blocks that did not land   54
phase 3 failures: 1
RESULT: FAIL (phase 3/4 assertion fired under injected fault bytes)

inject=size exit=1
INJECT size: planner projection shifted by -50 B
FAIL  size_after planner 458924 != actual 458974 (delta 50)
phase 3 failures: 1
RESULT: FAIL (phase 3/4 assertion fired under injected fault size)
```

Phase 3b was itself wrong on first run and is now correct: it compared moved
bytes against note lines starting with `//`, but the applier strips comment
markers when writing the note, so it measured 0 every time. It now reconstructs
each expected section — heading, provenance line, marker-stripped body — and
asserts it appears in the note in order.

### Gate transcripts, raw and unedited

```
$ senpai/validate-assignment-scope.sh 5c491cf0634699e9969c8909cb4403c3f465cfe3 Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 1 submitted path(s) against BASE_SHA=5c491cf0634699e9969c8909cb4403c3f465cfe3
exit=0

$ senpai/check-editable-budget.sh 5c491cf0634699e9969c8909cb4403c3f465cfe3
editable budget OK: current=2849777/3000000 bytes headroom=150223 growth=0/262144 files=140 (file count is diagnostic only; base=140)
exit=0

$ python3 research/fern_vendor_docc_detach_check.py Sources/MLXFastModel/LagunaRuntimeModel.swift
mixed-style runs preceding a declaration: 0
exit=0

$ python3 research/fern_vendor_docc_detach_check.py      # default argv, 5 vendor files
mixed-style runs preceding a declaration: 0
exit=0
```

`check-editable-budget.sh` reports `growth=0`, not a negative number, precisely
because nothing was applied. A negative growth figure would have been the
signature of a real win.

### The comment-strip checker FAILS, and that is the honest result

I extended `research/frieren_comment_strip_check.sh`'s `FILES` to include the
scored file and passed BASE_SHA explicitly (its default is the stale
`e1d070f2…`). It reports `RESULT: FAIL`, exit 1:

```
--- precondition: zero comment bytes inside """ regions ---
FAIL  Sources/MLXFastModel/LagunaRuntimeModel.swift   base tripleQuotes=212 comment_lines_inside_literal=5 bytes=372
      PRECONDITION VIOLATED: this file embeds commented kernel source.
      The strip-equivalence result below is NOT VALID for this file.
FAIL  Sources/MLXFastModel/LagunaRuntimeModel.swift   head tripleQuotes=212 comment_lines_inside_literal=5 bytes=372
...
--- code residue equality (base vs head, comments normalised away) ---
ok    Sources/MLXFastModel/LagunaRuntimeModel.swift   base=468336  head=468336  saved=0  residue=347691 IDENTICAL
...
recovered  = 0
RESULT: FAIL
```

This is a property of the file, not of any candidate: 212 `"""` literals embed
Metal source, 5 lines of which begin with `//`. The checker's own header says
*"Do not relax that assertion; re-scope the PR instead"*, so I did neither
suppress the file nor weaken the check — I documented in the header why it can
never pass and where the covering check lives. The literal-aware equivalent is
dry-run phases 1-2, which **do** hold:

```
--- phase 1: literal-interior comment integrity ---
ok    literal-interior comment TEXT byte-identical
ok    line-number shift is uniform: -21 (one value = no insertion inside the literal)
ok    no planned block covers a literal-interior line

--- phase 2: code residue equality (literal-aware) ---
ok    Sources/MLXFastModel/LagunaRuntimeModel.swift  base=468336  head=458085  saved=10251  residue=348063 IDENTICAL
```

Whether the shared checker should distinguish "not covered" from "failed" is a
design question I left for the advisor rather than deciding unilaterally in a
byte experiment.

## Final byte table

| quantity | bytes |
|---|---|
| file size at base | 468,336 |
| per-file cap | 524,288 |
| headroom at base | 55,952 |
| comment pool (blocks) | 120,254 |
| comment pool all-in (incl. literal-interior) | 120,626 |
| hard-kept | 82,899 |
| wave 1 gross moved | 11,765 |
| wave 1 pointer overhead | 2,403 |
| **wave 1 net** | **9,362** |
| wave 1 projected size / headroom | 458,974 / 65,314 |
| wave 2 remainder (fenced) | 1,145 |
| full-plan net (waves 1+2) | 10,251 |
| **actually applied in this branch** | **0** |

## Suggested follow-ups (not implemented)

1. **Decide the pointer/readability policy before anyone retries this.** At
   `ABSTRACT_HARD_LINES=3` the plan truncates 50 abstracts mid-sentence; fixing
   that costs 3,560-8,531 B of a 9,362 B win. Pointer overhead is another
   2,403 B. A version of this experiment that is both readable and worth doing
   probably does not exist on this file.
2. **Fix `BatchKVCache.swift:708-714`'s missing pointer** in a Part A follow-up,
   and re-audit Part A under byte counting.
3. **Give `frieren_comment_strip_check.sh` a third verdict** (`not covered`)
   so a structurally-inapplicable file does not destroy the signal for the nine
   it does cover.
4. **If per-file headroom ever becomes scarce**, the 82,899 B hard-kept pool is
   where the bytes are — but releasing any of it needs a stronger correctness
   argument than a comment mover can provide.

## Reproduction

```bash
python3 research/fern_partB_relocation_plan.py
bash    research/fern_partB_dry_run.sh                                              # full spec
bash    research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
MLXFAST_DRY_RUN_INJECT=rule  bash research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
MLXFAST_DRY_RUN_INJECT=bytes bash research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
MLXFAST_DRY_RUN_INJECT=size  bash research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
python3 research/fern_partB_pin_audit.py
python3 research/fern_partB_abstract_slack_cost.py
research/frieren_comment_strip_check.sh 5c491cf0634699e9969c8909cb4403c3f465cfe3   # exits 1, see above
python3 research/fern_vendor_docc_detach_check.py Sources/MLXFastModel/LagunaRuntimeModel.swift
senpai/validate-assignment-scope.sh 5c491cf0634699e9969c8909cb4403c3f465cfe3 Sources/MLXFastModel/LagunaRuntimeModel.swift
senpai/check-editable-budget.sh 5c491cf0634699e9969c8909cb4403c3f465cfe3
```

Logs: `research/partB-wave1-logs/` — `planner.log` (final policy),
`planner-armE-abstract8.log` (attribution row E, kept as the record of the
reverted over-correction), `dryrun-clean.log`, `dryrun-wave1.log`,
`dryrun-inject-{rule,bytes,size}.log`, `pin-audit.log`, `comment-strip.log`,
`docc-detach.log`, `setup.log`.
