# Local Amdahl Realization Audit

## Terminal decision

**NO-GO.** The frozen historical cohort contains **0 eligible mechanism clusters across 0 eligible families**, below the predeclared decision-use minimum of **8 mechanisms across 4 families**. Fourteen mechanisms across nine families were screened. Because no mechanism passes every frozen rule, this audit does not estimate, pool, or recommend an empirical local-to-whole-model realization factor.

- Assignment: `cedar-fern-local-amdahl-realization-audit-20260810` revision `r2-evidence-closure`
- Assignment base: `60ce7f20abb31a7ec775396822fb988d19ea732c`
- PR: #666
- Primary metric: eligible mechanism clusters, observed `0`, required `8`
- Family gate: eligible families, observed `0`, required `4`

The hypothesis that the campaign's historical evidence can support a decision-useful empirical realization factor is therefore **not established**. This is an evidence-identifiability failure, not evidence that realization is zero.

## Scope and evidence universe

The evidence universe was frozen before applying eligibility rules. It consists only of the current advisor branch and campaign-assigned PR evidence in the complete archive returned for `base:codex/mlxfast-cedar-20260804-advisor`. Deterministic extraction finds **262 PR sections and exactly 274 `senpai-result:v1` envelopes**: 254 PRs contain at least one result and eight contain none. The earlier prose count of 279 results is withdrawn because it cannot be reproduced from the frozen bytes.

The archive disposition is exhaustive: 14 screened PRs (#336, #353, #354, #434, #480, #491, #517, #602, #611, #613, #621, #628, #633, and #640), five active exclusions (#658, #659, #661, #662, and #665), and 243 other omissions, totaling 262. `research/local_amdahl_realization_archive_index.json` records every PR's section digest, result count and result identities, diagnostic flags, disposition, and explicit reason. Variants are clustered by mechanism unless they were predeclared independent. No M5 result or different-architecture result was reconstructed from M4 evidence.

The actual available bytes are content-addressed:

```text
source archive: SHA-256 b13377e52bc7fc5496cffe00e9dc87e5d66a23a0dbedae21d4f316ad281d507f (4,600,212 bytes)
committed index: SHA-256 dde91d675d71f4e5358002cc2612d03152358334027541d141e7d287b766e009
```

The validator recomputes both digests from bytes when the controller-state archive is available and regenerates the complete index for equality. The 16 separately referenced PR #517 repeat score/integrity artifacts are not available as matching standalone bytes in this checkout; their recorded digests remain metadata and are explicitly **unverified**, not promoted to verified evidence. The full artifact inventory is in `research/local_amdahl_realization_cohort.json`.

## Frozen eligibility rules

A mechanism is eligible only when every condition below is true. The machine-readable representation expands these into ten booleans so each failure is explicit.

1. Exactness was established before timing, and the isolated and whole-model evidence is linked to the same candidate SHA and configuration.
2. The isolated measurement preserves a complete causal chain and the exact scored call count.
3. A complete order-controlled isolated block preserves raw or reconstructable base and candidate times in a canonical unit, plus saving uncertainty.
4. The whole-model measurement uses the same candidate/base, hardware, fixture, timing window, component definition, and thermal protocol.
5. Both complete whole-model ABBA and BAAB orderings are present. A first-negative hard stop is censored and is never converted into a numeric result.
6. M5 or other-architecture effects are not reconstructed from M4 observations.
7. Variants are clustered unless they were predeclared as independent mechanisms.

Decision-use further requires at least eight eligible mechanism clusters across at least four families. If either gate fails, numeric realization-factor work stops after the ledger.

## Evidence semantics

Three evidence classes are kept separate:

- **Observed:** values explicitly preserved in campaign PR evidence or imported raw artifacts.
- **Censored:** a required phase or ordering that stopped or was never measured. Censored evidence is never assigned a numeric result.
- **Derived control:** arithmetic recomputed from preserved rows solely to validate the audit machinery. Derived controls are not empirical realization-factor estimates.

In particular, a whole-model speedup does not identify observed realization `O/P` unless the corresponding isolated evidence identifies projected whole-model saving `P` from absolute, order-controlled base and candidate times with uncertainty.

## Frozen cohort ledger

| PR | Mechanism | Family | Isolated evidence | Whole-model evidence | First exclusion |
|---:|---|---|---|---|---|
| #336 | LM-head two-row coarse reuse | `lm_head` | 48/48 exact; AB/BA ratios 1.036566725x/1.043477396x | Paired summary only; no complete matrices | Rule 2: exact scored call count missing; absolute isolated pair also absent |
| #353 | Retained BF16 router weights | `dispatch_materialization` | Strong ratio; no absolute pair | One A→B weighted speedup 1.004586111606x | Rule 3: absolute isolated pair missing |
| #354 | Launch descriptor reuse | `dispatch_materialization` | 5.15x/5.03x ratios; no exact count or absolute pair | One A→B weighted speedup 1.0003750671x | Rule 2: exact scored call count missing |
| #434 | OProj residual folding | `attention_projection` | Approximately 2–3%; no absolute pair or exact count | AB/BA 1.000591x/0.996637x, not matrices | Rule 2: exact scored call count missing |
| #480 | Pruned top-8 router | `router` | Medians 14.679487/14.522436 µs; isolated ABBA 1.009887x and BAAB 1.011287x with CIs; 257 blocks/order × 39 dispatches | One A→B weighted speedup 0.994155307x; reverse stopped | Rule 5: complete whole ABBA+BAAB absent; reverse is censored |
| #491 | Terminal-gated OProj reuse | `attention_projection` | One hit/512-token forward, zero decode hits; tail ratios 1.026–1.041x | AB/BA 1.0054886x/1.0039994x, not matrices | Rule 3: absolute isolated pair missing |
| #517 | Word-aligned scale decoder | `moe_scale_representation` | Four seven-sample aggregate gain vectors reported in `us/token`; medians 17,641.3, 17,647.8, 17,793.3, and 17,856.3 µs/decode-token; exact 4,864 compact + 128 fallback scored calls, but no absolute endpoints or isolated-loop operation normalizer | Two complete ABBA+BAAB matrices; all arms 130 checked steps, max absolute diff 0; repeat pooled decode/prefill/composite 1.004189x/1.000753x/1.003329x | Rule 3: an admissible absolute per-call saving and projected `P` are not identifiable |
| #602 | Shared-expert RMS/output fusion | `moe_fusion` | Aggregate AB/BA 1.015652x/1.014735x; raw rows and uncertainty absent | AB/BA 0.999696057x/0.995461689x, not matrices | Rule 3: reconstructable isolated block missing |
| #611 | Sorted MoE tail/RMS handoff | `moe_fusion` | 38 exact boundaries; approximately 1.0922x, no absolute pair | Complete ABBA weighted 1.004762086700x; BAAB stopped | Rule 3: absolute isolated pair missing; BAAB is censored |
| #613 | Packed shared expert | `moe_scale_representation` | Ratios 1.014916x, 1.022637x, 1.019450x, 1.015177x; aggregate old/packed decode 0.126354208/0.124332313 s | Complete ABBA retained; no BAAB | Rule 3: raw isolated rows and uncertainty missing |
| #621 | Full-attention params carrier | `attention_metadata` | 1,270 dispatches, 127 constructions, 1,143 reuses; about 5.4 µs/decode-step, no uncertainty | Directional screen only | Rule 3: isolated saving uncertainty missing |
| #628 | Packed routed-expert RHS offsets | `moe_metadata` | Exact 4,992 calls; isolated ABBA 1.027462x and BAAB 1.026999x with CIs, but no absolute pair | Complete ABBA weighted 0.999172162x; BAAB stopped | Rule 3: absolute isolated pair missing; whole BAAB is censored |
| #633 | Packed scale LUT | `moe_scale_representation` | Exact 4,992 calls; isolated direction only | Not measured; source returned to base | Rule 3: absolute isolated pair missing; rule 4 also fails |
| #640 | Prefill shared-expert fusion | `prefill_moe_fusion` | Exact 38 calls; ABBA saving 0.000368125 s and BAAB 0.0003568225 s with CIs | Not measured | Rule 4: no whole-model measurement |

### Why the near-complete case is still ineligible

PR #517 is the only screened mechanism with complete whole-model ABBA and BAAB matrices, matched identities, exact call census, exactness, and integrity evidence. Its four surviving isolated vectors are labelled `us/token`; they are aggregate reported gains per decode token, not absolute per-call timings. The scored-path census establishes 39 calls per token (38 compact plus one fallback), but the artifact does not retain absolute base/candidate endpoints or the isolated loop's operation-count normalizer that would prove how a vector sample maps to one scored call. Dividing an aggregate gain by 39 would therefore impose an unverified denominator rather than recover an observed absolute per-call saving. Consequently projected Amdahl saving `P` and realization `O/P` remain unidentified. Treating the whole-model 1.003329x composite as a realization factor would silently substitute outcome for realization and violate the frozen design.

## Deterministic controls

Run:

```bash
python3 research/validate_local_amdahl_realization_audit.py \
  --archive "$SENPAI_OPENHANDS_STATE_DIR/github/pull-requests-844db61edd851eedb7a0.md"
```

The validator performs all of the following:

1. Parses the source bytes and requires exactly 262 PR sections, 274 structured results, and exhaustive dispositions of 14 screened + 5 active + 243 omitted. It regenerates the committed index and requires byte-derived equality.
2. Recomputes three weighted whole-model arithmetic examples from preserved ordered rows:
   - PR #517 repeat ABBA: `1.003061264611x`
   - PR #517 repeat BAAB: `1.003605072138x`
   - PR #613 full ABBA: `0.993993354413x`
3. Exercises a synthetic positive control with known projected saving, observed saving, family, and realization. It recovers realization `0.8` exactly from `0.0008 / 0.001`.
4. Recomputes SHA-256 from actual bytes for the committed index and available source archive. It reports the 16 unavailable PR #517 artifacts as unverified; digest strings alone never count as verification.
5. Confirms eight declared negative controls fail closed:
   - duplicate mechanism row;
   - swapped time units;
   - omitted full-order metadata;
   - altered candidate SHA;
   - missing archive PR section;
   - mismatched archive result coverage;
   - real committed-index byte digest mismatch;
   - source-archive byte digest mismatch.
6. Recomputes the terminal gate as `eligible_clusters=0/8` and `eligible_families=0/4`.

These derived values validate ingestion, arithmetic, identity, units, ordering, clustering, and fail-closed behavior. They are not entered into an empirical realization distribution.

## Result and interpretation

The audit identifies a recurring archival gap: mechanisms often retain either strong isolated ratios or directional whole-model results, but not the complete join needed to estimate local-to-whole realization. Several otherwise useful experiments stop at the first negative full ordering; those stops are correctly represented as censored. Others preserve ratios without absolute local base/candidate times, preventing reconstruction of projected wall-time saving.

The resulting cohort is:

```text
screened mechanisms:        14
screened families:           9
eligible mechanism clusters: 0  (required: 8)
eligible families:           0  (required: 4)
terminal verdict:       NO-GO
```

No numeric factor, interval, family stratification, or recommendation is justified from this cohort. The correct campaign action is to preserve the distinction between “no identifiable estimate” and “estimated zero realization.”

## Reproduction and resource accounting

- Reproduction command: `python3 research/validate_local_amdahl_realization_audit.py --archive "$SENPAI_OPENHANDS_STATE_DIR/github/pull-requests-844db61edd851eedb7a0.md"`
- Without the external archive bytes, the validator still checks the committed index but explicitly reports the source archive unverified.
- W&B: not applicable; this is a historical metadata audit and launches no experiment.
- Current-run runtime: not applicable beyond a short standard-library validator invocation.
- Current-run peak model memory: not applicable; no model was loaded.
- Historical PR #517's reported 21 GB peak RAM is source evidence only, not resource usage by this audit.

## Scope and submission-surface proof

This work creates or updates only:

- `research/local_amdahl_realization_audit.md`
- `research/local_amdahl_realization_archive_index.json`
- `research/local_amdahl_realization_cohort.json`
- `research/validate_local_amdahl_realization_audit.py`

The verification step intersects changed paths with `benchmark.json`'s `editablePaths` and requires the intersection to be empty. No submitted Swift/Metal source, benchmark contract, timing gate, receipt, workflow, model artifact, or submission surface is changed. No build, model timing, inference, GPU run, official submission, or receipt operation was performed.

## Recommended follow-up

Before repeating this audit, standardize one immutable evidence bundle per candidate mechanism containing:

1. exact candidate/base SHA and configuration identity shared by isolated and whole-model phases;
2. exactness and scored call census before timing;
3. raw isolated base/candidate rows, canonical units, explicit order, and saving uncertainty;
4. complete whole-model ABBA and BAAB matrices under the same fixture, window, component, hardware, and thermal protocol; and
5. explicit censored markers for hard stops rather than inferred numeric values.

After at least eight mechanism clusters across four families satisfy that bundle, rerun the same frozen validator and only then fit an empirical local-to-whole realization model.
