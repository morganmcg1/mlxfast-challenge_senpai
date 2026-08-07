# LagunaRuntimeModel.swift comment-relocation manifest

Part B of `maple-2026-08-07r-vendor-byte-recovery` (PR #311).

Base `63ab67c888e1892086b7b5b623de4dd0ebe68c90`. Measured on an M4 Pro
(Apple GPU generation 16, 48 GiB, low-memory startup profile).

**`Sources/MLXFastModel/LagunaRuntimeModel.swift` is not modified by this PR.**
Its SHA-256 is `56d16941d61c5f1217faad6ef86dcc766b1632ac7078015702bc7f42a9434fcf`
at 468,336 B before and after every command below. The dry run copies the file
into `$TMPDIR` and re-hashes the repository copy afterwards; a mismatch is a hard
failure of `research/fern_partB_dry_run.sh`.

## 1. Why this file is the one that matters

| | bytes |
|---|---:|
| file size | 468,336 |
| per-file submission cap | 524,288 |
| headroom today | **55,952** |
| comment pool | 120,254 (25.7% of the file) |
| ... of which `///` | 96,027 |
| ... of which `//` | 24,227 |
| ... inside a `"""` literal | 372 |

Three PRs are in flight against this file (#301, #308, #309). At 55,952 B of
headroom a single sizeable addition from any of them can put the submission
surface over a hard static-review limit that local timing will never catch.

Reproduce:

```bash
python3 research/fern_vendor_byte_census.py census \
    Sources/MLXFastModel/LagunaRuntimeModel.swift
```

## 2. The 372 in-literal bytes

Five lines look like Swift comments but sit inside a `"""` multi-line literal
that carries Metal kernel source. They are compile input, not documentation:

```
4587            // Split-nibble decode: the same eight `half` bit patterns per
4588            // code word as the original shift+mask sequence, in fewer
4589            // integer ops with three mask constants instead of eight — the
4590            // form the current stock `fp_qmv_fast` compiles (every form is
4591            // an OR of masked shifts, so the decode is bit-identical).
```

Two independent guards keep them out of every plan:

1. `research/frieren_comment_blocks.py` only opens a block when the line is
   outside a literal on both the pre- and post-toggle state, so these five lines
   are never even offered as a candidate. `frieren_relocate_comments.py` repeats
   the check and refuses the spec if a range touches a literal.
2. `research/fern_partB_relocation_plan.py` recomputes the literal-interior set
   with the same awk semantics the checker uses and exits non-zero if any
   planned range covers one.

### The existing checker cannot validate this file as written

`research/frieren_comment_strip_check.sh` phase 1 asserts
`comment_lines_inside_literal=0` file-wide. On this file it reports
`bad=5 badbytes=372`, and that assertion is doing exactly its job: the checker's
`normalise()` strips every line matching `^[[:space:]]*//`, including lines
inside a literal, so a real change to embedded kernel source would be invisible
to phase 2. The assertion has **not** been relaxed. `fern_partB_dry_run.sh`
supplies a strictly stronger replacement for this one file:

- phase 1 enumerates the five lines and proves their **text** is byte-identical
  before and after, plus that their line-number shift is a single uniform value
  (a non-uniform shift would mean something was inserted inside the literal);
- phase 2 uses a literal-aware normaliser that keeps `"""`-interior lines, so
  kernel source is compared rather than deleted.

Whoever lands this manifest must use the literal-aware checker. Extending
`frieren_comment_strip_check.sh`'s `FILES=(...)` with this path without also
making `normalise()` literal-aware would produce a green result that proves
nothing.

## 3. Policy

Identical to Part A (`research/fern_vendor_relocate_plan.py`), so both halves of
the byte recovery answer to one auditable rule.

**HARD KEEP (whole block, never split)** — any block matching
`DARKBLOOM_|Copyright|MARK:|must match|Ported from|upstream` (case-insensitive).
That is 58,837 B, 48.9% of the pool, and it deliberately over-keeps: the regex
catches every live flag contract, every "must match the Metal kernel" pin, every
upstream-deviation marker, every `MARK:` separator and the copyright header.

**ABSTRACT KEEP (default)** — the block's opening sentence stays at the
declaration: leading lines up to and including the first ending in `.`/`!`/`?`,
stopping early at a blank comment line or a DocC section marker, never more than
3 lines. Only the remainder moves, and only when it clears 30 B.

**Pointer** — a block moving ≥ 500 B leaves one
`// See notes/LagunaRuntimeModel.notes.md#<symbol>` line. The applier mirrors the
block's own marker style, so a `///` run never gets a `//` line spliced into it
(that would silently truncate the DocC abstract attached to the declaration
below). `research/fern_vendor_docc_detach_check.py` machine-checks this.

## 4. Projected result

```
comment blocks          254
  literal-interior      5 line(s), 372 B at 4587,4588,4589,4590,4591  (never in any plan)
  hard-keep             58,837 B
planned blocks          94  (86 immediate, 8 fenced)
moved bytes             28,643
pointer bytes added        980
NET recovery            27,663
projected size         440,673 B  (84.0% of the 524,288 B cap)
headroom now            55,952 B
headroom projected      83,615 B   (+49.4%)
```

Dry run, both proofs green:

```
$ research/fern_partB_dry_run.sh
repo copy  before  56d16941d61c5f1217faad6ef86dcc766b1632ac7078015702bc7f42a9434fcf  468336 B
repo copy  after   56d16941d61c5f1217faad6ef86dcc766b1632ac7078015702bc7f42a9434fcf
ok    repository copy of Sources/MLXFastModel/LagunaRuntimeModel.swift is byte-identical

--- phase 1: comment-looking lines inside """ literals ---
base literal-interior comment lines = 5 (372 B)
head literal-interior comment lines = 5
ok    literal-interior comment TEXT byte-identical
ok    line-number shift is uniform: -190 (one value = no insertion inside the literal)
ok    no planned block covers a literal-interior line

--- phase 2: code residue equality (literal-aware) ---
ok    Sources/MLXFastModel/LagunaRuntimeModel.swift  base=468336  head=440673  saved=27663   residue=348063 IDENTICAL

RESULT: PASS (dry run only; Sources/MLXFastModel/LagunaRuntimeModel.swift untouched in this checkout)
```

`residue=348063` is the code left after comments are normalised away. It is
identical between the pristine and relocated copies, so the manifest is provably
a comment-only change.

## 5. Fence subtotals

A planned block is **apply after fence** when it overlaps a declared in-flight
range; otherwise **apply immediately**.

| PR | declared ranges | planned blocks overlapping | bytes |
|---|---|---:|---:|
| #301 | `:6577-6716`, `:6801-6900`, `:7545-7690` | 2 | 233 |
| #308 | `:4035-4457`, `:6801-6900`, `:7545-7690`, `:7851-8027` | 1 | 277 |
| #309 | `:4610-4881`, `:763-792`, `:801`, `:837-1099` | 5 | 937 |
| **wave 2 total** (deduplicated) | | **8** | **1,447** |
| **wave 1 — apply immediately** | | **86** | **27,196** |

The eight fenced blocks:

| lines | bytes | fence | symbol |
|---|---:|---|---|
| 989-990 | 133 | #309 | `lagunaResidualRMSNormRouterKernels` |
| 1076-1079 | 270 | #309 | `rowsPerGroup` |
| 4119-4122 | 277 | #308 | `nibDiv` |
| 4618-4619 | 157 | #309 | `lagunaDecodeNVFP4QKVR1Enabled` |
| 4627 | 65 | #309 | `scaleSetup` |
| 4731-4734 | 312 | #309 | `lagunaDecodeNVFP4QKVLaneMajorSource` |
| 6643 | 61 | #301 | `lowScaleFastPath` |
| 6655-6657 | 172 | #301 | `packedWordBody` |

**Wave 1 alone recovers 26,216 B net** (94.8% of the full manifest) and is
verified independently:

```
$ research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
Sources/MLXFastModel/LagunaRuntimeModel.swift: 86 blocks, moved 27196 B, added 980 B of pointers, net 26216 B
ok    repository copy of Sources/MLXFastModel/LagunaRuntimeModel.swift is byte-identical
ok    literal-interior comment TEXT byte-identical
ok    line-number shift is uniform: -180
ok    no planned block covers a literal-interior line
ok    ... base=468336  head=442120  saved=26216   residue=348063 IDENTICAL
RESULT: PASS
```

That is the operationally important number: the fenced 1,447 B is 5.2% of the
recovery and 2.6% of the resulting headroom, so **there is no reason to block
wave 1 on #301, #308 or #309**. Land wave 1 whenever the file is otherwise
quiet; sweep wave 2 after the last of the three PRs is terminal, re-running the
planner first so the line numbers are recomputed against the new base.

## 6. Largest single contributions (wave 1)

| lines | bytes | symbol |
|---|---:|---|
| 3398-3428 | 2,079 | `lagunaGatedOutputProjectionSource` |
| 2315-2336 | 1,458 | `lagunaPrefillSlidingQKNormRoPEKernel` |
| 8961-8979 | 1,287 | `lagunaPrefillRouterTop8KernelSource` |
| 6125-6142 | 1,220 | (`line6142`) |
| 1229-1246 | 1,182 | `lagunaSlidingQKNormRoPEKernel` |
| 657-676 | 1,178 | `lagunaDecodeAsyncStage` |
| 9582-9599 | 1,178 | `lagunaPrefillMoETailKernel` |
| 3684-3699 | 1,056 | `lagunaGateProductSoftplusSource` |

These are the design narratives wrapped around the embedded kernel sources: what
was tried, what the measured outcome was, which session produced it. None of it
is a pin on the kernel text itself — those lines match `must match` or
`upstream` and are hard-kept.

The full 94-row table is `research/fern_partB_lagunaruntimemodel_blocks.tsv`
(`start end bytes pointer fences symbol`).

## 7. How to apply

```bash
# 1. recompute against the current base -- line numbers are base-specific
python3 research/fern_partB_relocation_plan.py

# 2. wave 1
python3 research/frieren_relocate_comments.py \
    research/fern_partB_lagunaruntimemodel_spec_wave1.json

# 3. prove it was comment-only
research/fern_partB_dry_run.sh research/fern_partB_lagunaruntimemodel_spec_wave1.json
python3 research/fern_vendor_docc_detach_check.py

# 4. the checker is necessary, not sufficient -- still run the real gates
research/run_upstream_equivalence.sh
./benchmark.sh --local-iterate
senpai/check-editable-budget.sh <BASE_SHA>
```

Step 1 is not optional. Every `start`/`end` in the spec is a line number at
`63ab67c8`; applying a stale spec after any of #301/#308/#309 lands would move
the wrong lines, and the applier's comment-only validation would either reject
it or, worse, move a comment that no longer belongs to the same declaration.

## 8. Machine-applicable artefacts

| path | contents |
|---|---|
| `research/fern_partB_relocation_plan.py` | the planner; read-only against the scored file |
| `research/fern_partB_lagunaruntimemodel_spec.json` | full 94-block spec for `frieren_relocate_comments.py` |
| `research/fern_partB_lagunaruntimemodel_spec_wave1.json` | the 86 unfenced blocks |
| `research/fern_partB_lagunaruntimemodel_blocks.tsv` | per-block bytes, pointer flag, fence, symbol |
| `research/fern_partB_dry_run.sh` | scratch-tree apply + both proofs + hash guard |
| `research/fern_vendor_docc_detach_check.py` | DocC-abstract detachment guard |

## 9. What this manifest does not claim

- It is **not** a timing change. Comments do not reach the compiler's output;
  the expected decode and prefill effect is exactly zero. Do not measure it.
- The residue proof is necessary, not sufficient. It shows the change is
  comment-only in this file; it does not show the build still links or that
  greedy tokens are unchanged. Run the correctness gates.
- The 58,837 B hard-keep is intentionally over-broad. A tighter regex would
  recover more, but every byte it releases needs a human to agree that a live
  contract was not thrown away. That review is not attempted here.
- Line numbers are pinned to `63ab67c8` and expire the moment the file changes.
