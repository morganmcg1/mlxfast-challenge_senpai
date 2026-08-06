# PR #81 r2 — Metal-literal byte reclamation, regenerated at the post-#72 base

Delta document. The full method, threat model, exclusion argument, tier catalogue, and the
§6.3 A/A noise-floor finding live in the r1 report,
[`research/maple-tanjiro-pr81-metal-byte-reclaim.md`](maple-tanjiro-pr81-metal-byte-reclaim.md),
which remains accurate as method. Everything numeric below supersedes it.

r2 was requested as a **mechanical regeneration**, not a new experiment: the advisor accepted the
r1 work and selected tiers **T1 + T2**, then moved the assignment base to
`9e8c719f453151bd7b4e678cb6edbb06aaa18bad` (nezuko's #72 merged) and gave #81 merge priority.

**Metric — `editable_bytes_reclaimed` = 42,973 B** (r1: 42,757 B), at zero change to the emitted
Metal token stream and zero change to checked output.

---

## 1. Rebase mechanics

Per the r2 checklist, the two r1 code commits were discarded **as text** and the tool commits were
replayed onto the new base:

| r1 commit | r2 commit | content |
|---|---|---|
| `5319168` | `a93304e` | tool + r1 manifests |
| `109ee2c` | `9269a8b` | T2 strip / MSL certify subcommands |
| `ecf288c` | `bc71366` | r1 report |
| `2fb4b33` (T1) | `3ee10cf` (T1) | **regenerated**, not ported |
| `114dce2` (T2) | `2ffd343` (T2) | **regenerated**, not ported |

The r1 tip is preserved locally on `tanjiro-pr81-r1-backup` (`ecf288c`) for audit only.

Regeneration was the right call rather than conflict resolution. #72 rewrote
`LagunaRuntimeModel.swift` with 84 insertions / 98 deletions spread over **36 zero-context hunks**,
all in the routed-SwiGLU QMV region (≈L7330–L7900) — i.e. inside the same Metal literal bodies that
T1 re-indents and T2 strips. A textual replay of the r1 diffs would have had to be hand-repaired
line by line inside kernel source strings, which is exactly the failure mode the tool exists to
avoid. Both code commits are tool output; regenerate after every rebase and never hand-edit them.

New r2 branch tip: `3ee10cf` (T1) → `3858e98` (mitigation artefact) → `2ffd343` (T2) →
`fc884b1` (r2 manifests) → this report.

## 2. New-base facts

| quantity | r1 base `ab1f9a13` | r2 base `9e8c719f` |
|---|---:|---:|
| `LagunaRuntimeModel.swift` | 521,768 B | **521,506 B** |
| newlines | 11,512 | 11,512 |
| multi-line literal blocks | 108 | **108** |
| `"""` delimiters | 216 | 216 |

**The literal census did not move.** The advisor expected the literal count to change under #72;
it did not. #72 edited *inside* existing literals and added no new triple-quoted block, so the
census, the exclusion set, and the tier arithmetic all carry over structurally while the byte
totals shift slightly. Recorded so the next rebase does not assume a changed census either.

Census at `9e8c719f` (`research/out/tanjiro-pr81-r2/census-base.txt`): literal bodies 188,950 B
(36.2 % of the file); T1 theoretical saving 29,952 B; T2 in-literal comment pool 14,971 B on 216
lines; comment pool *outside* literals 125,463 B (untouched — that is tier T3, still unattempted);
39 single-line concatenation lines / 2,341 B; 0 tabs, 0 CR, 0 trailing whitespace. Closing-delimiter
indent histogram 4→17, 8→83, 12→8. Parser round-trip byte-exact.

## 3. T1 — dedent (commit `3ee10cf`)

105 of 108 blocks dedented; **29,576 B** removed (accounted total 29,576, exact);
521,506 → **491,930 B**. Three blocks skipped as forbidden, unchanged from r1:

| block | lines | dedent bytes foregone |
|---|---|---:|
| `lagunaTailNVFP4QMVHeader` (interpolated) | L4654–4701 | 184 |
| `source` (M5 injection instrument, T0) | L11373–11392 | 152 |
| `source` (M5 injection instrument, T0) | L11406–11411 | 40 |

T1 inserts and deletes no lines: newline count is 11,512 before and after, so **every base line
number stays valid** — which is what makes the T2 artefact's line numbers meaningful.

Idempotence: a second `dedent` run reports 0 blocks / 0 bytes.
Whitespace-only proof: `git diff --ignore-all-space 9e8c719f 3ee10cf` is **empty**, against a raw
diff of 4,094 insertions / 4,094 deletions.

### 3.1 Emitted-MSL certificate for T1

`dump` extracts every string Swift will hand to the Metal compiler: 108 multi-line literals + 1
single-line concatenation blob = **109 strings, 100 % coverage** of the file's string content.

- `diff MANIFEST_base.txt MANIFEST_t1.txt` → **empty** (109 lines, sha256 + byte size per string).
- `diff -r dump_base dump_t1` → **empty**.
- `certify dump_base dump_t1` → `109 strings compared; 109 byte-identical; 0 differ; 0 explained;
  **0 UNEXPLAINED**`.

T1 therefore changes the emitted Metal Shading Language by exactly zero bytes. This is the
mechanically strongest of the two tiers and is safe to take alone if the advisor ever wants to
split the commit.

## 4. T2 — strip in-literal comments (commit `2ffd343`)

**224 comments removed** (211 comment-only lines deleted, 13 trailing comments cut) across **32
literals**; **13,397 B** removed; 491,930 → **478,533 B**. Newlines 11,512 → 11,301, a drop of
exactly 211, matching the whole-line deletions.

Skipped forbidden regions and the comment bytes thereby foregone:
`lagunaTailNVFP4QMVHeader` L4654–4701 → 370 B; the two T0 injection-instrument literals → 0 B each
(they hold no comments).

Idempotence: a second `strip` run removes 0 comments and leaves the file byte-identical
(`cmp` clean). The parser still round-trips the stripped file byte-for-byte.

### 4.1 Emitted-MSL certificate for T2

T2 is the one tier that *does* change emitted MSL text, so the claim is deliberately narrower than
T1's and is certified rather than asserted: every changed string is reproduced byte-for-byte by an
**independent** C-style comment stripper applied to the base string. The Metal lexer discards `//`
comments before parsing, so an MSL-comment-only delta cannot change the compiled program.

- `certify dump_base dump_t2` → `109 compared; 77 byte-identical; 32 differ; 32 explained as pure
  comment removal; **0 UNEXPLAINED**`.
- `certify dump_t1 dump_t2` → identical verdict, confirming T2 is independent of T1.
- The 32 differing strings are exactly the 32 literals listed in the mitigation artefact.

**String-internal / whole-file delta identity.** Summed dumped-string bytes:
161,514 (base) → 148,117 (T2) = **−13,397 B**, which equals the whole-file T1→T2 delta of
13,397 B *exactly*. So every byte T2 removed came out of a string interior and **zero Swift code
bytes were touched**. Combined with §3's byte-identical manifests, the same identity holds for the
full base→T1+T2 reclamation: 42,973 B = 29,576 B of Swift-source indentation that never reaches the
compiler + 13,397 B of MSL comments that the Metal lexer discards.

### 4.2 Mitigation artefact (advisor §3 requirement)

`research/maple-tanjiro-pr81-stripped-msl-comments.md` (22,176 B, not a submitted path → **0
submitted bytes**) records all 224 removed comments, grouped by enclosing literal, each with its
kind (`whole-line` / `trailing`) and its line number in the pre-T2 tree — which §3 showed is also
the base line number. It is generated by
`research/tanjiro_metal_literal_tool.py strip <file> <report>`; regenerate on rebase, do not
hand-edit. Literals opened by a bare `return """` are labelled with the enclosing
function so every group is humanly locatable.

## 5. Static guards on the T1+T2 tree (§6.2)

| guard | base `9e8c719f` | T1+T2 | verdict |
|---|---|---|---|
| `DARKBLOOM_INJECT_DECODE_EMPTY` value | `0` | `0` (L11117) | intact |
| `DARKBLOOM_INJECT_EMPTY_TG` value | `160` | `160` (L11129) | intact |
| lines ending in `\` | 81 | 81 | unchanged |
| `#pragma clang loop unroll(full)` | 20 | 20 | unchanged |
| `#pragma` total | 24 | 24 | unchanged |
| tabs / CR / trailing-ws lines | 0 / 0 / 0 | 0 / 0 / 0 | unchanged |
| `"""` delimiters | 216 | 216 | unchanged |
| `swiftc -parse` | — | exit **0** | pass |

Counting note for whoever re-runs this: `grep -cE '\\\\$'` reports 80 backslash-EOL lines, one
short, because of shell quoting. The Python count (81) is authoritative; both bases agree.

## 6. Byte accounting

| | bytes |
|---|---:|
| base `LagunaRuntimeModel.swift` | 521,506 |
| after T1 | 491,930 (−29,576) |
| after T1+T2 | **478,533** (−13,397) |
| **total reclaimed** | **42,973** |

`senpai/validate-assignment-scope.sh 9e8c719f… Sources/MLXFastModel/LagunaRuntimeModel.swift`
→ `assignment scope OK: 1 submitted path(s)`, exit 0.

`senpai/check-editable-budget.sh 9e8c719f…` →
`current=2930084/3000000 bytes headroom=69916 growth=-42973/262144 files=142`, exit 0.

Two headrooms improve, and the second one matters more than the metric name suggests:

- **Total surface headroom 26,943 → 69,916 B (×2.59).**
- **Per-file headroom on the scored forward pass: 2,782 → 45,755 B (×16.4).** The 524,288 B
  per-file cap was the binding constraint: at the base, `LagunaRuntimeModel.swift` sat 2,782 B
  below it, so any future experiment adding more than ~2.7 kB to the scored file would have been
  refused by static review regardless of total headroom. That is now a 45.7 kB allowance.

## 7. Timing and correctness — one arm (§7 of the checklist)

One `./benchmark.sh --local-iterate` arm on the rebased T1+T2 candidate, per the advisor's
instruction not to repeat the r1 no-harm campaign:

| field | value | vs r1 |
|---|---|---|
| `passed_correctness` | **`true`** | same |
| `max_abs_diff` | **0** | same |
| `checked_steps` | **130** | same |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` | **character-for-character identical** |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` | **identical** |
| `peak_ram_gb` | 20.714 | ≈ same (21) |

The `golden_hash` is quoted in full so it can be compared by eye against r1 §4.1: the greedy token
stream is unchanged across a base change, a rebase, and both tiers.

Raw timing from the same arm, recorded for completeness and **not** offered as evidence:

| | value |
|---|---:|
| prefill seconds/token | 0.001112 |
| `prefill_speedup` | 0.330 (`passed_prefill_speedup_floor = false`) |
| decode seconds/token | 0.013054 |
| `decode_speedup` | 1.061 (`passed_decode_speedup_floor = true`) |
| local `est_score` | 0.793 |
| measured seconds | 2.2 (wall 152.1) |

Three honest caveats, in decreasing order of importance:

1. **T1 and T2 cannot change timing by construction.** T1 emits byte-identical MSL (§3.1) and T2
   emits MSL differing only in lexer-discarded comments (§4.1); no dispatch, geometry, allocation,
   or Swift control flow moves. Any measured delta is host noise. I am not claiming a speedup and
   the advisor should not read one here.
2. **The printed comparison is against a stale, unmatched baseline.** `benchmark.sh` differenced
   this arm against `score.local-iterate.baseline.json`, whose 0.013134 decode s/token is the r1-era
   base arm from a *different* base and a *different* session. It reports prefill −2.1 %, decode
   −0.6 %, `est_score` 0.785 → 0.793 (+1 %). Per `AGENTS.md` that is a stale cross-session
   comparison and per r1 §6.3 / programme law §0.9.32 both deltas sit at or near this host's A/A
   spread on byte-identical bytes (decode ±0.460 %, prefill ±0.822 % over a ~2.2 s timed phase).
   Treat it as "no harm detected", nothing more.
3. **`passed_prefill_speedup_floor = false` is a pre-existing M4 artefact**, not a regression: the
   local prefill floor compares this 48 GiB M4 Pro against the M5-derived pinned constant
   0.000368 s/token, which this host cannot reach. r1 measured the same `prefill_speedup ≈ 0.32`
   with the same `false` verdict **on the unchanged base**. The 0.330 here is if anything marginally
   better than the base observation. The M5 ranked run is the authority.

Reproduction: `./benchmark.sh --local-iterate` at `2ffd343` (T1+T2), 48 GiB M4 Pro, low-memory
startup profile active, thermal gate honoured on both phases (28.4 s prefill, 28.6 s decode), one
model-holding process.

## 8. Deliberately not re-run

- **The r1 no-harm timing campaign** (4 arms + A/A). The advisor ruled one arm sufficient; r1 §6.3
  already established that this 48 GiB M4 Pro host's `--local-iterate` timed phase (~2.3 s) has an
  A/A spread of decode +0.460 % / prefill −0.822 % on byte-identical bytes, so additional local
  arms buy noise, not evidence. That finding is now programme law §0.9.32.
- **`LagunaUpstreamEquivalence`.** The advisor characterised the r1 failure as a base-invariant M4
  host property, already controlled with a matched unchanged-base run: exit 1 at
  `LagunaCorrectnessTests.swift:249` with prefill `maximumAbsoluteLogitError = 0.125`
  (mean 0.011933609) over 5,991/5,991 tokens and all 8 decode steps exact, *identically on the
  unchanged base*. Nothing in T1/T2 can move it: T1 emits byte-identical MSL and T2 emits
  MSL that differs only in discarded comments.
- **T3 / T6 / T7**, out of scope for this assignment.

## 9. Suggested follow-ups

Not implemented here; offered for the advisor's queue.

1. **T3 — the comment pool outside the literals, ~18,286 B.** The largest remaining single-file
   reclamation, and the census re-measured it at the new base as 125,463 B of Swift-side comment
   bytes. It is riskier than T1/T2 in review terms because it deletes human-facing rationale from
   the scored file rather than from kernel strings, so it wants an explicit advisor policy on how
   much Swift commentary the submitted surface must retain, plus the same
   `research/`-side mitigation artefact this PR established for T2. Suggest deciding the policy
   before the next byte crunch, not during it.
2. **T4 — the fused-attention header hoist, 2,449 B.** Now *provable* rather than estimated: after
   T2 the sliding-window and full fused-attention headers are byte-identical, so one shared
   `let` replaces two literals with no MSL delta at all. Small, mechanical, certifiable by the
   same `certify` path.
3. **Run the T1 certificate as a cheap CI-style guard.** `dump` + `MANIFEST` diff costs seconds and
   would catch any future whitespace-only refactor of the scored file that accidentally changes an
   emitted kernel — a class of bug that no timing arm and no golden-token check will localise for
   you.
4. **Re-examine the per-file cap as an optimisation target in its own right.** The 2,782 B
   pre-#81 margin means the programme was one moderate kernel addition away from a static-review
   refusal on the most-edited file in the repo. A standing rule — e.g. keep ≥20 kB per-file margin
   on `LagunaRuntimeModel.swift` — would convert this PR's one-off win into a durable invariant.

## 10. Reproduction

```bash
git checkout 9e8c719f453151bd7b4e678cb6edbb06aaa18bad -- Sources/MLXFastModel/LagunaRuntimeModel.swift
O=research/out/tanjiro-pr81-r2
python3 research/tanjiro_metal_literal_tool.py census Sources/MLXFastModel/LagunaRuntimeModel.swift
python3 research/tanjiro_metal_literal_tool.py dump   Sources/MLXFastModel/LagunaRuntimeModel.swift $O/dump_base
python3 research/tanjiro_metal_literal_tool.py dedent Sources/MLXFastModel/LagunaRuntimeModel.swift   # T1
python3 research/tanjiro_metal_literal_tool.py dump   Sources/MLXFastModel/LagunaRuntimeModel.swift $O/dump_t1
python3 research/tanjiro_metal_literal_tool.py strip  Sources/MLXFastModel/LagunaRuntimeModel.swift \
        research/maple-tanjiro-pr81-stripped-msl-comments.md                                          # T2
python3 research/tanjiro_metal_literal_tool.py dump   Sources/MLXFastModel/LagunaRuntimeModel.swift $O/dump_t2
python3 research/tanjiro_metal_literal_tool.py certify $O/dump_base $O/dump_t1   # 0 UNEXPLAINED, 109 identical
python3 research/tanjiro_metal_literal_tool.py certify $O/dump_base $O/dump_t2   # 0 UNEXPLAINED, 32 explained
senpai/validate-assignment-scope.sh 9e8c719f453151bd7b4e678cb6edbb06aaa18bad \
        Sources/MLXFastModel/LagunaRuntimeModel.swift
senpai/check-editable-budget.sh 9e8c719f453151bd7b4e678cb6edbb06aaa18bad
./benchmark.sh --local-iterate
```

The `dump_*` trees are regenerable in seconds and are intentionally not committed; only
`census-base.txt` and the three `MANIFEST_*.txt` files are in-tree, which is what the certificate
actually needs.

No W&B runs exist in this campaign, so the structured result carries an empty `runs` list; that is
correct rather than missing. The durable evidence is the `research/*.md` artefacts and the committed
manifests cited above.

## 11. Structured result

Reported through the typed Senpai transition, not restated as PR-body text:

| field | value |
|---|---|
| status | `succeeded` |
| primary metric | `editable_bytes_reclaimed` |
| direction | `maximize` |
| baseline | 0 |
| candidate | **42973** |
| delta | **+42973** |
