SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- Student / PR: maple-frieren / #23 (`maple-2026-08-04e-head-latency`, r1)
- Hypothesis and target cost: the ~0.29–0.32 ms exposed decode-step head region
  splits into host work, driver launch latency, and tail idle; if the host part
  is large it is attackable by committing the first command buffer earlier.
- Decision: **dead hypothesis for the head region** (the assignment's stop rule
  fires on measurement), plus one **ambiguous** adjacent finding that is worth a
  follow-up arm.
- `BASE_SHA` / candidate commit: `969fea003eb6964f702c1f7c3e0234d022406a9f` /
  no candidate — nothing was changed on the submitted surface, and **no official
  submission was spent** (3 still unspent).
- Submitted candidate files: none.
- Supporting test or documentation files: `research/frieren-pr23-head-region.md`
  (full memo), `research/frieren_head_region.py` (trace analyser),
  `research/frieren_cb_count_arms.sh`, `research/frieren_cb_mb_sweep.sh`,
  `research/frieren_cb_first_commit.sh`, `research/frieren_cbprof_ranked.sh`.
  Research-only instrumentation commits (`0816a72`, `9529e3a`) are on the branch
  and are **not** part of any scored measurement.

### Evidence

- Host, memory profile, toolchain, thermal policy: AWS M4 Pro, 48 GiB,
  low-memory startup profile by default; the command-buffer arms ran under
  `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` for ranked parity. Direct worker
  probe, no thermal gate needed (no `--local-iterate` pair in the measurement
  set beyond the recorded baseline).
- Exact baseline and candidate commands: in the memo's Reproduction section.
- Tests and risk-based checks run: none required — the submitted surface is
  unchanged. The recorded same-host baseline (`score.local-iterate.baseline.json`,
  commit `7017ba2`) reported `passed_correctness = true`, `max_abs_diff = 0`,
  decode 0.0135023349609375 s/tok, prefill 0.001124003580078125 s/tok, i.e.
  `S = 575.5 ms`, `T = 9.006 ms`.
- Correctness and serial-protocol verdict: unchanged behaviour; both probes are
  read-only timestamp recorders behind default-off env gates. The measured
  invocation computes logits and KV rows only for the single supplied token,
  advances KV position by exactly one, and leaves no pending future token,
  logits, deferred cache row, or cross-request state. No drafting, lookahead,
  prompt-lookup, or multi-row evaluation of an unsupplied token anywhere.
- Peak RAM: the ranked/full startup profile runs on a 48 GiB host (useful
  campaign capability), at a ~3.4 % absolute step-time penalty from its memory
  settings, so only within-profile comparisons are valid.

### Part 1 — the three requested numbers (M4 Pro, medians over 278 steady steps)

| # | Region | µs | se |
| --- | --- | ---: | ---: |
| 1 | step entry → first command-buffer commit (**editable host work**) | **26.0** | 0.3 |
| 2 | first commit → first GPU kernel start (driver + firmware) | **59.1** | 0.6 |
| 3 | tail GPU idle after the model call returns | **4.4** | — |

Plus two terms the same trace exposed: **67.8 µs** of trusted-harness front idle
(IPC + `argMax().item()` readback + watchdog) and **114 µs** of interior GPU idle
spread over 76.8 command-buffer boundaries. Total GPU idle 269.9 µs/step;
GPU busy 8512.3 µs; step 8782.2 µs; GPU busy fraction 96.92 %.

Region 2 sub-split from Metal's own counters: commit → `kernelStartTime` 10.5,
`kernelStartTime` → `kernelEndTime` 25.5, `kernelEndTime` → `GPUStartTime` 30.1.

### Stop rule

Both stop conditions hold: driver launch latency (59.1) dominates the host
portion (26.0), and the host portion is 26 µs — a quarter of the 0.1 ms
threshold. Perfect elimination of every editable head microsecond is 0.30 % of
this host's step and 0.60 % of the 4.353 ms ranked step, i.e. ≈0.3–0.45 % of
score, below the 0.61 % bar before noise. I did not spend a submission on it.

### The ratio argument, made explicit and checked

`predicted M5 step = GPU_busy / r + serial_idle`. Solving
`4353 = 8512.3 / r + 269.9` gives `r = 2.085`, which is exactly the achievable-
bandwidth ratio if the M4 Pro sustains ~240 GB/s of 273 nominal and the M5 Max
~500 GB/s of 614 — inside your 485–530 band. So the measured split reproduces
the ranked step time with no free parameters beyond that ratio, and:

- a serial microsecond removed locally is one microsecond removed on M5;
- as a fraction it is worth `8782.2 / 4353 = 2.02×` more there;
- the whole 269.9 µs serial term is 3.07 % of the local step and **6.20 % of the
  ranked step** — your point, confirmed rather than assumed;
- but only 26.0 of those 269.9 µs are editable host work.

### Scaling-law decomposition

| Term | µs | Scales with | M5 |
| --- | ---: | --- | --- |
| Swift pre-encode bookkeeping | 5.5 | CPU clock/IPC | ~0.85× |
| MLX graph walk + encoder setup, head's 4 ops | ~15 | dispatch count × CPU clock | ~0.85× |
| `commit` (IOKit submit) | ~5 | fixed per-command-buffer OS cost | ~1.0× |
| kernel-driver ingest + submission processing | 36.0 | fixed per-CB driver cost | ~1.0× |
| firmware queue → GPU launch | 30.1 | fixed firmware/hardware latency | ~1.0× |
| trusted IPC + JSON | ~40 | CPU clock, pipe syscalls | ~0.85× |
| `argMax().item()` readback | ~28 | fixed GPU→CPU sync latency | ~1.0× |
| inter-command-buffer GPU bubbles | 114 | **command-buffer count** × ~1.4 µs | scales with CB count |
| post-return drain | 4.4 | CPU clock | ~0.85× |

Only the first two rows scale with CPU clock; only the bubbles scale with
command-buffer structure; the rest are fixed OS, driver, firmware and sync
latencies that neither a faster CPU nor a faster GPU removes. **A term that
scales with dispatch count is 15 µs of a 270 µs serial budget** — which is why
attacking dispatch count could not have worked.

### Reconciliation with #9's exact zero (δ ≤ 1.05 µs/dispatch)

Consistent, and now explained. The worker's encoding thread uses 2.6 ms of CPU
per 8.78 ms step — ~3.3× ahead of the GPU — so after the first commit every
dispatch's encode cost is **hidden**, not exposed. My decomposition attributes
~0 exposed cost per dispatch, well inside your bound. The only unhidden encode
is the head's ~4 ops. And MLX cuts command buffers on **referenced input
volume**, not op count (`device.cpp:562`, `:393-401`), so fusing dispatches
changes neither command-buffer count nor the 114 µs of boundary bubbles. #9's
zero is not evidence that per-dispatch cost is small in principle; it is
evidence that on this path all of it except the head is already hidden behind a
bandwidth-bound GPU.

There is a second, stronger reason, and it is a campaign-level caveat: the byte
volume of one decode step is ≈2.2–2.9 GB, which at 273 GB/s nominal is a
7.9–10.6 ms floor against a measured 8.51 ms GPU-busy region. **This host runs
decode at ~90–100 % of its memory-bandwidth wall.** A launch-overhead change
*cannot* show a win here. That is not evidence it is worthless on the ranked M5,
which has ~2× the achievable bandwidth for the same bytes. I would re-test the
#9 patches on M5 before treating that family as closed.

### Command buffers per ranked decode step

**~50/step, range 40–60.** Inference: the low-memory profile force-sets
128 Mi-elements / 64 ops with `setenv(..., overwrite=1)`
(`RuntimeStartupMemoryPolicy.swift:174-183`) — so an external `MLX_MAX_*` is
silently ignored on any <64 GiB host, which invalidates the obvious env screen
(I burned one 6-arm run finding this out; it became a 6-repeat A/A floor of
sd 0.20 %). The ranked profile sets 200/400 with `overwrite=0`
(`LagunaRuntimeWeights.swift:380-390`). I measured 78 command buffers/step at
the 128 threshold, so referenced volume ≈ 10.0 Gi elements/step and a 200
threshold gives ≈50. The op cap never binds (406 dispatches vs a 400 cap → 2
buffers). This supersedes my earlier "~45/step", which was a low-memory artifact
I had not yet traced.

Correction worth recording: the threshold unit is Mi-**elements**, not MB, and
the bf16 embedding table is exactly **196** — so the first `set_input_array` of a
decode step forces a cut iff `max_mb ≤ 195`. That is why my first command buffer
holds one op and commits at 26 µs, and it means **my front-idle structure does
not transfer 1:1 to the ranked box** at cap 200.

### Adjacent finding: the command-buffer volume threshold

Screened under `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` (ranked parity),
`ops=400`, 2000 steps/arm:

| max_mb | ms/step | n |
| ---: | ---: | ---: |
| 8 | 9.0297 | 2 |
| 16 | 9.0402 | 2 |
| 25 | 9.0196 | 2 |
| **50** | **8.9579 ± 0.0028** | 5 |
| 100 | 9.0442 | 2 |
| 200 (ranked) | 9.0893 ± 0.0318 | 4 |
| 4096 | 9.4137 ± 0.0041 | 3 |

Non-monotone with a minimum at 50 (also MLX's stock M5 Max default, which this
repo raised to 200). `t ≈ 4.1` for 50 vs 200 against a 0.20 % A/A floor. Honest
caveat: the four cap-200 arms are **bimodal** (9.0341/9.0344 vs 9.1423/9.1465,
nothing between); against the faster cluster the gap is 0.85 %.

**But this must not ship as a cap change.** Three isolated ranked receipts in
`research/nezuko-normalised-leaderboard.md` §5.2 change only this cap against a
cap-200 frontier control: 400 → `T +0.056 % / S +0.130 %`; 240 →
`T −0.069 % / S +2.783 %`; 160 → `T −0.838 % / S +1.464 %`. Scoring the 160
receipt end to end gives `1.00496^0.75 × 0.98557^0.25 = 1.0001` — the cap trades
decode against prefill and nets zero. It is read once into a `Device` member at
first device construction and `device.h`/`device.cpp` are outside
`editablePaths`, so it cannot be made phase-dependent from the submission
surface.

The reachable form is decode-only: `decodeFireMask` /
`DARKBLOOM_DECODE_ASYNC_STAGE` already fires `asyncEval` after selected layers
under an `isSingleTokenDecode` guard (`LagunaRuntimeModel.swift:10517`, `:10768`),
and prefill has a separate ladder, so a decode-only boundary change leaves `S`
untouched by construction. That axis is tuned at *layer* granularity (default
`at:0,1,7,15,23,31,39`; notes/52). The open question is whether the residual
`mb=50` win is *sub-layer*.

### Conclusion

- What happened and why: the head region is real but almost entirely not mine.
  26 µs of 270 µs of serial time is editable; 59 µs is driver/firmware launch
  latency and 68 µs is trusted harness. The stop rule fires. The same instrument
  found a larger, differently-shaped term (114 µs at command-buffer boundaries)
  whose blunt knob is score-neutral on the ranked box and whose reachable form
  is a decode-only boundary schedule.
- Evidence for/against the mechanism: for — the bandwidth-scaling identity
  reproduces the ranked step time from the local split with one parameter, and
  the M4 `mb` sweep has the same sign as the ranked cap-160 receipt. Against —
  26 µs is simply too small, and the local host is at its bandwidth wall so it
  cannot measure launch-overhead wins at all.
- Uncertainty / M5 transfer risk: the first-commit structure differs between
  cap 128 (local) and cap 200 (ranked) because of the 196-element embedding
  charge; the cap-200 bimodality is unexplained; and the local bus saturation
  means local nulls on scheduling changes carry little information about M5.
- Smallest useful next action: one arm testing sub-layer decode-only
  `asyncEval` boundaries at cap 200, screened against the running
  `mb50/mb200 × default/ladder1` contrast.
- Recommendation: **close this arm** (head region is a dead hypothesis, stop
  rule satisfied, no submission spent) and open the sub-layer boundary arm.
