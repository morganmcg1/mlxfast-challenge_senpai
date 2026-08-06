# PR170 arm B2 — prefill routed-gather regime discriminator (barrier / synchronisation axis)

## 0. What this submission is, and what it is not

This is a **measurement arm**, not a speed attempt. It deliberately *adds*
threadgroup barriers to the prefill routed gather GEMM
`fp_gather_qmm_rhs_expert_nax` and asks the official M5 how much prefill wall
time those barriers cost. I expect this candidate to be **rejected on
ranking** — it must be slower than the control by construction. A `rejected`
receipt still publishes the full `officialMetrics` block, and that block is the
entire deliverable here.

The arm is bit-exact: barriers do not change any value, so no checked output
changes and every correctness gate should pass exactly as it does for the
control. If a correctness gate fails, that is a bug in my probe, not a property
of the hypothesis, and I will say so.

Budget for the whole experiment is **3 arms plus one spare receipt**. This is
arm 3 of 3 (B2 = barriers ×2), following M2 (MMA ×2) and S2 (staging stream
×2). It is dispatched last on purpose: B2 is both a hypothesis test in its own
right (H3) and the correction term that turns the S2 point reading into a
defensible bandwidth estimate, so it is most useful once the other two deltas
are already in hand.

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
before anyone spends more receipts optimising the wrong axis. B2 prices
synchronisation, which is the axis a "just remove a barrier" optimisation would
be cashing in.

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
  to `"b2"`. `mlxfast submit` packages the working tree (verified:
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
discriminate**. Worse for the roofline story, if neither stream is actually
saturated the model says nothing at all — which is precisely the H3 case that
B2 exists to detect. A roofline argument cannot distinguish "at the ridge and
saturated" from "at the ridge and stalled on synchronisation"; an added-barrier
probe can.

The ledger byte count is weights-only; activation, scale, and index-gather
traffic sit on top.

## 4. Hypotheses (pre-registered)

- **H1 (compute-bound):** the MMA pipeline binds. Doubling MMA costs roughly a
  full extra compute-stream time; doubling the staging stream is largely
  hidden.
- **H2 (bandwidth/staging-bound):** the device→threadgroup staging stream
  binds. Doubling MMA is largely hidden; doubling the staging stream costs.
- **H3 (latency/sync-bound):** neither stream is saturated and the kernel is
  limited by barrier/occupancy serialisation. Both stream doublings are
  partially hidden and **this** arm costs disproportionately.
- **H0 (probe void):** the added work was eliminated, hidden behind an
  unrelated stall, or never reached the scored path.

## 5. Approach selection and tradeoffs

I chose **adding** work rather than removing it. Removing work is cheaper to
write but ambiguous: a removal that changes outputs fails the correctness
gates, and a removal that is bit-exact is by definition removing something that
was already free. Adding work keeps every checked token identical while
producing a clean marginal-cost reading, at the cost of one receipt per axis.

Barriers are the cleanest of the three probes with respect to correctness — an
extra `threadgroup_barrier` cannot change a value — but the hardest to give a
principled floor. There is no peak-derived lower bound for `ΔB2`, because
barrier cost is entirely a function of warp divergence and occupancy at that
point in the schedule, not of a published peak. **B2 therefore carries no
R0a/R0b gate**; it is interpreted only relative to `W`, `ΔM2`, and `ΔS2`. That
is a deliberate asymmetry, pre-registered rather than discovered after seeing
the number.

The probe must satisfy three of the four properties the other arms need:

1. **Bit-exact.** Trivially satisfied for barriers.
2. **Survive dead-code elimination.** A `threadgroup_barrier` with memory-flag
   semantics is not removable by the compiler.
3. **Defeat the JIT library cache.** MLX keys compiled kernels by name; the
   `_pb_3` name suffix handles this.
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

**Arm B2 (`probe = 3`)** inserts two extra `threadgroup_barrier` calls per
k-iteration, at roughly `fp_quantized_nax.h:1766` and `:1879`, bracketing the
existing staging/consume pair. The per-iteration barrier count therefore goes
from 2 to 4 — a clean doubling of the synchronisation rate inside the main
loop — while every load, store, and MMA is left untouched.

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

B2 is exactly the intended edit: `barr` 7 → 9 with `mma`, `dev_ld`, `tg_ld`,
`tg_st` all unchanged, and only 2 extra IR lines. Threadgroup memory stays
9232 B and occupancy stays 3 threadgroups/core, so the arm does not perturb
occupancy — which matters more here than for the other arms, since occupancy is
itself part of the H3 mechanism and a change in it would confound the reading.

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

Let `ΔB2 = S_B2 − S_control`, in milliseconds of prefill wall. B2 serves two
purposes:

1. **H3 test.** If `ΔB2` is large relative to `ΔM2` and `ΔS2`, the kernel is
   synchronisation-limited and neither stream doubling should have cost much.
   The pre-registered threshold is `ΔB2 > 0.25·W = 10.82 ms` with both stream
   deltas materially below their peak-derived floors.
2. **S2 correction term.** S2 adds one barrier as an unavoidable side effect;
   B2 adds two. The barrier-corrected S2 interval is
   `[ΔS2 − ΔB2, ΔS2 − ΔB2/2]` — the conservative end assumes S2's single
   barrier costs as much as B2's pair, the linear end assumes barrier cost
   scales with count.

B2 carries **no R0a void gate and no R0b over-cost gate**, for the reason given
in §5: there is no peak-derived expectation for barrier cost. A small `ΔB2` is
a real and informative result (barriers are cheap here), not a void probe.

The joint verdict follows the pre-registered rules R1–R5 in §4.2 of
`research/tanjiro-pr-gather-regime-discriminator.md`, evaluated mechanically by
`research/tanjiro-pr170-receipts.py`, in the order
R0a → R0b → R1/R1'/R1'' → R5 → R2 → R3 → R4.

## 9. Floor safety

`S_control = 97.895 ms`. The prefill 0.95 floor allows roughly
`S_candidate ≤ ~200 ms`, i.e. about **102 ms of injection headroom**. Barriers
are the cheapest of the three probes in expectation and the other two are
bounded well under 40 ms, so no arm can trip the prefill floor. Decode is
untouched by this kernel path.

## 10. Failures and course corrections in this experiment

- Withdrew the "67% of both rooflines / +14.30 ms excess" framing and replaced
  it with the ridge-point derivation above, plus peak-derived floors for M2 and
  S2 and an explicit no-floor declaration for B2.
- Withdrew a self-contradictory version of decision rule R5 and re-derived the
  rule ordering as R0a → R0b → R1/R1'/R1'' → R5 → R2 → R3 → R4.
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
sed -i '' 's|kNaxGatherProbeDefault = ""|kNaxGatherProbeDefault = "b2"|' \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
git status --porcelain          # must show only that one file
export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --model "senpai" \
  --note-file research/artifacts/tanjiro-pr170-note-b2.md
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

## 12. Caveats

- Marginal cost is a *whole-prefill* delta, not a kernel-isolated measurement.
  It includes any second-order scheduling effects the probe induces.
- Barrier cost is highly schedule-dependent. `ΔB2` prices *these two barriers
  at these two points*, not barriers in general, and should not be extrapolated
  to a barrier removed elsewhere in the loop without re-measuring.
- One receipt per arm means no within-arm repeat, so I cannot estimate M5 run
  variance from this experiment alone. The control's `+- 0.402 ms` ledger
  uncertainty is the only variance figure I carry.
- The ridge coincidence is specific to this model and this machine; the
  conclusion should not be transported to other shapes without redoing §3.

## 13. Next steps

With all three deltas in hand, run
`python3 research/tanjiro-pr170-receipts.py /tmp/subs.json m2=<id> s2=<id>
b2=<id>` to produce the mechanical verdict, record the raw `officialMetrics`
JSON for each receipt under `research/artifacts/`, and fill §5–§9 of the report
with the named binding constraint plus the concrete optimisation direction it
licenses. If the verdict is H2, the follow-up is staging/tiling work; if H1,
dual-issue and MMA scheduling; if H3, barrier removal and occupancy work — and
in that last case the standing S2-sham arm becomes worth its receipt.

_Submitted by an AI agent (OpenHands) on behalf of morganmcg1._
