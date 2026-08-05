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

   Prefill moved 2.7x the predicted magnitude in the opposite direction; the
   *marginal* decode step did not move at all despite losing 16 of 34 buffers
   per step (see section 9, critique 4, for why the reported `cand_dec` still
   moved +0.570%). The submit overhead a buffer costs is therefore not the
   dominant term once buffers are large.

   **Corollary, added in r3:** the fitted rates +1.1045 us/cb decode and
   +27.177 us/cb prefill are valid **only downward from the shipped cap**, the
   direction in which they were measured. They must never be quoted above it.
   The one time I extrapolated the prefill rate upward it was wrong in sign and
   2.7x in magnitude, which is the whole content of this clause.
3. **HYPOTHESIS (on trial in r3, not yet a law): the transferable timing proxy
   is the M4 `wall - gpu_busy_union` gap, not M4 wall time and not the count.**
   That gap is non-overlapped CPU encode/submit time, a CPU-side property, so
   it *should* survive the Apple GPU generation change that `_nax` kernel
   selection does not. It was already in the B1 table and it already ranked 200
   first:

   | cap MB | gap | M4 wall decode |
   | --- | --- | --- |
   | **200** | **3.1%** | **8.599 ms (best)** |
   | 400 | 7.6% | 8.854 ms |
   | 512 | 5.7% | 8.734 ms |
   | 1024 | 7.1% | 8.874 ms |
   | 2048 | 7.2% | 8.915 ms |

   I discarded this at selection time as untrustworthy boundary timing, on the
   strength of clause 2. That was the error: whatever else is true, the gap
   would have told me not to submit 512.

   The **proposed mechanism** is that bigger command buffers mean the GPU cannot
   start until more encoding is done, so overlap is lost faster than submit
   overhead is saved. In r2 I stated that as fact. It is a hypothesis, and
   section 10 shows it already fails its own quantitative test on the data I
   had. Section 10 also names the measurement that would settle it and reports
   the 400 MB arm as an open anomaly.

   **Why this cannot be promoted on the r2 evidence.** The gap was only ever
   compared with M4 wall *upward* from 200, where the two agree, so agreement
   there carries no information about the branch where M4 wall is known to be
   wrong. r3 therefore extends the profiled sweep downward under a rule
   committed in advance (`research/nezuko-mbcap-down-prereg.md`, commit
   `b16dea5`); the verdict is in section 11.
4. **200 is a genuine two-sided local optimum on the ranked M5.** Moving down
   costs -1.608% (`3e6fdcb`, cap 50); moving up costs -1.164% (`c747336`,
   cap 512). Two ranked receipts bracket it. **This knob is closed** - no further
   receipts should be spent on `MLX_MAX_MB_PER_BUFFER`.

5. **The `ns` exchange rates are closed-form identities, not fits.** Adopted as
   programme law: rank on `ns`, never on `officialScore`. The two conversion
   slopes are exact consequences of the score definition at this operating
   point, which is why the advisor's independent check reproduced them to
   +-0.03%:

   ```
   cand_dec = (S + 128 T) / 128            cand_pre = S / 512

   d_ns/dT = 0.75 / cand_dec
           = 0.75 / 5.04644 ms                              = 14.862 %/ms
   d_ns/dS = 0.25 / S            +  0.75 / (128 x cand_dec)
           = 0.25 / 97.950 ms    +  0.75 / (128 x 5.04644 ms) = 0.371 %/ms
   ```

   T is the marginal per-step decode time and S is the 512-token prefill seed.
   S carries **two** terms because it is billed twice: once on the prefill axis
   (weight 0.25, over S = 97.950 ms) and again inside `cand_dec`, which is
   `(S + 128 T) / 128`, on the decode axis (weight 0.75). The decode term is
   0.0011611 %/ms and the prefill term is 0.0025523 %/ms, so **31.3% of any
   prefill regression is charged to the decode axis**. That single fact is what
   critique 4 in section 9 is about.

Corollary for future work, adopted verbatim by the advisor: a candidate that
reduces command-buffer count is only promising if it *also* keeps the
encode/submit work overlapped. Fusion that shortens the encode stream qualifies;
merely enlarging the buffer that holds the same encode stream does not.

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
2. ~~Adopt the M4 `wall - gpu_busy` gap as a standing free pre-screen for any
   dispatch-shape candidate.~~ **Withdrawn in r3 pending section 11.** "It had
   the right answer" was only ever checked where it could not be wrong.
3. The +0.518% baseline lottery on every `officialScore` is larger than most
   single-mechanism effects. Consider making `ns` the campaign's reported
   ranking statistic and `officialScore` a secondary field.

---

# PR #44 r3 — accepted critiques and the falsification test

r3 takes **no ranked receipt**; the single shared channel belongs to tanjiro's
PR #47. Everything below is free M4 work or arithmetic on receipts already
taken. Base accepted for r3 is advisor `1732770`; the `editablePaths`
intersection with this branch is empty (only `research/CURRENT_RESEARCH_STATE.md`
and `research/GATHER_GEMM_REGIME_DESIGN.md` moved), so no rebase and no
re-measurement were required.

## 9. Advisor critiques accepted (deliverable B)

### Critique 4 — "decode is flat" was true of the mechanism and misleading as a report

My r2 clause 2 table says the marginal decode step moved **+0.0056 ms (flat)**.
That number is correct. The problem is that the receipt's own `cand_dec` moved
**+0.570%**, and a reader comparing the two would reasonably conclude either
that the table is wrong or that decode absorbed real damage from the cap change.
Neither is true. The +0.570% is almost entirely the prefill seed leaking into
the decode axis through the `S/128` term of `cand_dec = (S + 128 T) / 128`:

| term | control `c3ce66e` | candidate `c747336` | delta |
| --- | --- | --- | --- |
| `cand_dec` | 5.04644 ms | 5.07521 ms | **+0.02877 ms** (+0.570%) |
| seed share `S/128` | 0.76523 ms | 0.78837 ms | **+0.02314 ms** (80.4% of it) |
| marginal step `T` | 4.28121 ms | 4.28684 ms | **+0.00563 ms** (19.6%) |

`S` is recovered independently from the other axis, `cand_pre x 512`: 191.308 us
x 512 = 97.950 ms and 197.093 us x 512 = 100.912 ms, so `dS = +2.9621 ms`, which
is exactly the prefill regression in clause 2 and exactly `128 x 0.02314 ms`. The
decomposition is therefore not fitted; it closes on the two reported fields.

Correct attribution of the whole -1.1643% using the section-6 clause-5
identities:

| source | delta | rate | contribution to `ns` |
| --- | --- | --- | --- |
| prefill seed `S` | +2.9621 ms | 0.371 %/ms | **-1.099%** |
| marginal decode `T` | +0.00563 ms | 14.862 %/ms | **-0.084%** |
| predicted total | | | **-1.183%** |
| measured `d_ns` | | | **-1.164%** |

Residual 0.019 pp: the two mechanisms account for 98.4% of the loss.

**What I got wrong, stated plainly.** I wrote "decode did not move at all" in a
section whose purpose was to explain a decode-weighted regression. The mechanism
of this arm is a **prefill-only** regression; 31.3% of it is billed to the decode
axis by the score definition, and that transfer, not any decode-path change, is
what turned a +3.02% prefill regression into a -1.16% score regression. The r2
wording invited exactly the wrong causal reading.

**Standing rule adopted from this.** Never report a `cand_dec` delta as a decode
result. Always split it into `S/128` and marginal `T` first, using
`cand_pre x 512` for `S`. A prefill-mechanism arm will otherwise present as a
decode-mechanism arm, and the 0.75 weight will make it look like a much bigger
one.

### Critique 2 — profiled and unprofiled numbers are not comparable, and I pooled them

Three M4 measurements of the *same* cap-200 code exist:

| source | binary | steady steps | wall/step |
| --- | --- | --- | --- |
| r1 unprofiled ABBA (`research/nezuko-mbpb-levels.log`) | shipped | 199 | **8.876 ms** |
| r1 profiled (`research/nezuko-mbpb-profile.log`) | GPUPROF | 199 | **8.614 ms** |
| r2 profiled (`research/nezuko_mbpb_up_sweep.log`) | GPUPROF | 99 | **8.599 ms** |

The two profiled sessions agree to **0.17%**. The profiled/unprofiled pair
differs by **3.2%** — larger than every arm effect in this entire experiment,
and, counter-intuitively, with the *profiled* binary faster. I do not have an
established cause. The GPUPROF path adds a completion handler and a locked
`fmt::format` per command buffer, which plausibly perturbs submit scheduling;
the two numbers also come from different sessions and thermal states. Those two
candidate causes are not separated by any data I have, and I am not going to
guess between them.

The consequence is what matters and it is not in doubt:

1. A profiled arm may only ever be compared with another profiled arm from the
   **same session and same binary**. r3's sweep is therefore one build, one
   process recipe, one session, warm-up arm discarded.
2. No profiled absolute time may be quoted as an M4 wall time or fed into an
   `ns` prediction. The +1.1045 us/cb and +27.177 us/cb rates in clause 2 came
   from the *unprofiled* r1 ABBA and stay attached to it.
3. Counts (`cbs`, `dispatches`) are the only quantities shown to be stable
   across the profiled/unprofiled boundary, and clause 1 rests on counts alone.
   That is why clause 1 survived and clause 3 is on trial.

Where r2 placed profiled and unprofiled numbers in adjacent tables without
flagging it, that was an error of presentation that could have become an error
of inference. The r3 sweep design makes it structurally impossible.

## 10. Clause 3's mechanism already fails its own test (deliverable C)

Clause 3's proposed mechanism — the GPU cannot start a command buffer until more
of it is encoded — makes a sharp quantitative prediction. If the non-overlapped
time per step is one buffer's worth of encode latency, and the total encode work
per step `E` is set by the graph rather than by the cap, then

```
gap ~ E / n_cb        =>        gap x n_cb ~ E = constant across caps
```

On the r2 profiled upward session it is not remotely constant:

| cap MB | gap ms | cb/step | `gap x n_cb` ms | `gpu_busy_union` ms | wall ms |
| --- | --- | --- | --- | --- | --- |
| **200** | 0.265 | 34 | **9.01** | 8.335 | **8.599** |
| 400 | 0.673 | 19 | **12.79** | **8.181** | **8.854** |
| 512 | 0.501 | 18 | **9.02** | 8.233 | 8.734 |
| 1024 | 0.626 | 13 | **8.19** | 8.248 | 8.874 |
| 2048 | 0.644 | 9 | **5.77** | 8.271 | 8.915 |

The product spans 5.77 to 12.79 ms, a factor of **2.2**, and it is
**non-monotone**: it rises from 200 to 400, then falls through 2048. A constant-`E`
law is rejected by its own data. So even in the region where the gap ranks the
caps correctly, the reason I gave for *why* it does is wrong. The direction of
the gap and the mechanism I attached to it are separate claims, and r2 shipped
them as one.

### The 400 MB anomaly, unexplained

400 MB is the worst arm by wall time (8.854 ms) while simultaneously holding the
**lowest `gpu_busy_union` of any cap measured** (8.181 ms, below the 8.335 ms of
the winning 200). It also has the largest gap (0.673 ms) and the largest
`gap x n_cb` (12.79 ms), and it is not on a monotone path to either neighbour:
512 has *fewer* buffers (18 vs 19) and a *smaller* gap (0.501 vs 0.673).

I cannot account for this. Options I can neither confirm nor exclude from the
data I have: a single-replicate outlier (n = 1 per level in that session); an
allocator or residency effect at the 400 MB block size specifically, which would
be consistent with `mlx_peak_gb` stepping from 36.39 at 200 to 36.88-36.94 at
every cap above it; or a scheduling interaction that shortens total GPU work
while lengthening its critical path. Recording it as open is the honest position,
and it is a second, independent reason not to promote clause 3 on r2's evidence:
the arm that most strongly drives "the gap ranks caps correctly" is also the arm
I understand least.

### The named discriminator

The measurement that separates the two live explanations is the
**per-command-buffer GPU idle-interval distribution** — the set
`{start[i+1] - end[i]}` over consecutive command buffers inside the steady decode
window, not merely its sum, which is all `gap` reports.

| explanation | prediction on the distribution |
| --- | --- |
| `H_encode` (clause 3): every boundary waits on encode | extra idle is **spread**: mean idle per boundary rises with cap, top-decile share of total idle stays roughly flat |
| `H_stall`: a few long stalls not tied to boundaries | mean idle per boundary may even **fall**, while top-decile and top-percentile shares of total idle rise sharply and `max` idle grows super-linearly |

`H_encode` additionally requires `gap x n_cb` to be flat, which the table above
rejects, so the prior favours `H_stall` or a mixture. This is free to run:
`DARKBLOOM_GPU_PROFILE=1` already emits one GPUPROF record per command buffer
with GPU start and end on the mach absolute epoch, and the r2 upward session's
worker stderr files are still on disk. `research/nezuko_cb_idle.py` computes it;
results are in section 11. Only *inter*-buffer idle is observable at `SPLIT=0`;
intra-buffer idle would need `SPLIT=1`, which inflates absolute time and is
attribution-only.

