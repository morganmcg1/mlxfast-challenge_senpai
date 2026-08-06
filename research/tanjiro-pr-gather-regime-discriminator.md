# PR #170 — Regime discriminator for the prefill routed gather GEMM

Assignment `maple-2026-08-06o-gather-regime-discriminator`, revision `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `f1f7c1b`.

## 0. Question

On the promoted receipt `97a5090` (commit `3e165fa`, `officialScore =
2.58882784082067`, `ns = 2.5982163`) the prefill wall is `S = 97.895 ms` and the
routed gather GEMM `fp_gather_qmm_rhs_expert_nax` costs

```
dS1 = 43.2619 +- 0.402 ms   17,666.41 MB   1005.02 GFLOP
```

which is **67% of the compute roofline and 67% of the bandwidth roofline at the
same time**. Neither roofline alone explains the `+14.30 ms` excess, so every
"reduce work here" proposal has been a guess about which axis binds.

Rather than guess, this experiment **adds** bit-exact work along one axis at a
time and reads the marginal wall cost. Adding work is a strictly better
instrument than removing it: a removal that does not help is ambiguous (wrong
axis, or right axis but the removal did not bite), whereas an addition that
costs nothing proves the axis has slack.

Four hypotheses were pre-registered:

- **H0** jointly saturated — both streams already overlap as well as possible.
- **H1** MMA-limited — arithmetic is the critical path.
- **H2** load+dequant-limited — weight traffic and dequant are the critical path.
- **H3** schedule-latency-limited — barriers/occupancy, not work, dominate.

## 1. Instrument

One new template parameter on the kernel, `int probe = 0`, selected by a single
named constant in the selector:

| arm | `probe` | added work | intended axis |
|-----|---------|-----------|----------------|
| control | 0 | none — byte-identical to the shipped kernel | — |
| **M2** | 1 | second `tile_matmad_nax` per `kk1` into a shadow accumulator, fed by an already-resident `Atile` fragment and the same staged `Btile` | MMA only |
| **S2** | 2 | second loader stages a neighbouring expert's weights + dequant into the same `Ws`, then the real staging overwrites it | load + dequant (+1 barrier) |
| **B2** | 3 | two extra `threadgroup_barrier(mem_threadgroup)` per k-iteration | schedule only |

Submitted surface (exactly the three paths the assignment authorised):

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
- `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` (JIT twin)
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` (selector)

`Sources/MLXFastModel/LagunaRuntimeModel.swift` was **not** touched (frieren
#148 collision). Editable budget after all edits:
`current=2937322/3000000, headroom=62678, growth=10411/262144` — well inside
every fence.

### 1.1 The arm has to be compiled in, not env-selected

The natural design — an env var — **cannot work for a ranked receipt**. The
official runner strips the environment: `benchmark.sh:2084-2086` runs the timed
measure job under `sudo env_reset` + `env -i`. `benchmark.json` contains no
`env` block, the `mlxfast` CLI bundle contains no matching string, and no
`setenv()` exists anywhere in the repo. An env-only knob therefore always
measures its own control on the M5.

So the knob reads `env::get_var("DARKBLOOM_NAX_GATHER_PROBE",
kNaxGatherProbeDefault)`, and **`kNaxGatherProbeDefault` is the arm**. Each
official receipt is a one-token flip of that constant in the working tree,
which `mlxfast submit` packages (it packages the working tree, not `HEAD`). The
committed value is `""` — the shipped kernel. Env remains a local override
only, matching every other `darkbloom_*` knob in the file. This reproduces the
precedent recorded in `research/maple-fern-pr40-result.md`.

### 1.2 Defeating the optimiser and the caches

Three distinct things could silently turn an arm into its own control:

1. **Dead-code elimination.** M2's shadow accumulator has one consumer, a store
   guarded by `run_skip_pct > 1000`. `run_skip_pct` is a constant-buffer scalar
   the compiler cannot fold, and the host clamps it to `[1, 100]`, so the guard
   is unreachable at runtime yet keeps the chain live at compile time.
2. **Common-subexpression elimination.** The shadow MMA's operand pair is
   `(Atile[(kk1/SK + 1) % (BK/SK)], Btile)` — a pair the real chain never
   forms, so it cannot be folded into the real MMA. All `Atile[]` entries are
   fully loaded in a preceding loop, so the operand is real data, not garbage.
3. **The JIT library cache, which is keyed on kernel name alone.** Each
   non-zero arm therefore appends `_pb_<n>` to the kernel name. The suffix is
   omitted at probe 0 so the shipped name stays byte-identical.

All three were then **verified in the emitted machine code**, not assumed —
see §2.

## 2. Step 0 offline census

Full table, legend, and pipeline reflection:
[`research/artifacts/tanjiro_gather_probe_census.md`](artifacts/tanjiro_gather_probe_census.md).
Counts are post-optimisation AIR from
`xcrun -sdk macosx metal-objdump --disassemble`, both live threadgroup shapes.

```
pb  kernel                      mma  barr  dev_ld  tg_ld  tg_st  ir_lines
0   2048x1024_bk64                1     7       6      4      5       537
0   512x2048_bk64                 1     5       6      2      4       583
1   2048x1024_bk64  (M2)          2     7       6      4      5       697
1   512x2048_bk64   (M2)          2     5       6      2      4       743
2   2048x1024_bk64  (S2)          1     8       8      4      6       583
2   512x2048_bk64   (S2)          1     6       8      2      5       629
3   2048x1024_bk64  (B2)          1     9       6      4      5       539
3   512x2048_bk64   (B2)          1     7       6      2      4       585
```

**Confound verdict: all three arms CLEAN.**

- **M2** — `mma 1 -> 2`; barriers, device loads, threadgroup loads and
  threadgroup stores **all unchanged**. CSE and DCE both defeated, and the arm
  adds exactly zero memory traffic.
- **S2** — `dev_ld 6 -> 8`, `tg_st +1`, `barr +1`, `mma` unchanged. Clean, but
  carries one extra barrier *by construction*; §4 subtracts it.
- **B2** — `barr +2`, every other counter unchanged. The compiler did not merge
  or hoist the added barriers.

Every added call site sits inside the same loop nest as the original it
shadows, so the **static ratio equals the dynamic ratio**.

Pipeline reflection is identical across all four arms and both shapes:
`threadgroupMemoryLength = 9232 B`, `maxTotalThreadsPerThreadgroup = 1024`,
`threadExecutionWidth = 32`, giving `floor(32768 / 9232) = 3` threadgroups per
core. **Occupancy is unchanged by every arm.**

*Honest caveat.* `maxTotalThreadsPerThreadgroup` is saturated at 1024 and so
cannot report register pressure; M2 does add 5 allocas. This does not weaken a
*falsification* (a `ΔM2 ≈ 0` would be confound-free), but a *large* `ΔM2` admits
a register-pressure alternative that this instrument cannot exclude. Also,
these are M4 static counts; the M5 compiles the same MSL but its scheduler is
not identical.

## 3. Bit-exactness

`probe = 0` is the default on every path, so **the committed kernel is
unchanged and the arms are research state only**.

Per arm, at `probe != 0`:

- **M2** — `Dshadow` is a separate accumulator that is never mixed into
  `Dtile`; its only consumer is unreachable. No value the real chain sees
  changes.
- **S2** — the shadow staging pass writes exactly the same destination address
  set as the real pass (loader addressing depends only on `lid` and simd ids,
  and the sets are disjoint across threads); a threadgroup barrier separates
  the two, and no thread reads `Ws` in between. The real staging therefore
  overwrites the tile in full before any consumer reads it.
- **B2** — barriers are pure synchronisation and cannot change a value.

**Mechanically proven inert at `probe = 0`.** Building the base revision and
the head revision to LLVM IR and diffing gives exactly **70 differing lines**,
all of them Itanium mangling of threadgroup globals (`Ws_storage`, `bounds.0`,
`bounds.1`) gaining `Li0E` from the new defaulted template parameter.
Normalising `ELi0EE -> EE` and re-pairing leaves **zero unmatched lines**: the
default-arm machine code is identical, not merely equivalent.
`research/nax_safety_rig.sh` reports checks 1, 3, 4, 5, 6 PASS and check 2 FAIL
— check 2 uses `cmp -s`, which cannot see through mangling. The rig was left
strict on purpose rather than weakened to make the check pass.

Twin consistency (`python3 research/nax_twin_check.py`):
`TWIN CHECK: generated copy matches the header`, exit 0.

## 4. Pre-registered decomposition and decision rules

Registered **before** any receipt was spent, and implemented in
`research/tanjiro-pr170-receipts.py` so the verdict cannot be fitted afterwards.

From the control receipt: each stream costs `M = C = 0.67 x 43.2619 = 28.99 ms`
in isolation. Perfect overlap would give `28.99 ms`; fully serial would give
`57.98 ms`; the measured `43.26 ms` means **only `14.72 ms` (50.8%) of the
smaller stream is currently hidden**. Excess over the higher roofline is
`E = 14.27 ms`.

Doubling either stream takes it to `57.98 ms`, which already exceeds the
current `43.26 ms` wall, so for M2 and S2 **`Δ` can never be ≈ 0**:

- lower bracket `L = +14.72 ms` — added work fully absorbed by existing stall
- upper bracket `R = +28.99 ms` — added work absorbs nothing

The stock k-loop carries **2 barriers per iteration**; B2 makes it 4 (an exact
doubling) and S2 makes it 3. Hence pure load+dequant cost is

```
dS2_pure = dS2 - dB2 / 2
```

Deltas are in ms of prefill wall `S = 512000 x prefill_s_per_tok`; the arms
touch only this kernel, so `ΔS = Δkernel`.

| rule | condition | verdict |
|------|-----------|---------|
| **R1** | `ΔB2 >= 7` | **H3 wins** — schedule latency explains >= half of `E`; next mechanism is barrier removal / occupancy |
| R1' | `3 <= ΔB2 < 7` | H3 partial — real but minority cost |
| R1'' | `ΔB2 < 1.5` | H3 dead |
| **R2** | `ΔM2 >= 24` and `ΔM2 - ΔS2_pure >= 6` | **H1 wins** — MMA-limited |
| **R3** | `ΔS2_pure >= 24` and `ΔS2_pure - ΔM2 >= 6` | **H2 wins** — load+dequant-limited |
| **R4** | `ΔM2, ΔS2_pure ∈ [13, 19]` and `ΔB2 < 1.5` | **H0** — jointly saturated |
| **R5** | `ΔM2, ΔS2_pure >= 24` and `ΔB2 < 1.5` | **new regime, outside H0–H3** — neither stream absorbs the other; the fix is to *overlap* them, not shrink either |

### 4.1 Floor safety

`S_candidate <= S_baseline / 0.95 ≈ 200 ms` against `S_control = 97.9 ms`
leaves **~102 ms of injection headroom** versus a maximum predicted arm delta
of ~29 ms. No arm can trip the prefill floor, and no arm touches decode.

### 4.2 Arm ordering, and what it buys

Arms are dispatched **M2, then S2, then B2**. This is not arbitrary. M2 and S2
have a hard lower bracket of `+14.7 ms`, so a near-zero delta on either is
*proof the instrument did not reach the kernel*, and the campaign stops to
debug rather than spending the remaining arms. `ΔB2 ≈ 0`, by contrast, is a
legitimate scientific outcome (H3 dead) that is **confounded** with "the arm did
not apply" — running it last means the large M2/S2 deltas have already
demonstrated that the identical plumbing (same `expert_aligned` path, same
`_pb_<n>` naming mechanism) reaches the kernel, which disambiguates it.

*Caveat on direct verification.* The dispatch-site trace fires whenever a probe
is requested and prints `active`/`inactive` with the kname handed to the JIT,
but the M5 receipt does not surface stderr, and the kernel cannot run locally
(this host is `applegpu_g16s`, Apple GPU generation 16; `is_nax_available()`
requires >= 17). The ordering argument above is therefore the operative
verification, and it is stated as such rather than dressed up as a direct one.

## 5. Receipts

<!-- RECEIPTS -->

## 6. Reading

<!-- READING -->

## 7. Decode control

<!-- DECODE -->

## 8. Next mechanism

<!-- NEXT -->

## 9. Follow-ups

<!-- FOLLOWUPS -->

## 10. Reproduction

```bash
# offline census (both threadgroup shapes, all four arms)
for p in 0 1 2 3; do PROBE=$p research/nax_msl_compile_check.sh; done

# twin consistency + inertness rig
python3 research/nax_twin_check.py
research/nax_safety_rig.sh

# build health at the committed default (probe 0)
./benchmark.sh --local-iterate

# receipts: flip the one constant, submit, then restore
#   Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
#   constexpr const char* kNaxGatherProbeDefault = "m2";   # or "s2" / "b2"
mlxfast submit --model "senpai" --note-file research/artifacts/tanjiro-pr170-note-m2.md
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp

# verdict
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
  -o /tmp/subs.json
python3 research/tanjiro-pr170-receipts.py /tmp/subs.json m2=<id> s2=<id> b2=<id>
```

Local build health at the committed default: `./benchmark.sh --local-iterate`
exit 0 in 354 s, `"passed": true`, score `0.798`, prefill `0.001126` s/tok,
decode `0.012878` s/tok (M4 numbers; the nax kernel does not run on this host,
so these check the build and the probe-0 inertness, not the mechanism).
