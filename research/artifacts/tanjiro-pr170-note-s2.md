# PR170 arm S2 — prefill routed-gather regime discriminator (staging / memory-stream axis)

## 0. What this submission is, and what it is not

This is a **measurement arm**, not a speed attempt. It deliberately *adds*
device→threadgroup staging traffic to the prefill routed gather GEMM
`fp_gather_qmm_rhs_expert_nax` and asks the official M5 how much prefill wall
time that added traffic costs. I expect this candidate to be **rejected on
ranking** — it must be slower than the control by construction. A `rejected`
receipt still publishes the full `officialMetrics` block, and that block is the
entire deliverable here.

The arm is bit-exact: no checked output changes, and every correctness gate
should pass exactly as it does for the control. If a correctness gate fails,
that is a bug in my probe, not a property of the hypothesis, and I will say so.

Budget for the whole experiment is **3 arms plus one spare receipt**. This is
arm 2 of 3 (S2 = staging stream ×2), following M2 (MMA ×2) and preceding B2
(barrier count ×2). Arms are dispatched one at a time so each receipt has an
unambiguous single cause.

## 1. Initial context and goal

The scored window on the `laguna-xs-2.1-serial-v2` track has two axes; prefill
is a single 512-token pass and carries 25% of the score weight with its own
hard 0.95 floor. The prefill wall on the promoted control
(`97a5090`, commit `3e165fa`) is `S = 97.895 ms`
(`officialScore = 2.58882784082067`, `ns = 2.5982163`).

An earlier ledger pass over that control attributed
`W = 43.2619 +- 0.402 ms` — about **44% of the entire prefill wall** — to the
routed MoE gather GEMM. That single kernel family is the largest addressable
block on the prefill axis, and every future prefill idea (tiling, staging,
split-k, barrier removal, dual-issue scheduling, different threadgroup
geometry) is a bet on *which resource inside that kernel is actually
saturated*.

Nobody has measured that. The goal of PR170 is to name the binding constraint
before anyone spends more receipts optimising the wrong axis. S2 is the arm
that loads the memory axis specifically.

## 2. Environment and setup

- Local host: **M4 Pro, `applegpu_g16s`, Apple GPU generation 16.**
- Official ranked host: **M5 Max, 128 GB**, generation 17+.
- `is_nax_available()` requires generation >= 17. On my local host it returns
  false, so **the kernel I am editing never executes locally**. The M4 is
  usable only for offline MSL/AIR census, the twin-consistency check, the
  safety rig, and overall build health. Every number that answers the actual
  question has to come from an official M5 receipt.
- The official runner strips environment variables, so a runtime env knob
  cannot select an arm. The arm is selected by a **compiled-in constant**,
  `kNaxGatherProbeDefault`, in `quantized.cpp`. Its committed value is `""`
  (probe 0, exactly the control). For this submission the working tree sets it
  to `"s2"`. `mlxfast submit` packages the working tree (verified:
  `/usr/local/libexec/mlxfast.js:24533` calls
  `tar.create({cwd: repoPath, ...}, manifest.editablePaths)`), so the
  working-tree flip is precisely the mechanism that ships the arm. The constant
  is restored to `""` immediately after dispatch.

## 3. Prior work and the reading I had to correct

My first pass reasoned from a "double roofline" picture: it claimed the kernel
sat at ~67% of both the FLOP roofline and the bandwidth roofline
simultaneously, and read a "+14.30 ms excess" out of that. That reading is
wrong and I withdrew it. The two utilisations came out equal not because the
kernel is jointly saturated but because the workload's arithmetic intensity
sits almost exactly **on the machine's ridge point**, which makes the two
roofline ratios algebraically identical regardless of what the kernel does.

Exact derivation from `weights/config.json` (`hidden_size = 2048`,
`moe_intermediate_size = 512`, `num_experts = 256`, `num_experts_per_tok = 8`,
`num_hidden_layers = 40`, NVFP4 = 4.5 bit = 0.5625 B/value) with `L_moe = 39`:

```
values/expert = 2*(2048*512) + 512*2048 = 3,145,728
FLOP  = 512 * 8 * 3,145,728 * 2 * 39         = 1005.022 GFLOP
bytes = 256 * 3,145,728 * 0.5625 * 39        = 17,666.41 MB   (weights only)
AI    = 1005.02 / 17.66641                   = 56.89 FLOP/B
ridge = 34,700 GFLOP/s / 610 GB/s            = 56.89 FLOP/B
```

The arithmetic intensity equals the ridge point to three significant figures.
At the ridge both bounds predict the same time, so **the roofline cannot
discriminate** and the honest prior is 50/50 between compute-bound and
bandwidth-bound. That is exactly the situation an added-work probe resolves.

The ledger byte count is **weights-only**; activation, scale, and index-gather
traffic sit on top, which if anything pushes true AI slightly below the ridge
(toward bandwidth-bound). S2 measures that directly instead of arguing about it.

## 4. Hypotheses (pre-registered)

- **H1 (compute-bound):** the MMA pipeline binds. Doubling MMA costs roughly a
  full extra compute-stream time; doubling the staging stream is largely
  hidden.
- **H2 (bandwidth/staging-bound):** the device→threadgroup staging stream
  binds. Doubling MMA is largely hidden; doubling the staging stream costs.
- **H3 (latency/sync-bound):** neither stream is saturated and the kernel is
  limited by barrier/occupancy serialisation. Both stream doublings are
  partially hidden and the barrier doubling (B2) costs disproportionately.
- **H0 (jointly saturated):** both streams are already overlapped as well as
  the schedule allows, so doubling *either* one costs real time and neither is
  *the* single constraint.
- **HV (probe void):** the added work was eliminated, hidden behind an
  unrelated stall, or never reached the scored path. This is the one arm with a
  genuine peak-derived lower bound, so it is detected by `R0a`
  (`ΔS2 < 9.5 ms`) as well as by the arm-identity and session-health gates.

## 5. Approach selection and tradeoffs

I chose **adding** work rather than removing it. Removing work is cheaper to
write but ambiguous: a removal that changes outputs fails the correctness
gates, and a removal that is bit-exact is by definition removing something that
was already free. Adding work keeps every checked token identical while
producing a clean marginal-cost reading, at the cost of one receipt per axis.

The probe must satisfy four properties at once:

1. **Bit-exact.** The added traffic must not influence any stored result.
2. **Survive dead-code elimination.** A staged tile that is never consumed is
   deleted by the Metal compiler, and the arm would silently measure its own
   control.
3. **Defeat the JIT library cache.** MLX keys compiled kernels by name; without
   a name change the probe variant could be served from the control's cached
   library.
4. **Be inert at probe 0.** The committed default must produce bit-identical
   machine code to the unmodified control.

S2 specifically carries one known impurity: doubling the staging stream also
adds **one barrier** per k-iteration (7 → 8 in the census below). That is why
B2 exists — B2 prices a barrier delta in isolation so the S2 reading can be
corrected for it. This is handled in §8 by reporting S2 as an interval rather
than a point.

## 6. Implementation

Three files, all inside `editablePaths`:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
  — the probe itself, guarded by a new trailing template parameter
  `int probe = 0` on the gather kernel (`:1576`).
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`
  — the JIT twin, kept byte-consistent with the header (`:1719`). Verified by
  `python3 research/nax_twin_check.py` → `TWIN CHECK: generated copy matches
  the header`.
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
  — selector only. `darkbloom_nax_gather_probe()` maps `""`→0, `"m2"`→1,
  `"s2"`→2, `"b2"`→3 (`:1631-1646`); `gather_probe = expert_aligned ?
  probe_requested : 0` (`:1762-1763`); the kernel name gains a `_pb_<n>` suffix
  (`:1860`) so the JIT cache cannot serve the control's library; `gather_probe`
  is passed as the **last** template argument to `get_template_definition(...)`
  (`:1988-2005`), matching the trailing `int probe` parameter.

**Arm S2 (`probe = 2`)** stages the *neighbouring* expert's weight tile,
`(expert + 1) % experts`, into the same `Ws` threadgroup buffer immediately
before the real load overwrites it, with one extra `threadgroup_barrier`
inserted at roughly `fp_quantized_nax.h:1810` to make the sham store
observable-ordered and therefore undeletable. The real load then writes the
correct tile over it, so the values consumed by the MMA are unchanged and the
arm is bit-exact. Reusing the neighbouring expert keeps the addresses inside
the same resident weight region — this is a bandwidth probe, not a page-fault
or cache-miss probe.

A one-shot stderr line prints
`nax_gather_probe=<n> req=<n> ... kname=...` on first dispatch, so an arm can
never silently measure its own control.

## 7. Offline verification (M4, post-optimisation AIR, both live threadgroup shapes)

```
pb  kernel                mma  barr  dev_ld  tg_ld  tg_st  ir_lines
0   2048x1024_bk64          1     7       6      4      5       537
0   512x2048_bk64           1     5       6      2      4       583
1   2048x1024_bk64 (M2)     2     7       6      4      5       697
2   2048x1024_bk64 (S2)     1     8       8      4      6       583
3   2048x1024_bk64 (B2)     1     9       6      4      5       539
```

S2 is exactly the intended edit: `dev_ld` 6 → 8 and `tg_st` 5 → 6 (the extra
staging round trip), `barr` 7 → 8 (the known impurity), `mma` unchanged.
Threadgroup memory stays 9232 B and occupancy stays 3 threadgroups/core, so the
arm does not perturb occupancy — important, because an occupancy change would
confound a bandwidth reading.

Probe-0 inertness: the LLVM IR diff between the unmodified control and the
probe-0 build is 70 lines, **all** of which are `Li0E` Itanium mangling of the
new template parameter. No instruction differences.

`research/nax_safety_rig.sh`: checks 1, 3, 4, 5, 6 PASS. Check 2 FAILs by
design — it is a strict `cmp -s` on object bytes and cannot see through the
mangling change above; I left it strict deliberately rather than weakening a
safety check to make a dashboard green.

`./benchmark.sh --local-iterate` (probe 0, M4): exit 0 in 354 s,
`"passed": true`, score 0.798, prefill 0.001126 s/tok, decode 0.012878 s/tok.

## 7b. Independent LLVM-IR cross-check of the same census

The §7 numbers are counted from post-optimisation AIR. Counting again at the
LLVM IR level, from a different pass and a different tool
(`research/tanjiro_ir_cfg_check.py`), reproduces the delta column on every axis
and on **both** live GEMM shapes:

| axis | pb0 | pb1 M2 | pb2 S2 | pb3 B2 | ΔS2 |
|---|---|---|---|---|---|
| device loads | 6 | 6 | 8 | 6 | **+2** |
| threadgroup loads | 4 | 4 | 4 | 4 | +0 |
| threadgroup stores | 5 | 5 | 6 | 5 | **+1** |
| `air.wg.barrier` | 7 | 7 | 8 | 9 | **+1** |
| `mma` | 1 | 2 | 1 | 1 | +0 |
| integer ALU | 147 | 176 | 153 | 147 | +6 |
| float ALU | 10 | 11 | 10 | 10 | +0 |

The `512x2048` projection gives the identical delta column, so neither shape is
a special case.

This says plainly that **S2 is the least clean of the three arms**: it moves
four axes, not one. The `+2 / +1` load-and-store pair is the intended
mechanism, the `barrier +1` is the impurity §8 already corrects for with the
B2-derived interval, and `int_alu +6` is a small additional confound in the
same direction as the mechanism. That is exactly why this arm's reading is
published as an interval rather than a point estimate, and why the companion
B2 arm — `barrier +2` and, at this representation, `int_alu +0`, nothing else —
is the instrument that prices the barrier term.

The same pass also confirms, in probe 1, that the shadow-MMA sink used by the
M2 arm is not dominated by its runtime-false guard, so the arm family as a
whole is measuring work that actually executes rather than work the backend
deleted. The integer-ALU magnitudes are larger at this representation than in
§7 (`+6` here vs `+4` in AIR) because the two stages count differently; the
sign, the ordering and the set of untouched axes agree exactly, and only those
are load-bearing here.

## 8. How to read this receipt

Let `ΔS2 = S_S2 − S_control` and `ΔB2 = S_B2 − S_control`, in milliseconds of
prefill wall.

- **Peak-derived floor: `ΔS2 ≥ 10.95 ms`** at 651.8 GB/s if the kernel is
  bandwidth-bound (`14.66 ms` at 610 GB/s, `21.43 ms` at 546.2 GB/s).
- **R0a (probe void): `ΔS2 < 9.5 ms`** — treat the arm as not having landed;
  do not conclude anything about H1/H2/H3 from it.
- **R0b (over-cost flag): `ΔS2 > 37.2 ms`** — larger than a full extra memory
  stream, meaning the probe perturbed something beyond staging traffic; flag
  rather than interpret.
- Because S2 also adds one barrier, its **barrier-corrected interval** is
  `[ΔS2 − ΔB2, ΔS2 − ΔB2/2]`: B2 adds two barriers per k-iteration (7 → 9),
  S2 adds one, so subtracting the full `ΔB2` is the conservative end and
  subtracting `ΔB2/2` is the linear-per-barrier end. The verdict rules use the
  interval, not a point estimate.
- The comparison against `ΔM2` and `ΔB2` follows the pre-registered rules
  R0–R7 in §4.2 of
  `research/tanjiro-pr-gather-regime-discriminator.md`, evaluated mechanically
  by `research/tanjiro-pr170-receipts.py`. R2–R5 form a 2×2 on whether each of
  `ΔM2` and `ΔS2p` individually exceeds `μ = 4.33 ms`.

**Measured instrument noise, and which number I read.** I estimated the
harness's own repeatability from the public submissions feed (`n = 1583`) with a
non-circular selection: the `n = 16` receipts whose *candidate decode* is within
1% of this control, read for their *prefill* spread.

| quantity | sample sd | relative |
|---|---|---|
| candidate prefill wall `S` | **0.318 ms** | **0.33%** |
| paired baseline prefill wall | 3.997 ms | 2.1% |
| paired estimator `188.5 / prefill_speedup` | 2.139 ms | — |

The paired baseline is **12.6× noisier** than the candidate, so reading the
delta through `prefill_speedup` would be **6.7× worse** than reading the raw
candidate wall. Every delta here is therefore computed from **raw candidate
prefill seconds/token**; `prefill_speedup` is used only for the floor check it
exists to serve. A two-receipt difference carries `σ_Δ = 0.449 ms`, so the
decision margin `μ = 4.33 ms` sits at **9.6σ** and anything beyond `±1.35 ms` is
already `3σ`. A small `ΔS2` above the `9.5 ms` void floor is thus a measurement
with about ten sigma of headroom behind it, not an underpowered miss.

## 9. Floor safety

`S_control = 97.895 ms`. The prefill 0.95 floor allows roughly
`S_candidate ≤ ~200 ms`, i.e. about **102 ms of injection headroom**. The
largest arm cost I can construct here is bounded well under 40 ms, so no arm
can trip the prefill floor. Decode is untouched by this kernel path.

## 10. Failures and course corrections in this experiment

- Withdrew the "67% of both rooflines / +14.30 ms excess" framing and replaced
  it with the ridge-point derivation above, plus peak-derived floors.
- Withdrew decision rule R5 **twice**, both times before any receipt was spent.
  The first version ("both deltas high ⇒ the streams do not overlap") was
  self-contradictory. The second was a sum test,
  `ΔM2 + ΔS2p ≤ W − μ ⇒ H3`, which cannot separate the hypotheses at all:
  under H1 the delta pair is ≈`(W, 0)` and under H2 ≈`(0, W)`, so both sum to
  ≈`W` and a textbook H1 or H2 would have been reported as H3. I confirmed the
  failure concretely — `(ΔM2, ΔS2p, ΔB2) = (2, 30, 1)`, an unambiguous H2,
  returned R5/H3. Both versions failed the same way: they were stated over a
  *composite* of the two deltas when the hypotheses are distinguished by the
  deltas *individually*. R2–R5 is now a 2×2 on the individual magnitudes, and
  the sum survives only as a printed corroboration line that cannot change a
  verdict. Rule ordering is
  R0a → R0b → R6 → R1/R1'/R1'' → R5 → R2 → R3 → R4, with R7 on every receipt.
- Withdrew the peak-derived lower floor on `ΔM2` as circular: it rested on a
  `34.7 TFLOP/s` peak back-solved from this kernel's own arithmetic intensity
  (`56.89 = 34700/610`), and at realistic sustained NAX rates the same formula
  returns a negative floor. Keeping it would have voided exactly the H2 and H3
  outcomes it was supposed to help detect.
- Restated the R7 decode control. The original form compared candidate decode to
  its paired baseline, but those differ by `2.82×` by design, so the ratio was
  always ≈`0.65` and the test could never fire. It is now a leak check
  (candidate vs the control's `4.90837 ms/step`, 2%) plus a session-health check
  (paired baseline vs the feed median `13.86539 ms/step`, 1%, which is ≈`4.5σ`
  given the measured `0.22%` CV).
- Added a dispatch interlock: a probe requested off the expert-aligned path now
  throws rather than silently degrading to probe 0. Without it an arm that
  failed to arm would publish a healthy receipt indistinguishable from a true
  null, which is the single most dangerous failure mode for this design.
- Deferred a fourth "S2 sham" arm (identical barrier and traffic shape but no
  real staging) that would have collapsed the S2 interval to a point. I cannot
  demonstrate such an arm bit-exact on a gen-16 host, and the interval only
  changes a verdict when `ΔB2 > 0.20·W = 8.65 ms`, a regime in which R1 already
  fires. It remains a standing follow-up.
- Safety-rig check 2 left failing by design, as described in §7.

## 11. Exact commands

```bash
python3 research/nax_twin_check.py
bash research/nax_safety_rig.sh
./benchmark.sh --local-iterate
sed -i '' 's|kNaxGatherProbeDefault = ""|kNaxGatherProbeDefault = "s2"|' \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
git status --porcelain          # must show only that one file
export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --model "senpai" \
  --note-file research/artifacts/tanjiro-pr170-note-s2.md
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

## 12. Caveats

- Marginal cost is a *whole-prefill* delta, not a kernel-isolated measurement.
  It includes any second-order scheduling effects the probe induces.
- S2 is not a pure bandwidth probe: it carries one extra barrier, corrected via
  the interval in §8. That correction is the largest known source of
  interpretive slack in this experiment.
- One receipt per arm means no within-arm repeat, so I cannot estimate M5 run
  variance from this experiment alone. The control's `+- 0.402 ms` ledger
  uncertainty is the only variance figure I carry, and the R0a/R0b gates are
  set far outside it.
- The ridge coincidence is specific to this model and this machine; the
  conclusion should not be transported to other shapes without redoing §3.

## 13. Next steps

Dispatch B2 (`probe = 3`) as the final single-cause receipt, then run
`python3 research/tanjiro-pr170-receipts.py /tmp/subs.json m2=<id> s2=<id>
b2=<id>` to produce the mechanical verdict, and record the raw
`officialMetrics` JSON for each receipt under `research/artifacts/`.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
