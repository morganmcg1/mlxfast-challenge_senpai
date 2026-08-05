# PR #44 r2 — ranked receipt for `MLX_MAX_MB_PER_BUFFER = 512`

Student: `maple-nezuko`. Assignment `maple-2026-08-05b-mb-per-buffer-50`, revision `r2`.
Base: `1849b376d73f69f9a6b9018619ac665ae4bceb33`.
Submitted surface: `Sources/MLXFastModel/LagunaRuntimeWeights.swift:386`, one token,
`setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)` -> `"512"`. Growth 0 bytes.

## 1. What r2 asked for and what was delivered

| r2 requirement | Delivered |
| --- | --- |
| Submitted diff is one file, one token | Yes: 1 file changed, 1 insertion, 1 deletion |
| Diff ends at reverted `200` or a value shown better | Ends at `512`, chosen from the free M4 counts sweep |
| B1 free M4 counts-only sweep {200,400,512,1024,2048} | Complete, `research/nezuko_mbpb_up_sweep.log` |
| Hard stop if counts flat at 200 | Not triggered: prefill 81 -> 41 cb, decode 34 -> 18 cb/step |
| A2 prereg committed before submitting | Commit `42851d2`, `research/nezuko-mbcap-up-prereg.md` |
| Exactly one ranked receipt at the knee | One submission: `c747336c` |
| Rank on `ns`, never `officialScore` | Yes, see section 5 |

## 2. Why 512 is the knee

All B1 cells: 406 dispatches, 0 divergences, `gpu_busy_sum == gpu_busy_union`,
`peak_ram_gb 20.72`. Command-buffer counts are exact integers and, per the r1
M4 TRANSFER LAW, transfer M4 -> M5 unchanged.

| cap MB | decode cb/step | prefill cb | mlx_peak_gb | M4 gpu_busy decode (ms) | M4 wall decode (ms) | wall-busy gap |
| --- | --- | --- | --- | --- | --- | --- |
| 200 | 34.0 | 81 | 36.39 | 8.335 | 8.599 | 3.1% |
| 400 | 19.0 | 42 | 36.94 | 8.181 | 8.854 | 7.6% |
| **512** | **18.0** | **41** | 36.94 | 8.233 | 8.734 | 5.7% |
| 1024 | 13.0 | 41 | 36.94 | 8.248 | 8.874 | 7.1% |
| 2048 | 9.0 | 41 | 36.94 | 8.271 | 8.915 | 7.2% |

The 200 row reproduces r1's measured M5 counts (34 decode cb/step, 81 prefill cb)
exactly, which is the sweep's internal validity check.

Predicted `ns` gain from the r1-fitted M5 per-cb costs (decode +1.1045 us/cb,
prefill +27.177 us/cb):

| cap MB | predicted d_ns |
| --- | --- |
| 400 | +0.640% |
| **512** | **+0.666%** |
| 1024 | +0.748% |
| 2048 | +0.814% |

Four reasons 512 rather than 2048:

1. 512 is the first cap that reaches the prefill cb floor of 41. That floor
   contributes +0.404% of the +0.666%, i.e. the majority of the effect, and it
   is the part that cannot be recovered by any larger cap.
2. 512 -> 2048 adds only +0.148% predicted, which is about 1 sigma of the
   `ns` repeat noise (cv 0.149%). One receipt cannot separate them, and r2
   permits only one receipt.
3. M4 `gpu_busy` for decode is *minimised at 400* and then rises monotonically
   to 2048. The linear per-cb cost law is fitted at 34 cb/step; 9 cb/step is a
   3.8x extrapolation, and the busy-time trend warns the law breaks down there.
   512 stays inside the fitted regime.
4. 512 restores a value that already exists in the dependency tree, so it is
   the least novel setting that captures the prefill floor. Memory cost is
   +0.55 GB `mlx_peak_gb` on a 128 GB ranked host: not a constraint.

## 3. Correctness and attribution control

`./benchmark.sh --local-iterate` (training `0857f427`): `passed_correctness true`,
`max_abs_diff 0`, golden `b9509697...` matched, `peak_ram_gb 21`, decode
0.013302 s/tok.

`./benchmark.sh --local-submit` (training `2d02e196`, commit `19ef2ac`; later
commits touch only `research/`, so the submitted surface is identical):
`passed true`, `passed_correctness true`, `max_abs_diff 0`, `checked_steps 1025`,
`error ""`, `first_failing_case/layer/step` all null, golden
`f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`,
`peak_ram_gb 21`.

`research/run_upstream_equivalence.sh` returns rc=1 on this host. I did not
report that as a pass. Instead `research/nezuko_equiv_control.sh` replayed a
**single built binary** at caps 200 / 50 / 512 using an environment override
(the env value wins over `setenv(..., 0)`, so there is no rebuild and no
confound between cap and binary):

| cap | prefill max abs logit error | prefill mean | decode steps 1-8 | argmax |
| --- | --- | --- | --- | --- |
| 200 (base) | 0.125 | 0.011933609 | all exactly 0 | 5991 / 509 / 902 |
| 50 (r1) | 0.125 | 0.011933609 | all exactly 0 | 5991 / 509 / 902 |
| 512 (r2) | 0.125 | 0.011933609 | all exactly 0 | 5991 / 509 / 902 |

The three per-cap blocks are byte-identical, md5
`9e46ee364ceaf57dbbab59b28dca78b3`. The divergence is therefore a property of
this host and the unchanged base, not of the cap: M4 Pro reports Apple GPU
generation 16 and does not select the `_nax` prefill kernels the ranked M5 uses.
It is prefill-only; decode is bit-exact. The pre-committed rule branch was
"if all three caps show it, submit and report the control table rather than
claiming a clean equivalence pass" - which is what this section does.

## 4. Pre-registered prediction (committed `42851d2`, before submitting)

`cand_pre` 189.1848 us, `cand_dec` 5.020275 ms, `ns` 2.561436, **d_ns +0.666%**.
Decode ratio 1.0052, prefill ratio 1.0112: both interior to the 0.95 floors and
to the legacy band.

Verdict rule, fixed in advance:

| observed d_ns | verdict | action |
| --- | --- | --- |
| > +0.30% | CONFIRM | keep 512 |
| +0.15% .. +0.30% | WEAK CONFIRM | keep 512, amend slope |
| -0.15% .. +0.15% | NULL | revert to 200 |
| < -0.15% | REFUTE | revert to 200, amend transfer law |

Also pre-registered: with a needed candidate edge of +1.61% for 50% promotion
odds, a +0.666% prediction is about 2.4x short, so **this receipt was expected
to return `rejected` on ranking even if it confirms perfectly**. That is a
statement about the crown, not about the mechanism.

## 5. Ranked result

PENDING
