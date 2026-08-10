# Official M5 exact-payload repeatability audit

## Verdict

**NO-GO: insufficient exact-payload repeatability evidence.** The largest eligible group contains one independent terminal official receipt (`n = 1`), below the predeclared `n >= 5` threshold. This is not evidence that either payload is unstable; it means repeatability cannot be estimated from the retained evidence. Per the frozen rule, no variance, coefficient of variation, confidence interval, or performance recommendation is reported.

No build, inference, benchmark, W&B run, or official submission was performed for this research-only audit.

## Eligibility fixed before screening

A receipt was eligible only when all four conditions held:

1. It was a distinct terminal official Laguna serial timing execution on the ranked M5 Max 128 GB host. A second UUID was not assumed independent without a distinct timing execution/session.
2. The submitted bytes were identified by an archive SHA-256 or a complete canonical manifest of `{path,size,sha256}` records. The canonical manifest is compact UTF-8 JSON, sorted by path, with sorted object keys and a final LF. A Git commit or tree alone was never an identity.
3. The durable official record supplied finite score, prefill, and decode measurements (and paired speedups where published), with correctness/timing gates passed. A rank-only rejection remained terminal evidence.
4. Receipt snapshots, contract revisions, and payload revisions were never mixed. Group identity was `(payload fingerprint, receipt-time benchmark/harness contract, ranked hardware)`.

A group was a GO only at `n >= 5` independent executions of one exact identity. Outcome, promotion, and score were not selection criteria.

## Outcome-blind census

The durable API export for benchmark `1854efdf-feba-4773-bae9-b80520881a74` contained 1,791 attempts: 147 accepted, 1,076 rejected, and 568 failed. Its SHA-256 was `fdd8d2f0e374918c882bb9ece93544bf983c5511ec2e2bac37ba9689ce4228c0`. API rows provide authoritative `officialScore`, `officialMetrics`, submission UUID, timestamps, status, and submitted commit, but generally not a complete payload manifest or archive hash; those rows cannot be grouped by exact bytes from the API alone.

Reachable history contained 154 exact `Validate submission <UUID>` subjects. Before inspecting scores, the census selected the newest contiguous contract cohort, bounded at 62 commits. Sixty commits (2026-07-24 through 2026-07-29) shared benchmark SHA-256 `e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6`; the next commit crossed the contract boundary, so 94 older/different-contract commits were excluded rather than pooled. All 60 selected UUIDs matched terminal API rows with complete official metrics. Their complete submitted-surface manifests formed **60 distinct singleton groups and zero duplicates**. Adding receipt-time harness fingerprints can only split these already-unique manifest groups, not merge them. The census artifact SHA-256 was `059bcc7504cb893d78fc22b8d196ecae6ea5fd7d0f384c1f846fec912e81d144`.

The public reachable validation history ends on July 29 and does not retain the newer cc6/e27 validation provenance. Those two identities were therefore checked separately against the immutable evidence already merged in `ranked-best-payload-gap-audit.{md,json}` and the complete API export. This separation avoids fabricating ancestry or mixing revisions.

## Qualifying singleton evidence

| Identity | Receipt and provenance | Authoritative official M5 result |
|---|---|---|
| cc6 manifest `9f28c40a519c602d92f165f1a460824dc2421d2fb58513ad122f677c228a9921` (142 files; archive unavailable) | UUID `cc6ddc12-ecbd-4c07-beec-445060a21a62`; commit `c5b0a13c5cc032b485022db41bcd745792316714`; tree `48037ad5eca1262c84461b315b37886ccf26dfb7`; harness `f9b5f986…`; accepted; correctness passed | score `2.61650354381456`; prefill `0.000188158853515625` s/token (`2.0441331295729355x`); decode `0.004930056640625` s/token (`2.8409180802229947x`); peak RAM 21 GB; **n=1** |
| e27 manifest `2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230`; archive `497cf68f4bf96b66bbc5f8b2cbe96846c07badb25e77e8471204513c120ea490` | UUID `e27f1ce4-23bb-4b5f-8e8e-90082be9ea3a`; API commit `5c542169b5e6c295805f50fa65df3150816eb443`; tree `1a4d9c9f6d705df44d384002ef70181432bea2c8`; harness `5a981666…`; correctness/floors passed, rank-only rejection | score `2.60664969895906`; prefill `0.000187976888671875` s/token (`2.0102798437644536x`); decode `0.0048906780546875` s/token (`2.8424405431090602x`); peak RAM 21 GB; **n=1** |

The manifests differ, and their harness revisions differ, so these receipts cannot be pooled. The cc6 note describes nineteen earlier official executions of the same executable logic, but each replay changed a source comment nonce. They are different byte payloads under the frozen rule and do not increase cc6's count.

## Exclusions and provenance controls

- API attempts without an archive hash or complete payload manifest were excluded from exact-byte grouping even when their official metrics were complete.
- Failed/incomplete attempts and local or M4 measurements were excluded. No missing metric was imputed and no speedup was reconstructed across sessions.
- Promotion ledgers were not used as a sampling frame because they are outcome-selected.
- Repeated snapshots of one UUID count once. UUID aliases would also count once unless distinct official timing sessions were proven.
- Git trees were used only as supporting provenance after a full submitted-surface manifest was available.
- The historical base object `16e01da840b…` referenced by the census tooling was absent locally, so that ancestry claim is explicitly unverified. The audit does not rely on it.

A fresh in-memory one-byte corruption control independently verified the cc6 manifest pipeline. Flipping byte zero of `Sources/MLXFastModel/LagunaRuntimeModel.swift` changed that file from `c9074bdbe90879e1cfdae4af0c1f57ae5921dfee712ce9102858915d7108cdc0` to `67fe87b6c902c076cda42cbed6e47bde9ad6042ea6351280db6d7db709a14307`, and the complete manifest from `9f28c40a…` to `6a3083e9644f2e3b0ac3412bf119f083cc6bcc93953f341e50169a1f94dd6b8e`. Detection was true; no repository file was modified.

Reproduction: `git log --all --format='%H %s' --grep='^Validate submission '`; hash each `benchmark.json`, expand `editablePaths` with `git ls-tree -r`, read blobs with `git cat-file blob`, and hash the canonical manifest above. Join UUIDs to the frozen API export without filtering status or score.

## Statistical policy and next evidence

The existence test is decisive: `max(n) = 1 < 5`. Computing dispersion from singleton groups would manufacture precision. If an exact identity later reaches five proven independent sessions, report every observation chronologically and compute geometric mean, log-scale sample standard deviation/CV, median, IQR, range, and a clearly caveated 95% t interval for score, prefill, and decode. Any acceptance threshold must be declared before viewing those outcomes.

At least four additional independent timings of one unchanged archive are required. Because ordinary exact-archive resubmission can deduplicate to an existing submission, this should use an authorized official rerun mechanism that preserves the archive hash and exposes distinct timing-session IDs—not nonce edits or repeated UUID snapshots.

## Novelty versus the earlier audit

`ranked-best-payload-gap-audit.md` asked whether the cc6 and e27 ranked-best artifacts were the same payload or semantically equivalent and proved that their manifests differ. This audit asks a different, stricter question: whether **any one exact payload/contract identity has enough independent official M5 executions to estimate run-to-run repeatability**. It freezes eligibility before outcomes, screens the all-attempt API export and reachable validation cohort, groups by cryptographic identity, validates the manifest with an independent corruption control, and applies an explicit `n >= 5` decision rule. The new conclusion is evidence-sufficiency NO-GO, not another payload-difference claim.
