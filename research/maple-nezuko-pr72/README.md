# PR #72 raw timing snapshots

Every file is a verbatim `score.local-iterate.json` produced by
`./benchmark.sh --local-iterate` on the AWS Mac M4 Pro research host
(`applegpu_g16s`, 48 GiB, low-memory startup profile). Each one carries its own
`metrics.commit`, so arm identity is recoverable from the artifact itself and
does not depend on the filename.

Analysis and interpretation live in
`research/maple-nezuko-pr72-group32-scale-census.md` (§8.3). The
pre-registration written before the first timed run is
`research/maple-nezuko-pr72-preregistration.md`.

## Campaign A — old base `00374ba`, base-first, 4 base / 3 candidate

Base arm is the temporary revert fixture `6563bb2`; candidate is `c844df3`.

| slot | file | arm |
| ---: | --- | --- |
| 1 | `base_r1.json` | base |
| 2 | `cand_r1.json` | candidate |
| 3 | `base_r2.json` | base |
| 4 | `cand_r2.json` | candidate |
| 5 | `base_r3.json` | base |
| 6 | `cand_r3.json` | candidate |
| 7 | `base_r4.json` | base |

`cand_trace.json` was run with `DARKBLOOM_TRACE_FUSION=1` and is **excluded**
from the timing pool; the tracer costs the same order as the effect.

## Campaign B — new base `ab1f9a1`, counterbalanced C B B C B C, 3 / 3

Base arm is the unchanged advisor base checked out detached at `ab1f9a1`;
candidate is the rebased `41d4ede`.

| slot | file | arm |
| ---: | --- | --- |
| 1 | `newbase_cand_r1.json` | candidate |
| 2 | `newbase_base_r1.json` | base |
| 3 | `newbase_base_r2.json` | base |
| 4 | `newbase_cand_r2.json` | candidate |
| 5 | `newbase_base_r3.json` | base |
| 6 | `newbase_cand_r3.json` | candidate |

`newbase_cand_trace.json` is the traced run and is likewise **excluded**.

## Scripts

```bash
python3 analyze.py newbase   # campaign B: means, SE, 95 % CI, permutation test
python3 analyze.py ""        # campaign A
python3 drift.py newbase     # campaign B slot-ordered OLS + adjacent-pair
python3 drift.py oldbase     # campaign A, same two estimators
```

`analyze.py` asserts `passed_correctness` and `max_abs_diff == 0` on every file
it loads, so a silently-degraded replicate cannot enter a mean. Both scripts
read the JSONs from their own directory.

Both report the **reduction** convention `(base − cand) / base`. The report
uses the same convention throughout; the alternative `base / cand − 1` differs
by at most 0.02 pp at these magnitudes.

The `decode_speedup` / `prefill_speedup` fields inside these files compare
against a pinned **M5** calibration and are meaningless on this host. Only
same-host paired `seconds_per_token` is used anywhere in the analysis.
