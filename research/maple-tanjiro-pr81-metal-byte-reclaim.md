# PR #81 — Metal-literal byte reclamation in `LagunaRuntimeModel.swift`

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"editable_bytes_reclaimed","available":true,"value":42757},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- Student / PR: `maple-tanjiro` / #81 (`maple-2026-08-06e-metal-literal-byte-reclaim`, revision `r1`)
- Hypothesis and target cost: `Sources/MLXFastModel/LagunaRuntimeModel.swift` carries a large
  amount of *submitted* whitespace and commentary that is never part of the emitted Metal
  Shading Language. Removing it mechanically should reclaim tens of kilobytes of the
  524,288 B per-file cap and the 3,000,000 B surface cap at exactly zero change in emitted MSL
  and zero change in checked output. This is a byte-budget experiment, not a timing experiment.
- Decision: **green** (byte goal met and certified; explicitly *not* a timing claim)
- `BASE_SHA` / candidate commit: `ab1f9a1323421703f944ac1895841e39b8302542` /
  `114dce29c21f7f4bafe080e51cc488c831e7144f`
- Submitted candidate files: `Sources/MLXFastModel/LagunaRuntimeModel.swift` (only)
- Supporting test or documentation files: `research/tanjiro_metal_literal_tool.py`,
  `research/maple-tanjiro-pr81-metal-byte-reclaim.md` (neither is on the submitted surface)
- Official submission `--model` value (planned or used; default `senpai`): **n/a — no official
  submission dispatched from this PR.** Assignment §7 pre-allocates the ranked channel to PR #80
  (`maple-frieren/attn-scale-pairwise`). Were one ever dispatched it would use
  `mlxfast submit --model "senpai"`.
- Explicit API model-value rejection, if fallback attribution was required: **n/a** — no submission
  was attempted, so no rejection and no fallback attribution occurred.
- Assignment-scope preflight: `senpai/validate-assignment-scope.sh "$BASE_SHA"
  Sources/MLXFastModel/LagunaRuntimeModel.swift` → in-scope; `research/` files are research-only
  and are not part of `editablePaths`.
- Editable bytes / headroom / growth:
  `editable budget OK: current=2924074/3000000 bytes headroom=75926 growth=-42757/262144 files=142`
  (base was `current=2966831/3000000 headroom=33169 growth=0/262144 files=142`)
- Scored-path reachability evidence: the file *is* the scored forward pass
  (`AGENTS.md`: "The scored forward pass is `Sources/MLXFastModel/LagunaRuntimeModel.swift`"). Every
  edited byte lives either inside a Metal source string literal that the runtime hands to
  `MLXFast.metalKernel(...)`, or in the closing `"""` delimiter of such a literal. The emitted-MSL
  harness below materialises those strings directly from the generator functions.

---

## 0. Base, `baseline_advanced` clearance, and mechanism provenance

**Base.** Everything below is measured against the assigned base
`ab1f9a1323421703f944ac1895841e39b8302542`. A `baseline_advanced` event fired at
2026-08-06T02:22:30Z reporting `current_base_sha = 53672755c57b636517dcfcfc5d9253e1012a87e4`. The
advisor cleared it in a PR comment as a docs-only round-13 refresh of
`research/CURRENT_RESEARCH_STATE.md`, whose intersection with `benchmark.json`'s `editablePaths` is
empty, and instructed **no rebase**. I did not rebase. My byte arithmetic therefore still rests on
the base numbers the assignment quotes (`current = 2,966,831 / 3,000,000`, headroom 33,169 B,
growth 0, files 142; the target file 521,768 B, i.e. 2,520 B under the per-file cap), and I
re-derived all four independently in §2. The result is submitted with that newer base SHA explicitly
accepted rather than silently ignored.

**Mechanism provenance (§0.9.30, two-pools rule).** I claim **only** the literal pool. The
**42,757 B** in this PR is T1 (29,360 B of literal indentation) + T2 (13,397 B of `//` comments
*inside* literals). I make **no** claim on the **24,164 B** `DARKBLOOM_STAGE2_GATHER` deletion pool,
which belongs to fern's PR #40 and remains unowned. The two pools are additive and disjoint: T1/T2
touch only whitespace and comment text inside Metal source strings, and delete no `DARKBLOOM_*`
construct at all — §4.3 shows both injection-guard sites intact and unchanged at every stage.
Conflating the pools was casualty #24; this report keeps them separate by construction.

For reference against the advisor's 49,301 B low-risk literal-pool estimate (T1 27,192 + T2 15,815 +
T4 ~3,690 + T5 2,604): I realised 42,757 B of it from T1+T2 alone, where the brief predicted
43,007 B for those two tiers. The tier-level split moved (T1 came in 2,168 B *over*, T2 2,418 B
*under*) for the reason given in §6; the two errors nearly cancel. T4 and T5 are deliberately not
attempted — see §7.

---

## 1. What was changed

Three commits on `maple-tanjiro/metal-literal-byte-reclaim`, deliberately kept separable so the
advisor can cherry-pick a prefix (assignment §4.2):

| commit | tier | contents | file bytes after |
| --- | --- | --- | ---: |
| `2fb4b339a99c89731321399d88adf8f38683acaf` | **T1** | dedent Metal literal bodies + closing `"""` | 492,408 |
| `109ee2ceb49b38f292db1a075748c79a7c396bce` | — | research tool only (no submitted file touched) | 492,408 |
| `114dce29c21f7f4bafe080e51cc488c831e7144f` | **T2** | strip `//` comments *inside* the literals | 479,011 |

`2fb4b33` touches **only** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, so it is
cherry-pickable on its own without `109ee2c`/`114dce2`.

**This change is a script output; regenerate after every rebase; never hand-edit the result.**

Regeneration (deterministic and idempotent, both subcommands proven no-op on a second run):

```bash
python3 research/tanjiro_metal_literal_tool.py dedent Sources/MLXFastModel/LagunaRuntimeModel.swift   # T1
python3 research/tanjiro_metal_literal_tool.py strip  Sources/MLXFastModel/LagunaRuntimeModel.swift   # T2
```

### Byte accounting

| stage | file bytes | Δ | per-file headroom (cap 524,288) |
| --- | ---: | ---: | ---: |
| base `ab1f9a1` | 521,768 | — | 2,520 B (1.00×) |
| after T1 | 492,408 | −29,360 | 31,880 B (12.65×) |
| after T2 | **479,011** | **−42,757** | **45,277 B (17.97×)** |

Surface-wide: `current` 2,966,831 → 2,924,074 B; headroom 33,169 → **75,926 B** (2.29×).
`growth=-42757/262144`, i.e. the submission is a net shrink and consumes no growth allowance.

File SHA-256: base `b4b260f441ed6e145aff8d26a3ac677c94ea73ffc57a6ee15c0ef7aef4951c0d`,
T1 `0329108be8e16ff8cc85e5fc8dd2c098ad843a7f4d3019d2a3a4f521dae37276`,
T2 `290c996e2c96ab9e68e29c76c1fe59d44bad52bd4bbd15346e9b42a5c65cca0e`.

Line count: 11,526 → 11,526 (T1, whitespace only) → 11,315 (T2, 211 comment-only lines removed).

---

## 2. Independently re-derived census and corrections to assignment §2/§5

I re-derived the census with my own parser rather than trusting the brief. Agreement is good;
the disagreements are listed so the advisor can correct the shared model.

| metric | my census (base) | assignment §2 | verdict |
| --- | ---: | ---: | --- |
| `"""` delimiters | 216 | 216 | agree |
| multi-line literal blocks | 108 | 108 | agree |
| literal body bytes | 187,237 (35.9 %) | 187,243 | −6 B (delimiter-line accounting) |
| body + delimiters | 190,364 | 190,370 | −6 B |
| comment pool outside literals | 125,860 | 126,053 | −193 B |
| `+ "..."` concat lines | 39 lines / 2,341 B | 41 / 2,334 B | minor |
| **T1 achievable across all 108 blocks** | **29,736** | 27,192 | **+2,544 B in our favour** |
| T2 pool (`//` inside literals) | 14,971 on 216 lines | 15,815 | −844 B |
| tabs / CR / trailing whitespace | 0 / 0 / 0 | 0 / 0 / 0 | agree |

Realised numbers differ from "achievable" because of the deliberate exclusions:

- **T1 realised 29,360 B** (105/108 blocks). 376 B foregone: `lagunaTailNVFP4QMVHeader`
  L4654–4701 (184 B, §5.3 forbidden region), and the two T0-instrument literals at L11387–11406
  (152 B) and L11420–11425 (40 B).
- **T2 realised 13,397 B** vs the 15,815 B estimate. The 2,418 B shortfall is (a) 370 B of
  comments inside the excluded `lagunaTailNVFP4QMVHeader`, and (b) the estimate counted comment
  *text* whereas the tool deletes whole comment-only lines and cuts trailing comments — after T1
  those lines carry no leading indentation left to remove, so the realised figure is the honest one.

### Corrections to §5 hazards

1. **§5 hazard 1 is wrong in detail.** The brief says the file contains 24
   `#pragma clang loop unroll(full)` directives. Reality: **20** `#pragma clang loop unroll(full)`
   plus **4** bare `#pragma unroll` = 24 pragmas total. All 24 counts are unchanged after T1+T2.
2. **§5.2 confirmed and tightened.** There are 81 backslash-EOL continuations across six
   `#define` macros (`LAGUNA_RESCALE` L1698, `T_LOAD_K` L1711, `T_LOAD_V` L1729 and their twins at
   L2217/L2227/L2245). The trailing-backslash run-length histogram is `{1: 1, 2: 80}`; the single
   **odd** run is L967 `\(guardOpen)\`, which is a genuine Swift newline-continuation escape rather
   than a Metal macro continuation. Both the dedent and strip scanners refuse to touch any line
   whose trailing backslash run is odd, and the strip scanner additionally asserts that no
   `#define` body acquires a comment or blank line.
3. **§5.3 confirmed.** L4656 is the only interpolation in the file that is not closed on its own
   line; it is exactly the region the brief excludes. All other 127 interpolation lines are
   self-contained.
4. **§5.6 confirmed.** No test references the kernel-source functions
   (`grep -rn "laguna.*Kernel\b" Tests/ Vendor/` is empty) and there is no formatter or lint gate in
   `benchmark.sh`, `.github/workflows/*.yml`, or `Package.swift`, so no gate can object to the
   reformat.
5. **New hazard the brief did not mention: no block comments and no escaped quotes.** Inside literal
   bodies, `/*`, `*/` and `\"` all occur **0** times, which is what makes a plain `//`-only stripper
   sound. Twenty-one lines contain an apostrophe, all of them inside `//` prose that T2 deletes.
6. **New hazard: T2 can make two previously-distinct fragments identical.** See §3.3. It is benign
   here because every kernel is constructed with an explicit `name:` argument, so MLX never derives
   a cache key or function name from the source text alone.

---

## 3. §6.1 primary bar — emitted-MSL identity certificate

### 3.1 Harness and coverage

`research/tanjiro_metal_literal_tool.py dump FILE OUTDIR` materialises **every** Metal source string
in the file straight out of the source text: all **108** multi-line `"""` blocks plus the single
`+ "..."` concatenated blob = **109 strings**, written to one file each plus a `MANIFEST.txt` of
SHA-256 and byte length. Interpolations (`\(...)`) are preserved as opaque source text, which makes
the certificate *value-independent*: it holds for every possible value of every interpolated Swift
expression, not just the ones a particular run happens to produce.

**Coverage: 109/109 source-producing sites, 100 %. No source-producing function is unreachable by
the harness.** The two literals inside the T0 instrument and the `lagunaTailNVFP4QMVHeader` literal
are dumped and compared like any other; they are excluded from *modification*, not from
*verification*.

`certify BASEDIR CANDDIR` compares the two dumps. A differing string is accepted **only** if an
independent, plainly-written C-comment stripper (`strip_comments_msl`, a separate implementation
from the one used to edit the file) applied to the base reproduces the candidate byte-for-byte.
Anything else is reported `UNEXPLAINED` and the tool exits non-zero.

### 3.2 T1 — exact byte identity

```text
certify msl_base msl_t1
certify: 109 strings compared; 109 byte-identical; 0 differ; 0 UNEXPLAINED
```

Corroborating evidence:

- `diff -r msl_base msl_t1` → empty.
- `MANIFEST_base.txt` and `MANIFEST_t1.txt` are identical, 109 lines each.
- `git diff --ignore-all-space ab1f9a1 2fb4b33 -- Sources/MLXFastModel/LagunaRuntimeModel.swift`
  → **empty**, i.e. the commit is provably whitespace-only at the Swift-source level too.
- `git diff --shortstat` for T1: 4,069 insertions, 4,069 deletions, 0 net lines.
- `swiftc -parse` exit 0.

**N compared = 109, differing = 0.** This is the strongest possible form of the §6.1 bar.

### 3.3 T2 — 32 differing strings, all explained

```text
certify msl_base msl_t2
certify: 109 strings compared; 77 byte-identical; 32 differ; 32 explained as pure comment removal; 0 UNEXPLAINED
```

(`certify msl_t1 msl_t2` gives the identical verdict, re-confirming that T1 contributed nothing.)

Every one of the 32 was reproduced byte-for-byte by the independent stripper, so the change is a
pure deletion of `//`-to-end-of-line runs and of whole comment-only lines. **No token of Metal
source moved, changed, or disappeared.** Two independent implementations agreeing on all 32 is the
substance of the claim; the naive stripper did not even need interpolation-awareness to match,
which independently confirms no interpolation sits inside or adjacent to a stripped comment.

| # | fragment | base B | cand B | −B | −lines |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | `003_?` | 1800 | 1771 | 29 | 1 |
| 2 | `005_source` | 2049 | 1805 | 244 | 4 |
| 3 | `006_source` | 1892 | 1477 | 415 | 7 |
| 4 | `007_source` | 11366 | 10242 | 1124 | 19 |
| 5 | `008_header` | 2885 | 2449 | 436 | 7 |
| 6 | `009_source` | 13158 | 12422 | 736 | 13 |
| 7 | `010_header` | 2574 | 2449 | 125 | 2 |
| 8 | `011_source` | 2561 | 1919 | 642 | 10 |
| 9 | `012_source` | 2081 | 1878 | 203 | 3 |
| 10 | `013_source` | 2445 | 2250 | 195 | 3 |
| 11 | `014_source` | 2302 | 2209 | 93 | 2 |
| 12 | `017_?` | 1553 | 1296 | 257 | 4 |
| 13 | `019_projectionLoop` | 3404 | 3196 | 208 | 3 |
| 14 | `021_?` | 7178 | 5661 | 1517 | 26 |
| 15 | `026_body` | 854 | 785 | 69 | 1 |
| 16 | `027_body` | 1471 | 1371 | 100 | 2 |
| 17 | `035_metadataAdvance` | 2843 | 2606 | 237 | 2 |
| 18 | `044_scaleAdvance` | 2679 | 2465 | 214 | 3 |
| 19 | `051_lagunaDecodeNVFP4QKVLaneMajorSource` | 1953 | 1808 | 145 | 2 |
| 20 | `055_lagunaNormAffineQKVBody` | 3543 | 3261 | 282 | 2 |
| 21 | `063_metadataAdvance` | 4872 | 4272 | 600 | 7 |
| 22 | `073_source` | 3642 | 3325 | 317 | 5 |
| 23 | `079_source` | 4234 | 3845 | 389 | 6 |
| 24 | `080_source` | 3353 | 2971 | 382 | 6 |
| 25 | `082_source` | 2730 | 2468 | 262 | 4 |
| 26 | `083_source` | 1715 | 1645 | 70 | 1 |
| 27 | `086_?` | 3578 | 2162 | 1416 | 23 |
| 28 | `092_?` | 2031 | 1627 | 404 | 6 |
| 29 | `093_lagunaDecodeRouterOrdinalHeader` | 666 | 551 | 115 | 2 |
| 30 | `096_?` | 1012 | 774 | 238 | 4 |
| 31 | `099_?` | 5841 | 4222 | 1619 | 26 |
| 32 | `102_?` | 3428 | 3114 | 314 | 5 |
| | **total** | | | **13,397** | **211** |

The 13,397 B removed inside the dumped strings equals the whole-file reduction exactly, which
proves T2 removed nothing outside a Metal literal.

**Fragment-collision note.** In the base dump there are 8 groups of byte-identical strings; after T2
there are 9. The new group is `008_header` ≡ `010_header` (the sliding-attention and full-attention
fused-attention headers). Their *only* difference in base was five comment lines:

```text
--- msl_base/008_header.msl
+++ msl_base/010_header.msl
-// Alpha-skip rescale, replica of sdpa_vector.h's shipped
-// DARKBLOOM_RESCALE_FACTOR (DARKBLOOM_ALPHASKIP == 1 arm).
-// K loads: 8-byte vec loads from the ring, or the threadgroup
-// substitute for the just-written slot. Same elements, same order,
-// same bfloat -> float conversion points as the scalar form.
```

This is harmless — these are *fragments* interpolated into two kernels that each carry their own
explicit `name:`, so no cache key or function name is derived from the string — and it is a useful
objective finding: the sliding and full fused-attention headers are, at the Metal-token level,
literally the same 2,449 B. That upgrades the T4 "hoist the attention header" item from an estimate
to a fact (see §7).

### 3.4 T3 was not attempted

Assignment §9 states that a clean T1 with a complete identity certificate is a full success and
warns against reaching for T3 to inflate the number. T3 (stripping *relative* indentation inside
literals) is compile-identical but **not** byte-identical, which is a strictly weaker certificate
than the one above, and the per-file headroom after T1+T2 is already 17.97× the base. It was
therefore skipped, and no token-level equivalence report for it is offered or implied.

---

## 4. §6.2 behavioural certificates

### 4.1 Paired `--local-iterate` correctness

| field | base (`5319168`, run `4635e5c1-16b2-47c3-a5ef-9c4e78a5fd9a`) | T1 (`2fb4b33`, run `3c57a2d0-678b-4ccd-83e7-b7158d49bd01`) | T1+T2 (`114dce2`, run `061ca725-8e40-43ba-9621-265c081b3b19`) |
| --- | --- | --- | --- |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| `passed_correctness` | true | true | true |
| `max_abs_diff` | 0 | 0 | 0 |
| `checked_steps` | 130 | 130 | 130 |
| `peak_ram_gb` | 21 | 21 | 21 |
| `error` | "" | "" | "" |
| `weights_hash` | `aff9943005…4b3d` | identical | identical |

The `golden_hash` values are pasted in full above and are character-for-character equal.
`harness_hash` differs between the three trees (`2f3ce1f6…`, `1c77e24b…`, `3e3f985a…`) because it
hashes the whole tree including the research tool; that is expected and is not a correctness signal.

A fourth arm — the unchanged base re-run as the A/A control of §5, run
`de11ad43-49d4-4241-8590-243c4dc393b2` — reproduced the same four fields
(`golden_hash = b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`,
`passed_correctness = true`, `max_abs_diff = 0`, `checked_steps = 130`, `peak_ram_gb = 21`,
`error = ""`), and its `harness_hash` equals the first base arm's, confirming an identical tree.

### 4.2 Upstream equivalence — fails identically on the unchanged base (pre-existing M4 divergence)

`research/run_upstream_equivalence.sh` **fails on this host**, and it fails in exactly the same way
on the unchanged base tree. This is a §9-adjacent finding, so it is reported in full rather than
summarised.

Candidate tree (`114dce2`, T1+T2), supervised run `cce2e248-2e9c-450d-bbbc-478f14cf3220`:

```text
◇ Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() started.
{
  "decodeTokenCount" : 8,
  "promptTokenCount" : 512,
  "steps" : [
    { "label" : "prefill",  "maximumAbsoluteLogitError" : 0.125, "meanAbsoluteLogitError" : 0.011933609, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-0", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-1", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 },
    { "label" : "decode-2", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-3", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-4", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 },
    { "label" : "decode-5", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-6", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-7", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 }
  ]
}
✘ Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() recorded an issue at
  LagunaCorrectnessTests.swift:249:5: Expectation failed:
  (report → …).passes(maximumAbsoluteLogitError: tolerance → 0.0)
✘ Test run with 1 test in 0 suites failed after 6.1 seconds with 1 issue.
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

Unchanged base tree (`5319168`, no edit to `LagunaRuntimeModel.swift`), supervised run
`fbeb410c-b7f5-4ae5-a96d-2781f073eb42`:

```text
◇ Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() started.
{
  "decodeTokenCount" : 8,
  "promptTokenCount" : 512,
  "steps" : [
    { "label" : "prefill",  "maximumAbsoluteLogitError" : 0.125, "meanAbsoluteLogitError" : 0.011933609, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-0", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-1", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 },
    { "label" : "decode-2", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-3", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-4", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 },
    { "label" : "decode-5", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" : 5991, "upstreamToken" : 5991 },
    { "label" : "decode-6", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  509, "upstreamToken" :  509 },
    { "label" : "decode-7", "maximumAbsoluteLogitError" : 0, "meanAbsoluteLogitError" : 0, "runtimeToken" :  902, "upstreamToken" :  902 }
  ]
}
✘ Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled() recorded an issue at
  LagunaCorrectnessTests.swift:249:5: Expectation failed:
  (report → …).passes(maximumAbsoluteLogitError: tolerance → 0.0)
✘ Test run with 1 test in 0 suites failed after 6.069 seconds with 1 issue.
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

Reading of this evidence:

1. **The two reports are numerically identical**, field for field — same
   `maximumAbsoluteLogitError = 0.125`, same `meanAbsoluteLogitError = 0.011933609` to all eight
   printed digits, same `runtimeToken`/`upstreamToken` on every one of the nine steps, same
   `EQUIVALENCE_EXACT_STEPS=8`. The candidate does not move the oracle by one bit. For this
   experiment that is the strongest possible statement: the oracle is not merely "still passing at
   tolerance", it reproduces bit-identical logits, which is what a byte-identical-MSL change should do.
2. **The failure is not zero-test.** The wrapper selected and executed one test
   (`1 test in 0 suites`), so this is a genuine tolerance assertion at
   `LagunaCorrectnessTests.swift:249`, not the zero-test trap `run_upstream_equivalence.sh` exists to
   catch. The wrapper correctly refused to call it a pass.
3. **Only prefill diverges; every decode step is exact.** `AGENTS.md` states that M4 Pro hosts report
   Apple GPU generation 16 and do not select the `_nax` prefill kernels used by the ranked M5. A
   prefill-only, decode-exact divergence on an M4 Pro is precisely the shape that note predicts. The
   argmax still agrees (`runtimeToken == upstreamToken == 5991`), so this is a near-tie numeric
   difference in the prefill kernel family, not a behavioural one.
4. I followed the `AGENTS.md` procedure for a non-M5 disagreement — *"test the unchanged base"* — and
   the base has the same divergence. I did **not** set `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1`: that
   override is for public goldens, and the public golden gate already passes cleanly here
   (`golden_hash` identical, `max_abs_diff = 0`, §4.1). Suppressing an oracle failure would have been
   the wrong tool and would have destroyed the base-versus-candidate comparison that actually
   resolves this.

**Verdict.** §9 lists "upstream equivalence failure" as a stop condition. I read that as *a failure
the change introduces*. This failure is a property of the host and is present, with identical
numbers, on the untouched base, so it is not a stop condition for this change — but it does mean
**this host cannot supply a green oracle certificate for anything**, and the M5 remains authoritative
per `AGENTS.md`. The advisor should treat §4.1 (`golden_hash` identical, `max_abs_diff = 0`,
130/130 checked steps) plus the §3 byte-identity certificate as the correctness evidence, and should
expect this test to pass on the ranked M5 exactly as it presumably does for the current frontier.

Follow-up worth someone's time, unrelated to this PR: the base's own oracle failure on M4 Pro means
no student on a non-M5 host can currently satisfy the *"run the oracle when a change affects
numerical behaviour"* instruction. Either the test needs an architecture guard (its name already says
`OnM5WhenEnabled`) or the runbook should say plainly that a prefill tolerance failure on generation-16
hardware is expected. I have not changed either, since both files are outside my scope.

### 4.3 §3.1 injection-guard grep, before and after

Base:

```text
11553:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11565:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

After T1 (line numbers unchanged, T1 removes no lines):

```text
11342:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11354:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

After T1+T2 (shifted by the 211 deleted comment-only lines, values unchanged):

```text
11131:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11143:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

The guarded constants remain exactly `0` and `160`. The T0 region itself is byte-untouched by both
tiers (it is in `excluded_ranges()`), so the instrument is intact and the §3 T0 veto is respected.

### 4.4 Editable-budget check on the branch

```text
$ senpai/check-editable-budget.sh ab1f9a1323421703f944ac1895841e39b8302542
editable budget OK: current=2924074/3000000 bytes headroom=75926 growth=-42757/262144 files=142 (file count is diagnostic only; base=142)

$ git cat-file -s $(git rev-parse HEAD:Sources/MLXFastModel/LagunaRuntimeModel.swift)
479011
$ git cat-file -s $(git rev-parse 2fb4b33:Sources/MLXFastModel/LagunaRuntimeModel.swift)
492408
$ git cat-file -s $(git rev-parse ab1f9a1:Sources/MLXFastModel/LagunaRuntimeModel.swift)
521768
```

---

## 5. §6.3 no-harm timing check

This section exists **only** to show the change did not hurt. It is not a speedup claim in either
direction, and no ranked receipt was requested or produced.

| Metric | Baseline `5319168` | T1 `2fb4b33` | T1+T2 `114dce2` | Baseline repeat `5319168` |
| --- | ---: | ---: | ---: | ---: |
| decode seconds/token | 0.0131342145234375 | 0.0133427333984375 (+1.588 %) | 0.0132953505859375 (+1.227 %) | 0.013194583984375 (+0.460 %) |
| prefill seconds/token | 0.00113611279296875 | 0.0011126861171875 (−2.062 %) | 0.001125958658203125 (−0.894 %) | 0.00112676847265625 (−0.822 %) |
| same-host paired estimate | — | 0.9934 | 0.9931 | 0.9986 |
| harness `score` field | 0.7850458384665575 | — | 0.7796469797290735 | 0.7839674102424522 |
| `harness_hash` | `2f3ce1f6…` | `1c77e24b…` | `3e3f985a…` | `2f3ce1f6…` (same as base) |

The paired estimate is a same-host research metric, not an official M5 score. It is
`(base_decode/cand_decode)^0.75 * (base_prefill/cand_prefill)^0.25` computed from the two arms'
own seconds-per-token, **not** the harness `*_speedup` fields, which on this M4 are scaled by
M5-derived pinned baseline constants.

**On the §6.3 A/A floor.** The brief quotes a local M4 A/A floor of prefill −1.30 % / decode
+0.48 % and says anything outside it means the emitted MSL changed and I should stop and
investigate. Both candidate arms land outside that band on decode (+1.59 %, +1.23 %) and the T1 arm
also on prefill (−2.06 %). Per §9 I stopped and investigated. The band's premise does not hold here:

- the emitted MSL is **certified byte-identical** for T1 (109/109, §3.2), so for that arm it
  demonstrably did not change, yet that arm shows the *largest* deviation of the three;
- `golden_hash` and `max_abs_diff` are unchanged on every arm, so no numerical behaviour changed;
- T1 is provably whitespace-only at the Swift level (`git diff --ignore-all-space` empty).

**The decisive internal control is the T1 ↔ T1+T2 pair.** T2 removes only comment text from inside
kernel strings, so those two trees compile the same shaders and execute the same instructions; that
pair is effectively an A/A. It differs by **decode −0.355 %, prefill +1.193 %** — i.e. moving between
two behaviourally identical trees already produces most of the deviation being attributed to the
change. Across all three arms the total spread is **decode 1.588 %, prefill 2.105 %** with no
monotone relationship to how much source was removed (T1+T2 removes 46 % more bytes than T1 yet sits
*closer* to base on both axes). That is the signature of noise, not of a mechanism.

**The fourth arm is a true base↔base A/A and it settles the question.** I re-ran `5319168`
unchanged, in the same session, as run `de11ad43-49d4-4241-8590-243c4dc393b2`. Its `harness_hash` is
`2f3ce1f6c0338f06bbc8c60fbdf791a12e64245af0ad8fde319b1f87e6995382`, character-for-character equal to
the first base arm's, which independently confirms it is the identical tree — the same bytes, the same
binary, zero possible mechanism. That pair differs by **decode +0.460 %, prefill −0.822 %**, giving a
paired estimate of **0.9986** instead of the 1.0000 it must equal in truth.

Set against the brief's quoted A/A floor of decode +0.48 % / prefill −1.30 %, that is the key number:
a pair that *cannot* differ already consumes **96 % of the decode allowance** and 63 % of the prefill
allowance. The band is therefore not wrong — it is a fair estimate of this instrument's A/A spread —
but it has essentially **zero margin**, so a single candidate pair crossing it carries no information.
It is a usable sanity check and not a usable §9 stop condition.

Stronger still: **all four arms emit equivalent Metal.** Base and base-repeat are the same bytes;
T1's emitted MSL is certified byte-identical to base across 109/109 strings (§3.2); T1+T2 differs
from T1 only by comment text inside those strings. Every one of the four therefore compiles the same
shaders and executes the same instructions, so **every difference in the table above is noise by
construction** — there is no candidate arm whose timing *could* legitimately differ. The observed
spread across those four provably-equivalent arms is **decode 1.588 %, prefill 2.105 %**, i.e. 3.3×
the decode band and 1.6× the prefill band. Ordering the arms by bytes removed (0, 0, 29,360, 42,757)
against decode delta (0, +0.460, +1.588, +1.227) shows no monotone relationship, and the arm that
removes the *most* bytes is closer to base than the arm that removes fewer.

Root cause of the noise: this host's `--local-iterate` timed phase is only ~2.3 s of
`timed_benchmark_seconds` (and 2.3 s of `correctness_seconds`) inside a 140–200 s wall window, on a
48 GiB M4 Pro running the low-memory startup profile. Roughly 2 s of measurement is a far coarser
instrument than the ranked M5.

**Recommendation for the next brief that quotes this band.** Keep the ±1.30 % / +0.48 % numbers as a
descriptive A/A estimate — my base↔base pair lands inside both, so they are honest — but do **not**
use them as a §9 stop condition on a 48 GiB M4 Pro, because their margin is zero and the spread over
four provably-equivalent arms is 1.6–3.3× wider. Concretely: require a **repeated base arm in the
same session** and compare the candidate deviation against *that measured* A/A rather than against a
constant. That costs one extra ~2.5-minute run and converts an uninformative threshold into a real
control. Had I obeyed the band literally I would have stopped on a change whose emitted MSL is
certified byte-identical.

I am explicitly **not** reporting a timing win or a timing regression. The correct summary of this
section is *no measurable effect, exactly as the byte-identical MSL certificate predicts* — which is
the intended outcome of a byte-budget experiment.

Additional M4 caveats already known and present in the base run too: `prefill_speedup ≈ 0.32` and
`passed_prefill_speedup_floor = false` are M4 artefacts of M5-derived pinned baseline constants,
not a property of this change.

---

## 6. Where the brief turned out to be wrong

Collected for the advisor's benefit (details in §2):

1. §5 hazard 1's "24 `#pragma clang loop unroll(full)`" is really 20 of those plus 4 bare
   `#pragma unroll`.
2. §3's T1 estimate of 27,192 B under-counts; the true all-blocks figure is 29,736 B and the
   realised figure after the mandated exclusions is 29,360 B.
3. §3's T2 estimate of 15,815 B over-counts; the realised figure is 13,397 B, because after T1
   there is no leading indentation left on a comment-only line to remove.
4. §2's comment-pool figure (126,053 B) is 193 B high and the concat-line figure (41 lines /
   2,334 B) is 39 lines / 2,341 B.
5. §6.3's local A/A floor is too tight for a 48 GiB M4 Pro `--local-iterate` session (§5 above).
6. §3's T4 entry treats the sliding/full attention `header` duplication as an estimate; T2 proves
   the two fragments are token-identical (§3.3).

---

## 7. Judgement on T4, T5, T6, T7, T8 — is the remaining ~20 KB worth a round?

**Short answer: not as a byte exercise. Headroom is no longer the binding constraint.** Per-file
headroom went from 2,520 B to 45,277 B and surface headroom from 33,169 B to 75,926 B. A further
20 KB buys optionality that nothing currently needs, at real risk to a file that two students are
editing concurrently. I would spend the next round on timing, not bytes.

That said, ranked by value-per-risk if the advisor does want more:

- **T4 (hoist duplicate fragments, ~3,690 B est.) — defer, then take the header only.** Two of the
  three candidates sit exactly where PR #80 (`maple-frieren/attn-scale-pairwise`) is editing: the
  `scaleSetup` pair at L4225/L4718 (307 B, byte-identical) and the sliding/full attention `header`
  (~2,449 B after T2, now *proven* identical). Hoisting either now would create an ugly conflict.
  The `extract` pair at L4183/L6686 (447 B, byte-identical) is benign and could go any time. Do
  **not** unify `singleWeightLoad` L3533 with `unrolledWeightLoad` L3576 — they are a known false
  positive and are genuinely different. **Safe when:** #80 has merged. The header hoist is then the
  single best remaining item because it is now backed by a byte-identity proof rather than an
  eyeball.
- **T5 (collapse `\`-padding and blank lines, 2,604 B) — defer.** 2,604 B is the smallest payoff of
  any remaining tier and it is the only one that requires touching the interior of the six `#define`
  macros with their 81 backslash continuations, where an off-by-one in trailing-whitespace handling
  silently changes macro expansion. Bad ratio.
- **T6 (unify QKNorm/H1 and Packed/Selected, ~8,800 B) and T7 (unify sliding/full fused attention,
  ~12,100 B) — out of scope for a byte round, and I do not recommend converting them into one.**
  These are not reformatting; they are refactors that change which Swift code path builds which
  kernel. They cannot be certified by the §6.1 harness in the same value-independent way, because
  after unification the "same" string is produced by a different parameterisation, so the proof
  obligation moves from "these bytes are equal" to "these two parameterisations cover exactly the
  original two cases" — a much weaker and more human proof. **What would make them safe:** extend
  the dump harness to enumerate the *cross product* of every interpolated Swift flag (there are a
  bounded number of `laguna*Enabled` gates) and certify that the set of emitted strings before and
  after unification is equal as a multiset. That is a real piece of work, and it is only worth doing
  if unification is wanted for a *timing* reason (e.g. fewer distinct kernels to warm), not for
  bytes.
- **T8 (125,860 B comment pool outside literals) — selective only, and I did none of it.** The pool
  is the largest single reserve in the file, but it is also the accumulated design record of the
  whole campaign: L312, L3265, L5122, L6607, L6735, L7468 and others document *why* a kernel is
  shaped the way it is, and L7468 explicitly records that "the ordinary accepted kernel above stays
  byte-for-byte unchanged". A bulk strip would delete the campaign's institutional memory to buy
  bytes nobody needs. If bytes are ever genuinely needed, the safe subset is: comments that are
  stale (describe code that no longer exists), duplicated verbatim between twin generators, or
  restate the adjacent line. That subset should be selected by hand and reviewed, not scripted.

**Related honesty note on T2, which I did apply.** T2 deletes 211 lines of commentary *inside* the
kernels — the most technically dense documentation in the repo. It is fully certified and it is what
§4 scheduled as Commit 2, so I shipped it. But it costs real explanatory context for 13,397 B that,
after T1, nothing is waiting on. **If the advisor's judgement is that in-kernel commentary is worth
more than the headroom, merge `2fb4b33` (T1) alone and drop `114dce2` (T2)** — T1 is isolated and
cherry-pickable precisely so that choice stays open, and T1 alone already gives 12.65× per-file
headroom at a strictly stronger (byte-identical) certificate.

---

### Evidence

- Host, memory profile, toolchain, and thermal policy: Apple M4 Pro, 48 GiB unified memory →
  low-memory startup profile (< 64 GiB); Swift 6.3.3; stock `benchmark.sh` 40 °C thermal gate, never
  bypassed; `setup.sh` previously run; weights present, 21,568,891,382 B across 9 files,
  `weights_hash aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`.
  This is **not** the ranked M5; M4 Pro reports Apple GPU generation 16 and does not select the
  `_nax` prefill kernels, so no timing number here is evidence about ranked prefill.
- Exact baseline and candidate commands:
  - `./benchmark.sh --local-iterate` at `5319168` (baseline, run `4635e5c1…`), `2fb4b33` (T1, run
    `3c57a2d0…`), `114dce2` (T1+T2, run `061ca725…`), and `5319168` again (A/A control, run
    `de11ad43…`)
  - `python3 research/tanjiro_metal_literal_tool.py census|dump|dedent|strip|verify|certify`
  - `research/run_upstream_equivalence.sh` at `114dce2` (run `cce2e248…`) and at `5319168`
    (run `fbeb410c…`)
  - `senpai/check-editable-budget.sh ab1f9a1323421703f944ac1895841e39b8302542`
  - `senpai/validate-assignment-scope.sh ab1f9a13… Sources/MLXFastModel/LagunaRuntimeModel.swift`
  - `swiftc -parse Sources/MLXFastModel/LagunaRuntimeModel.swift`
- Tests and risk-based checks run, including selected-test count: emitted-MSL identity harness
  (109 strings, 100 % coverage, run twice: base→T1 and base→T2); idempotence check on both
  `dedent` and `strip` (second invocation removes 0 bytes); `verify` round-trip (108 blocks,
  residual closing indent 20 B from the three excluded blocks); `swiftc -parse` (exit 0);
  `run_upstream_equivalence.sh` on **both** the candidate and the unchanged base, each selecting and
  executing **1 test** (non-zero, so not the zero-test trap) — see §4.2, both fail identically and
  the failure is a pre-existing M4 prefill divergence; **four** paired `--local-iterate` correctness
  runs.
- Correctness and serial-protocol verdict: `passed_correctness=true`, `max_abs_diff=0`,
  `checked_steps=130`, `golden_hash` identical to base on all four arms. The vendored-upstream oracle
  fails on this host, but with **numerically identical** output on the untouched base (§4.2), so it
  records no candidate-induced difference; the ranked M5 is authoritative there. No caching, no
  lookahead, no cross-request state was added — the change removes source bytes only and cannot
  affect the serial non-speculative contract.
- Divergent tokens or failure category, if any: no divergent tokens on any gate. One failure
  category to declare honestly: `research/run_upstream_equivalence.sh` exits 1 on this host on both
  base and candidate (prefill `maximumAbsoluteLogitError = 0.125`, all decode steps exact, argmax
  agreeing on every step). Fully documented in §4.2.
- Peak RAM or generated-weight size, if relevant: `peak_ram_gb=21` on every arm;
  `bandwidth_gb_per_token=0` as expected for a RAM-resident model.
- Official ranking status versus correctness/floor status, if submitted: **not submitted.** Assignment
  §7 reserves the ranked channel for PR #80. `passed_prefill_speedup_floor=false` appears on this M4
  host in the *baseline* as well and is an artefact of M5-derived pinned constants, not a candidate
  regression.

| Metric | Baseline | Candidate (T1+T2) | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.0131342145234375 | 0.0132953505859375 | speedup 0.9879 (+1.227 % time) |
| prefill seconds/token | 0.00113611279296875 | 0.001125958658203125 | speedup 1.0090 (−0.894 % time) |
| same-host paired estimate | — | 0.9931 | — |

The paired estimate is a same-host research metric, not an official M5 score.

### Conclusion

- What happened and why: `LagunaRuntimeModel.swift` stored its 108 Metal kernel sources indented to
  the Swift nesting level of their generator functions, and carried explanatory `//` comments inside
  those kernel strings. Neither contributes anything the harness checks. Removing both with a
  deterministic, idempotent script reclaimed **42,757 B** — 8.2 % of the file, taking per-file
  headroom from 2,520 B to 45,277 B — at a *certified* zero change in the emitted Metal token
  sequence and zero change in every checked greedy token.
- Evidence for or against the mechanism: strongly for. T1 is byte-identical across all 109 emitted
  strings and provably whitespace-only at the Swift level. T2's 32 differing strings were each
  reproduced by a second, independently written comment stripper. All four arms produce the same
  `golden_hash` with `max_abs_diff=0`, and the upstream oracle returns bit-identical logits on the
  candidate and the untouched base.
- Uncertainty or M5 transfer risk: essentially none for correctness — the emitted MSL is unchanged,
  so the M5 compiles exactly the same shaders it compiles today, and the certificate is
  value-independent rather than fixture-dependent. The only M5-relevant uncertainty is timing, and
  the honest claim there is "no expected effect"; the M4 deltas reported in §5 are noise on an
  instrument too coarse to resolve them, which is itself a finding about the §6.3 A/A band.
- Smallest useful next action: merge, and choose between the two-commit and T1-only variants per §7.
  Nothing else in this workstream needs another run.
- Recommendation: **merge.** `2fb4b33` (T1) is the high-confidence core and stands alone;
  `114dce2` (T2) adds 13,397 B at a slightly weaker but still two-implementation certificate and
  costs in-kernel documentation. Merge order relative to PR #80 is the advisor's call — I have not
  rebased on my own initiative (§4.2) and will do so on request.

---

## Regeneration warning (assignment §4.1)

**This change is a script output; regenerate after every rebase; never hand-edit the result.**

```bash
python3 research/tanjiro_metal_literal_tool.py dedent Sources/MLXFastModel/LagunaRuntimeModel.swift  # T1
python3 research/tanjiro_metal_literal_tool.py strip  Sources/MLXFastModel/LagunaRuntimeModel.swift  # T2
```

Both subcommands are deterministic and idempotent — a second invocation of either removes 0 bytes —
so re-running them on a rebased file reproduces the same result rather than compounding. After any
rebase onto a base that itself touched `LagunaRuntimeModel.swift`, discard the textual merge of these
commits and re-run the two commands instead; a hand-resolved conflict inside a Metal literal is
exactly the failure mode the script exists to prevent. Verify with
`certify <base-dump> <candidate-dump>` (§3.2) before trusting the regenerated file.

---

## Suggested follow-ups

Not implemented here; listed for the advisor to schedule or discard.

1. **Take the proven header hoist (T4 partial, 2,449 B), after PR #80 merges.** §3.3 established as a
   *fact*, not an estimate, that post-T2 the sliding and full fused-attention headers
   (`008_header` ≡ `010_header`) are byte-identical at 2,449 B each; they differed in base only by 5
   comment lines. Every kernel passes an explicit `name:`, so MLX never derives a cache key from
   source text and sharing one string is safe. This is the single best remaining byte-per-risk item.
2. **`extract` fragment hoist (447 B) is safe at any time.** The L4183/L6686 pair is byte-identical
   and does not touch anything PR #80 edits. `scaleSetup` (L4225/L4718, 307 B) collides with #80 and
   should wait. Do **not** unify `singleWeightLoad` (L3533) with `unrolledWeightLoad` (L3576) — §3.3
   records that as a verified false positive.
3. **Do not spend a round on T3, T5, T6, or T7 for bytes.** Per-file headroom is now 45,277 B
   (17.97×) and surface headroom 75,926 B, so bytes are no longer the binding constraint; §7 argues
   the next round belongs to timing. If T6/T7 are ever wanted, they need the dump harness extended to
   certify the *multiset* of emitted strings across the cross-product of the `laguna*Enabled` gates —
   worth building only for a timing reason, never for ~20 KB.
4. **Fix the A/A protocol in future briefs.** Replace the constant ±1.30 %/+0.48 % band with a
   measured same-session base↔base repeat (§5): my A/A on identical bytes consumed 96 % of the decode
   allowance, and four provably-MSL-equivalent arms spread 1.588 % on decode / 2.105 % on prefill.
   As written the band would have stopped a certified byte-identical change.
5. **Decide what to do about the oracle on non-M5 hosts** (§4.2). `run_upstream_equivalence.sh` fails
   on the *unchanged base* on M4 Pro with a prefill-only, argmax-agreeing divergence, so no student on
   generation-16 hardware can currently produce a green oracle certificate. Either give the test an
   architecture guard (its name already says `OnM5WhenEnabled`) or state in the runbook that this
   failure is expected off-M5. Both files are outside my scope, so I changed neither.
6. **Consider a `--check` mode for the tool.** `research/tanjiro_metal_literal_tool.py` could gain a
   subcommand that fails non-zero when the checked-in file differs from the script's output, making
   the "never hand-edit" rule mechanically enforceable by whoever rebases next. I did not add it
   because nothing currently runs research scripts automatically (§5.6: no formatter or lint gate).
7. **T8 remains untouched and I recommend leaving it that way** unless a specific comment is provably
   stale. The 125,860 B pool outside the literals is the programme's design record (L312, L3265,
   L5122, L6607, L6735, L7468 all encode invariants a future round would otherwise rediscover the
   hard way).
