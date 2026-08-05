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

## 5. Ranked result — one receipt, `c747336`

| field | value |
| --- | --- |
| receipt id | `c747336c-2f0b-4870-8481-faccaeafe99f` (short `c747336`) |
| runner commit | `cc4b1dc77d59c4a55cffdabab0fee68e2071e22f` |
| status | `rejected` (ranking only; see gates below) |
| `cand_pre` | **197.093424 us** |
| `cand_dec` | **5.0752060 ms** |
| computed `ns` | **2.514736** |
| control `ns` (`c3ce66e`) | 2.544360 |
| **d_ns** | **-1.1643%** |
| `officialScore` | 2.51665710865438 |
| `draw = officialScore / ns` | **1.000764** |
| paired-baseline prefill | 385.178873 us, **96.8th percentile** (z = +1.777; feed mean 372.375 us, sd 7.205 us, n = 1035) |
| paired-baseline decode | 13.895972 ms |
| `max_abs_diff` | **0** |
| `passed_correctness` | **true**, `error` empty, `case_count` 11, `checked_steps` 1344 |
| `first_failing_case/layer/step` | all null |
| decode floor | `decode_speedup` 2.7380, floor 0.95, `passed_decode_speedup_floor` **true** |
| prefill floor | `prefill_speedup` 1.9543, floor 0.95, `passed_prefill_speedup_floor` **true** |
| semantic GPQA | **passed true**, 9/9 cases, judge `claude-opus-4-8` |
| GPQA TTFT | **passed true**, 9/9 cases, p50 0.078 s, max 2.4 s, reported 0.41 s, source `hidden_gpqa_first_token` |
| peak RAM | 21 GB (`process_resident_memory_gb` 0.11) |
| golden hash | `be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71` |
| harness hash | `e53be436efca8dcf09d28aed87dbbedb53bab82a5d788760c64530a94d57e727` |
| submitted (UTC) | 2026-08-05T14:12:43.108Z (local record 14:12:35Z) |
| runner timestamp (UTC) | 2026-08-05T14:23:02Z |
| released (UTC) | 2026-08-05T14:34:20.825Z |
| wall / timed / correctness seconds | 47 / 40 / 36 |

Hand-computed legacy acceptance band (ratio = control time / candidate time):

| axis | ratio | band | verdict |
| --- | --- | --- | --- |
| decode | 0.994332 | [0.980, 1.053] | INSIDE |
| prefill | 0.970646 | [0.952, 1.053] | INSIDE |

So every correctness gate and both hard 0.95 floors passed, and the legacy band
would also have passed. `rejected` here means only that 2.516657 did not beat the
current best 2.552308.

### Verdict: REFUTE

d_ns = **-1.1643%**, well below the pre-registered -0.15% REFUTE threshold and
7.9 sigma from the predicted +0.666% (sigma = 0.149%). Pre-registered action
taken: **reverted to `200`**, and the transfer law is amended in section 6.

### Why ranking on `ns` mattered here

| receipt | `cand_pre` us | `cand_dec` ms | `ns` | d_ns | `officialScore` | gap on score | baseline pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `c3ce66e` control 200 | 191.308 | 5.04644 | 2.544361 | - | 2.52327586 | - | 54.0% |
| `3e6fdcb` r1 cap 50 | 195.503 | 5.11955 | 2.503448 | -1.608% | 2.49387730 | -1.165% | 88.6% |
| `c747336` r2 cap 512 | 197.093 | 5.07521 | 2.514736 | **-1.164%** | 2.51665711 | **-0.262%** | **96.8%** |

`c747336` drew the 96.8th-percentile baseline, worth +0.908% of lottery. On
`officialScore` alone the arm looks nearly neutral at -0.262%; the code is in
fact -1.164% slower. The script's independent decomposition gives candidate
-1.171% + baseline +0.908% = -0.262%, and the candidate term agrees with d_ns to
0.007 pp. This is the third consecutive receipt where `ns` is baseline-independent
and `officialScore` is not.

Pre-registered promotion-odds statement held: bootstrap P(beat 2.552308) = 0.0%,
and the receipt did return `rejected`. That was recorded before submitting.

## 6. Amended transfer law and mechanism

The r1 law said: command-buffer *counts* transfer M4 -> M5 exactly; boundary
*timing* does not, not even in sign. Clause 1 survived - the cap-200 sweep row
reproduced the ranked M5's 34 decode cb/step and 81 prefill cb exactly. Clause 2
was over-applied. Amended:

1. **Counts transfer exactly.** Unchanged, and re-confirmed.
2. **Per-command-buffer cost is not a constant and must not be extrapolated
   across caps.** The +1.1045 us/cb decode and +27.177 us/cb prefill costs were
   fitted on 200 vs 50, i.e. by *adding* buffers. Extrapolating to *removing*
   buffers inverted the sign of the prefill term:

   | axis | predicted | observed |
   | --- | --- | --- |
   | prefill S (512 tokens) | -1.087 ms (-40 cb x 27.177 us) | **+2.9621 ms** |
   | decode T (marginal step) | -0.0177 ms (-16 cb x 1.1045 us) | **+0.0056 ms** (flat) |

   Prefill moved 2.7x the predicted magnitude in the opposite direction; decode
   did not move at all despite losing 16 of 34 buffers per step. The submit
   overhead a buffer costs is therefore not the dominant term once buffers are
   large.
3. **The transferable timing proxy is the M4 `wall - gpu_busy` gap, not M4 wall
   time and not the count.** That gap is non-overlapped CPU encode/submit time,
   a CPU-side property, so it survives the Apple GPU generation change that
   `_nax` kernel selection does not. It was already in the B1 table and it
   already ranked 200 first:

   | cap MB | gap | M4 wall decode |
   | --- | --- | --- |
   | **200** | **3.1%** | **8.599 ms (best)** |
   | 400 | 7.6% | 8.854 ms |
   | 512 | 5.7% | 8.734 ms |
   | 1024 | 7.1% | 8.874 ms |
   | 2048 | 7.2% | 8.915 ms |

   I discarded this at selection time as untrustworthy boundary timing, on the
   strength of clause 2. That was the error. Raising the cap raises the gap,
   which is the mechanism: bigger command buffers mean the GPU cannot start
   until more encoding is done, so overlap is lost faster than submit overhead
   is saved.
4. **200 is a genuine two-sided local optimum on the ranked M5.** Moving down
   costs -1.608% (`3e6fdcb`, cap 50); moving up costs -1.164% (`c747336`,
   cap 512). Two ranked receipts bracket it. **This knob is closed** - no further
   receipts should be spent on `MLX_MAX_MB_PER_BUFFER`.

Corollary for future work: a candidate that reduces command-buffer count is only
promising if it *also* keeps the encode/submit work overlapped. Fusion that
shortens the encode stream qualifies; merely enlarging the buffer that holds the
same encode stream does not.

## 7. Final state of the branch

Per the pre-registered REFUTE action the arm is reverted, so the submitted
surface diff against base `1849b376` is **empty**. Everything retained is under
`research/`:

- `research/nezuko-mbcap-up-prereg.md` - prereg, committed `42851d2` before submitting
- `research/nezuko_mbpb_up_sweep.log` - B1 free M4 counts sweep
- `research/nezuko_mbcap_predict.py` - `ns` predictor and conversion slopes
- `research/nezuko_equiv_control.sh` / `.log` - three-cap single-binary attribution control
- `research/nezuko_r2_gates.sh` / `.log` - gate driver
- `research/receipt_baseline_lottery.py` - baseline-lottery decomposition
- `research/nezuko-mbcap-up-submission-note.md` - public note attached to `c747336`
- this file

## 8. Suggested follow-ups (not implemented)

1. Take the next assignment as written: `oproj_act_h64/h48` fusion with the
   attention epilogue (`LagunaRuntimeModel.swift:5893-5905`, `:5989-5995`),
   14.30% of the decode step, ratio 0.601. It shortens the encode stream rather
   than enlarging the buffer, so it is on the right side of the corollary above.
2. Adopt the M4 `wall - gpu_busy` gap as a standing free pre-screen for any
   dispatch-shape candidate. It cost nothing here and it had the right answer.
3. The +0.518% baseline lottery on every `officialScore` is larger than most
   single-mechanism effects. Consider making `ns` the campaign's reported
   ranking statistic and `officialScore` a secondary field.
