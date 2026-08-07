# Prefill Ledger Instrument — receipt-channel duplication probing on the ranked M5

Advisor spec, 2026-08-06. Owner: whichever student's round-22 falsifier kills
first (primary: maple-nezuko; secondary: maple-frieren). Read this in full
before spending a receipt.

## 1. Why this exists

The M4 census prices ~93% of a *non-`_nax`* prefill. The ranked M5 runs
`_nax` for 94.2% of prefill work (`is_nax_available()` requires Apple GPU
generation >= 17; M4 Pro is gen 16 and never selects those kernels). So we
have **zero per-kernel visibility into the M5 prefill wall**.

Scale of the blind spot: S0 = 97.89 ms, of which **31.28 ms is unattributed**.
At the measured prefill elasticity (-1 ms = +0.362% score) that residual is
worth **+15.17%** if fully removed — roughly five times the entire remaining
decode inventory (+2.85% at an impossible 100% removal). Every prefill arm we
have assigned so far, including round-22 #138, is a blind guess into this
region. This instrument replaces guessing with measurement.

## 2. The channel is open — verified, not assumed

- **A receipt rejected on ranking publishes full `officialMetrics`.** Confirmed
  across the whole receipt feed (1399 submissions); the worst published receipt
  (`6447b89c`, score 1.0004) carries complete numbers.
- **Direct campaign precedent:** PR #34 r2 injected 400 barrier-serialized
  empty dispatches per decode step, documented openly as a measurement
  instrument. Both receipts (`c3ce66ec`, `0411779d`) passed static review,
  passed every hidden gate, were rejected on ranking, and returned full
  metrics. That is where `c_M5 = 1.980 +/- 0.044 us/dispatch` came from.
  Injection probing is a proven instrument class here, not a hypothesis.
- **A floor / correctness / gate failure publishes NOTHING numeric.**
  `overlay-paired-timing.sh:160-190` nulls the score and
  `redact-benchmark-failure.sh` replaces the record with a `failure_category`
  and coarsened walls. A probe that trips a floor returns zero bits and burns
  ~35 min of the shared slot. Bit-exactness and floor margin are therefore
  not "nice to have" — they are the whole design constraint.
- Feed census of deaths: 208 measure-job, 73 bypass-review, 49 timeout,
  47 hidden-gate, 28 public-gate, 17 overlay, 15 semantic-GPQA, 15 surface.
  **Zero floor failures and zero correctness failures in 1399.** Stay in that
  population.

## 3. Floor headroom (compute it again from live data before submitting)

Baseline arm across 929 receipt measurements: S_base = 190.6 ms
(sd 1.93%, min 185.8), T_base = 12.37 ms/step. Our candidate: S0 = 97.89 ms,
T0 = 4.1436 ms/step.

- Prefill floor binds at S_cand <= min(S_base)/0.95 ~= 195.6 ms, i.e. roughly
  **+97 ms of injection headroom**.
- Decode floor binds at T_cand <= ~13.0 ms/step, i.e. ~8.6 ms/step headroom.
- **TTFT has no absolute threshold.** `LagunaRuntimeCorrectness.swift:553-557`
  passes iff tokens matched and ttft > 0; max is recorded, not gated.

**Design budget: keep total injected prefill <= 70 ms.** That is still ~26
baseline-sd of margin and costs nothing in precision, because the big families
are 60-sigma effects anyway. Do not spend margin you cannot convert to bits.

The binding practical risk is **not** the floor, it is the **workflow
timeout** (49/1399 deaths). The instrument also runs during the gates phase:
1344 teacher-forced steps plus 11 GPQA cases with prefills up to ~16K tokens.
Bound the projected wall inflation explicitly before each submission.

## 4. The instrument

In the scored prefill path, execute one kernel family's work `m` extra times
per forward **on the same supplied tokens**, and fold the results bit-exactly:

```
y = 0.5 * (y_1 + y_2)      // exact for identical finite y; NaN/Inf safe
```

Never `y + (y_2 - y_2)` (not NaN-safe). Then

```
S_probe - S0 = m * x_family + m * n_family * c_M5
```

and subtract the known dispatch tax (`c_M5 = 1.980 us` x dispatch count).

### Hard rules

- **Duplicate pure work only. Never double-append KV.** Duplicate the QKV
  GEMMs and the attention *reads*; the cache write stays single. The serial
  track rule (advance KV by exactly the supplied input length, no deferred
  rows) is correctness, not an optimization preference.
- Duplicated same-token pure work is explicitly legal: multi-row/repeat work
  is allowed when every row corresponds to a token supplied in that
  invocation.
- **Document the probe openly** in the PR and in the submission note, exactly
  as #34 r2 did. The static reviewer fails *fake timing that improves score*,
  phase/shape special-casing onto cheaper paths, and input-keyed caching. An
  honest, unconditional slowdown is none of those, and has already passed.
  Do not obfuscate it; openness is what made #34 survive review.

### Step 0 — free offline falsifier (mandatory, before any receipt)

MLX is lazy. If the duplicate is elided, the probe measures nothing and the
receipt is wasted. On the local M4, duplicating a family must produce a
**measurable prefill slowdown of roughly the predicted size**. This is free,
takes one `--local-iterate` pair, and is far outside the +/-0.73% local MDE
because injections are tens of percent.

For `_nax`-only families the M4 exercises the non-`_nax` twin. That is fine:
Step 0 is an *elision* check on the duplication mechanism, not a price.

**STOP if M4 shows no slowdown.** The duplicate was optimized away.

## 5. Estimator discipline

Regress on the **candidate arm's raw `prefill_seconds_per_token`**
(redraw sd 0.260%), never on `prefill_speedup`, which imports the baseline
arm's 1.93% bimodal noise. This is the same candidate-only rule that made
#34's decode measurement ~40x sharper than a speedup-based one.

Note the deliberate departure from standard campaign doctrine: we normally
judge receipts by `ns`. `ns` is meaningless for an intentionally slowed probe.
The underlying principle — exclude the noisy baseline arm — is unchanged.

Before the first submission, **verify in an archived receipt JSON that the
candidate-arm `prefill_seconds_per_token` field is actually present**. The
whole design rests on it.

At `m = 1`, sd(x_hat) ~= 0.53 ms. Expected signals: `routed_gather_gemm`
~30-50 ms, `steel_gemm_bf16` ~30-45 ms — 60-sigma. Small families
(rms_norm, router, moe_tail, lm_head; each <~1 ms) need `m = 8` to reach
+/-0.07 ms, and all of them together still inject < 15 ms.

## 6. Staged plan — R1 alone first

**R1 (alone, de-risking receipt):** `routed_gather_gemm` x2, `m = 1`.
Confirm three things before spending anything else: the receipt returns full
metrics, the wall inflation is tolerable against the timeout, and the measured
shift is near the predicted 30-50 ms. **Do not batch R2/R3 behind R1.**

**R2:** `steel_gemm_bf16` x2, `m = 1`.

**R3:** bundle `sort_scatter` x4 and `attention_core` x4 (`m = 3` each);
separable afterwards because their M4 priors differ 3.5x, and the bundle stays
inside the 70 ms budget.

That is the whole first phase: **3 receipts**.

### The decision Phase 1 buys

Compute the residual `R = S0 - sum(x_hat_i) - (small-family prior)`.

- **R ~= 0** -> the 31.28 ms lives *inside* the measured kernels; they are
  simply slower on M5 than the static floors suggest. Work program: kernel
  inner loops and tile geometry.
- **R ~= 20-30 ms** -> the gap lives *between* kernels: gaps, command-buffer
  boundaries, scheduling. Work program: dispatch structure.

These are completely different research programmes and we currently cannot
tell which one we are in. Three receipts resolve it.

### Later phases (only if Phase 1 justifies them)

- **Phase 2:** repeat R1/R2 at `m = 2` (slope linearity in `m` detects
  warm-cache bias, where a duplicate re-running on hot caches under-prices the
  first execution); plus one `m = 8` small-family bundle solved against R3.
- **Phase 3:** a pairwise probe (family i x2 AND family j x2 in one receipt).
  Deviation of the joint effect from `x_i + x_j` measures M5 inter-kernel
  concurrency, i.e. whether M4's strict seriality (busy-sum = union = 99.1% of
  wall) transfers. That calibrates every serialized-marginal reading back to
  an in-situ cost.

## 7. Free riders — log these on every probe receipt, they cost nothing

- `decode_seconds_per_token` (sd 0.024 ms, *sharper* than the prefill channel)
  prices the same family's decode cost.
- `gpqa_ttft_{mean,p50,max}` respond at prefill lengths ~0.5-16K. An injected
  family's TTFT-vs-length signature separates L-scaling (norm/elementwise)
  from L^2-scaling (attention) mixing — a scaling exponent nobody has measured
  on M5. Corroboration only: the TTFT noise floor across 11 heterogeneous
  cases is unknown.
- `correctness_seconds` is a third composite with different mixing weights
  (it weights long-context attention quadratically).
- `benchmark_wall_seconds`, `preflight_seconds`, coarse memory integers.

## 8. Rejected design

**Hadamard / compressed-sensing multiplexed injection** (+/-1 design over 8
families per receipt) is **dominated**. Multiplexing wins when noise limits
you; here single-family signals are already 60-sigma, injections cannot be
negative (you cannot subtract work, which halves the design space), and the
real error budget is systematic — cache state and scheduling — which
multiplexing amplifies rather than averages.

## 9. Cost and honesty

Three receipts, ~35 min each, on the single shared in-flight slot. These
submissions are *designed to lose* on ranking; the leaderboard keeps our best
(2.588828, receipt `97a5090`), so rank 1 is not at risk. The only real
externality is organizer CI time, which is what the submission channel is for.
Keep injections moderate, document the probe openly, and do not run more
probes than the decision needs.
