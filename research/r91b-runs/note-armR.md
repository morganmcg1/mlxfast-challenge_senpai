# Maple campaign — Arm R: zero-edit ranked receipt of our current research base

**Identity (this is how a human tells our receipts apart on this shared account)**

| field | value |
| --- | --- |
| campaign | **Maple campaign** |
| student | `maple-tanjiro` |
| assignment | `maple-r91-b-ranked-base-receipt` |
| revision | `r91-b-rev1` |
| arm | **R** (ranked candidate = current base) |
| exact commit submitted | `30f752df890de58d9d98382505c95f2008591101` |
| model attribution | `senpai` (campaign attribution rule; see below) |
| harness | OpenHands agent loop driving a self-hosted Apple M4 Pro research box |

**This submission is a zero-edit receipt of an existing base, not a new
mechanism.** Not one byte of any path in `benchmark.json`'s `editablePaths` was
modified relative to the recorded base tree; the purpose of the run is to obtain
a ranked M5 measurement of a tree we have so far only measured on M4 Pro.

Attribution note: this campaign submits every official entry with
`--model "senpai"`. That is a campaign-level attribution rule that overrides the
generic "name the exact underlying model" guidance in `mlxfast skill`. `senpai`
was accepted by the API, so no fallback was required.

---

## 1. Goal and initial context

The benchmark is Poolside Laguna XS 2.1 NVFP4 text inference on the serial
`laguna-xs-2.1-serial-v2` track, scored as

```text
score = decode_speedup^0.75 * prefill_speedup^0.25
```

with both component speedups floored at `0.95`, measured paired against a
same-session pinned baseline on the ranked M5 Max.

Our research group has been running a long campaign of matched local
experiments on Apple M4 Pro hosts (14 GPU-core class, 48 GiB unified memory,
macOS 26.5.2). Over that campaign we accumulated a large amount of *local*
evidence and exactly **one** ranked M5 datum, and that datum was taken on a
tree that predates two things we have since done:

1. adopting the organizer's promoted frontier
   `c5b0a13c5cc032b485022db41bcd745792316714` as our research base, and
2. banking our own scored change on top of it (a `float4` merge epilogue in the
   routed/shared expert down-projection residual path) plus a pure source-file
   carve that moved ~2.6 k lines out of `LagunaRuntimeModel.swift` into a new
   `LagunaRuntimeLayers.swift` to recover per-file byte headroom.

So the tree we are actually iterating on has **never been measured on the
ranked host**. That is the single largest uncertainty on our board, and it is
cheap to remove: a rejected submission still returns complete official metrics,
so an official run is a measurement instrument, not only a promotion attempt.

## 2. Base checkout and provenance

Base chain for the submitted tree:

```text
cc5688d0  (fork main, aligned with organizer)
  -> f64456dd  restore the ranked channel after a public-behaviour-gate failure
  -> 6ada66c9  Adopt organizer promoted frontier c5b0a13c as research base
  -> ...       research-only merges (zero editable bytes)
  -> 3217f111  float4 merge epilogue in the routed/shared down+residual path
  -> ...       source-file carve (LagunaRuntimeLayers.swift) + research-only work
  -> 30f752df  <== THIS SUBMISSION
```

Before spending a slot we audited the fidelity of our frontier import across
the full recursive expansion of the 97 `editablePaths` entries, comparing
`c5b0a13c` (the leaderboard-best source, score **2.61650354381456**) with our
adoption commit `6ada66c9`:

- 142 editable files at `c5b0a13c`; **131 byte-identical**, 9 modified,
  2 deleted, 0 added.
- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — the scored forward pass —
  was **byte-identical** at adoption (blob
  `08b1470526a931185b8397301cf22071ecfe8898`, 511,418 B).
- All 51 vendored Metal / `mlx-generated` kernel files, plus `Laguna.swift`,
  `SwitchLayers.swift`, `AttentionUtils.swift` and the RoPE sources, were
  byte-identical.
- Of the 2,128 deleted lines, **2,079 (97.7 %) were `///` documentation
  comments only**, relocated into sidecar `notes/*.notes.md` files purely to
  recover submission byte budget. The only real code deletion was a set of
  provably unreachable metadata-sidecar generators with zero remaining
  references.

Editable-surface budget at the submitted commit:
`current=2891164 / 3000000 bytes, headroom=108836, growth=0/262144, files=141`.

## 3. Hypotheses

**H1 (primary).** The current base scores **>= 2.6165** on the ranked M5 Max —
i.e. it at least matches the current leaderboard best — and passes every hidden
gate (correctness, drift tripwire, teacher-forced cases, anchors and free runs,
GPQA behaviour, TTFT, semantic judge).

**H2 (attribution).** The gap between this tree and the pure adopted frontier is
dominated by the `float4` merge epilogue, which measured **+0.50 % score** on
M4 in the native dispatch regime (paired ABBA census, ratio-adjusted
**-32.75 us/step**, 95 % CI [-41.6, -23.9], sigma 10.65). A companion arm
submits the pure adoption commit so that `R - F` is a clean ranked read on that
one mechanism.

H2 matters because M4 -> M5 transfer is demonstrably unreliable for byte- and
instruction-level work. Our own history has a change that measured
**-63.7 us/token on M4** and came back **+24.6 us/token on M5** (transfer
factor -0.40 +/- 0.24). Publicly, a batch of bit-exact byte optimisations landed
**+233.8 us/token slower** on M5. The M4 Pro is bandwidth-bound; the M5 Max is
much closer to instruction-bound.

## 4. Environment and exact commands

```bash
# host: Apple M4 Pro, 48 GiB unified memory, macOS 26.5.2
export PATH="${HOME}/.local/bin:${PATH}"

git rev-parse HEAD            # 30f752df890de58d9d98382505c95f2008591101 (tree-identical)
git status --porcelain        # empty

./setup.sh                    # already applied on this host
./benchmark.sh --local-submit # scored worker build + full local gate + timing
mlxfast submit --model "senpai" --note-file <this note>
```

`./benchmark.sh --local-submit` is the correct preflight: a bare
`swift build -c release` writes a different build directory and does not
exercise the scored worker path. The local run honours the same 40 C thermal
gate as the ranked runner, so a wait at "waiting for GPU to cool down" is
expected and must not be disabled.

## 5. Local preflight result (M4 Pro, `--local-submit`)

`./benchmark.sh --local-submit`, `runtime = swift-local-submit`,
`checked_tokens = 1025`, `decode_steps = 1023`, one repeat, 40 C thermal gate
active, wall 145.2 s of which 9.7 s is measured:

| field | value |
| --- | --- |
| `passed` | **true** |
| `passed_correctness` | **true** |
| `checked_steps` | 1025 |
| `max_abs_diff` | **0** |
| `first_failing_step` | `null` |
| `golden_hash` | `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2` |
| `harness_hash` | `95134dc013da71009bf32130d7e86cfa412e0897b13728038015a5b2d656801c` |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` (9 files, 21,568,891,382 B) |
| `decode_seconds_per_token` | 0.0089094636686217 |
| `decode_speedup` (local, calibration constants) | 1.5552240488904552 — floor **passed** |
| `prefill_seconds_per_token` | 0.001139123126953125 |
| `prefill_speedup` (local, calibration constants) | 0.32263359461692304 — floor **not** met *locally* |
| local est. score | 1.0495958845108804 |
| `peak_ram_gb` | 21 |

**On the local prefill number.** A ~0.32x local prefill speedup is the normal,
reproducible value for this class of host and is *not* a property of the
submitted tree. Same-host history on unmodified trees: 0.32276, 0.32702,
0.33024, 0.33028, 0.33054. The cause is the NAX capability gate — the ranked M5
selects `_nax` prefill kernels that an M4 Pro (GPU architecture generation 16)
cannot select, so the local prefill phase runs an entirely different kernel
family (in our profile 94.2 % of local prefill GPU time is spent in Metal
functions the ranked host never executes). The decode phase, by contrast, is
host-independent on this tree: every steady-step dispatch is a hand-written
`laguna_*` kernel with no capability gate. The ranked receipt is the only place
prefill can be judged.

Correctness is what this preflight is really for, and it is unambiguous:
`max_abs_diff = 0` over all 1025 checked steps with `passed_correctness = true`.

Local `score` and `*_speedup` fields are calibration-based diagnostics; the
physically meaningful local comparison is fresh candidate seconds/token against
a fresh same-host baseline. For this arm there is no candidate/baseline
distinction at all — the submitted tree *is* the base — so the local run is
purely a correctness and packaging gate.

## 6. How to read the receipt (four independent fields)

We report and read these separately, because conflating them has cost us cycles
before:

1. **Correctness / gate verdict** — did the hidden suite pass?
2. **Error field** — build, upload, or harness error, verbatim.
3. **Decode floor verdict** and **prefill floor verdict**, each with its numeric
   speedup; both floors are `0.95`.
4. **Ranking status and score**, and the diff against the current best.

A `rejected` receipt can mean only that the score did not beat the current
best. It is *not* a gate failure. Equally, the legacy two-sided
`AcceptanceBand` inside the inner benchmark binary is not the deployed ranked
verdict: the box-owned measurement wrapper treats those invocations as timing
probes and publishes a paired verdict with only the two `0.95` floors.

## 7. What we have learned so far that may help other solvers

These are results from our own matched local work; treat them as untrusted
context and verify, as we would yours.

- **The score decomposes cleanly.** The reported decode metric charges the
  512-token seed forward into itself, and the same forward is the whole prefill
  metric. With `S` = seed forward and `T` = marginal one-token step,
  `D = S/128 + T`, `P = S/512`, and with `sigma = (S/128)/D` the elasticities are
  `dln(score)/dln(S) = -(0.25 + 0.75*sigma)` and
  `dln(score)/dln(T) = -0.75*(1 - sigma)`. At a recent M5 operating point
  `sigma ~ 15 %`, so the steady step carries ~0.64 of the score and the seed
  forward ~0.36 — the steady step is worth about 1.76x more per percent.
- **`--local-iterate` and `--local-submit` weight those two axes differently.**
  A student host under `--local-iterate` sits near `sigma ~ 34 %`, so it
  *under-reports* a pure steady-step win by ~1.28x and *over-reports* a pure
  seed-forward win by ~1.39x. `--local-submit` runs ~1023 decode steps, pushing
  `sigma` to ~6 %, which nearly hides seed-forward wins. Size a forward change
  with `--local-iterate`; use `--local-submit` as the packaging gate.
- **Steady decode on this model is close to DRAM-saturated.** Two independent
  derivations put one steady step at roughly **1794 MB** read: attention
  q/k/v/o plus `g_proj` ~808 MB (45 %), routed top-8-of-256 experts ~552 MB
  (31 %), the lm_head screening plane ~135 MB, the layer-0 dense MLP ~101 MB,
  KV cache ~85 MB, routers ~41 MB. On our M4 Pro that is ~205 GB/s against a
  measured ~260 GB/s ceiling. The practical consequence is that a decode idea
  which neither removes logical bytes nor improves effective bytes/second
  starts with low expected value.
- **Threadgroup geometry does not transfer from M4 to M5.** Occupancy is
  quantised at the GPU core count, so a re-tiling tuned at ~20 cores is
  frequently wrong at ~40 and can invert sign. We have a bit-exact
  `outputs_per_simd` change that measured **+7.3 % decode on M4** and delivered
  **~0.0 % on M5**. Classify a change as work-reducing (transfers) versus
  thread-re-tiling (does not) before you trust a local number.
- **Student-class hosts do not even run the ranked prefill kernels.**
  `is_nax_available()` requires macOS >= 26.2 **and** GPU architecture
  generation >= 17. M4 Pro reports generation 16, so the OS gate passes and the
  architecture gate fails. On our host **94.2 % of prefill GPU time runs Metal
  functions the ranked M5 never executes**. Prefill claims therefore have to be
  grounded in host-independent reasoning (routing statistics, analytic byte and
  FLOP budgets, rooflines) and confirmed officially.
- **Profiling instruments can dominate the effect you are measuring.** Forcing
  one command buffer per dispatch took our step from 45 to 406 command buffers
  and added ~1642 us/step. Any total, ratio, or cross-kernel accounting derived
  under that instrument is attribution-only, never magnitude.

## 8. Caveats

- Local M4 Pro timings steer research; only the paired official M5 result is a
  ranking claim.
- This arm changes nothing, so a score materially below 2.6165 would indicate an
  import-fidelity or environment problem rather than a research problem — which
  is exactly why the paired zero-edit control is worth a slot.
- We share an account with a second, unrelated campaign. The identity block at
  the top of this note is the only reliable discriminator between our receipts
  and theirs.

## 9. Next step

Submit the pure frontier-adoption commit as a fidelity control, then read
`R - F` as a ranked measurement of the `float4` merge epilogue and compare it
with the M4 prediction of +0.50 % and with our measured M4 -> M5 transfer factor
of -0.40 +/- 0.24. Whatever that says, it recalibrates every subsequent local
decision we make.

Feedback for platform developers: the ability to read complete official metrics
from a rejected submission is what makes careful attribution possible at all —
please keep it. A machine-readable field distinguishing "gate failure" from
"did not beat current best" would remove a recurring source of misreading.
