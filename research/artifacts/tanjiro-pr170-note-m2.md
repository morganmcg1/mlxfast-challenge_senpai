# PR170 arm M2 — prefill routed-gather regime discriminator (MMA / compute axis)

## 0. What this submission is, and what it is not

This is a **measurement arm**, not a speed attempt. It deliberately *adds*
arithmetic work to the prefill routed gather GEMM
`fp_gather_qmm_rhs_expert_nax` and asks the official M5 how much prefill wall
time that added work costs. I expect this candidate to be **rejected on
ranking** — it must be slower than the control by construction. A `rejected`
receipt still publishes the full `officialMetrics` block, and that block is the
entire deliverable here.

The arm is bit-exact: no checked output changes, and every correctness gate
should pass exactly as it does for the control. If a correctness gate fails,
that is a bug in my probe, not a property of the hypothesis, and I will say so.

Budget for the whole experiment is **3 arms plus one spare receipt**. This is
arm 1 of 3 (M2 = MMA×2). Arms S2 (shared/threadgroup-memory stream ×2) and B2
(barrier count ×2) follow, dispatched one at a time so each receipt has an
unambiguous single cause.

## 1. Initial context and goal

The scored window on the `laguna-xs-2.1-serial-v2` track has two axes; prefill
is a single 512-token pass and carries 25% of the score weight with its own
hard 0.95 floor. The prefill wall on the promoted control
(`97a5090`, commit `3e165fa`) is `S = 97.895 ms`
(`officialScore = 2.58882784082067`, `ns = 2.5982163`).

An earlier ledger pass over that control attributed
`W = 43.2619 +- 0.402 ms` — about **44% of the entire prefill wall** — to the
routed MoE gather GEMM, i.e. to `fp_gather_qmm_rhs_expert_nax`. That single
kernel family is therefore the largest addressable block on the prefill axis,
and every future prefill idea (tiling, staging, split-k, barrier removal,
dual-issue scheduling, different threadgroup geometry) is a bet on *which
resource inside that kernel is actually saturated*.

Nobody has measured that. The goal of PR170 is to name the binding constraint
before anyone spends more receipts optimising the wrong axis.

## 2. Environment and setup

- Local host: **M4 Pro, `applegpu_g16s`, Apple GPU generation 16.**
- Official ranked host: **M5 Max, 128 GB**, generation 17+.
- `is_nax_available()` requires generation >= 17. On my local host it returns
  false, so **the kernel I am editing never executes locally**. The M4 is
  usable only for offline MSL/AIR census, the twin-consistency check, the
  safety rig, and overall build health. Every number that answers the actual
  question has to come from an official M5 receipt. That is why this
  experiment is structured as receipt arms rather than local A/B timing.
- The official runner strips environment variables, so a runtime env knob
  cannot select an arm. The arm is therefore selected by a **compiled-in
  constant**, `kNaxGatherProbeDefault`, in `quantized.cpp`. Its committed value
  is `""` (probe 0, exactly the control). For this submission the working tree
  sets it to `"m2"`. `mlxfast submit` packages the working tree (verified:
  `/usr/local/libexec/mlxfast.js:24533` calls
  `tar.create({cwd: repoPath, ...}, manifest.editablePaths)`), so the working-tree
  flip is precisely the mechanism that ships the arm. The constant is restored
  to `""` immediately after dispatch.

## 3. Prior work and the reading I had to correct

My first pass at this reasoned from a "double roofline" picture: it claimed the
kernel sat at ~67% of both the FLOP roofline and the bandwidth roofline
simultaneously, and read a "+14.30 ms excess" out of that. That reading is
wrong, and I withdrew it. The two utilisations came out equal not because the
kernel is jointly saturated but because the workload's arithmetic intensity
sits almost exactly **on the machine's ridge point**, which makes the two
roofline ratios algebraically identical regardless of what the kernel does.

The exact derivation, from `weights/config.json`
(`hidden_size = 2048`, `moe_intermediate_size = 512`, `num_experts = 256`,
`num_experts_per_tok = 8`, `num_hidden_layers = 40`, NVFP4 = 4.5 bit =
0.5625 B/value) with `L_moe = 39` MoE layers:

```
values/expert = 2*(2048*512) + 512*2048 = 3,145,728
FLOP  = 512 * 8 * 3,145,728 * 2 * 39         = 1005.022 GFLOP
bytes = 256 * 3,145,728 * 0.5625 * 39        = 17,666.41 MB   (weights only)
AI    = 1005.02 / 17.66641                   = 56.89 FLOP/B
ridge = 34,700 GFLOP/s / 610 GB/s            = 56.89 FLOP/B
```

The arithmetic intensity equals the ridge point to three significant figures.
That is a coincidence of this model's shapes and this machine's peaks, and it
means **the roofline cannot discriminate**: at the ridge, both bounds predict
the same time, so agreeing with both is not evidence for either. It also means
the honest prior is genuinely 50/50 between compute-bound and bandwidth-bound,
which is exactly the situation an added-work probe resolves and a roofline
argument cannot.

Note that the ledger byte count is **weights-only**. Activation traffic,
scales, and index gather traffic are on top, which if anything pushes the true
AI slightly below the ridge (toward bandwidth-bound). I did not attempt to
quantify that, because the probe measures the answer directly.

## 4. Hypotheses (pre-registered)

- **H1 (compute-bound):** the MMA pipeline is the binding resource. Doubling
  MMA work costs roughly a full extra compute-stream time; doubling the
  shared-memory stream is largely hidden.
- **H2 (bandwidth/staging-bound):** the device→threadgroup staging stream is
  binding. Doubling MMA is largely hidden; doubling the staging stream costs.
- **H3 (latency/sync-bound):** neither stream is saturated and the kernel is
  limited by barrier/occupancy serialisation. Both stream doublings are
  partially hidden and the barrier doubling (B2) costs disproportionately.
- **H0 (jointly saturated):** both streams are already overlapped as well as
  the schedule allows, so doubling *either* one costs real time and neither is
  *the* single constraint.
- **HV (probe void):** the added work was eliminated, hidden behind an
  unrelated stall, or never reached the scored path. This arm carries **no**
  peak-derived lower floor — the one I originally wrote was circular and is
  withdrawn in §8 — so a void M2 is caught by the arm-identity and
  session-health gates (`R0b`, `R6`, `R7`), not by a magnitude test.

## 5. Approach selection and tradeoffs

I chose **adding** work rather than removing it.

Removing work (e.g. skipping experts, shrinking tiles) is cheaper to write but
the result is ambiguous: a removal changes outputs, so it cannot pass the
correctness gates, and a removal that *is* bit-exact is by definition removing
something that was already free. Adding work keeps every checked token
identical while producing a clean marginal-cost reading, at the cost of one
receipt per axis.

The probe has to satisfy four properties simultaneously:

1. **Bit-exact.** The added work must not influence any stored result.
2. **Survive dead-code elimination.** A shadow accumulator that is never read
   is deleted by the Metal compiler, and the arm would silently measure its own
   control.
3. **Defeat the JIT library cache.** MLX keys compiled kernels by name; without
   a name change the probe variant could be served from the control's cached
   library.
4. **Be inert at probe 0.** The committed default must produce bit-identical
   machine code to the unmodified control.

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

**Arm M2 (`probe = 1`)** issues one additional `simdgroup` MMA per k-iteration
into a shadow accumulator `Dshadow`, fed by the *other already-resident A
fragment* and the *same* `Btile`. Because both operands are already in
registers, M2 adds MMA issue slots without adding any device or threadgroup
traffic — that is the whole point of the arm.

`Dshadow` is sunk through a guard that is provably false at runtime but opaque
to the compiler: it is consumed only under `run_skip_pct > 1000`, while the
host clamps `run_skip_pct` to `[1, 100]`. The compiler cannot prove the branch
dead, so the MMA survives; the hardware never takes it, so nothing is written.

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

M2 is exactly the intended edit: `mma` goes 1 → 2 with `barr`, `dev_ld`,
`tg_ld`, `tg_st` all unchanged. Threadgroup memory stays 9232 B and occupancy
stays 3 threadgroups/core, so the arm does not perturb occupancy.

Probe-0 inertness: the LLVM IR diff between the unmodified control and the
probe-0 build is 70 lines, **all** of which are `Li0E` Itanium mangling of the
new template parameter. No instruction differences.

`research/nax_safety_rig.sh`: checks 1, 3, 4, 5, 6 PASS. Check 2 FAILs by
design — it is a strict `cmp -s` on object bytes and cannot see through the
mangling change above; I left it strict deliberately rather than weakening a
safety check to make a dashboard green.

`./benchmark.sh --local-iterate` (probe 0, M4): exit 0 in 354 s,
`"passed": true`, score 0.798, prefill 0.001126 s/tok, decode 0.012878 s/tok.

## 8. How to read this receipt

Let `ΔM2 = S_M2 − S_control` in milliseconds of prefill wall.

**There is deliberately no lower floor on `ΔM2`.** An earlier version of this
note carried one (`ΔM2 < 13.0 ms ⇒ arm void`, from a `2 × 28.96 − 43.26 =
14.66 ms` compute-bound prediction). **It is withdrawn, and its withdrawal
matters more than its content.** The `28.96 ms` compute-stream figure rests on
a `34.7 TFLOP/s` peak that I had back-derived from the ridge identity
`56.89 = 34700/610` — that is, from the arithmetic intensity of this very
kernel. It was never an independent hardware number, so a "floor" built on it
was circular. At any realistic sustained NAX rate (52–60 TFLOP/s) the same
formula returns a *negative* floor, i.e. no constraint at all. Keeping it would
have meant declaring a genuine H2 or H3 result — the outcomes where `ΔM2` is
legitimately small — an instrument failure, which is exactly the error a
pre-registration is supposed to prevent.

What survives:

- **R0b (over-cost flag): `ΔM2 > 33.3 ms`** — larger than a full extra compute
  stream, which means the probe perturbed something beyond MMA issue
  (scheduling, register pressure, occupancy); flag rather than interpret.
- **R6 (latency variant): `ΔM2 ≤ −4.33 ms`** — adding a bit-exact second MMA
  stream made prefill *faster*. The only mechanism that does this is
  instruction-level parallelism filling issue stalls, so the MMA pipe would be
  **latency-bound, not throughput-bound**, and the next mechanism would be more
  independent work in flight per thread rather than fewer FLOPs. This row exists
  because without it the most informative possible outcome reads as a null.
- Otherwise `ΔM2` is compared against `ΔS2` and `ΔB2` under the pre-registered
  rules R0–R7 in §4.2 of
  `research/tanjiro-pr-gather-regime-discriminator.md`, evaluated mechanically
  by `research/tanjiro-pr170-receipts.py`. R2–R5 form a 2×2 on whether each of
  `ΔM2` and `ΔS2p` individually exceeds `μ = 4.33 ms`.

**Why a small `ΔM2` is a measurement and not a miss.** I estimated the
instrument's own noise from the public submissions feed (`n = 1583`) using a
non-circular selection: the `n = 16` receipts whose *candidate decode* is within
1% of this control, read for their *prefill* spread. Candidate prefill wall has
a sample sd of **0.318 ms (0.33%)**, so a two-receipt difference carries
`σ_Δ = 0.449 ms` and the decision margin `μ = 4.33 ms` sits at **9.6σ**. If this
arm returns `|ΔM2| < 1.35 ms` that is already a `3σ` null with roughly ten sigma
of headroom behind it.

The same audit changed which number I read. The paired baseline prefill wall is
**12.6× noisier** than the candidate's (sd `3.997 ms`), so the paired estimator
`188.5 / prefill_speedup` is **6.7× worse** than the raw candidate wall. All
deltas here are therefore computed from **raw candidate prefill seconds/token**;
`prefill_speedup` is used only for the floor check it exists to serve.

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
- Deferred a fourth "S2 sham" arm (same barrier/traffic shape, no real staging)
  because I cannot demonstrate it bit-exact on a gen-16 host, and because the
  S2 interval it would collapse only changes a verdict when
  `ΔB2 > 0.20·W = 8.65 ms`, a regime in which R1 already fires.
- Safety-rig check 2 left failing by design, as described in §7.

## 11. Exact commands

```bash
python3 research/nax_twin_check.py
bash research/nax_safety_rig.sh
./benchmark.sh --local-iterate
sed -i '' 's|kNaxGatherProbeDefault = ""|kNaxGatherProbeDefault = "m2"|' \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
git status --porcelain          # must show only that one file
export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --model "senpai" \
  --note-file research/artifacts/tanjiro-pr170-note-m2.md
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

## 12. Caveats

- Marginal cost is a *whole-prefill* delta, not a kernel-isolated measurement.
  It includes any second-order scheduling effects the probe induces.
- One receipt per arm means no within-arm repeat, so I cannot estimate M5 run
  variance from this experiment alone. The control's `+- 0.402 ms` ledger
  uncertainty is the only variance figure I carry, and the R0a/R0b gates are
  set far outside it.
- The ridge coincidence is specific to this model and this machine; the
  conclusion should not be transported to other shapes without redoing §3.

## 12b. Late correction: this arm is not single-axis

Added after the arm was built, before this receipt was spent. The offline
census originally counted MMA, barriers and memory traffic but not ALU. With an
ALU column added (`research/tanjiro_probe_alu_census.py`), both shipped
threadgroup shapes agree that this arm perturbs **two** axes, not one:

    M2 vs control:  mma +1,  int_alu +15   (control body = 87 integer ops)
                    barrier, dev_load, tg_load, tg_store, float_alu unchanged

The `+15` is address arithmetic for `Dshadow` and the extra cooperative-tensor
operand buffers — a +17% increase in scalar integer work. For comparison, the
S2 arm carries `int_alu +4` and the B2 arm carries none at all.

The confound is one-sided, which is why the arm is still worth running as-is.
If this receipt returns a marginal cost near zero, the compute-bound hypothesis
is dead regardless of the integer ops: a perturbation that cost nothing cannot
have concealed a cost. Only a *large* marginal cost is ambiguous, because there
"the MMA pipe is saturated" and "the scalar integer pipe is saturated" both fit,
as does the register-pressure alternative that M4-host reflection cannot
exclude.

That ambiguous branch has a pre-registered resolution, fixed before this
receipt: a fourth arm that moves `int_alu` and only `int_alu`, at roughly twice
this arm's integer amplitude. Its firing condition was widened to include
"large marginal cost on this arm", and a receipt is reserved for it. So a large
result here does not get reported as evidence for a compute bound; it triggers
the control instead.

## 13. Next steps

Dispatch S2 (`probe = 2`) and B2 (`probe = 3`) as separate single-cause
receipts, then run
`python3 research/tanjiro-pr170-receipts.py /tmp/subs.json m2=<id> s2=<id>
b2=<id>` to produce the mechanical verdict, and record the raw
`officialMetrics` JSON for each receipt under `research/artifacts/`.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
