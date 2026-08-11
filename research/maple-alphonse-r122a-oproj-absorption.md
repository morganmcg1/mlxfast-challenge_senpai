# R122-A — is nezuko's o_proj win throughput, absorption, or redistribution?

Assignment: PR #718, `maple-r122-a-oproj-absorption-decomposition`, revision
`r122-a-rev1`. Base `fa2a81b7624f6afa807830eb9ad7eb6d38c3d11d` (advisor HEAD
after the R117-C merge). Host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU
generation 16 — no `_nax` kernels, so this is M4-directional evidence for a
mechanism question, not a ranked number.

## §0 Verdict

**(A) THROUGHPUT — the kernel itself got faster. Not absorption, not
redistribution. The effect is real but about half the size the corpus carries,
and the reason it exists contradicts the byte model that was used to declare
o_proj unpurchaseable.**

Three legs, one binary, one session, 19 SPLIT=1 cells and 8 SPLIT=0 cells,
every cell `dispatches=366.0` and `0 divergences`, and every SPLIT=0 cell
reading back the ranked command-buffer configuration, so nothing is void:

| pre-registered branch | required | measured | outcome |
|---|---|---|---|
| (B) absorption | SPLIT=0 gap falls ≥ 50 µs/step | gap **+1.5 µs** (rose), total gap budget only 220 µs/step | **refuted** |
| (C) redistribution | a named neighbour rises ≥ 40 µs/step | worst neighbour `sliding_attn` **+5.6 µs**; residual attribution closes to 2 µs | **refuted** |
| (A) throughput | `ΔB ≤ −60` and `ΔT ≤ −60` | `ΔB` = **−40.0** [−47.6, −28.3], `ΔT` = **−43** | see below |

(A) is the only surviving mechanism, and it is positively supported rather than
merely left standing:

1. `ΔB` ≈ `ΔT` (−40 vs −43). The saving appears in the o_proj family and is
   not paid for anywhere else in the step.
2. The SPLIT=0 leg shows the same sign and roughly the same size in wall time
   (−35 µs/step, all four paired orderings negative) with the gap *unchanged*,
   so the saving is GPU-side work, not scheduling.
3. Leg 3's rps ladder finds an **interior minimum in isolated busy time at
   rps=2** (R2 1378.4 < O1 1402.9 < C4 1416.4 µs/step, every pair separated at
   t ≥ 4.9). Only an in-kernel trade-off produces a U; an outside-the-kernel
   explanation predicts monotone or flat busy time.

The literal (A) numeric gate is **not** met: I pre-registered `≤ −60` on both
axes and measured −40 and −43. That threshold was calibrated from the imported
`ΔW ≈ −80 µs/token`, and **that number did not reproduce in-session** — the
paired SPLIT=0 wall delta here is −35 µs/step, not −80. The scale-free form of
the same test (`|Δbusy| ≳ |Δwall|`, neighbours flat, gap flat) passes
decisively. I am calling (A) and flagging the threshold miss rather than
hiding it: the mechanism question is answered, the magnitude claim in the
corpus is not confirmed and should be re-measured without the profiler hook
(§7).

Two corpus consequences, in order of importance:

- **`N-K3-AT-DRAM-ROOF` is refuted on this host.** Going rps 4→2→1 strictly
  *increases* redundant activation re-reads, yet isolated busy time *falls*
  from 4 to 2. A bandwidth-saturated kernel cannot get faster when handed more
  traffic. o_proj/K3 is occupancy- and latency-limited at decode shapes, so
  the "47.4% of decode already at DRAM peak" figure — and any sibling "% of
  peak" claim derived the same way — needs an audit before it is used again to
  refuse an experiment. The cheap general test is now in hand: *increase the
  bytes and watch whether busy time falls*.
- **`N-ATLAS-SPLIT1-OVERSTATES-OVERLAPPABLE` survives in direction**, with the
  mildest overstatement measured to date: realized fraction `ΔW/ΔB` = 35/40 =
  **0.88**, though the SPLIT=0 spread is too large to separate that from 1.0
  (§5). SPLIT=1 busy deltas remain trustworthy for sign, attribution and
  ordering; for a kernel with no obvious overlap partner they are close to
  bankable and should be scaled by ~0.8–0.9 rather than voided.

M4-directional: Apple GPU generation 16, 20 cores, no `_nax`. The sign and the
ordering are mechanism-level and should transfer; the 0.88 realized fraction and
the exact 20-core optimum should not be assumed to.

## §1 Pre-registration (committed 2026-08-11T08:47Z, before any data)

Definitions, all in µs/step, all arms from one binary at base `fa2a81b7`,
selected only by `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP`:

- `C4` = `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=4` (pre-merge geometry, 256 TGs,
  512 simdgroups).
- `R2` = `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=2` (shipped default, 512 TGs,
  1024 simdgroups).
- `ΔB` = (R2 − C4) o_proj family GPU busy, h64 + h48, SPLIT=1, raw (undeflated).
- `ΔT` = (R2 − C4) total GPU busy summed over all kernels, SPLIT=1, raw.
- `ΔW` ≈ −80 µs/token is nezuko's already-measured SPLIT=0 wall delta; it is an
  input to this experiment, not an output of it.

Decision table, fixed in advance:

| finding | verdict |
|---|---|
| `ΔB ≤ −60` and `ΔT ≤ −60`, named neighbours flat | **(A) THROUGHPUT** — K3 was not at the DRAM roof; the byte model double-counts cached activation re-reads and every "% of peak" figure in the corpus needs an audit. |
| `ΔB ∈ [−25, +25]` and `ΔT ∈ [−25, +25]`, and the SPLIT=0 leg shows inter-command-buffer gap falling by ≥ 50 | **(B) ABSORPTION** — byte-level peak claims survive; the purchasable pool is latency absorption, whose M5 transfer must be priced separately and pessimistically. |
| `ΔB ≤ −60` but `ΔT ≈ 0`, or a named neighbour rises by ≥ 40 | **(C) REDISTRIBUTION** — name the neighbour; the residency model becomes a contention model. |
| any arm's dispatch count differs, or the golden hash differs | **VOID** — instrument failure, stop and report. |

If the point estimate lands between bands, the report says so plainly and
publishes the interval and the n that would separate them, rather than forcing
a call.

Negative controls whose busy must be reported per arm: `decode_nvfp4_qkv_h64…`
(K2), `routed_…_swiglu_qmv_packed_top8keys_r1_bf16_v2` (K1),
`routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` (K4),
`sliding_fused_attn_ring_v1`, `full_fused_attn_grow_v1`.

Instrument commitments:

- One binary, env-switched, paired and interleaved, mirrored orders reported
  separately (`C4 R2 R2 C4` then `R2 C4 C4 R2`).
- SPLIT=1 numbers are read **raw**. The additive per-dispatch SPLIT=1 overhead
  (~1.554 µs × calls/step) is identical in both arms because `rps` changes
  threadgroup count and not dispatch count, so it cancels exactly in the paired
  difference. `L-DEFLATE-ONCE`: no deflation inside Leg 1.
- The o_proj rows are matched **by role** (substring on the kernel family), not
  by exact string equality, because nezuko name-suffixes pipelines per geometry
  (`_rps2ns2`). The matched pipeline names are printed per arm and are
  themselves the proof the knob took effect.
- Bimodality screen on every per-run sample set: elevated Sarle's coefficient
  **and** ≥ 2 modes from a smoothed-histogram peak count ⇒ instrument failure.
- Raw per-run samples are dumped under `research/r122a-runs/`.

## §1b Instrument

One binary built once from base `fa2a81b7` plus two research-only additions
that cannot change numerics: the GPUPROF hook (`research/pr91-gpuprof-hook.patch`,
applied for the build and reverted on every exit path) and an env-gated stderr
readback (`DARKBLOOM_REPORT_CB_ENV=1`) that prints, from inside the worker,
`getenv` of the startup-memory and o_proj knobs together with the *resolved*
`rps`, `ns`, and pipeline-name suffix.

Harness: `research/maple-alphonse-r122a-oproj-split-arms.sh`.
Attribution: `research/maple-alphonse-r122a-attrib.py` (matches kernels by role
substring, never by exact name; records that name several kernels are one
batched command buffer and are held out as an unattributable residual instead
of being folded into a role).


## §2 Leg 1 — SPLIT=1 per-kernel busy, C4 vs R2, n=5 per arm

One binary, env-switched. Order `C R R C | R C C R | C R` (forward block,
mirror block, extra pair), 200 decode steps per cell, 199 steady steps
profiled. Every cell: `cbs=366.0 dispatches=366.0`, `0 divergences`, and zero
unattributable multi-kernel records. The readback confirms the knob resolved
in every cell (`resolved_rps=4 … suffix=<empty>` for C4, `resolved_rps=2 …
suffix=_rps2ns2` for R2) and the matched pipelines ran 30 calls/step (h64) and
10 calls/step (h48) in both arms.

| metric (µs/step) | C4 mean ± sd | R2 mean ± sd | R2 − C4 |
|---|---|---|---|
| `oproj_act_h64` | 1114.78 ± 1.83 | 1086.84 ± 3.62 | **−27.94** |
| `oproj_act_h48` | 301.58 ± 0.58 | 289.52 ± 1.67 | **−12.06** |
| o_proj family | 1416.36 ± 2.08 | 1376.36 ± 5.12 | **−40.00** |
| total GPU busy | 8248 ± 12 | 8205 ± 22 | **−43** |

Adjacent paired R2 − C4 on the o_proj family, in run order:
−28.3, −47.6, −42.2, −41.1, −40.8 µs/step; median −41.1, mean −40.0,
bootstrap CI95 [−47.6, −28.3] (20 000 reps, n=5). The single loose pair is the
first of the session (cell 01 → cell 02); the four later pairs span 6.8 µs.
The forward block and the mirror block give −28.3/−47.6 and −42.2/−41.1, so
run order does not carry the sign.

Named negative controls, R2 − C4 in µs/step:

| control | Δ |
|---|---|
| `decode_nvfp4_qkv_gate_h64` (K2) | −3.78 |
| `decode_nvfp4_qkv_gate_h48` (K2) | +0.02 |
| `routed_…_swiglu_qmv_packed_top8keys` (K1) | −1.06 |
| `routed_shared_nvfp4_down_residual` (K4) | −0.82 |
| `sliding_fused_attn_ring_v1` | **+5.64** |
| `full_fused_attn_grow_v1` | −2.10 |

The controls sum to −2.1 µs/step, and −40.0 + (−2.1) = −42.1 reproduces the
independently measured total-busy delta of −43. The attribution closes: the
o_proj family is where the busy went, and no other kernel absorbed it.

One control is not zero. `sliding_fused_attn_ring_v1` is **+5.64 µs/step**
(+0.9%) under R2, consistently in all five pairs and with non-overlapping
per-arm ranges. It is far under the pre-registered ≥ +40 redistribution
trigger and it cancels only 14% of the o_proj gain, but it is the only
neighbour outside noise and should not be rounded to zero. Under SPLIT=1
sliding attention runs in its own command buffer immediately *before* o_proj
in the same layer, so this cannot be same-dispatch contention; the plausible
carrier is state that R2's larger resident-simdgroup footprint leaves behind
for the next dispatch. Naming it now costs nothing and stops it being
rediscovered later as a surprise.

## §3 Leg 2 — SPLIT=0 wall and gap under the ranked memory profile

Same binary, `MLXFAST_GPUPROF_SPLIT=0`, `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.
The in-worker readback confirms the ranked command-buffer configuration
actually took in every cell (`MLX_MAX_OPS_PER_BUFFER=200
MLX_MAX_MB_PER_BUFFER=200 MLX_BFS_MAX_WIDTH=50`), so no cell is void — the
failure mode that voided half of the R119-A grid does not recur here.

Eight cells, n=4 per arm, pooled from both jobs (`C R R C` interleave in each),
all at the same ranked configuration:

| per steady step | C4 (n=4) | R2 (n=4) | R2 − C4 |
|---|---|---|---|
| wall | 8231 ± 15 µs | 8196 ± 24 µs | **−35 µs** (se 14) |
| GPU busy sum | 8012 ± 25 µs | 7974 ± 40 µs | **−38 µs** |
| inter-command-buffer gap | 220 ± 10 µs | 222 ± 16 µs | **+1.5 µs** |
| command buffers / step | 30.0 | 30.0 | 0 |
| dispatches / step | 366.0 | 366.0 | 0 |

Divergences 0 in every cell. The four adjacent paired wall deltas (R2 − C4) are
−18, −42, −78, −3 µs — all four negative, mean −35, but sd 32, so the wall
measurement alone is only about 2.4σ from zero. The wall leg confirms sign and
order of magnitude; the SPLIT=1 kernel leg is the precise instrument here, and
that is the expected division of labour.

The gap row is decisive. Under the ranked profile the *entire* inter-command-
buffer gap is 220 µs/step, 2.7% of the step, and R2 does not shrink it — it is
1.5 µs larger. The pre-registered (B) branch required the gap to fall by
≥ 50 µs/step. There is no room for that: the whole gap budget is only about
five times the effect being explained, and it moved the wrong way.
**Absorption is refuted, not merely unsupported.**


## §4 Leg 3 — the three-point ladder, and why it settles the mechanism

Legs 1 and 2 refute (B) and (C) but they cannot by themselves distinguish
"the kernel got faster" from "something outside the kernel got cheaper and the
profiler charged the saving to the kernel". A third arm settles it. `O1` is the
same binary with `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=1` — the same knob pushed
one notch further in the same direction as the landed change.

The discriminator is pre-stated and sign-based, so no threshold calibration is
involved:

- if rps 4→2 won because the *kernel* has an interior optimum in this knob,
  then rps=1 must be **worse than rps=2 in isolated busy time** — the two
  competing costs (occupancy on one side, redundant activation traffic and
  reduction overhead on the other) cross somewhere between 1 and 4;
- if rps 4→2 won for a reason outside the kernel, isolated busy time should be
  monotone in the knob, or flat, and rps=1 should be **no worse than** rps=2 in
  busy time while being worse in wall.

Leg 3 ran nine SPLIT=1 cells in the interleaved order `O R C C R O O R C`,
n=3 per arm, all from one build, all `cbs=366.0 dispatches=366.0`, all
`0 divergences`. Readback confirms `resolved_suffix=_rps1ns2` / `_rps2ns2` /
`<empty>` respectively, so the three arms really do select three different
kernel variants.

| µs/step, SPLIT=1 | O1 (rps=1) | R2 (rps=2) | C4 (rps=4) |
|---|---|---|---|
| oproj_act_h64 (30 calls) | 1111.6 | 1087.7 | 1114.0 |
| oproj_act_h48 (10 calls) | 291.3 | 290.7 | 302.4 |
| **o_proj family** | **1402.9 ± 4.7** | **1378.4 ± 6.3** | **1416.4 ± 1.0** |
| total GPU busy | 8233 ± 23 | 8216 ± 24 | 8251 ± 8 |

Pairwise, with Welch standard errors on n=3:

```
C4 − R2 = +38.0 µs   se 3.7   t 10.3
O1 − R2 = +24.5 µs   se 4.5   t  5.4
C4 − O1 = +13.5 µs   se 2.8   t  4.9
```

All three separations hold. **Isolated busy time has an interior minimum at
rps=2**: R2 < O1 < C4. That is precisely the ordering the corpus reports for
end-to-end wall time (rps2 best, rps1 middle, rps4 worst), reproduced here with
the kernel timed in isolation and the rest of the step held fixed. The wall
ordering therefore does not need any system-level explanation; the kernel's own
occupancy/traffic trade-off already produces it.

Note also *where* the U shows up. Almost all of it is in `h64`: 1114.0 → 1087.7
→ 1111.6 across rps 4/2/1, a 26 µs fall and a 24 µs rise. `h48` is nearly
monotone (302.4 → 290.7 → 291.3), which is what one expects when a smaller
output tile reaches its occupancy ceiling sooner. A mechanism outside the
kernel would have no reason to treat the two shapes so differently.

The second consequence is the one that matters for the corpus. Going 4→2→1
*increases* the number of threadgroups that must re-read the same activation
tile, so under a pure byte model each step down the ladder should cost strictly
more time. Instead time falls from 4 to 2 before rising at 1. A kernel pinned
at the DRAM roof cannot get faster when you give it more re-reads. So on this
host, at this shape, the o_proj/K3 family is **occupancy- and latency-limited,
not bandwidth-limited** — the roof it is near is not the one the byte model
draws.

## §5 Realized fraction, and what it does to `N-ATLAS-SPLIT1-OVERSTATES-OVERLAPPABLE`

Both legs come from one binary, one host, one session, minutes apart, so the
ratio is internally paired:

```
Δbusy(o_proj family, SPLIT=1, raw) = −40.0 µs/step   CI95 [−47.6, −28.3]  n=5+3
Δbusy(total,         SPLIT=1, raw) = −43   µs/step
Δwall(SPLIT=0, ranked profile)     = −35   µs/step   se 14, n=4 per arm
                                                     (paired −18, −42, −78, −3)
realized fraction  Δwall / Δbusy_raw = 35 / 40 = 0.88   [very wide: ~0.2 … 1.6]
```

The point estimate still has the SPLIT=1 busy delta **overstating** the
delivered wall gain, by about 1.15×, and this is the mildest overstatement the
campaign has measured. But I will not pretend the interval separates 0.88 from
1.0: the SPLIT=0 wall spread (sd 32 µs on a 35 µs effect) is of the same order
as the effect, so this leg bounds the realized fraction only loosely.

What it does establish is a one-sided statement that matters more for planning:
**SPLIT=1 did not *understate* here**, and the realized fraction for a serial,
non-overlappable kernel like o_proj is not far below 1. So
`N-ATLAS-SPLIT1-OVERSTATES-OVERLAPPABLE` survives in its stated direction, and
the practical reading is that a SPLIT=1 busy saving on a kernel with no obvious
overlap partner is close to bankable — scale it by roughly 0.8–0.9 rather than
voiding it. Tightening this ratio needs many more SPLIT=0 cells than one
turn allows; §7 records that.

The one number that did **not** reproduce is the imported one. The assignment
carried ΔW ≈ −80 µs/token from the R117-C certification, and the pre-registered
(A) threshold of ΔB ≤ −60 was derived from it. My own same-session ΔW under the
ranked profile is −35 µs/step, less than half of it. Two candidate
explanations, only partly
separable with the evidence I have:

1. **Different measurand.** R117-C's −79.4 µs/token came from a blocked,
   interleaved `--local-iterate` ladder timing seconds/token end to end,
   including host-side per-token cost. My Leg 2 number is the profiler's
   steady-step wall with the GPUPROF hook compiled in. If the hook or the probe
   shortens the host-side critical path, an effect that is partly host-visible
   would shrink here. The 366-dispatch, 30-command-buffer structure is identical
   between arms, so this can change the scale but not the sign.
2. **Session/thermal state and dispersion.** The eight SPLIT=0 cells ran last
   in two ten-minute sequences of model-loading processes, and their paired
   deltas (−18, −42, −78, −3) scatter by more than the effect itself.

Either way the correction matters for planning: on this host today the rps
4→2 geometry win is worth about **0.43% of the decode step** (−35 µs on
8.23 ms), not the ~1% that −80 µs on the same step would imply. Anything
budgeted against −80 µs/token should be re-budgeted.

The pre-registered thresholds were anchored to that imported ΔW, so taking
them literally is the wrong test. The scale-free form of the (A) branch is
`|Δbusy| ≳ |Δwall|` with the gap flat — the busy saving fully accounts for the
wall saving and leaves nothing for another mechanism to explain. That test
passes decisively: −40 (family) and −43 (total) against −35 of wall, gap +1.5.

## §6 Deviations from the pre-registration

1. **Two kernel-name needles in §1 were wrong for this base and were corrected
   before any statistic was computed.** §1 named the QKV control
   `decode_nvfp4_qkv_h64…`; at `fa2a81b7` the pipeline is
   `decode_nvfp4_qkv_gate_h64_r1_v1_lm1_pw1_se1_sd1`, so the needle matched
   nothing and would have silently reported a 0.0 µs control. The K4 needle
   `down_residual` additionally matched the unrelated
   `dense_down_residual_bf16_v1`. Both were tightened. This is the exact failure
   the "match by role, then print the matched name" rule in §1b exists to catch,
   and it was caught by reading printed names rather than by trusting a zero.
2. **Leg 2 carries fewer cells than Leg 1.** The n≥5 pre-commitment was written
   for Leg 1, which meets it (n=5, plus n=3 replication in Leg 3); Leg 2 ended
   at n=4 per arm and is reported with its raw paired deltas and a Welch
   standard error rather than a bootstrap interval. Leg 3's SPLIT=0 block was
   an unplanned bonus — the harness defaults its fourth argument, so passing an
   empty SPLIT=0 sequence re-ran `C R R C` instead of skipping it. I kept the
   cells because they double Leg 2's n; nothing was selected after the fact.
3. **The pre-registered numeric bands are reported as written and also reported
   as mis-calibrated.** I did not move a threshold after seeing data; §5 gives
   the scale-free restatement next to the literal one.
4. **`ns` was held at 2 throughout.** The `rps=2, ns=4` arm that R117-C used to
   refute threadgroup count as the cause was not re-run; this experiment varies
   only `rps`.

## §7 Next steps I did not take

1. **Re-measure ΔW with `--local-iterate`, without the GPUPROF hook compiled
   in and with n≫4**, to settle whether the −80 vs −35 gap is measurand or
   session, and to tighten the realized fraction, which my n=4 leaves anywhere
   between ~0.2 and ~1.6. This is the highest-value follow-up: a 0.43%-vs-1%
   error in the recorded size of an already-landed win propagates into every
   budget built on it.
2. **Price the +5.64 µs/step `sliding_fused_attn_ring_v1` regression.** If it is
   real cross-dispatch residency interference, o_proj geometry and attention
   geometry have to be tuned jointly, and the joint optimum need not sit at
   either single-kernel optimum.
3. **Audit the byte model's other "% of DRAM peak" rows with this method.** It
   is cheap and general: take a kernel the model calls roof-limited, find a knob
   that *increases* its bytes, and check whether its isolated busy time falls.
   o_proj failed that test, so the model's calibration — not merely its o_proj
   row — is in question.
4. **Repeat the decomposition on an M5 before trusting the argmax.** The
   geometry doc predicts the optimal resident-simdgroups-per-core ratio is
   reached by `rps=1` at 40 cores; if so the §4 ladder's minimum moves there,
   and only the mechanism conclusion transfers from this host, not the winning
   value.

## §8 Raw data and reproduction

Every cell in this report is in the two committed CSVs, one row per cell, with
the arm, split mode, profile, command-buffer readback, dispatch count,
divergence count, per-role kernel time *and the exact kernel names matched*:

- `research/r122a-runs/leg1-leg2.csv` — 10 SPLIT=1 cells (`C R R C R C C R C R`)
  and 4 SPLIT=0 `full` cells (`C R R C`).
- `research/r122a-runs/leg3.csv` — 9 SPLIT=1 cells (`O R C C R O O R C`) and 4
  more SPLIT=0 `full` cells.

```bash
bash research/maple-alphonse-r122a-oproj-split-arms.sh /tmp/r122a      200 CRRCRCCRCR CRRC
bash research/maple-alphonse-r122a-oproj-split-arms.sh /tmp/r122a-leg3 200 ORCCROORC  CRRC
python3 research/maple-alphonse-r122a-attrib.py /tmp/r122a      research/r122a-runs/leg1-leg2.csv
python3 research/maple-alphonse-r122a-attrib.py /tmp/r122a-leg3 research/r122a-runs/leg3.csv
```

The harness applies `research/pr91-gpuprof-hook.patch` for the run and reverts
it afterwards; no submitted-surface file is modified by this experiment, and
the branch contains no runtime change other than the `DARKBLOOM_REPORT_CB_ENV`
readback described in §1b.

