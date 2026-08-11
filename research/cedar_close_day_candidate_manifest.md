# Cedar close-day candidate manifest

Status: **INCONCLUSIVE — C1/C2/C3 are historical and superseded; C3 composition claim remains falsified; no official submission dispatched**

This manifest preserves the three close-day candidate identities named by the assignment. N1 is now the live official leader, so C1, C2, and C3 are historical, superseded, and non-dispatchable. This audit record is not dispatch authority and cannot authorize any candidate or bypass frontier synchronization and queue controls.

## Authoritative bases and cutoff

- Frozen official comparison base used by the historical audit: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
  - tree: `99cd398dc28b424c1e2bb766d210affa58f17d54`
- Assigned advisor base used by the historical audit: `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4`
  - tree: `687dd28a4b82afe6335108d39251da22230c627a`
- Current fetched advisor ref at the r3 cutoff: `56627049c538474747297c8345a3a59260bf5226`
  - tree: `0eb8732a0a2d6469ac6139a3cf48a346eca575a3`
- Live official leader N1:
  - receipt: `cdcd0918-0002-45b0-a14b-81f34c40a398`
  - organizer commit: `4ea72c3b28873fca23b12b6f33193a2eeb5042f8`
  - score: `2.6195531094824`
  - decode: `203.93695 tok/s`, `2.823562x`
  - prefill: `5314.29504 tok/s`, `2.091784x`

Submitted-surface deltas and budgets below are historical measurements against the frozen official base. The submission contract was identical at the frozen and assigned bases, but the assigned advisor base already changed submitted `LagunaRuntimeModel.swift`: atlas kernel `v2` became `v3_tg128`, its copy/dispatch geometry changed from 512 to 128 threads, and `decodeAtlasPosition` was computed once and reused. It also contained comment-only byte reclaim plus non-submitted research, harness-verification, and test changes. Historical mechanism ownership therefore must be judged in assigned-advisor-base context; frozen-base comparison alone includes inherited atlas executable work.

## N1 frontier and authority boundary

N1's promoted snapshot changes seven submitted files. That snapshot must be adopted whole, and only after the reviewed fork-main synchronization lands. This r3 documentation correction does not import, reconstruct, validate, or authorize that snapshot; the named organizer object was not available in this checkout during the bounded static check. No official submission from any stale base is permitted.

N1 is executable-identical to an earlier rejected official receipt except for a comment. The accepted N1 receipt is therefore authoritative ranking evidence, but the official outcome variance is not clean causal proof that the comment or any executable mechanism caused the promotion.

C1/C2/C3 deterministic audit work has no W&B run. Ranked context remains [`7ep17pqq`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq) and [`ut3wdjct`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ut3wdjct). N1 has official receipt evidence only and no W&B run.

## Historical candidate inventory — superseded and non-dispatchable

| Candidate | PR | Historical immutable head | Tree | Submitted delta from frozen base | Budget verdict |
|---|---:|---|---|---|---|
| C1 | #720 | `aa152d6102b191adaaa9e95e8374d08e5a5e83c2` | `4eb3888cf226e184b0d512319183896ef638df60` | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | PASS: 2,984,323 / 3,000,000 bytes; 15,677 headroom; +474 / 262,144 growth; 142 files |
| C2 | #721 | `5b5e73a469a636f28f37a8857b3f58c3bc27f620` | `e266fb28a3db32af72ea0e8a27784d1e2988c18d` | C1 file plus `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | PASS: 2,997,654 / 3,000,000 bytes; 2,346 headroom; +13,805 / 262,144 growth; 142 files |
| C3 | #722 | `fb8b4194d669e9122bf93f2d985439001abb31dc` | `a453d532f6d8b46d384a442b7cd89135e4e62c59` | C2 files plus `Sources/MLXFastModel/LagunaOProjGeometry.swift` | PASS: 2,999,925 / 3,000,000 bytes; 75 headroom; +16,076 / 262,144 growth; 143 files |

The r2 read-only head check found PR #720 at `aa152d6102b191adaaa9e95e8374d08e5a5e83c2`, PR #721 at `5b5e73a469a636f28f37a8857b3f58c3bc27f620`, and PR #722 at `fb8b4194d669e9122bf93f2d985439001abb31dc`. C1 implementation commit `3d4b6bfeef2f68b4976d9a7c84561bb771377e8b` is superseded as the PR head, although its submitted runtime payload remains the verified historical C1 payload. All submitted files satisfy the 524,288-byte per-file ceiling; the largest is the C1/C2 runtime at 511,892 bytes. These preserved identities are audit evidence, not live dispatch candidates.

## Submitted-file identities

| Candidate | Path | Bytes | SHA-256 | Git blob |
|---|---|---:|---|---|
| C1 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 511,892 | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` |
| C2 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 511,892 | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` |
| C2 | `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 60,069 | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | `7738d670b5570159284aae626b5a5b63c08f371e` |
| C3 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 507,128 | `8dcd63ed8cca09b6cd2846617fc468d7aab763546a0de05f4fdffa4bea9afc77` | `33e0dcc678e6bae69bcb16d56c4090015c7a44c7` |
| C3 | `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 60,069 | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | `7738d670b5570159284aae626b5a5b63c08f371e` |
| C3 | `Sources/MLXFastModel/LagunaOProjGeometry.swift` | 7,035 | `6145acfbfd3c08aed9850ef0d87327d80875467a8bee33cfcb5d0140cf8bfadb` | `ae47f9911a7d8372cd14eecaaaaf58425fb32ea2` |

Tree hashes and SHA-256 values preserve the historical audit identities. They do not authorize dispatch, reconstruction, cherry-picking, amendment, or synthesis of a replacement candidate.

## Composition audit

### C1: shared-R1 lineage

C1 changes exactly one submitted file relative to the frozen official base: `LagunaRuntimeModel.swift`. Its submitted snapshot is pinned by the current PR/dispatch head, tree, size, SHA-256, and blob above.

Current C1 commit `aa152d6102b191adaaa9e95e8374d08e5a5e83c2` is a two-parent merge with tree `4eb3888cf226e184b0d512319183896ef638df60`: first parent `3d4b6bfeef2f68b4976d9a7c84561bb771377e8b`, the superseded r1 implementation commit, and second parent `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4`, the assigned advisor base. The merge changes only non-submitted `research/CURRENT_RESEARCH_STATE.md` relative to `3d4b6bfe...`; its submitted runtime remains blob `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` and SHA-256 `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b`.

### C2: exact C1 plus organizer row-32

- Current C1 and C2 have byte-identical runtime files.
- The complete full-repository current-C1-to-C2 diff is one submitted file: `LagunaLmHeadPrune.swift` (`+354/-14`); there is no additional research-only delta between these audited heads.
- C2's `LagunaLmHeadPrune.swift` is byte-identical to organizer row-32 commit `0101733e2d3c2629a04d86c24f236a43ef38bc33` (same git blob `7738d670b5570159284aae626b5a5b63c08f371e`).
- Current C1 is not an ancestor of C2; C2 is a separate merge commit. The composition verdict concerns submitted payload identity, not literal lineage or whole-tree identity.

Verdict: **PASS — C2 is exactly C1 plus organizer row-32 on the submitted surface.**

Historical routing caveat: the immutable C2 was not a synthesized “row-32-only” candidate; it retained C1's shared-R1 runtime, and its prior Gate B route required the exact audited head. N1 now supersedes that route: do not dispatch C2, remove shared-R1, or create a replacement commit under this manifest.

### C3: exact composition claim falsified

- The complete C2-to-C3 tree delta contains exactly two submitted paths: added `LagunaOProjGeometry.swift` (135 lines) and modified `LagunaRuntimeModel.swift` (`+89/-79`).
- The o_proj geometry mechanism is present and defaults to rows-per-simdgroup `2` and simdgroups `2`, but remains environment-tunable rather than exclusively pinned.
- Contrary to the required predicate, `gate_sp` remains present and default-on in C3 through `DARKBLOOM_AFFINE_GATE_SOFTPLUS`; the scored attention path invokes its dispatcher, and activated-o_proj selection depends on it. This mechanism was inherited from C2 rather than newly added by C3, but C3 therefore does not satisfy “no gate_sp mechanism.”
- The runtime delta also removes 68 comment lines and adds 69 blank lines outside the substantive geometry edits, including allocation documentation, an official replay nonce, and the active64 receipt history. This is non-executable churn, but it is unrelated submitted-source delta.
- No unrelated executable mechanism was apparent in the direct C2-to-C3 diff.

Verdict: **FAIL — C3 is not an exact clean C2-plus-Maple-o_proj snapshot under the assignment predicate.** The stopping rule applies regardless of external Gate A or queue state.

## Inherited advisor-base changes

All three candidates inherit a submitted runtime change relative to the frozen base in `Sources/MLXFastModel/LagunaRuntimeModel.swift`: the atlas kernel moves from `v2` to `v3_tg128`, copy/dispatch geometry moves from 512 to 128 threads, and `decodeAtlasPosition` is computed once and reused. This executable work belongs to the advisor base, not C1/C2/C3.

They also inherit common non-submitted support changes in:

- `Sources/MLXFastHarness/TransformVerification.swift`
- `Sources/MLXFastTrustedHarness/TransformVerification.swift`
- `Tests/MLXFastTests/TransformTests.swift`

Research-only evidence under `research/` and `senpai/research-frontier-briefing.md` is likewise non-submitted. The exact inherited research/support inventory remains mechanically recoverable with:

```bash
git diff --name-status 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7..<candidate-head> -- research/ senpai/ Sources/MLXFastHarness/ Sources/MLXFastTrustedHarness/ Tests/MLXFastTests/
```

Frozen-base payload hashes and budgets remain valid, but executable ownership must be assessed against advisor base `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4`.

## Historical gate context and no-dispatch checklist

Global disposition:

- [x] N1 is the live official leader; C1, C2, and C3 are historical and superseded.
- [x] This manifest is evidence only and is not dispatch authority.
- [x] No official submission from the frozen base, assigned advisor base, or any other stale base is permitted.
- [ ] N1's seven submitted files may be adopted only as one reviewed snapshot after fork-main synchronization lands; this manifest does not complete that work.
- [ ] Any later candidate requires a fresh assignment base, current-frontier validation, and independent queue authorization outside this manifest.

### Historical C1 / PR #720

- Prior purpose: Gate B shared-R1 measurement candidate.
- Prior decision threshold: raw candidate decode `<= ~4.867 ms/token` would have selected the C1 lineage.
- Preserved head: `aa152d6102b191adaaa9e95e8374d08e5a5e83c2`.

Current disposition: **SUPERSEDED — do not dispatch.**

### Historical C2 / PR #721

- Prior purpose: held exact C1-plus-row-32 fallback.
- Prior routing condition: Gate B parity would have selected this exact C2 head, never a synthesized row-32-only variant.
- Preserved head: `5b5e73a469a636f28f37a8857b3f58c3bc27f620`.

Current disposition: **SUPERSEDED — do not dispatch.**

### Historical C3 / PR #722

- Prior intended purpose: selected C2 lineage plus Maple o_proj after external Gate A (`<= 4.905 ms/token`).
- Preserved head: `fb8b4194d669e9122bf93f2d985439001abb31dc`.
- [x] Independent hard stop: C3 retains default-on `gate_sp` and contains unrelated submitted-source churn.

Current disposition: **FAIL AND SUPERSEDED — do not dispatch regardless of gates or queue state.**

## Stopping conditions and evidence limits

- The falsified C3 composition claim triggered the original assignment's hard stop; that FAIL remains preserved.
- N1's accepted receipt supersedes C1, C2, and C3. Their exact payload identities, budgets, composition evidence, and ancestry caveats remain historical audit evidence only.
- This manifest grants no dispatch authorization. A request to submit any C1/C2/C3 head, use a stale base, extract only part of N1's seven-file snapshot, or reconstruct a candidate is a hard stop.
- N1 adoption requires the complete promoted snapshot through reviewed fork-main synchronization, followed by fresh current-frontier assignment and validation outside this manifest.
- No official candidate was submitted while producing this manifest.
- No model benchmark, W&B run, or GPU job was required or launched; this assignment is a static source/tree/budget and authority audit.
- Official M5 correctness and timing remain authoritative. N1's accepted receipt establishes the live ranking cutoff, but variance from its executable-identical rejected predecessor is not clean causal evidence.

_This audit record was generated by an AI agent (OpenHands) on behalf of the Senpai research campaign._
