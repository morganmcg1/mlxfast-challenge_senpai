# Submitted-Surface Reclamation Audit

## Verdict

**GO for a separate one-file implementation experiment.** The conservative dry-run identifies 133,943 removable bytes in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, exceeding both required reclamation thresholds without proposing edits to any generated source, embedded kernel string, selector registry, license block, or other submitted file.

This branch is research-only. It does not modify the submitted surface and makes no correctness, latency, score, or ranked-hardware claim.

## Provenance and frozen inputs

- Assignment PR: `#665`
- Assignment branch: `cedar-nezuko/submitted-surface-reclamation-audit`
- Required base: `5eeeba7df24d32423c3867cb778c5d64bb8bfde3`
- Assignment head before audit artifacts: `a624290be14ce495200ba96fd746c2d82ecd6ec6`
- `benchmark.json` SHA-256: `e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6`
- Canonical logical submitted-manifest digest: `2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230`
- Laguna source SHA-256: `ed084a8aa840f651449b8c9f344c2cd40786de9eccee2c291bde419716022ccb`

The analyzer reads the contract at the required base through Git, requires the working-tree contract to be byte-identical, expands every editable path, rejects symlinks and non-regular entries, and cross-checks every submitted path, byte count, and SHA-256 against `research/ranked-best-payload-gap-audit.json`.

## Exact submitted surface

The reconstructed surface matches the assignment controls exactly:

| Control | Observed |
| --- | ---: |
| Submitted files | 142 |
| Submitted bytes | 2,984,121 |
| Global limit | 3,000,000 |
| Global headroom | 15,879 |
| Laguna bytes | 511,690 |
| Per-file limit | 524,288 |
| Laguna headroom | 12,598 |

Classification recorded for every submitted file in the JSON manifest:

| Dimension | Count |
| --- | ---: |
| Ordinary compiled source | 29 |
| Ordinary compiled source with runtime-embedded text | 3 |
| Generated runtime-embedded source | 29 |
| Runtime-effective kernel source | 81 |
| Swift | 29 |
| C++ | 32 |
| C++/Metal header | 54 |
| Metal | 27 |
| Generated | 29 |
| Runtime-embedded source | 32 |

Generated twins and runtime-effective kernels are classified but deliberately excluded from reclamation.

## Proposed follow-up change

The follow-up implementation should touch only:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift`

No additional submitted file is needed, well below the assignment cap of eight follow-up paths.

| Measure | Before | Dry-run after | Reclaimed / added headroom |
| --- | ---: | ---: | ---: |
| Total submitted bytes | 2,984,121 | 2,850,178 | 133,943 |
| Global headroom | 15,879 | 149,822 | 133,943 |
| Laguna bytes | 511,690 | 377,747 | 133,943 |
| Laguna headroom | 12,598 | 146,541 | 133,943 |

Required thresholds are at least 16,384 bytes globally and at least 8,192 bytes in Laguna. The dry-run exceeds them by 117,559 and 125,751 bytes respectively.

## Conservative reclamation proof

The analyzer found 1,970 sorted, non-overlapping, half-open byte ranges. `research/submitted_surface_reclamation_manifest.json` binds the plan to the single target path and records each range's byte offsets, original line, byte count, expected SHA-256, classification, and proof identifier.

Only indentation plus a whole-line Swift `//` or `///` comment body is selected. The terminating newline is never selected. The lexer recognizes normal strings, raw strings, multiline strings, raw multiline strings, line comments, and nested block comments at the byte level. A candidate is rejected unless the entire non-whitespace line is one lexer-classified line comment.

The proof obligations are:

1. Removed bytes are lexical trivia on lines containing no code token.
2. Every original newline is retained, so line numbering and newline count are unchanged.
3. Every non-deleted byte remains in original order.
4. No live `#line`, `#column`, or `#sourceLocation` token exists in the target file.
5. Block comments, inline comments, strings, raw strings, and embedded Metal source strings are excluded.
6. Generated files, kernel sources, embedded-source carriers, required license/tooling blocks, selector registries, and C/C++ macro hazards are excluded.
7. In-memory deletion followed by reverse reinsertion reconstructs the exact original bytes and SHA-256.
8. Verification refuses stale files, changed hashes, overlapping ranges, malformed offsets, changed contract bytes, or a changed submitted manifest.

The selected class is therefore narrower than generic “comment stripping”: it removes only proven whole-line Swift line-comment trivia while preserving all source-location-affecting newlines.

## Positive controls

All controls in `research/submitted_surface_reclamation_controls.txt` pass through the production validation path:

1. Comment-like sequences inside Swift strings are not selected.
2. Embedded Metal source ranges are not selected.
3. A required license block is not selected.
4. An active selector-registry token is not selected.
5. A C/C++ macro-continuation hazard is not selected.
6. A corrupted expected range hash is rejected.
7. A corrupted submitted-surface manifest is rejected by the same production validator.
8. Submitted files remain read-only because the dry-run operates only on in-memory byte strings.

These controls demonstrate false-positive resistance, fail-closed stale-input handling, and submitted-surface isolation.

## Historical novelty and active overlap

Earlier cleanup commits removed obsolete implementation paths rather than performing this lexical-only reclamation:

- `1e090aaf6e6905fdba1e1490109d4071feb4baeb` removed stale gated-output variants.
- `6d32b6c7581b5e1dadaa0df3b391809bcf17ac76` removed routed R1 dispatch scaffolding.
- Related cleanup history includes `61e93d8`, `2911353`, `6db554d`, and `d703dc5`.

The leaderboard campaign brief proposed reclaiming dormant negative arms, with active-selector risk. This plan is materially narrower: it changes no implementation, selector, layout, registry, generated source, or kernel text. It removes only hash-identified lexical trivia from the current frontier.

`research/CURRENT_RESEARCH_STATE.md` lists active work on vector lifetime, ranked-path identity, thermal gating, prefill host attribution, differential-fence attribution, and official repeatability. None overlaps this one-file source-budget reclamation plan.

## Reproduction

Generate a fresh manifest and controls receipt:

```bash
python3 research/audit_submitted_surface_reclamation.py \
  --output research/submitted_surface_reclamation_manifest.json \
  --controls-output research/submitted_surface_reclamation_controls.txt
```

Verify the committed manifest against the current frozen source and contract:

```bash
python3 research/audit_submitted_surface_reclamation.py \
  --verify research/submitted_surface_reclamation_manifest.json
```

Expected summaries:

```text
surface=142 bytes=2984121 ranges=1970 reclaimed=133943 decision=GO
verified: files=142 bytes=2984121 reclaimed=133943 decision=GO
```

## Required validation for the future implementation

The current assignment expressly excludes implementing submitted edits, builds, inference, timing, or official submission. A separate implementation experiment should:

1. Re-run the analyzer on its exact base and require identical source/contract receipts.
2. Apply only the manifest’s 1,970 hash-verified ranges to Laguna.
3. Re-run the surface-budget validator and confirm the exact 133,943-byte reduction.
4. Perform clean builds with frozen resolved versions.
5. Run `research/run_upstream_equivalence.sh`.
6. Run the public 64-step drift tripwire.
7. Run the local-submit correctness gates.
8. Require hidden 512-token teacher-forced, anchor, free-run, GPQA TTFT/semantic, and timed token-exactness gates before promotion.
9. Reconfirm both global and Laguna headroom from the actual implementation commit.

## Limitations and interpretation

- No submitted file is modified by this audit.
- No model, GPU, inference, benchmark, local-submit, or official M5 run was executed.
- W&B run ID and URL: not applicable for this static source audit.
- Runtime and peak memory: not applicable.
- Primary performance metric, latency, speedup, and score: not measured.
- The GO verdict means only that the source-budget hypothesis is precise, reversible, threshold-clearing, and suitable for a separately validated implementation experiment.
