# PR #35 r3 — byte budget status against the advisor contract

Ran the two required checks against the accepted base
`1849b376d73f69f9a6b9018619ac665ae4bceb33`.

## Scope check

```
$ senpai/validate-assignment-scope.sh 768bb9d4adfc2baac7d74c0008afc92d010329da \
    Sources/MLXFastModel/LagunaRuntimeModel.swift \
    Sources/MLXFastModel/LagunaRuntimeWeights.swift \
    Sources/MLXFastModel/LagunaScaleCensus.swift
assignment scope OK: 3 submitted path(s) against BASE_SHA=768bb9d4...
```

Correcting a mistake I made reading `benchmark.json` earlier: its `editablePaths`
lists the **directory** `Sources/MLXFastModel`, not individual files. A per-file
set-membership test against those 97 entries therefore returns false for every
file in the directory and means nothing. The consequence that does matter: a new
file dropped into `Sources/MLXFastModel/` is submitted whether or not I intended
it to be, which is why the census instrument had to come back out of `Sources/`.

## Budget check

```
$ senpai/check-editable-budget.sh 1849b376d73f69f9a6b9018619ac665ae4bceb33
editable budget OK: current=2973988/3000000 bytes headroom=26012
  growth=33015/262144 files=143 (file count is diagnostic only; base=142)
```

That was measured with the census still present. Per-file bytes
(`git cat-file -s`):

| file | base `1849b376` | pushed `3ee7ce7` (r2) | worktree now | delta vs base |
| --- | --- | --- | --- | --- |
| `LagunaRuntimeModel.swift` | 508,529 | 516,566 | 521,585 | **+13,056** |
| `LagunaRuntimeWeights.swift` | 31,844 | 39,008 | 44,463 | **+12,619** |
| `LagunaScaleCensus.swift` | — | — | removed | 0 |

## Where the contract actually binds

The `<= 516,600 B` figure reconciles exactly with the harness cap, which is
worth stating because it changes how the shared room should be read:

```
524,288 (per-file cap) - 508,529 (base) = 15,759 B of room above base
        = 8,037 (mine) + ~4,000 (fern's fused norm+QKV+gate) + ~3,700 (spare)
```

So `516,600` is a **reservation inside the 524,288 per-file cap**, not a harness
limit. Status against each real constraint:

| constraint | limit | now | verdict |
| --- | --- | --- | --- |
| `LagunaRuntimeModel.swift` per-file cap | 524,288 | 521,585 | passes, 2,703 B spare |
| my reservation on that file | 516,600 | 521,585 | **over by 4,985 B** |
| total editable surface | 3,000,000 | 2,973,988 | passes, 26,012 B spare |
| my share of surface growth | +8,100 | +25,675 | **over by 17,575 B** |

Nothing here fails the harness today. What it does is eat 4,985 B of the room
reserved for fern's fused norm+QKV+gate kernel, so I am flagging it rather than
quietly spending someone else's allocation.

## How it gets paid back, and why not yet

The reclaim is the authorized strip of `DARKBLOOM_ATTN_SCALE_NARROW` (r1),
granted in comment 6 and not revoked. r1 currently occupies both files:

- `LagunaRuntimeWeights.swift`: `LagunaNarrowScaleBank`,
  `lagunaNarrowNVFP4ScaleBank`, `lagunaNarrowScaleBankReproducesScales`, and the
  `NARROW` / `NARROW_QKV` / `NARROW_OPROJ` gates (~110 lines).
- `LagunaRuntimeModel.swift`: `lagunaGatedAffineOProjNVFP4NarrowKernels`,
  `lagunaActivatedOProjNarrowKernels`, `lagunaDecodeNVFP4QKVR1NarrowKernels`, the
  `narrow:` ternaries inside two shared source builders, three dispatch
  branches, two bank build sites and two call-site arguments (~200 lines).

**I have deliberately not done the strip yet.** Two reasons:

1. The budget binds at submission, not at local iteration, and deliverable B is
   still completely unvalidated — never built, never proven bit-exact, never
   timed. Stripping ~310 lines across two files to fit a candidate that has no
   measurement yet is the "combine several unmeasured mechanisms" failure
   `AGENTS.md` warns against, in reverse.
2. B's certificate-decline path currently falls back to **r1**, and the `0xFF`
   escape already reads the **stock** plane. Removing r1 means repointing that
   fallback to stock first. That is a correctness-relevant edit, so it should
   land when B's correctness is being verified, not before.

One thing the strip is not free of: r1 is the **only** narrow arm for `o_proj`
(there is no lane-major o_proj kernel yet), so stripping r1 returns o_proj to
the stock plane until lane-major is extended to it. The census says o_proj is
representable (`row_le15` 0.981372, 384 groups, a multiple of 64), so the right
end state is one representation on both sites rather than keeping r1 alive for
o_proj alone. That extension is Step 3 work.

Order I am following: validate B → strip r1 and repoint the fallback to stock →
re-run both checks and report the numbers → only then extend planes.
