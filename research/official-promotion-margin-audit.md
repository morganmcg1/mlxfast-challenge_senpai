# Official promotion-margin audit

**Status: `PROMOTION_MARGIN_PROVEN`**

This is a deterministic static audit of the frozen cc6 and terminal e27 records. It made no production edit and ran no build, inference, timing, W&B, live receipt, or official operation. Sources are the assignment's frozen values, `research/official-m5-repeatability-audit.md`, `research/ranked-best-payload-gap-audit.json`, `research/submitted_surface_reclamation_manifest.json`, and the required-base Git objects. The exact machine output is `research/official-promotion-margin-audit.json`; `research/official_promotion_margin_audit.py` reproduces it.

## 1. Complete payload-identity gate

At required base `ac0e7cf6f283c8ac655af955d7ccf57c5141185e`, the calculator:

1. reads that commit's `benchmark.json` and all 97 `editablePaths`;
2. expands every path through the commit tree, reads every blob, and records sorted `(path, size, sha256)` tuples;
3. independently normalizes all e27 records from both frozen manifests;
4. compares every record, count, total byte count, contract digest, and canonical full-manifest digest.

Results:

- contract SHA-256: `e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6`
- expanded files: **142**
- total bytes: **2,984,121**
- required-base, gap-audit, and reclamation manifest SHA-256: `2622b4de40b12f19fb696755425819b3c5faf7dfc300ac9d2ca7f9e2f9575230`
- first difference: `null`

Thus the required-base submitted surface is exactly terminal e27's complete payload, not merely a matching shortlist. Any missing or different input makes the calculator emit `INDETERMINATE` and the first difference.

## 2. Score reproduction

The official formula is

\[
S=d^{0.75}p^{0.25}.
\]

Python `Decimal` uses precision 80 and `ROUND_HALF_EVEN`. A reproduction passes only when computed and published scores round identically to 12 significant decimal digits.

| Record | Decode `d` | Prefill `p` | Computed score | Published score | Rounded computed/published | Gate |
|---|---:|---:|---:|---:|---:|---|
| cc6 | 2.8409180802229947 | 2.0441331295729355 | 2.6165035438145613471 | 2.61650354381456 | 2.61650354381 / 2.61650354381 | PASS |
| e27 | 2.8424405431090602 | 2.0102798437644536 | 2.6066496989590594354 | 2.60664969895906 | 2.60664969896 / 2.60664969896 | PASS |

Absolute differences from the printed official scores are `1.3471057283922438490e-15` and `5.6460031268706140879e-16`, respectively.

## 3. Exact promotion boundary

The weighted incremental multiplier that ties cc6 from exact e27 is

\[
R=\frac{2.61650354381456}{2.60664969895906}
 = 1.0037802719941367788.
\]

This is a **0.37802719941367788428%** weighted improvement. A candidate on the exact e27 payload must strictly exceed `R`; equality is only the algebraic tie boundary. Both component speedups must also remain at least `0.95`, and all correctness gates still apply.

With the other phase unchanged:

- decode-only factor: `R^(1/0.75) = 1.0050435356522653763`; from e27's `0.0048906780546875` s/token this saves `24.542528017515222157` microseconds/token;
- prefill-only factor: `R^(1/0.25) = 1.0152070470061098753`; from e27's `0.000187976888671875` s/token this saves `2.8157540774815781529` microseconds/token, or `1.4416660876705680143` ms per 512-token pass.

The general tie frontier for incremental factors `(x_d,x_p)` is

\[
0.75\ln x_d + 0.25\ln x_p = \ln R.
\]

## 4. Mixed log-margin frontier

The share columns allocate `ln(R)` between decode and prefill. All rows reproduce the cc6 tie score and pass both component floors. Savings are relative to e27; `P512` is prefill milliseconds per 512-token pass.

| D% | P% | D factor | P factor | D speedup | P speedup | D us/tok | P us/tok | P512 ms | Score | Floors |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 100 | 1 | 1.01520704700611 | 2.84244054310906 | 2.04085026384401 | 0 | 2.815754077482 | 1.441666087671 | 2.61650354381456 | PASS |
| 25 | 75 | 1.00125850616253 | 1.01138374137327 | 2.84601777204918 | 2.03316434959377 | 6.147212166371 | 2.115794625972 | 1.083286848498 | 2.61650354381456 | PASS |
| 50 | 50 | 1.00251859616282 | 1.00757483444462 | 2.84959950295397 | 2.02550738076833 | 12.286697752297 | 1.413189137350 | 0.723552838323 | 2.61650354381456 | PASS |
| 75 | 25 | 1.00378027199414 | 1.00378027199414 | 2.85318574148917 | 2.01787924835821 | 18.418466469505 | 0.707927608878 | 0.362458935745 | 2.61650354381456 | PASS |
| 100 | 0 | 1.00504353565227 | 1 | 2.85677649332768 | 2.01027984376445 | 24.542528017515 | 0 | 0 | 2.61650354381456 | PASS |

## 5. Generic 1.001 screening gate

Applying exactly `1.001` to e27 gives `2.6092563486580190600`, still below cc6. The remaining factor to the tie is `1.0027774944996371417`, or `0.27774944996371417011%`.

Therefore `1.001` remains only a generic local screening condition. The deterministic official margin must be considered alongside candidate-specific local, full-model, and ranked-M5 evidence. This arithmetic provides no M4-to-M5 transfer factor and does not predict an official result.

## 6. Positive controls and decision rule

All controls fail the affected gate as intended:

- swapping exponents computes `2.1921246008594486618`, which fails the 12-significant-digit e27 score check;
- changing one e27 decode digit to `2.8424406431090602` computes `2.6066497677375346919`, which fails that check;
- changing one SHA digit in the first manifest record identifies index 0, `Sources/MLXFastModel/DenseTensorStore.swift`, and changes the manifest digest to `2e2b03b6fc372226522a048c7cf7e73aa12a0307ec074a75f1c1cacc912f8b72`.

For any future candidate inheriting the exact e27 surface: require a ranked-M5 weighted incremental multiplier strictly greater than `1.0037802719941367788`, both official component floors, and every correctness gate. Frontier rows are tie boundaries, not forecasts.

cc6 and terminal e27 must never be retried, rerun, resubmitted, or mutated.

PROMOTION_MARGIN_PROVEN
