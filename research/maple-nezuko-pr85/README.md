# PR #85 artifacts — layer-0 dense MLP lossless BF16 re-encode

Main write-up: `research/maple-nezuko-pr85-dense-mlp-lossless-repack.md`.

**Verdict: NO-GO.** The re-encode is provably lossless (0 mismatching bit
patterns over 50,331,648 weights) and removes 25.14 MB/decode step, but decode
is **+0.905 % slower** (p = 0.0087), a score change of −0.71 % against a
predicted +0.59 %…+0.68 %. The unpack ALU costs ≈ 2.2× the bandwidth it buys.
Not for merge.

## Census

| file | contents |
|---|---|
| `census-value.log` | SANITY, exponent ranges, entropies, `tz` histogram |
| `census-gates.log` | the SANITY → GO-8 → GO-12 → GO-12e → GO-13 → T8 ladder |
| `census-scheme.log` | delta-width sweep `d ∈ {3,4,5}`, block bases, wrong-axis bases |

Script: `research/nezuko_dense_census.py` (`value | gates | axis | block |
scheme | all`). CPU-only, no GPU. Per §0.9.33 every quantity in these logs is
machine-independent and would be bit-identical on the ranked M5.

## Certificate

| file | contents |
|---|---|
| `certificate-run.log` | traced run; `DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_DENSE_PACKED_VERIFY=1` |
| `certificate-run.score.json` | its `score.local-iterate.json` |

The certificate is a pure CPU `memcmp` over all 50,331,648 weights of the three
planes: **0 mismatching BF16 bit patterns**. The decode time in
`certificate-run.score.json` is from a *traced* run and is deliberately
excluded from the timing pool.

## Campaign A — within-binary A/B

One build, no checkout or rebuild between runs; the arms differ only by the
`DARKBLOOM_DENSE_PACKED` environment variable, so the binary is byte-identical
across all 12 slots.

| slot | file | arm | `DARKBLOOM_DENSE_PACKED` |
|---:|---|---|---|
| 1 | `a_01_on.json` | ON | unset |
| 2 | `a_02_off.json` | OFF | `0` |
| 3 | `a_03_off.json` | OFF | `0` |
| 4 | `a_04_on.json` | ON | unset |
| 5 | `a_05_off.json` | OFF | `0` |
| 6 | `a_06_on.json` | ON | unset |
| 7 | `a_07_on.json` | ON | unset |
| 8 | `a_08_off.json` | OFF | `0` |
| 9 | `a_09_on.json` | ON | unset |
| 10 | `a_10_off.json` | OFF | `0` |
| 11 | `a_11_off.json` | OFF | `0` |
| 12 | `a_12_on.json` | ON | unset |

> ⚠ **The polarity in this table is historical.** At campaign time the flag was
> opt-out (`!= "0"`), so ON = unset. After the campaign returned NO-GO the flag
> was inverted to opt-in (`== "1"`) in commit `98c3221`, so that a merged
> negative write-up cannot silently land the measured regression on the
> frontier. This table is left as-run for provenance; to reproduce the arms
> against current `HEAD`, spell ON as `DARKBLOOM_DENSE_PACKED=1` and OFF as
> unset. See §8 of the main report.

**The order is exactly orthogonal to slot position.** ON occupies slots
{1,4,6,7,9,12} summing to 39; OFF occupies {2,3,5,8,10,11} also summing to 39.
Both arms therefore have mean slot 6.5, so arm ⊥ slot and any linear
session drift is estimated independently of the arm effect rather than
contaminating it. The order is also balanced 3/3 within each half and never
runs the same arm more than twice consecutively.

### Provenance note

The `commit` field differs across slots (`2a16e97`, `db3d118`, `5d06a4e`,
`e93b204`, …) because write-up commits were made while the campaign ran.
`git diff --name-only 2a16e97 HEAD` returns **only files under `research/`** —
zero build inputs — so the compiled binary is identical for every slot and the
provenance difference is cosmetic. `analyze.py`'s `check_provenance()` warns on
this rather than failing, and hard-asserts the fields that actually matter
(`golden_hash`, `harness_hash`, `weights_hash`, `runtime`, `num_layers`).

## Analysis

```bash
cd research/maple-nezuko-pr85 && python3 analyze.py a
```

`analyze.py` asserts `passed_correctness`, `max_abs_diff == 0` and
`checked_steps == 130` on every slot, then reports per-arm mean/sd/SE and 95 %
CI, an exact permutation test, a slot-ordered OLS drift fit, the mandatory
§0.9.32 **A/A null control** built from balanced 3-vs-3 splits within each arm,
`peak_ram_gb`, and the M4 → M5 → score conversion. Its captured output is
`analysis-a.txt`.

The prefill null channel did not come back flat (−1.01 %, p = 0.026), so
`covariate.py` re-tests the decode effect controlling for it:

```bash
cd research/maple-nezuko-pr85 && python3 covariate.py
```

It reports the within-run Pearson `r(decode, prefill)`, the OLS slope
`d(decode)/d(prefill)`, and a prefill-adjusted decode effect with its own exact
permutation test. Captured output is `covariate-a.txt`. Result: `r = −0.156`
rules out a shared see-saw, and **87 % of the regression survives adjustment**
(+0.786 %, p = 0.0152), so the prefill anomaly does not explain the decode
result. §6.4 of the write-up discusses this.

| file | contents |
|---|---|
| `analysis-a.txt` | `analyze.py a` output — headline effect, permutation test, A/A null |
| `covariate-a.txt` | `covariate.py` output — prefill-adjusted decode effect |

## Ranked dispatch

`ranked-dispatch-58e28b8d.md` records the Step 0 dispatch of the merged
frontier (#72 + #81), the Step 0b scope/budget re-check, and the channel
collision with the PR #80 reallocation.
