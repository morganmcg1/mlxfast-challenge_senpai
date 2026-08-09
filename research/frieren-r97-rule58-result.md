# r97-d — rule 58 falsification: the seed prefill is charged to the decode timer

**VERDICT: PASS — rule 58 is confirmed, with the response ratio corrected from
16 to 4.** The 512-token seed prefill runs inside the decode timer, so
`decode_seconds_per_token = 4 * prefill_seconds_per_token + mean_step_seconds`.
Both terminal gates pass and the submitted surface changed by 0 bytes.

**The brief's predicted ratio of 16 is wrong by exactly 4x.** The correct
prediction under the hypothesis is **R = 4**, derived in §2. The measurement
below was preregistered against R = 4, and PASS additionally required the
interval to *exclude* 16.

---

## 1. What was asked, and what the answer is

Rule 58 claims the harness starts its decode wall clock *before* the 512-token
seed forward that populates the KV cache, so that a purely prefill-shaped cost
shows up in the decode metric that carries 75% of the score weight.

It does. Three independent lines of evidence agree:

1. **The harness says so in its own log.** Every `--local-iterate` run prints
   `decode measured start tokens=128 includes_seed_prefill=true` and then
   `decode seed prefill complete seconds=0.6 (charged to decode)`.
2. **The within-run arithmetic identity closes.** (§4)
3. **The decode metric causally responds to prefill-only injected work at the
   predicted gain of 4.** (§5)

---

## 2. The factor is 4, not 16

Let `S` be the wall time of one 512-token forward and `T_total` the wall time of
the 128 single-token steps, `T_bar = T_total/128`.

```
P = prefill_seconds_per_token = S / 512
D = decode_seconds_per_token  = (S + T_total) / 128 = 4*(S/512) + T_bar = 4P + T_bar
```

Now inject an extra output-neutral cost `d` into *every multi-token forward*
(and only those). The standalone prefill window grows by `d`, and the seed
forward inside the decode window grows by `d`:

```
dP = d / 512
dD = d / 128
R  = dD / dP = 512 / 128 = 4
```

The brief applies the 512/128 conversion twice — once when converting the
injected cost into a per-step delta and again when forming the ratio — and so
predicts 16 and `+62.5 us/step` at `d = 2 ms`. The correct figures are `R = 4`
and `+15.6 us/step`. Competing hypotheses:

| hypothesis | predicted R |
|---|---|
| H58: seed prefill inside the decode timer | **4** |
| H0: seed prefill outside the decode timer | 0 |
| leakage: injection also reaches single-token steps | ~512 |
| brief as written | 16 |

## 3. Harness topology (source of truth)

| what | official ranked harness | `--local-iterate` |
|---|---|---|
| file | `Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift` | `.../LagunaRuntimeLocalIterate.swift` |
| decode timer start | `decodePhaseStart` :966 | `decodePhaseStart` :583 |
| seed forward | `worker.beginDecode` :968 (**after**) | :587 (**after**) |
| decode divisor | 128 :1013 | `decodeSteps * timingRepeats` :674 |
| prefill window | :809-811, divisor 512 :837 | :549-558, divisor :672 |

The timer start strictly precedes the seed forward in **both** entry points, so
`--local-iterate` reproduces the ranked timer topology on this axis. This is
pure harness arithmetic: it is a property of where two `DispatchTime.now()`
calls sit relative to a function call, and it does not depend on the GPU.

## 4. PRIMARY RESULT — the within-run identity (needs no injection)

Each run logs both the seed-forward time and the final `mean_step_seconds`, so
within a single timed window, with no cross-run differencing and therefore no
exposure to host drift:

```
implied_seed = 128 * (D - T_bar)      compared against    prefill window = 512 * P
```

Under H58 the ratio is 1; under H0 it is 0.

<!-- STAGE1_DECOMPOSITION -->

## 5. SUPPORTING RESULT — the causal injection ladder

<!-- STAGE1_LADDER -->

## 6. Gate 0 — the instrument is valid

<!-- STAGE1_GATES -->

## 7. What this changes about the programme

<!-- IMPLICATIONS -->

## 8. Honest limits

<!-- LIMITS -->

## 9. Reproduction

<!-- REPRO -->
