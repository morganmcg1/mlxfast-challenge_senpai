# r97-d preregistration — direct falsification test of rule 58

- **PR**: #531 · assignment `maple-r97-d-rule58-factor4` · revision `r97-d-rev1`
- **BASE_SHA**: `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`
- **Host**: AWS M4 Pro, 48 GiB unified memory (`hw.memsize = 51539607552`)
- **Committed before any timing run.** No timing data existed when this file was
  written; the only prior work was source reading.

---

## 0. Correction to the assignment's predicted response ratio: it is 4, not 16

The assignment brief asks me to test that the response ratio
`Δdecode_per_step / Δprefill_per_token` equals **16**, and predicts
`+62.5 µs/step` at `Δ = 2 ms`. **Both numbers are wrong by a factor of 4.** The
factor 4 is applied twice. The correct H58 prediction is **ratio = 4** and
`+15.6 µs/step`.

Derivation. Let `S` = seconds for one 512-token forward, `T` = steady per-step
decode seconds. From the trusted harness (verified below):

```
P = prefill_seconds_per_token = S / 512
D = decode_seconds_per_token  = (S + 128·T) / 128 = S/128 + T = 4P + T
```

Rule 58's identity `D = 4P + T` is exactly the statement that
`ΔD = 4·ΔP` when `T` is held fixed. So the response ratio **is the factor
itself**:

```
inject Δ seconds into every multi-token forward
  ΔP = Δ / 512
  ΔD = Δ / 128
  ΔD / ΔP = (Δ/128) / (Δ/512) = 512/128 = 4
```

The brief writes `ΔD = 4·Δ/128 = Δ/32`, i.e. it multiplies the already-included
factor 4 by 4 again. Its own stated `ΔP ≈ 3.9 µs/token` at `Δ = 2 ms` is
correct, and `4 × 3.9 = 15.6 µs/step`, not `62.5` — the brief is internally
inconsistent with itself, which is the tell.

Interpretation of the measured ratio, which is the useful general form:

```
R = ΔD/ΔP = (seed tokens charged into the decode window) / (decode steps)
          = charged_seed_tokens / 128
R = 4  ⇒ all 512 seed tokens are charged   (H58 true, rule 58 exact)
R = 0  ⇒ no seed prefill in the decode window (H0)
```

**This correction is not a loosening of the suggested bar.** Testing against the
brief's 16 would have guaranteed a spurious "rule 58 REFUTED" verdict and
triggered an unnecessary programme-wide re-pricing. My registered bar is
strictly *harder* than the brief's: I require the CI to contain 4, exclude 0,
**and additionally exclude 16**, so the brief's own hypothesis is explicitly
falsified rather than silently dropped, and I require a CI half-width tighter
than ±20 %.

## 1. Verified harness facts (re-verified at this base, not assumed)

Official path, `Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift`:

| fact | evidence |
|---|---|
| prefill timed window = one IPC round trip around one worker `prefill` | `:809` start, `:810` call, `:811` elapsed |
| prefill divisor = `promptTokens.count` = 512 | `:837`; `Constants.swift:94` |
| prefill warmup runs = 0, timed runs = 1, no min/median/trim | `Constants.swift:129-130`; mean over a 1-element array at `:836` |
| **decode start clock captured BEFORE `beginDecode`** | `:966` start, `:968` `worker.beginDecode(seedTokens:)` |
| decode divisor = 128, seed tokens = 512, seed tokens NOT added to divisor | `:1013`; `Constants.swift:109`, `:123` |
| decode window = seed forward + 128 steps, single window, no warmup/repeat | `:966 → :1010` |
| worker `decode_begin` runs exactly one whole-prompt seed forward, no warmup | `LagunaRuntimeWorker.swift:383-408` |

So `D = 4P + T` holds **by construction of the trusted harness arithmetic**.
This preregistration tests it *empirically end-to-end*, which is a different and
stronger claim: it also proves that the injected work actually lands in both
windows and that nothing else (async deferral, IPC, allocator) breaks the
identity.

Measurement path I will actually use, `LagunaRuntimeLocalIterate.swift`
(`--local-iterate`) — **structurally identical**, which is why it is a valid
instrument for this question:

| fact | evidence |
|---|---|
| `decodePhaseStart` before `beginDecode`; seed charged to decode | `:583`, `:588`, `:590-591` (`"(charged to decode)"`), `:653` |
| decode divisor = `decodeSteps × timingRepeats`, `decodeSteps = 128` | `:674`, `:713`; `Constants.swift:113` (`localIterateBenchmarkDecodeSteps = benchmarkDecodeSteps`) |
| prefill divisor = `promptTokens.count × timingRepeats` | `:672` |
| prefill and decode use the **same** `localCase.promptTokens` | `:121`, `:133` |
| `timingRepeats` default 1 | `LagunaRuntime.swift:272` |
| local-iterate requires the participant **worker** path | `:140-144` |

⚠️ The non-official in-process pair (`measurePrefillSecondsPerToken` `:712-776`,
`measureDecode` `:843-944`) is compiled out of the trusted target by
`.define("MLXFAST_TRUSTED_HARNESS")` (`Package.swift:78-81`) and cannot produce
any number I report. Every number in my writeup will come from the worker path,
evidenced by the `"...decode measured start ... includes_seed_prefill=true"` and
`"prefill measured start prompt_tokens=..."` progress lines in the run log plus
the `score.local-iterate.json` artifact.

**Registered prediction is parameterised, not hardcoded to 4.** I will read the
actual `prompt_tokens=` and `decode_steps=` from each run log and register the
prediction as `R = prompt_tokens / decode_steps`. If the local golden case is
512 tokens (expected), `R = 512/128 = 4`. If the harness reports anything else,
the predicted `R` moves with it and I will say so explicitly. This protects the
test from a fixture assumption.

## 2. The instrument: already committed, default-inert, no patch needed

The assignment expected me to write an injection patch. **I do not need to** —
a complete, default-inert, output-neutral prefill work injector already exists
in the scored runtime at this base, and it is exactly the right shape:

| item | location |
|---|---|
| hook call site, inside the 40-layer loop | `LagunaRuntimeModel.swift:9128` |
| hook body | `:9511-9556` |
| **prefill-only branch** (`isSingleTokenDecode ? 0 : lagunaInjectPrefillMatmuls`) | `:9515-9516` |
| predicate source (`inputs.dims(1, 1)`) | `:9084` |
| knob `DARKBLOOM_INJECT_PREFILL_MATMULS`, default 0 | `:9373-9374` |
| injected op: `matmul(scratch.matA, scratch.matB)` | `:9535` |
| shapes: 512×8192 @ 8192×2048 bf16 | `:9409-9411` |
| spread evenly over 40 layers | `lagunaInjectShare` `:9501-9506` |
| `lagunaInjectActive` false when all knobs 0 ⇒ fully inert | `:9507-9509` |

**Consequence: my submitted diff to `Sources/` is exactly zero bytes.** The
instrument ships already, inert, and I select it purely by environment variable
on the command line. `DARKBLOOM_` is one of the prefixes the worker environment
sanitiser passes through (`LagunaRuntimeWorker.swift:1928-1958`), so the knob
reaches the model inside the worker subprocess and nothing else research-specific
does. No rebuild, no code-layout confound, and every arm runs a **byte-identical
binary** — which is a materially better design than the patch the brief asked
for. I will not delete the instrument block.

**Output neutrality is structural, not empirical.** `lagunaInjectLayerWork`
appends the matmul result to a local `pending` array and calls `asyncEval`
(`:9535`, `:9555`). The result is never read, never combined with `h`, and the
function returns `Void`. There is no path by which it can perturb the token
stream. I still verify bit-exactness empirically (Gate 0b) rather than relying
on this argument alone.

### Rule 64 statement (required): this is nowhere near the free-ALU region

Each injected matmul is `2·M·N·K = 2·512·2048·8192 = 17.18 GFLOP`
(`lagunaInjectMatmulFlops`, `:9416`), i.e. **8.59 G fma per injected matmul per
prefill call**. Rule 64's free budget is ≈96 fma per K iteration per thread. The
injection is roughly **eight orders of magnitude** above any knee and is
deliberately, measurably expensive. **Nobody may cite this arm as a free-region
or ALU-price measurement.** It is a timer-topology instrument only. The
conclusion it produces — the factor in `D = R·P + T` — is *harness arithmetic,
not GPU physics*, so it transfers M4→M5 even though every µs price in this
writeup does not. Rule 66 applies to prices, not to this ratio; I quote the
bound `|T| < 0.5` and no point estimate.

## 3. Design (rule 56: which design answers which question)

**A within-run randomised ladder is impossible for this question, and I register
that up front rather than discovering it later.** Two independent reasons:

1. `lagunaInjectPrefillMatmuls` is a `private let` global read once from the
   environment at process init (`:9373`). The rung cannot change inside a run
   without a source patch.
2. More fundamentally, `--local-iterate` emits **exactly one** `D` and **one**
   `P` per run (single windows, `timingRepeats = 1`). The unit of analysis is
   therefore necessarily the *run*. There is no within-run replication to block
   over.

So the brief's suggested "#497 blocked randomised within-run ladder, SE 1.34
µs/step" does not apply to this estimand, and its quoted SE is not available
here. I register the correct design instead:

**Stage 0 — calibration and Gate 0 (switching-free, one process per rung).**
`research/decode_probe.py --prefill --steps 128`, which drives the built worker
directly and separately reports: the standalone 512-token prefill window, the
`decode_begin` seed-forward window, and every individual step time. ~1.5 min per
run vs ~5 min for `--local-iterate`. Purposes:
- measure `Δ` per unit rung, to size Stage 1's rungs;
- Gate 0a leakage evidence (per-step times at max rung vs rung 0);
- Gate 0b bit-exactness (teacher-forced divergence count, token dump hash);
- a **direct** `S`/`T` decomposition, letting me reconstruct
  `D_pred = S/128 + mean(T)` and compare it against the harness-reported `D`.
  This is an independent second route to the same conclusion.

**Stage 1 — the primary ratio estimate (blocked randomised, run-level).**
`--local-iterate` via `research/run_local_benchmark.sh` (which fixes this host's
frozen GPU die sensor). 4 rungs `{0, r, 2r, 4r}`, order randomised within each
block from a fixed seed (93), ≥3 blocks. Every arm is the same binary, selected
only by `DARKBLOOM_INJECT_PREFILL_MATMULS`.

**Rung sizing rule, registered now:** choose `r` from Stage 0 so the predicted
top-rung `ΔD ≥ 250 µs/step` (≈5 % of `D`), keeping every rung ≤ 40 so
`lagunaInjectShare` spreads at most one matmul per layer.

**Estimators.**
- Per-rung paired deltas vs the rung-0 mean, giving a ratio at each rung
  independently. Nonlinearity in `Δ(n)` cancels in a per-rung ratio, so this is
  robust even if the injected cost is not linear in `n`.
- Primary: OLS **slope through the origin** of `ΔD` on `ΔP` over all rungs.
- CI: nonparametric bootstrap resampling **blocks** (4000 resamples, seed 93).
- I will *not* regress `D` on `P` directly across runs. Shared per-run thermal
  state induces a common-mode correlation whose own slope is ≈ `D/P` ≈ 26, which
  would bias that estimator upward. Fitting `D~n` and `P~n` separately and
  ratioing the slopes keeps the nuisance in the residual of each.

## 4. Registered bars

**GATE 0a — prefill-only (terminal if it fails).** The injected work must fire
zero times during single-token decode steps. Evidence: the source predicate at
`:9515-9516`, **plus** empirical proof that the mean steady step time at the max
rung differs from rung 0 by less than **1 % of the injected Δ** and is within
3 SE of zero. Leakage would multiply the decode response by 128 and produce
`R ≈ 512`, so an observed `R ≈ 4` is itself corroborating evidence.

**GATE 0b — bit-exact / output-neutral (terminal if it fails).** At every rung:
zero teacher-forced divergences in the probe, identical generated-token SHA-256
across all rungs, and `--local-iterate` `metrics.passed_correctness == true`
with the full checked-step count.

**PASS — rule 58 CONFIRMED.** The 95 % CI of the slope-through-origin `R`
- contains the predicted `prompt_tokens / decode_steps` (expected 4), **and**
- excludes 0, **and**
- excludes 16 (the brief's value), **and**
- has half-width < 20 % of the prediction, i.e. CI ⊂ [3.2, 4.8] when the
  prediction is 4.

**FAIL — rule 58 REFUTED.** The CI excludes the predicted ratio. Report
immediately and loudly, before polishing, including the corrected effective
prefill weight and corrected `% score per ms of prefill`.

**AMBIGUOUS.** CI contains both 0 and the prediction, or half-width ≥ 20 %.
Then chase the instrument, not more replicates.

## 5. Power

`D ≈ 4894 µs/step` on this rig. I have no committed prior for the run-to-run SD
of `--local-iterate` `D`; I register the conservative assumption **CV ≤ 1.5 %**
(SD ≤ 73 µs/step). With a top-rung `ΔD ≈ 300 µs` and 3 blocks, the per-rung
paired SE is ≈ 60 µs ⇒ `t ≈ 5`, and the 4-rung slope is tighter still. `ΔP` at
the top rung is ≈ 20-40 % of `P`, far above any plausible prefill noise, so the
ratio's precision will be dominated by the decode axis. If the realised SD
exceeds this assumption I will add blocks until the ±20 % half-width bar is met
or the ~4 h budget is exhausted, and report which.

## 6. Scope, budget, and what I will not do

- **Submitted-surface diff: 0 bytes.** The instrument is already committed and
  inert; I change no file under `Sources/` or `Vendor/`. I will still run
  `senpai/check-editable-budget.sh` and report the numbers. Headroom at base:
  100,524 B of 3,000,000.
- Research-only files: `research/frieren-r97-rule58-preregistration.md` (this
  file), `research/frieren-r97-rule58-result.md`, and the driver/analysis
  scripts. The brief also asks for
  `research/frieren-r97-rule58-inject.patch`; since the instrument needs no
  patch, I will instead ship a short reproduction recipe in the result file and
  say so explicitly rather than fabricate an empty patch.
- No `--local-submit`, no official receipt for this arm (per the brief; rule 63
  makes the ranked channel a strictly worse instrument here).
- I will not delete the injection block.
- One model-holding process at a time; 40 C thermal gate honoured on every run.

## 7. W&B

Project `mlxfast-maple`, entity `wandb-applied-ai-team`. One run per rung plus a
summary run, logging at minimum `rule58_response_ratio`,
`rule58_delta_decode_us_per_step`, `rule58_delta_prefill_us_per_token`,
`gate0_prefill_only`, `gate0_bitexact`, and the raw per-run table.
