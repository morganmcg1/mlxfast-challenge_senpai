# Cedar close-day candidate manifest

Status: **audit complete; no official submission dispatched**

This manifest freezes the three close-day candidates named by the assignment. It is an audit record, not permission to bypass the official queue. Every dispatch still requires explicit queue authorization and the applicable external gate below.

## Authoritative bases

- Frozen official comparison base: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`
  - tree: `99cd398dc28b424c1e2bb766d210affa58f17d54`
- Assigned advisor base: `60dcb0e765608f4f0ca0ec1bb7bfae1a957fe0a4`
  - tree: `687dd28a4b82afe6335108d39251da22230c627a`
- Current ranked leader: `cc6ddc1`, score `2.61650354381456`

Submitted-surface deltas and budgets below are measured against the frozen official base. The assigned advisor base contains research/support changes and a comment-only byte reclaim, so branch ancestry alone is not used as composition evidence.

## Candidate inventory

| Candidate | PR | Immutable head | Tree | Submitted delta from frozen base | Budget verdict |
|---|---:|---|---|---|---|
| C1 | #720 | `3d4b6bfeef2f68b4976d9a7c84561bb771377e8b` | `38c71ec131bc7cd330cdcf42d1c5e8d7b4e6518b` | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | PASS: 2,984,323 / 3,000,000 bytes; 15,677 headroom; +474 / 262,144 growth; 142 files |
| C2 | #721 | `5b5e73a469a636f28f37a8857b3f58c3bc27f620` | `e266fb28a3db32af72ea0e8a27784d1e2988c18d` | C1 file plus `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | PASS: 2,997,654 / 3,000,000 bytes; 2,346 headroom; +13,805 / 262,144 growth; 142 files |
| C3 | #722 | `fb8b4194d669e9122bf93f2d985439001abb31dc` | `a453d532f6d8b46d384a442b7cd89135e4e62c59` | C2 files plus `Sources/MLXFastModel/LagunaOProjGeometry.swift` | PASS: 2,999,925 / 3,000,000 bytes; 75 headroom; +16,076 / 262,144 growth; 143 files |

The recorded PR heads matched these immutable commits at audit time. All submitted files satisfy the 524,288-byte per-file ceiling; the largest is the C1/C2 runtime at 511,892 bytes.

## Submitted-file identities

| Candidate | Path | Bytes | SHA-256 | Git blob |
|---|---|---:|---|---|
| C1 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 511,892 | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` |
| C2 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 511,892 | `c57aef4397d40efd982d13f5cca97a789113af09230f0faeacebe5e5c566a07b` | `ae9acf9034c5fd2509a61fb4861f24e9e252c95c` |
| C2 | `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 60,069 | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | `7738d670b5570159284aae626b5a5b63c08f371e` |
| C3 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 507,128 | `8dcd63ed8cca09b6cd2846617fc468d7aab763546a0de05f4fdffa4bea9afc77` | `33e0dcc678e6bae69bcb16d56c4090015c7a44c7` |
| C3 | `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 60,069 | `3068171860a61e3d6de611215922866babe77d6b5f59acb061d59c2e48907db4` | `7738d670b5570159284aae626b5a5b63c08f371e` |
| C3 | `Sources/MLXFastModel/LagunaOProjGeometry.swift` | 7,035 | `6145acfbfd3c08aed9850ef0d87327d80875467a8bee33cfcb5d0140cf8bfadb` | `ae47f9911a7d8372cd14eecaaaaf58425fb32ea2` |

Tree hashes and SHA-256 values are the dispatch identities. A dispatcher must not rebuild, cherry-pick, amend, or otherwise synthesize a replacement candidate.

## Composition audit

### C1: shared-R1 lineage

C1 changes exactly one submitted file relative to the frozen official base: `LagunaRuntimeModel.swift`. Its submitted snapshot is pinned by the head, tree, size, SHA-256, and blob above.

### C2: exact C1 plus organizer row-32

- C1 and C2 have byte-identical runtime files.
- The complete submitted-surface C1-to-C2 diff is one file: `LagunaLmHeadPrune.swift` (`+354/-14`).
- C2's `LagunaLmHeadPrune.swift` is byte-identical to organizer row-32 commit `0101733e2d3c2629a04d86c24f236a43ef38bc33` (same git blob `7738d670b5570159284aae626b5a5b63c08f371e`).

Verdict: **PASS — C2 is exactly C1 plus organizer row-32 on the submitted surface.**

Routing caveat: the immutable C2 is not a synthesized “row-32-only” candidate; it retains C1's shared-R1 runtime. Do not remove shared-R1 or create a new commit under this manifest. Dispatch C2 only when the advisor's Gate B decision explicitly selects this exact head.

### C3: C2 plus Maple o_proj, with audited byte reclaim

- C3 retains C2's exact row-32 file.
- C3's `LagunaOProjGeometry.swift` is byte-identical to the Maple PR #707 source candidate.
- The complete submitted-surface C2-to-C3 diff touches only `LagunaRuntimeModel.swift` and the added `LagunaOProjGeometry.swift`.
- Every executable runtime hunk is attributable to Maple o_proj geometry: o_proj rows-per-simdgroup/simdgroup constants and result initialization, pipeline suffix selection, and matching gated/activated o_proj guard tiles, grids, and threadgroups.
- The other runtime differences are comment deletion or blank-line preservation from the advisor's 5,310-byte comment-only reclaim (2,892-byte receipt nonce ledger plus 2,418 bytes of catalogued comments). They do not alter executable behavior.
- An explicit scan found no `gate_sp` mechanism in C3.

Verdict: **PASS at executable/source-hunk level — C3 is C2 plus Maple o_proj, with disclosed comment-only byte reclaim and no hidden gate_sp mechanism.** Exact byte-level patch replay from Maple's older base is not claimed because the base contexts differ.

## Inherited non-submitted changes

All three candidates inherit the same non-submitted executable/support changes relative to the frozen base:

- `Sources/MLXFastHarness/TransformVerification.swift`
- `Sources/MLXFastTrustedHarness/TransformVerification.swift`
- `Tests/MLXFastTests/TransformTests.swift`

They also inherit research-only evidence under `research/` and `senpai/research-frontier-briefing.md`. That material includes current-state and idea ledgers; candidate audit reports, manifests, and validators; host census and M4/M5 calibration evidence; decode vector-lifetime and local Amdahl studies; ranked promotion, payload, environment, weight, AOT, authority, and selector audits; prefill attribution; submitted-surface reclamation; and transform-coverage records.

These files are outside the submitted surface and do not change the candidate payloads. The exact inherited research/support inventory remains mechanically recoverable with:

```bash
git diff --name-status 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7..<candidate-head> -- research/ senpai/ Sources/MLXFastHarness/ Sources/MLXFastTrustedHarness/ Tests/MLXFastTests/
```

## External gates and dispatch checklists

Global prerequisites for every candidate:

- [ ] The official queue explicitly authorizes this exact candidate.
- [ ] The PR head still equals the immutable head in this manifest.
- [ ] The commit tree still equals the recorded tree.
- [ ] Every submitted file matches the recorded SHA-256 identity.
- [ ] The budget remains PASS against frozen base `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
- [ ] The dispatcher submits the existing commit without amendment, reconstruction, or additional files.

### C1 / PR #720

- Purpose: Gate B shared-R1 measurement candidate.
- External gate: none beyond queue authorization for measuring Gate B; its resulting raw decode determines the next route.
- Decision threshold: raw candidate decode `<= ~4.867 ms/token` selects the C1 lineage.
- [ ] Global prerequisites complete.
- [ ] Queue authorization explicitly names C1 / PR #720 / head `3d4b6bfeef2f68b4976d9a7c84561bb771377e8b`.

Dispatch verdict: **structurally safe only after the checklist passes.**

### C2 / PR #721

- Purpose: held exact C1-plus-row-32 fallback.
- External gate: Gate B routing must explicitly select this exact C2 head; parity language must not be interpreted as permission to synthesize a row-32-only variant.
- [ ] Global prerequisites complete.
- [ ] Gate B result and advisor route explicitly name C2 / PR #721.
- [ ] Queue authorization explicitly names head `5b5e73a469a636f28f37a8857b3f58c3bc27f620`.

Dispatch verdict: **structurally safe only when the exact-head routing caveat and checklist pass.**

### C3 / PR #722

- Purpose: selected C2 lineage plus Maple o_proj.
- External Gate A: Maple o_proj raw candidate decode must be `<= 4.905 ms/token`.
- External lineage gate: the advisor must have selected the C2 lineage before C3 dispatch.
- [ ] Global prerequisites complete.
- [ ] Gate A passes at `<= 4.905 ms/token`.
- [ ] The C2 lineage is explicitly selected.
- [ ] Queue authorization explicitly names C3 / PR #722 / head `fb8b4194d669e9122bf93f2d985439001abb31dc`.

Dispatch verdict: **structurally safe only after Gate A, lineage selection, and the checklist pass.**

## Stopping conditions and evidence limits

- No official candidate was submitted while producing this manifest.
- No model benchmark, W&B run, or GPU job was required or launched; this assignment is an immutable source/tree/budget audit.
- A failed external gate, moved PR head, hash mismatch, budget failure, missing queue authorization, or request to reconstruct a candidate is a hard stop.
- Official M5 correctness and timing remain authoritative; this manifest proves composition and payload identity, not hidden-gate success or performance.

_This audit record was generated by an AI agent (OpenHands) on behalf of the Senpai research campaign._
