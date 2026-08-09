# r103-C — the LagunaRuntimeModel.swift per-file cap is dissolved

## 140,043 B

That is the new per-file headroom on `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
net of everything: net of the sidecar, net of the newline-preservation tax, net of
the editable-surface budget. It was **5,052 B**. The file is no longer near its cap;
it is at 73.3% of it.

- Assignment `maple-r103-c-lrm-comment-pool-rung2` rev `r103-c-rev1`, PR #575
- Branch `maple-nezuko/r103-lrm-comment-pool-rung2`, BASE_SHA `0f6862d099252d40a807df30abfbbd7c9cd596ae`
- Host: M4 Pro (Apple GPU gen 16), Darwin 25.5.0, 48 GiB, 14 CPU
- **Zero semantic change. Zero timing claim. Zero official receipts.** This arm is
  worth 0% of the score; it buys capacity for other arms, not speed.

---

## 1. What was done

`LagunaRuntimeModel.swift` is the scored forward pass and it was 519,236 B against
a 524,288 B per-file cap — 5,052 B of headroom, i.e. roughly one function's worth of
future work before the submission surface refuses the file outright. 25.3% of that
file was comment prose.

Rung 1 moves the prose out. Every `//` comment segment that the literal-aware
scanner classifies as a real comment is removed from the source and written
verbatim, in source order, with its original line anchors, into
`research/maple-nezuko-r99-lrm-provenance.md`. `research/` is not part of the
submitted surface (confirmed empirically, see N-4), so the prose survives review
without costing a submitted byte.

Two design choices carry the whole result:

1. **Line-preserving strip.** A line left empty by the strip is kept as an empty
   line rather than deleted. Swift bakes `#file`/`#line` into the default arguments
   of `precondition`, `assert` and `fatalError`; the file has 239 such sites. Keeping
   the line numbering is what makes the emitted object file byte-identical instead of
   merely behaviourally equivalent. It costs 1,984 B (one newline per emptied line)
   out of 136,975 B — a 1.4% price for an airtight proof.
2. **No in-file pointers, no kept abstracts.** The sidecar is a complete, ordered
   record with line anchors, so nothing needs to be left behind at the call site.
   In-file pointer comments would be pure overhead against the exact cap this arm
   exists to relieve. (This is the single decision that separates this result from
   the previous attempt on this file — see §7.)

## 2. Byte accounting

Rung 0 census, taken fresh on the unchanged base:

| quantity | bytes |
|---|---:|
| `LagunaRuntimeModel.swift` at base | 519,236 |
| per-file cap | 524,288 |
| **headroom at base** | **5,052** |
| literal-aware comment pool (1,985 segments) | 131,165 (25.3%) |
| relocatable blocks (contiguous runs, indentation-widened) | 284 |
| `darkbloom-flag` mentions in the pool | 72 |
| `receipt-provenance` mentions in the pool | 4 |

Rung 1 result:

| quantity | bytes |
|---|---:|
| comment text removed | 131,165 |
| orphaned leading indentation / trailing whitespace also removed | 3,826 |
| **file shrink realised** | **134,991** |
| newline-preservation tax vs a line-deleting strip | 1,984 |
| `LagunaRuntimeModel.swift` after | 384,245 |
| **headroom after** | **140,043** (27.7× base) |
| sidecar `research/maple-nezuko-r99-lrm-provenance.md` | 147,254 (does not count — N-4) |

A line-deleting strip would have freed 136,975 B (headroom 142,027 B). I did not
take those extra 1,984 B because they would have cost the object-identity proof.

Editable-surface budget, before and after:

```
before:  current=2815199/3000000  headroom=184801  growth=0/262144        files=142
after:   current=2680208/3000000  headroom=319792  growth=-134991/262144  files=142 (base=142)
```

Total editable headroom rises 184,801 → 319,792 B (+73%), and the per-review growth
allowance goes *negative*, i.e. this arm hands 134,991 B of review budget back to
whatever merges alongside it.

## 3. The acceptance oracle, and how the first one failed

Rule 74's hazard is specific: this file carries Metal kernel source inside Swift
string literals, so a `//` inside such a literal is JIT kernel text, not a comment.
"It builds" is therefore not an acceptance gate — a stripper bug that ate kernel
text would still build and would still produce wrong kernels at runtime.

**First attempt (abandoned).** Instrument the MLX JIT choke point
(`Vendor/mlx-swift/.../metal/device.cpp`, `Device::get_library`) to dump every
emitted MSL source string, then diff the corpus before and after. This produced an
**empty corpus after two complete benchmark runs** (jobs `c4ef273b-919f-4251-8864-b8d5f22d6178`
and `5bfbaa71-1089-4e5d-a4a5-253d9ba3593d`, both exit 0). The env var was renamed to
`MLX_NEZUKO_MSL_DUMP` to clear the worker's environment allowlist
(`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1928` permits the `MLX_` prefix)
and it still produced zero files.

**Frontier critique.** Rather than debug it, I asked a fresh frontier agent whether
the corpus diff was even the right gate. It is not, and the reasons are structural,
not incidental:

- the M4 Pro host never selects the `_nax` kernel family the ranked M5 uses, so a
  corpus that *had* dumped would still be blind to the kernels that matter;
- parametrized kernel-name instantiation and filename sanitisation alias distinct
  sources onto the same dump path;
- **host-side selection strings and dispatch parameters never appear in MSL at all** —
  a stripper bug that altered a Swift string used to pick a kernel would be invisible;
- the design had no A/A determinism control, so a "no diff" verdict could not be
  distinguished from "the tool does nothing".

**Adopted oracle: the Swift compiler.** If the emitted object file is byte-identical,
then every string literal, every kernel source, every selection string, every
`#line` default argument and every piece of debug metadata is identical, because all
of them are *in* that object file. This is strictly stronger than any runtime corpus
diff and it costs four builds. The `device.cpp` instrumentation was fully reverted
(`git diff 0f6862d0 -- Vendor/` → 0 files) and the revert is committed as `1d1e651`.

## 4. Gates

### G1 — emitted-object identity: **PASS**

`research/nezuko_r103c_object_identity.sh ORIG CAND` runs four **interleaved,
forced-clean** builds of the scored worker (orig, cand, orig, cand), wiping
`MLXFastModel.build/*.o` before each and asserting the object's mtime is newer than
the source's.

```
A1 orig: a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d
B1 cand: a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d
A2 orig: a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d
B2 cand: a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d
A/A determinism: PASS    B/B determinism: PASS    A/B identity: PASS
```

2,211,568 B object, four identical digests. The A/A and B/B arms are the control
that the earlier design lacked: they prove the oracle is deterministic before the
A/B arm is allowed to mean anything.

**A false PASS I nearly published.** The naive version of this check let SwiftPM do
an incremental rebuild. It reported a matching digest — from a *stale* object with
mtime 21:32:10 against a source written at 21:57:45. SwiftPM also replays cached
diagnostics, so seeing the file's warnings re-emitted is not evidence that anything
recompiled. Anyone repeating this gate needs the forced clean and the mtime
assertion; without both, the gate passes by not running.

(Housekeeping resolved along the way: three `.o` files —
`LagunaRuntimeLayers`, `LagunaDensePacked`, `LagunaR86BoundaryLadder` — are stale
artifacts of deleted sources. The module genuinely has 9 Swift files.)

### G2 — Metal / AOT surface: **PASS, and vacuous by construction**

Zero `.metal`, `.cpp` or `.h` files differ from base (`git diff 0f6862d0 --name-only`
over those extensions → 0). The metallib is byte-identical at both locations,
sha256 `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec`. I report
this as vacuous rather than as a green tick: the change touches one Swift file, so
there was never a route by which the Metal surface could move.

### G3 — trusted-test surface: **PASS (456/457)**

- `research/nezuko_embedded_header_check.py 0f6862d0…` → PASS: "changed AOT sources: 0",
  "embedded-twin risk: 0".
- Text-reading trusted tests audited by hand. Only
  `Tests/MLXFastTests/LagunaConfigTests.swift:128` mentions `LagunaRuntimeModel` at
  all, and only to instantiate it. The scanners that actually read source text target
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift`
  (`RuntimeStartupMemoryPolicyTests.swift:66,196`), the *non-existence* of
  `Gemma4SubmissionControls.swift` (`BenchmarkSupportTests.swift:750`), and synthetic
  temp fixtures (`BenchmarkScriptTests.swift`). None can see this edit.
- `swift test --force-resolved-versions`: 457 tests in 6 suites, **456 pass, 1 fail**.

The single failure is `senpaiOperationalGuidanceMatchesTheDeployedRankedPath`
(`SenpaiOperationalContractTests.swift:190`), which shells out to
`senpai/test_submit_official.py`; that file's `setUp` runs
`git push -qu origin main`, which cannot succeed in this sandbox, so all 9 of its
cases error in setUp (`FFFFFFFFF`). It is a sandbox/network artifact in `senpai/`,
not a submitted-surface file, and it is independent of this change — G1 proves the
compiled `LagunaRuntimeModel` object is byte-identical, so no test outcome *can*
depend on the edit.

### G4 — relocation soundness: **PASS**

`research/nezuko_r103c_relocation_verify.py ORIG STRIPPED SIDECAR`:

```
1. line numbering preserved:        PASS (12147 lines)
2. canonical digest unchanged:      PASS (b876ca17398806e1)
3a. block count:                    PASS (284)
3b. verbatim prose in source order: PASS (136699 bytes of pool)
4. reconstruction:                  PASS (byte-identical to original)
```

Check 2 is the literal-aware canonical hash: it strips comments but preserves string
and character literals verbatim, so a stripper bug that ate kernel text inside a
literal would change the digest. Check 4 is the strongest form — the original file is
*reconstructed* from stripped source plus sidecar and compared byte for byte.

Idempotence verified separately: re-applying the tool to the stripped file yields
0 blocks, 0 bytes, file unchanged.

### End-to-end runs

| run | tree | verdict |
|---|---|---|
| A | unchanged base | `passed: true`, `passed_correctness: true`, `max_abs_diff: 0`, 1023 decode tokens checked, exit 0 in 259.7 s |
| D | candidate | `passed: true`, `passed_correctness: true`, `max_abs_diff: 0`, 1023 decode tokens checked, exit 0 in 218.9 s |

Both were `./benchmark.sh --local-submit`. Across the two runs:

- `golden_hash` identical: `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`
- `weights_hash` identical: `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`
- `harness_hash` **differs** (`8281cd25…` → `f536f253…`)

The last one is a positive control worth stating: it confirms Run D really did
measure the modified tree rather than accidentally re-measuring base. The source
changed; the outputs did not.

`passed_prefill_speedup_floor` is `false` in *both* runs (prefill speedup 0.33× on
each). That is a property of this M4 Pro host, which reports Apple GPU generation 16
and never selects the `_nax` prefill kernels the ranked M5 uses. It is present
identically at base and is not a property of this change.

Their timing fields are recorded in Appendix B for the archive and are **not** used
as evidence of anything; see §6.

## 5. Preregistered nulls

| null | condition | fired? |
|---|---|---|
| N-1 | comment pool < 80,000 B → stop | **No.** Pool 131,165 B (25.3%). |
| N-2 | G1 fails → stop immediately, report the kernel and bytes | **No.** G1 passed with an A/A control. |
| N-3 | G4 fails → tool is unsound, stop | **No.** G4 passed. It initially failed check 4 because block spans excluded leading indentation; the fix widens each span backward over spaces and tabs, and the reconstruction is now byte-exact. |
| N-4 | `research/` counts against the 3,000,000 B budget → report net separately | **No, confirmed empirically.** `senpai/check-editable-budget.sh` reports `current=2680208` after adding a 147,254 B sidecar to `research/`, i.e. the sidecar is invisible to the budget. **Net = gross.** |

## 6. Rung 3 (timing null) — deliberately not run

The assignment makes rung 3 optional if G1 and G2 both pass. Both passed, so it is
skipped, and this is the correct call for a reason stronger than cost: **G1 is a
proof of the thing rung 3 could only estimate.** The emitted object file is
byte-identical, so the binary that runs is the same binary. A timing experiment can
only add noise to a question that already has an exact answer.

I want to be explicit about the failure mode this avoids, because I committed it on
rung 1 of the predecessor arm: I reported a timing result as "neutral" when the
observed spread was 0.565%, about 73 µs/step. "Neutral" without a stated bound X is
not a result, it is a vibe. If anyone ever does run rung 3 here, the report must read
"no effect larger than X µs/step" with X printed, and X will be worse than the exact
zero G1 already gives.

For the same reason I make **no timing claim of any kind** in this report, including
from runs A and D.

## 7. Prior art (rule 83 archive sweep) and one resolved discrepancy

I grepped the research archive before writing this. Three prior measurements of this
file's comment pool exist, and they disagree:

| source | pool measured | file size at its base |
|---|---:|---:|
| PR #311 | 120,254 B | — |
| `research/maple-fern-lagunaruntimemodel-byte-recovery.md` (PR #320, BASE_SHA `5c491cf0…`) | 120,254 B | 468,336 B |
| PR #548 | 130,149 B | — |
| this arm (BASE_SHA `0f6862d0…`) | 131,165 B | 519,236 B |

Pool size tracks file size across bases, so the 120,254 → 130,149 → 131,165 drift is
just the file growing. That part is consistent.

The discrepancy worth flagging is the *recovery ceiling*. PR #320 concluded the
measured ceiling on this exact file was **9,362 B net** (11,765 B gross minus 2,403 B
of pointer overhead), fired its own ≥10,000 B stopping rule, and applied nothing —
correctly, under its own policy. That number is 14× smaller than the 134,991 B
realised here, and the gap is **entirely policy, not measurement**:

- PR #320 moved 54 of the blocks; this arm moves all 284.
- PR #320 kept a 3-line abstract in place for each moved block and inserted a pointer
  comment, paying 2,403 B of in-file overhead and leaving 82,899 B classified as
  "hard-kept". This arm keeps nothing in file and pays 0 B of pointer overhead,
  because the sidecar is ordered and line-anchored and therefore navigable without
  in-file breadcrumbs.
- PR #320 was working against 55,952 B of headroom and explicitly reasoned that
  "headroom is not currently scarce". At `0f6862d0…` headroom is 5,052 B. The
  cost/benefit that justified stopping then does not hold now.

Its own follow-up note anticipated this: *"a version of this experiment that is both
readable and worth doing probably does not exist on this file"*. It does — but only
if you stop trying to keep the prose in the file.

**No prior attempt has ever applied comment stripping to any file under `Sources/`.**
PR #548's rung 0 stripped only `Vendor/` files (176,468 B freed). This is the first
time the technique is applied to a scored-path source file, which is why the
acceptance bar here is object identity rather than a build.

`research/frieren_comment_strip_check.sh` is **not cited as evidence anywhere in this
report**, and must not be. Its `normalise()` (lines 81–90) strips `//` regardless of
literal state, so on a file that carries Metal source inside Swift string literals it
cannot distinguish a correct strip from one that ate kernel text. It can never
validly pass on `LagunaRuntimeModel.swift`.

## 8. Hazard-absence assertions

Verified directly on the base file, because each of these would have been a route to
a silent semantic change:

| hazard | count |
|---|---:|
| `/* … */` block comments | 0 |
| raw string literals `#"` | 0 |
| regex literals | 0 |
| `#sourceLocation` directives | 0 |
| explicit `#line` / `#file` / `#function` | 0 (only implicit default args) |
| CR bytes | 0 |
| U+2028 / U+2029 | 0 |
| tab characters | 0 |
| backtick fences | 0 |
| comment segments | 1,985 |
| …of which trailing (same line as code) | **1** |

Zero block comments is the load-bearing one: every comment in the file is `//`-style,
and 1,984 of the 1,985 are full-line, so **no column shift is possible** — the strip
cannot move any code character sideways. Combined with line preservation, no code
character changes its (line, column) position at all. That is why G1 was expected to
pass rather than hoped to.

## 9. Reproduction

```bash
BASE=0f6862d099252d40a807df30abfbbd7c9cd596ae
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
SIDECAR=research/maple-nezuko-r99-lrm-provenance.md

# rung 0 — census
git show "$BASE:$SRC" > /tmp/lrm_orig.swift
python3 research/nezuko_comment_tool.py census /tmp/lrm_orig.swift

# rung 1 — relocate (idempotent: re-running yields 0 blocks, 0 bytes)
git checkout "$BASE" -- "$SRC"
python3 research/nezuko_relocate_tool.py apply "$SRC" "$SIDECAR"
cp "$SRC" /tmp/lrm_cand.swift

# G4 — lossless and exactly reversible
python3 research/nezuko_r103c_relocation_verify.py /tmp/lrm_orig.swift "$SRC" "$SIDECAR"

# G1 — the compiler agrees, with A/A and B/B controls
research/nezuko_r103c_object_identity.sh /tmp/lrm_orig.swift /tmp/lrm_cand.swift

# end-to-end
./benchmark.sh --local-submit
```

## 10. Suggested follow-ups (not implemented)

1. **Spend the headroom.** 140,043 B on the scored forward pass is the deliverable;
   it is only worth something if a later arm uses it. The negative growth figure
   (−134,991 B) also means an arm that merges alongside this one gets its full
   262,144 B review allowance back.
2. **Run the same rung on the other near-cap submitted files.** The tooling is now
   proven on the hardest case — a file with Metal source in string literals. Anything
   else on the surface is easier.
3. **Retire `research/frieren_comment_strip_check.sh` or give it a third verdict.**
   It currently returns PASS/FAIL where the honest answer on literal-bearing files is
   "not covered". PR #320's follow-up #3 asked for the same thing. Until then it is a
   trap: it will happily green-light a strip that ate kernel text.
4. **Adopt object-file identity as the standard gate for zero-semantic-change arms.**
   Four forced-clean builds, one A/A control, one digest comparison. It is cheaper
   than a benchmark run and it proves more.

---

## Appendix A — digests

Submitted surface:

| path | bytes | sha256 |
|---|---:|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` (base) | 519,236 | (canonical `b876ca17398806e1`) |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` (candidate) | 384,245 | `a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4` |

Research surface (not submitted):

| path | bytes | sha256 |
|---|---:|---|
| `research/maple-nezuko-r99-lrm-provenance.md` | 147,254 | `46e4dc2a14d44b13c0418d1fa0a2b67792120f627ad99e9e1955acb4894a45a9` |

Build products:

| artifact | sha256 |
|---|---|
| `MLXFastModel.build/LagunaRuntimeModel.swift.o` (all four builds) | `a241e0f9ab439dbe934c000d3db4758d9f4df6a3ea95364cd5e37554a2a5068d` |
| `mlx.metallib` (both locations, base and candidate) | `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec` |

Evidence logs (kept outside the repo at `workspace/evidence-r103c/`):

| file | sha256 |
|---|---|
| `runA-base-local-submit.log` | `c3da501d17708824d08a9a281bc0e2e012ae5bb7be583865f9909af32beff8f5` |
| `g1-aa-control.txt` | `c31c4a820cfc3e6d48d06568d19670e1dac8f5bf5faf3c1646320543243cc483` |
| `g1-object-identity.log` | `8baf78e7ed1decb69d10bd9bd11863ed03a36237c4944fa30df256720a4d5282` |
| `g3-swift-test.log` | `48bbebb974277a6ee45f916fe2629b88a877dcdb5bf41e28a681226e6e556f10` |
| `g4-relocation-verify.log` | `6dd21108ce88bc16be8003ef4806249ccd13f3e3637ef60959f0e0fd34e7afc9` |
| `runD-candidate-local-submit.log` | `cf17492e5902276fad0966777d715302d20f63c635e8efbe270df4dc371ed2dc` |

## Appendix B — recorded run fields (archive only, not a claim)

| run | tree | prefill s/tok | prefill ×  | decode s/tok | decode × | est score | wall |
|---|---|---:|---:|---:|---:|---:|---:|
| A | base | 0.001138 | 0.323 | 0.008945 | 1.549 | 1.0467 | 259.7 s |
| D | candidate | 0.001124 | 0.327 | 0.008966 | 1.545 | 1.0481 | 218.9 s |

These are single unpaired runs on a non-ranked M4 Pro host, taken for correctness and
packaging. They carry no timing information about this change and none is claimed. In
particular, do not read the est-score column: G1 proves the emitted object is
byte-identical, so any difference here is host noise by construction, and I have not
computed a µs/step bound that would let me say otherwise.
