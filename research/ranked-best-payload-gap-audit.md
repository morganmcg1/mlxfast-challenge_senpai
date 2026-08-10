# Ranked-best payload gap audit

## Decision

**NO-GO.** There is no missing ranked-best payload mechanism to import. The
current frontier is byte-identical to the complete 142-file submitted surface
of the stronger local candidate, receipt
`e27f1ce4-23bb-4b5f-8e8e-90082be9ea3a`. That candidate directly inherits the
ranked-best receipt and adds only two already-tested changes, but its official
M5 score was **0.376604% below** the crown.

No successor experiment is recommended from this gap audit. The conservative
M5 incremental-gain lower bound and the Amdahl incremental gain from importing
ranked-best payload are both **0%**, because all identified mechanisms are
already present.

## Scope and identities

- PR: `#654`; branch: `cedar-frieren/ranked-best-payload-gap-audit`
- Assignment base: `41d686f15eafda68d9f77905997dab6d78dfdcda`
- Audited branch head before report changes:
  `f8c3523a596c0ae32716947c9b84bc2fa738ed4f`
- Final result commit: recorded exactly by the typed Senpai result. A Git commit
  cannot contain its own hash without changing that hash.
- Scope: research report and manifest only. No production, vendor, generated,
  contract, default, or harness files changed. No build, benchmark, inference,
  official submission, or resubmission was run.
- Current pinned `benchmark.json` SHA-256:
  `e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6`
- Contract expansion: 97 editable-path entries, 142 regular submitted files,
  3,000,000-byte limit.

The machine-readable reconstruction is
[`ranked-best-payload-gap-audit.json`](ranked-best-payload-gap-audit.json). It
stores every path, size, SHA-256, Git blob OID, receipt provenance, score,
exclusion, and the corruption control.

## Receipt provenance and payload hashes

| Receipt | Role | Validation commit | Parent | Tree |
|---|---|---|---|---|
| `cc6ddc12-ecbd-4c07-beec-445060a21a62` | ranked best | `c5b0a13c5cc032b485022db41bcd745792316714` | `01e247a74d1ed8108d503bc0ee7b8c4e14a7c5ff` | `48037ad5eca1262c84461b315b37886ccf26dfb7` |
| `e27f1ce4-23bb-4b5f-8e8e-90082be9ea3a` | challenger | `5c542169a236f61641fbb72ed98d36941c16601b` | `c5b0a13c5cc032b485022db41bcd745792316714` | `1a4d9c9f6d705df44d384002ef70181432bea2c8` |

The validation commits preserve the submitted files but omit `benchmark.json`,
so paths come from the current pinned contract. The e27 validation object is
not advertised by `origin`; its SHA, parent, and tree were independently
inspected, and its 142 file records are reconstructed from assignment base
`41d686f...`, independently verified byte-identical to the e27 submitted
surface.

Canonical logical manifests are compact UTF-8 JSON arrays sorted by path, with
objects `{path,size,sha256}`, sorted keys, and one trailing LF.

| Receipt | Logical manifest SHA-256 | `git ls-tree` listing SHA-256 | Bytes | Headroom | Prepared archive SHA-256 |
|---|---|---|---:|---:|---|
| cc6 | `9f28c40a519c602d92f165f1a460824dc2421d2fb58513ad122f677c228a9921` | `a03196e71a1fb715e590daf819c9ec0f14d331df9f10060a1d780239052fca47` | 2,983,849 | 16,151 | unavailable |
| e27 | `2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230` | `e04b7b09609a4b9f3b79e26d20b267d0acf879b11671f617a92fcbb22ad32c9b` | 2,984,121 | 15,879 | `497cf68f4bf96b66bbc5f8b2cbe96846c07badb25e77e8471204513c120ea490` |

The e27 archive hash is the authoritative value observed in its receipt note;
the archive bytes were not retained, so it was not independently reproduced.
Public note SHA-256 values are
`39b78de7c5958a375546786ea9055209560a8a2f0bf65a4dc815898072b2e91f`
(cc6) and
`cad1db3a27c0ab77150cad0b5c1920f03d7048bbcc4299b50e277d38a0a42c3a`
(e27).

## File and mechanism diff

The e27 validation commit is a direct child of cc6. Across the submitted
surface, exactly one file changes:

`Sources/MLXFastModel/LagunaRuntimeModel.swift`: **18 insertions, 12 deletions,
+272 bytes**.

There are no contract, configuration, generated, metallib, transform, vendor,
or harness changes between the receipts. The e27-only model delta combines:

1. PR `#549`, commit `5706554e88e44bf34b3dabd385089e875da9dbbe`:
   retile the fused decode embedding/RoPE atlas producer from 512 to 128 lanes
   and copy four 128-wide segments per lane.
2. PR `#604`, commit `1ffcd2d0d5b010c27df5f7278fe3b0fdb15f8834`:
   compute `decodeAtlasPosition` once and elide full/sliding attention-mask
   construction only when no-mask safety is proven.

The cc6 active-64 router tournament is inherited unchanged by e27 and the
current frontier. Its final promotion changed only a source comment nonce from
its immediately preceding executable candidate; it did not introduce another
executable mechanism. Therefore the complete mechanism set is already present
at the assignment base and audited source head.

Historical local evidence was positive but small: PR #549 pooled weighted
speedup `1.00416608`; PR #604 weighted measurements `1.001154`, `1.004668`, and
`1.006868` (geometric weighted `1.004227648`). Those directional M4 results do
not override the exact combined M5 receipt.

## Official score comparison

| Receipt | Score | Candidate prefill s/token | Candidate decode s/token | Paired prefill speedup | Paired decode speedup | Verdict |
|---|---:|---:|---:|---:|---:|---|
| cc6 | 2.61650354381456 | 0.0001881588535 | 0.00493005664 | unavailable | unavailable | promoted crown |
| e27 | 2.60664969895906 | 0.000187976888671875 | 0.0048906780546875 | 2.010279844 | 2.842440543 | correct; rank rejected |

The official score ratio e27/cc6 is `0.9962339646438491`, or
`-0.3766035356150943%`. E27 passed 1,344 correctness checks, `max_abs_diff=0`,
GPQA, and both performance floors.

Raw cross-session candidate timing ratios favor e27: prefill
`1.0009680170227873`, decode `1.0080517639624138`, and weighted
`1.0062761412549392` (`+0.6276141254939249%`). These are not paired speedups:
they came from separate official sessions. The paired official score is the
authoritative rank evidence. Consequently there is no defensible positive M5
lower bound for an additional import.

## Manifest corruption control

A positive control flipped bit 0 of byte 0 of e27's model file **in memory**;
the worktree was untouched. The file SHA-256 changed from
`7b3249ef10725c52f7b4df11cdcb72707e15c70eb5f85fc617a97c2d73e659b7`
to `80dba54b811990d96b8fd2c1b23892504d06123a26edb7b8c9a7aa1e2d81f63a`,
and the logical manifest SHA-256 changed from
`2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230`
to `60a679db49291b8ec1caf5c0682a03708140310dfebbf0f895d2bcee098a016f`.
Detection was `true`.

## Missing and excluded evidence

- cc6's prepared archive bytes/hash and paired component speedups were not
  retained or published. Its immutable validation commit reconstructs content.
- Exact CLI archive bytes cannot be recreated safely from Git because tar
  metadata, filesystem enumeration, and the deleted temporary archive matter.
- Values `0.0011314403` prefill and `0.0134978831` decode in the e27 note were
  explicitly separate local measurements, not cc6 official candidate timings,
  and are excluded.
- Direct receipt URLs were unavailable; UUIDs and durable CLI retrieval
  commands are recorded below.
- W&B did not hold either authoritative receipt payload. Context-only runs:
  [7ep17pqq](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq)
  and [ut3wdjct](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ut3wdjct).
  Candidate W&B run: **N/A**.
- Peak memory: approximately 21 GB from e27 receipt evidence. Audit runtime and
  GPU memory: **N/A**, because no model process was launched.

## Reproduction and validation

Receipt retrieval:

```text
mlxfast submission-note cc6ddc12-ecbd-4c07-beec-445060a21a62
mlxfast submission-note e27f1ce4-23bb-4b5f-8e8e-90082be9ea3a
```

Manifest validation uses the checked-in JSON directly:

```text
python3 -c 'import json; p="research/ranked-best-payload-gap-audit.json"; d=json.load(open(p)); assert d["decision"]["status"]=="NO-GO"; assert d["frontier_equivalence"]["all_142_submitted_files_identical"]; assert d["positive_manifest_corruption_control"]["detected"]'
git diff --check
git diff --name-only 41d686f15eafda68d9f77905997dab6d78dfdcda -- Sources Vendor benchmark.json Package.swift Package.resolved
```

The last command must print nothing. The final exact commit SHA and clean-tree
proof are supplied by the typed terminal result, after this report is committed.
