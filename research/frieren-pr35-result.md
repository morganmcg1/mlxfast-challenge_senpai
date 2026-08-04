# PR35 -- narrow the NVFP4 attention scale codes (result)

Assignment `maple-2026-08-04j-scale-code-width`, revision `r1`, branch
`maple-frieren/scale-code-width`, base `codex/mlxfast-maple-20260804-advisor`
(`eaedee8430f1e2779b235a7fbc296ee20ef3e44b`). Host: AWS-hosted M4 Pro
(`Mac16,11`), 48 GiB, `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.

**Bottom line.** The attention scale planes shrink from 32 B to 21 B per
32-group block with the original uint8 codes reconstructed exactly. That is
-30.61 MB/step of the ~1.79 GB decode stream (-1.71%), and it measures
**-67.6 us/step +- 7.9 us (-0.78%)** for the shipped configuration against its
kill switch (12 x 512 steps, ON/OFF/OFF/ON) and **-95.3 us/step** for the
mechanism isolated inside one process (parity A/B, 10 sigma). Both readings are
consistent with the -112/-146 us byte roofline once the +43 us three-load
reconstruction penalty is accounted for. No receipt was spent (the submission
slot was held); the mechanism is ready for a ranked pair whenever the advisor
schedules one.

**Read this too.** The rung ran into the trusted per-file editable-surface byte
cap: the frontier `LagunaRuntimeModel.swift` was 15,759 bytes below a hard
524,288 limit, and this work needed 24,104. It now fits with 7,722 bytes spare
(`swift test` 454/454), but only because both research instruments were deleted
from the surface and the packing code moved into `LagunaRuntimeWeights.swift`.
See "Editable-surface byte budget" below -- the next student to touch that file
needs a plan for it.

## Mechanism

The uint8 E4M3 scale plane is exactly 1/9 of every NVFP4 stream. For the four
decode-only attention QMV families the init-time census
(`research/frieren-pr35-scale-census.md`) measures `max - min <= 31` for
**100.00%** of the 32-group blocks one simdgroup iteration reads, so each block
is re-encoded as

```text
16 B nibbles (4-bit index per group) + 4 B high bits + 1 B block base = 21 B
```

against the 32 B the stock plane spends, and the kernel RECONSTRUCTS the
original byte

```text
code = base + nibble + (high_bit << 4)
```

before the unchanged `laguna_tail_nvfp4_scale`. Nothing downstream sees a new
value: this is a lossless re-encoding of the same 8-bit codes, checked at init
by an MLX round trip that discards any bank that does not reproduce its plane
byte for byte. The stock plane stays resident (prefill and the fallback read
it); the three narrow planes add 60 MB of MLX active memory.

## Byte accounting (40 layers: 30 sliding h64, 10 full h48)

| site | stock scale B/step | narrow B/step | saved |
| --- | --- | --- | --- |
| q/k/v QMV | 49.81 MB | 32.69 MB | 17.11 MB |
| o_proj QMV | 39.32 MB | 25.81 MB | 13.50 MB |
| total | 89.13 MB | 58.50 MB | **30.61 MB** |

30.61 MB is 1.71% of the ~1.79 GB/token decode stream. This host achieves
1.79 GB / 8.55 ms = 209 GB/s in decode against a 273 GB/s peak, so the
byte-roofline prediction for the pair is **-112 us/step (peak) to -146 us/step
(achieved rate)**.

## Part 3 screen

### Between-process arms are too coarse (run `f56514dc`)

Six interleaved 256-step probe arms (off/qkv/on, both orders) gave medians
OFF 8.550 / 8.618 ms, QKV 8.552 / 8.537 ms, ON 8.536 / 8.536 ms: an ABBA
reading of -48 us/step against a 68 us between-replicate offset. That
instrument cannot resolve this effect, and the process screen alone would have
wrongly rejected the mechanism.

### In-process parity A/B is decisive (run `5cdaebba`)

`DARKBLOOM_SCALE_ALTERNATE=1` flips the narrow dispatch by model-invocation
parity, so both arms run in one worker and neighbouring decode steps pair off.
512 steps => 248 pairs; `paired` is stock minus candidate (positive = candidate
faster) and `paired_rev` re-pairs each candidate step against the *previous*
stock step, so a monotone drift would break the sign symmetry.

| arm | scale bytes / 32 groups | scale loads / group | paired | paired_rev | stdev |
| --- | --- | --- | --- | --- | --- |
| q/k/v narrow | 21 B | 3 | **+50.1 us** | -49.7 us | 66.5 us |
| q/k/v narrow (replicate) | 21 B | 3 | **+44.5 us** | -46.7 us | 61.7 us |
| o_proj narrow | 21 B | 3 | **+48.0 us** | -50.3 us | 56.4 us |
| q/k/v `dummy` control | 32 B | 3 | -24.1 us | +25.3 us | 77.7 us |
| q/k/v `nibble` control | 16 B | 1 | discarded | discarded | 373.5 us |

Standard error per arm is stdev/sqrt(248) = 3.6-4.9 us, so every entry above is
a 10-sigma effect with the sign symmetry intact.

**Mechanism total: -95.3 us/step = -1.11%** of the 8.55 ms OFF step
(q/k/v -47.3 us as the mean of two replicates, o_proj -48.0 us),
1.19 us per attention QMV dispatch over the 80 dispatches a step issues.

The `dummy` control keeps the stock 32 B plane but reads three bytes per group
in the narrow arm's access pattern, so it prices the reconstruction's extra
loads alone: **+24.1 us/step** on q/k/v, or ~+43 us/step scaled to both sites
by their group counts. Adding that back, the byte-only win is 71.4 us for
17.11 MB (240 GB/s) on q/k/v and ~67 us for 13.50 MB (202 GB/s) on o_proj:
between this host's achieved decode rate and its peak, i.e. the byte component
lands **at the byte roofline**, and the shipped net is 65-85% of it because the
three-load reconstruction gives ~43 us back.

The `nibble` control (4-bit plane only, deliberately wrong scale magnitudes) is
discarded: its garbage logits changed the lm_head pruner's data-dependent
screen and slowed *both* parities by ~1.2 ms/step, which swamps the byte
signal. The load/byte decomposition above therefore rests on `dummy` alone.

Both research kernels are removed again at `c810175`; the parity alternator and
the census stay because they are the two instruments that can re-measure this.

### Pure-configuration replicate screen (run `1a623fb2`)

The parity instrument only ever runs alternating arms, so the shipped
configuration -- every step narrow, no alternator -- is screened separately:
six 512-step passes per arm, ordered ON/OFF/OFF/ON so a monotone host drift
cancels within each round (`research/frieren_pr35_pure.sh`, aggregated by
`research/frieren_pr35_pure_stats.py`).

| pass | ON median | OFF median |
| --- | --- | --- |
| round 1 | 8.5859 / 8.5778 ms | 8.6669 / 8.6150 ms |
| round 2 | 8.5802 / 8.5571 ms | 8.6414 / 8.6489 ms |
| round 3 | 8.5783 / 8.5741 ms | 8.6440 / 8.6428 ms |
| mean | **8.5756 ms** (stdev 9.8 us) | **8.6432 ms** (stdev 16.7 us) |

**OFF - ON = +67.6 us/step +- 7.9 us (-0.78% of the step)**; the
drift-cancelling round contrast agrees exactly (+67.6 us, se 5.0 us, rounds
+59.1 / +76.5 / +67.1 us). Every ON pass logged `narrow-scales built` for both
sites and every OFF pass logged nothing, so the kill switch really was flipped.
Every pass reported 0 token divergences.

Two instruments, two numbers: **-67.6 us for the shipped configuration between
processes** and -95.3 us for the mechanism isolated inside one process. The
between-process arm also pays the candidate's init and its 60 MB of extra
resident planes, and the alternating run touches both planes every two steps
(73.8 MB/step of scale traffic against 58.50 narrow-only), so a slightly larger
in-process reading is expected. The conservative shipped figure is -67.6 us,
i.e. 46-60% of the -112/-146 us byte roofline, and about -110 us once the +43 us
reconstruction penalty measured above is added back.

### Shipped-path hygiene

A read-only review of the mechanism found that the diagnostic
`LagunaNarrowScaleLog.note` ran an `NSLock`, two string interpolations and a
`Set` insert on **every** attention QMV dispatch, i.e. up to 80 times per decode
step, which the frontier never paid. Dispatch notes now follow the file's
`lagunaTrace` convention: `@autoclosure` arguments behind
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`, off by default (`48d28a2`). Bank
construction logs once per site at init instead, so a built or declined bank is
still reported without any env var.

The parity numbers above are unaffected: under the alternator both parities
took one `note` call per dispatch, so the overhead cancelled in the pair
difference. It did bias the *between-process* screens against the candidate,
because the kill-switch arm skipped the call entirely. The pure screen above
was run after the fix, on the shipped code.

### Editable-surface byte budget (hard gate, hit by this rung)

`swift test` catches this before the official run does:
`staticReviewKernelPolicyAndLaunchBudgetCoverEnlargedSurface`
(`Tests/MLXFastTests/BenchmarkScriptTests.swift`) pins
`EditableSurfaceByteBudget.defaultMaxFileBytes == 524_288` **per editable
file**, and `Sources/MLXFastCLI/main.swift` enforces the same budget
fail-closed for official runs. The promoted frontier already spends 508,529 of
those bytes on `Sources/MLXFastModel/LagunaRuntimeModel.swift`, so the whole
programme has **15,759 bytes of headroom in that one file**. This rung's
mechanism plus its two research instruments was 24,104 bytes: 8,345 over the
cap, i.e. unrankable until shrunk. The same test also pins
`fileCount == 142`, so moving code into a *new* editable file breaks a trusted
expectation and is not an option.

Remediation (`419f3b6`), none of which touches a kernel or a dispatch guard:

| action | bytes |
| --- | --- |
| removed the init-time scale census (recoverable from `2c1d72d`; numbers in `research/frieren-pr35-scale-census.md`) | -6,987 |
| removed the in-process parity alternator (recoverable from `ad00688`; its A/B is reported above) | -1,353 |
| moved packing + reconstruction certificate + log into the existing `LagunaRuntimeWeights.swift` | -6,757 |
| final `LagunaRuntimeModel.swift` | 516,566 (7,722 under the cap) |

The generated Metal source and every guard are unchanged by that commit, so the
-67.6 us/step measured at `7428d6c` describes the submitted tree; the 32-step
probe was re-run after the move (0 divergences, both sites `built`, median
8.472 ms/step), and `swift test --force-resolved-versions` is back to 454/454.

Programme note: the cheapest way to restore headroom on this file is to retire
research code that is no longer measuring anything. The PR #27
`M5 HARDWARE-CONSTANT INSTRUMENT` block is 12,134 bytes of deliberately
tree-slowing measurement code still sitting in the scored file; deleting it
would buy back more than this whole rung spends.

## Correctness

| gate | result |
| --- | --- |
| 32-step teacher-forced probe, narrow ON | 0 divergences; all four sites logged `active`; no bank declined |
| 6 x 256-step probe arms (off/qkv/on) | 0 divergences each |
| 5 x 512-step parity runs | 0 divergences (narrow, o_proj, dummy arms) |
| OFF-arm generated kernel text | byte-identical to the frontier q/k/v and o_proj text for every head count and gate variant; re-checked byte-identical (stock *and* narrow) across the research-arm removal at `c810175` |
| init-time reconstruction check | MLX round trip requires `(decoded != scales).sum() == 0` per bank; a failing bank is discarded and the site falls back to the stock plane |
| certificate fault injection (`research/frieren_pr35_fault.sh`) | with one nibble-plane bit flipped before the check, all 80 banks logged `declined (reconstruction mismatch)`, all four dispatch shapes logged `inactive`, and the 32-step probe still had 0 divergences; the control arm on the same worker built all 80 banks and logged `active` |
| `peak_ram_gb` | 20.7190 (OFF) -> 20.7213 (ON); MLX active 33.38 -> 33.44 GB |
| 32-step probe after the byte-budget shrink (`419f3b6`) | 0 divergences; `narrow-scales built: qkv` and `: oproj` at init; median 8.472 ms/step |
| `swift test --force-resolved-versions` | 454/454 in 6 suites (the budget test fails without `419f3b6`) |
| `./benchmark.sh --local-submit` on the shipped tree (`3cc08ce`, 22:12:41Z) | `passed: true`, `passed_correctness: true`, `max_abs_diff: 0`, `checked_steps: 1025`, `golden_hash f49e4c2c...`, `peak_ram_gb 21`; the only warnings are the known spurious acceptance-band notices that local modes raise because they use the pinned baseline constants instead of the M5 paired baseline |

Local-submit speed numbers are directional only and are **not** evidence about
the ranked ratios: this host's decode 0.009225 s/token against the pinned
baseline constant reads 1.502x and its prefill 0.001142 s/token reads 0.322x,
which is the usual M4-vs-pinned-M5 mismatch, not a real prefill regression. The
paired within-host screens above are the measurement.

## Suggested follow-ups (not implemented)

Ranked with a read-only design review of the two kernels. The important
correction to my earlier ranking: the stock scale plane is **already** streamed
once per step in fully-consumed 128 B lines (the q/k/v scale row is exactly
128 B at stride 128, so lane `l`'s four byte loads all hit one line), so a
lane-major layout saves *loads and pointer arithmetic*, not DRAM bytes.

1. **4-bit lane-major index with a per-row base and a sentinel escape**
   (best next rung, ~ -70..-90 us/step). The census row spans give `row_le15`
   = 0.9944 / 0.9864 / 0.9958 / 0.9814 for q/k/v/o, so 98.1-99.6% of rows fit a
   4-bit index plus one uint8 row base: 65 B vs 128 B per row, -12.4 MB/step
   net of escapees (-43.7 MB gross, ~+1 MB for the escaping rows, which re-read
   their stock row). Encode the escape as a **sentinel base byte** (`0xFF`;
   real bases are row minima of codes <= 41) rather than a flag plane, so no
   extra load or address stream appears. The escape predicate is
   simdgroup-uniform in both kernels -- the q/k/v row is a function of
   `simd_gid`, and all 32 o_proj lanes share `row` in each inner iteration --
   so it hoists out of the q/k/v k-loop entirely and never diverges. Packed
   lane-major it also *reduces* work versus the shipped narrow arm: one
   `ushort` (four nibbles) plus the base byte loaded once before the q/k/v
   loop, then `sbits = base + (rec & 0xF); rec >>= 4;` -- two loads per row
   against this rung's twelve and stock's four, and ~2 ALU/group against ~6.
   That is the direct antidote to the +43 us reconstruction penalty measured
   here, on top of a larger byte win. Watch o_proj register pressure (4 row
   records + 4 bases hoisted); reloading the L1-hot record per iteration is a
   fallback that keeps every byte saving.
2. **Lane-major permutation of the three planes shipped here** (-15..-30 us,
   low risk, useful only if (1) is deferred): 3 hoisted loads per row instead
   of 12, same 84 B/row, certificate identical modulo a permuted index. All
   strides (64/16/4 B) stay 4-byte aligned.
3. **Routed/shared planes.** MoE scales are 66 MB/step. Their blk32 spans reach
   39, so they need the escape path from (1) rather than this rung's
   escape-free envelope; re-census the fused per-layer routed banks first,
   because the 0.4-1.9% attention escape rate is not evidence about them.
4. **Rejected by the same review, recorded so nobody re-tries them.**
   Replacing the narrow bank with a lane-major *stock* plane is a
   +60..+100 us regression (it forfeits the byte win to recover at most the
   +43 us overhead). Interleaving scales next to codes saves zero bytes (the
   lines are already fully consumed), breaks the 8 B alignment of the `uint2`
   code loads, and would have to duplicate the ~713 MB code plane because
   prefill and the MLX fallback need the standard layout. A single interleaved
   lane-major 5-bit stream inflates to >= 96 B/row because the 5th bits and
   bases are shared across lanes -- more bytes in a byte-bound kernel.
