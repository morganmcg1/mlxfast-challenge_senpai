# M4→M5 transfer calibration

**Verdict: NO-GO.** The committed evidence cannot estimate whether the proposed
M4 gate predicts an official M5 win better than either the current heuristic or
submitting without M4 screening.

## Provenance and scope

- Repository / PR: `morganmcg1/mlxfast-challenge_senpai` #653
- Required base: `f7cf412e910a8f937f13b25828ca9b952ecf20f6`
- Assignment head: `1f6f747765005b5e125f931e672ade82bb77ee8a`
- Result commit: recorded by the typed submission; a Git commit cannot embed its
  own final SHA without changing that SHA.
- Deliverables are analysis-only under `research/`. No production, vendor,
  generated, contract, test, harness, or workflow file was changed.
- No build, model benchmark, official submission, W&B query, receipt API query,
  or unrelated PR/branch inspection was performed.

The checked-in top-15 replication report identifies the final host as M4 Pro
48 GB. That supersedes the stale M4 Max 128 GB host field in `candidates.json`.
All evidence below is therefore treated as M4 Pro evidence.

## Frozen decision rule

The rule was fixed before assigning any official outcome as a validation label.
A row is eligible only when it has:

1. exact candidate/control SHAs, PR, receipt IDs, mechanism family, changed
   bytes, and scored-path reach;
2. a transferable kernel family (not NAX-only, threadgroup/SIMD ownership,
   split-K, or a sub-0.1% geometry claim);
3. exactness/equivalence passes;
4. isolated M4 ABBA and BAAB results whose conservative projected decode
   speedup is at least `1.001`, with positive effects in both orders;
5. mirrored full-model M4 intervals with conservative weighted speedup at least
   `1.001` and prefill/decode lower bounds at least `0.95`; and
6. an official M5 paired candidate/control receipt exposing correctness, phase
   speedups, and weighted score.

The prediction is the binary eligibility gate. Precision uses an exact
one-sided 80% Clopper-Pearson lower bound. Validation is leave-one-mechanism-
family-out, with chronological fallback when a family has fewer than two rows.
A GO requires at least five independent eligible pairs across three families,
held-out precision LCB at least `0.60`, and observed precision at least `0.10`
above both comparators:

- **Current heuristic:** isolated M4 lower-bound projection >=0.1% plus
  reverse-order stability, without the full transfer/provenance gate.
- **No M4:** submit every otherwise admissible candidate.

The event is an exact mechanism's official M5 weighted speedup versus its actual
parent of at least `1.001`, with correctness and both component floors passing.

## Evidence inventory and result

| Quantity | Observed | Required |
|---|---:|---:|
| Promoted snapshots inspected | 15 | — |
| Same-fresh-M4-cohort actual-parent marginals | 6 | — |
| Strictly eligible M4/M5 pairs | **0** | **5** |
| Eligible mechanism families | **0** | **3** |
| Proposed held-out precision / LCB80 | N/A | LCB >=0.60 |
| Current-heuristic precision | N/A | comparator |
| No-M4 precision | N/A | comparator |

None of the 15 promoted snapshots combines isolated ABBA+BAAB intervals,
mirrored full-model M4 intervals, and an exact mechanism-matched paired M5
candidate/control receipt. Nine also lack a same-cohort M4 measurement of the
actual parent. The reported official score changes are cross-receipt,
cumulative-frontier exploratory labels, not paired causal outcomes.

For context only, the six same-cohort M4 marginals and subsequent official
frontier deltas were:

| Rank | M4 marginal | exploratory M5 delta |
|---:|---:|---:|
| 112 | +1.0373% | +1.1678% |
| 113 | +1.0944% | +1.2647% |
| 114 | -0.1411% | +0.1546% |
| 117 | +4.1554% | +3.1997% |
| 125 | -0.2629% | +0.0505% |
| 126 | -7.2750% | +0.1216% |

This table is deliberately not scored: it is selected on promoted outcomes,
mixes mechanisms and controls, and includes a strong geometry sign reversal.
Its 13/15 >=0.1% event prevalence is likewise outcome-selected and cannot be
used as no-M4 precision.

## Required negative audit

- #637 `1f2980f`: vector-realization ABBA `0.999451845`; no BAAB/full/M5.
- #638 `b9d75bb`: load-sharing ABBA/BAAB projected decode `0.980922443`; no
  full/M5.
- #641 `1237c64`: vector-realization ABBA `0.999549789`; no BAAB/full/M5.
- #643 `84d8c61`: load-sharing ABBA CI crossed parity and BAAB was negative
  (`0.996736`); no full/M5.

All four are correctly rejected by the frozen gate and supply no M5 labels.
Receipt `e27f…` remains a no-rerun case: committed metadata records clean
correctness but weighted regression `-0.3766%`; it is not converted into a new
experiment or treated as a mechanism-matched pair.

## Minimum evidence needed to revisit NO-GO

Collect at least five independent candidate/control pairs from at least three
mechanism families, including negatives rather than only promoted candidates.
For each pair preserve exact SHAs/PR/receipt IDs/bytes/reach, isolated M4
ABBA+BAAB intervals, mirrored full-model M4 phase intervals, exactness evidence,
and the exact official M5 paired phase ratios, correctness, score, and terminal
status. Then execute the frozen leave-family-out validation and comparator
analysis unchanged.

## Reproduction and integrity

Machine-readable data:
`research/m4-m5-transfer-calibration.json`

Dataset SHA-256:
`4394d737ef087171c643e87016ecd0fabae773375e7833332fe8c636c1910843`

```bash
python3 -m json.tool research/m4-m5-transfer-calibration.json >/dev/null
shasum -a 256 research/m4-m5-transfer-calibration.json
git diff --name-only f7cf412e910a8f937f13b25828ca9b952ecf20f6...HEAD
```

The dataset records SHA-256 hashes for every committed source and explicitly
marks GitHub beyond #653, W&B, and external receipts as N/A. Runtime and peak
memory are N/A because the assignment prohibited execution.

_This report was prepared by an OpenHands AI agent on behalf of the assigned
research student._
