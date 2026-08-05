# PR #35 r2 deliverable A — pre-registration

Assignment `maple-2026-08-04j-scale-code-width`, revision `r2`, student
`maple-frieren`. Committed and pushed **before** any official submission in
this round, so the prediction, estimator, power, and falsification checks are
timestamped ahead of the data.

Base: `d18ebbb` (verified docs-only from the r2 anchor `279b6e24`;
`git diff --stat 279b6e24..d18ebbb -- Sources Vendor benchmark.json Package.swift`
is empty and `git diff --name-only 279b6e24..d18ebbb | grep -v '^research/'` is
empty).

Branch head under test: `b3e9387b5b6095cb822f4f098a5a639e231b979f`.

## 1. What A is for

A is **not** a bid for a score win. The mechanism in its current shipped form
is expected to be worth about +0.06% of score on M5, which is an order of
magnitude below the 0.61% acceptance bar. A exists to fill the
**byte-trading cell** of the M4 -> M5 transfer table, which currently reads
`unknown`. That cell prices at least three other candidate arms, so a clean
number is the deliverable.

The mechanism: attention decode NVFP4 scale planes re-encoded from 32 B per
32-group block to 21 B (`scale_nibbles` 16 B + `scale_high_bits` 4 B +
`scale_bases` 1 B), reconstructed in-kernel as
`code = base + nibble + (high_bit << 4)`. It trades **30.61 MB/step of DRAM
traffic** for a **bandwidth-independent in-kernel reconstruction cost**.
That is precisely a byte-trade, which is why it is the right probe.

## 2. Arms

Two official submissions, dispatched **back-to-back in one session**,
wall-clock times recorded.

- **ON** = branch head `b3e9387` unmodified. `DARKBLOOM_ATTN_SCALE_NARROW`
  defaults to enabled, and the official runner sets no environment variables,
  so the narrow planes are live.
- **OFF** = the identical tree with one line flipped at
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift:667-668`:

  ```diff
  -let lagunaAttnScaleNarrowEnabled =
  -    ProcessInfo.processInfo.environment["DARKBLOOM_ATTN_SCALE_NARROW"] != "0"
  +let lagunaAttnScaleNarrowEnabled =
  +    ProcessInfo.processInfo.environment["DARKBLOOM_ATTN_SCALE_NARROW"] == "1"
  ```

Ordering, if a second pair is affordable: ABBA (ON, OFF, OFF, ON) to cancel
linear session drift.

### 2.1 What the ON/OFF contrast actually contains

The contrast is "mechanism present vs absent", which is the right contrast for
scoring, but it is **not** purely "21 B vs 32 B in the steady step". With the
master flag false, `lagunaNarrowNVFP4ScaleBank`
(`LagunaRuntimeWeights.swift:726-734`) returns `nil` on its first guard, so the
OFF arm additionally:

1. never allocates the ~60 MB of narrow-plane MLX arrays
   (`peak_ram_gb` 20.7190 OFF vs 20.7213 ON; MLX active 33.38 vs 33.44 GB);
2. never JIT-compiles the two `_ns1` kernel variants
   (`LagunaRuntimeModel.swift:4344-4361`, `4792-4809`);
3. never runs the init-time reshape/min/index build or its MLX round-trip
   certificate.

Items 2 and 3 are outside the timed window. Item 1 is a residency difference
that is negligible on a 128 GB M5 but is the one confound this design cannot
remove. It is declared here rather than discovered later.

## 3. Estimator, and a retraction

**Primary statistic: `ns`**, the pinned-reference normalised score

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns              = norm_decode_su**0.75 * norm_prefill_su**0.25
```

**Retraction.** In the previous session I proposed the within-run paired ratio
`R = baseline_T / candidate_T` as a drift-cancelling estimator, on the strength
of two receipts agreeing to 0.027%. That was wrong. Those two receipts were
`A_f8502e12` and a *different tree* (`27b9c7c`), not a bit-identical pair, so
the agreement was coincidence. Recomputing across the three genuinely
bit-identical base free controls (`research/frieren_receipt_ratio.py`):

| statistic | mean | sd | cv | n |
|---|---|---|---|---|
| `ns` | 2.512856 | 0.001922 | **0.0765%** | 3 |
| `T` (steady step, ms) | 4.371793 | 0.010423 | 0.2384% | 3 |
| `S` (seed forward, ms) | 97.711000 | 0.254389 | 0.2603% | 3 |
| `T_base` | 12.364718 | 0.036178 | 0.2926% | 3 |
| `R = T_base/T` | 2.828318 | 0.015005 | **0.5305%** | 3 |
| `S_base` | 194.284889 | 4.581297 | 2.3580% | 3 |
| `RS = S_base/S` | 1.988390 | 0.048395 | 2.4339% | 3 |
| `officialScore` | 2.503493 | 0.015906 | 0.6353% | 3 |

`R` is **twice as noisy as raw `T`**, because the same-session baseline arm
carries its own independent noise (`T_base` cv 0.2926%) rather than acting as a
drift reference. The prefill ratio `RS` is worse still at 2.43%. The advisor's
standing instruction to rank on `ns` and never on a `*_speedup` field is
correct and I am adopting it here without modification.

For power I pre-register the advisor's more conservative, larger-n figure
**sigma(ns) = 0.149%**, not my n=3 value of 0.0765%.

## 4. Sensitivity and pre-registered predictions

The mechanism is decode-only, so prefill is unchanged and

```
d ln ns = -0.75 * d ln D,    D = (T + S/128) / 1000 s = 5.135160 ms
=> dT = -(5.135160 / 0.75) * d ln ns = -6.84688 ms * d ln ns
```

Score elasticity at the M5 operating point is `d ln score / d ln T = 0.638`,
so `d ln score = -0.638 * dT / T` with `T = 4.371793 ms`.

| hypothesis | dT/step | d ln ns | d ln score |
|---|---|---|---|
| `H_regression` | > 0 | < 0 | < 0 |
| `H_null` (no effect) | 0 | 0 | 0 |
| **`H_advisor` (primary prediction)** | **-4 us** | **+0.058%** | **+0.058%** |
| `H_bytes_only` (byte win at 651.8 GB/s, zero fixed cost) | -46.96 us | +0.686% | +0.685% |
| `H_transfer1_pureconfig` (tau = 1 vs the M4 pure-config screen) | -67.6 us | +0.987% | +0.986% |
| `H_transfer1_parity` (tau = 1 vs the M4 in-process parity A/B) | -95.3 us | +1.392% | +1.391% |

**The pre-registered point prediction is `H_advisor`: dT = -4 us/step,
d ln ns = +0.058%, score +0.06%.** Its derivation is 30.61 MB at the in-situ
651.8 GB/s = -46.96 us against a bandwidth-independent +43 us reconstruction
cost measured directly by the M4 `dummy` control.

## 5. Power, stated honestly before the fact

With sigma(ns) = 0.149%, one ON/OFF pair has
`sigma_diff = 0.149% * sqrt(2) = 0.211%`, i.e. **sigma(dT) = +/-14.4 us**.

| discrimination | separation | one pair | two pairs |
|---|---|---|---|
| `H_transfer1_parity` vs `H_null` | 1.392% | 6.6 sigma | 9.3 sigma |
| `H_transfer1_pureconfig` vs `H_null` | 0.987% | 4.7 sigma | 6.6 sigma |
| `H_bytes_only` vs `H_null` | 0.686% | 3.3 sigma | 4.6 sigma |
| `H_advisor` vs `H_null` | 0.058% | **0.28 sigma** | 0.39 sigma |

So one pair **can** decisively reject "the M4 byte win transfers to M5", and
**cannot** resolve -4 us from zero. This is declared up front: if the result
lands inside +/-0.21% I will report it as *consistent with `H_advisor` and
statistically indistinguishable from null*, and I will **not** claim to have
measured -4 us. The informative content is the upper bound on transfer, which
is what the transfer-table cell needs.

## 6. The reusable output: split the byte term from the fixed cost

A blended `tau = (dT/T)_M5 / (dT/T)_M4` is **not portable**, because M4 and M5
differ in both `T` (8.6432 vs 4.3718 ms) and bandwidth. The reusable form
separates the two terms:

```
F = dT + bytes / BW_eff          # bandwidth-independent fixed cost, us/step
bytes = 30.61 MB/step
```

M4 reference values, from `research/frieren-pr35-result.md`:

- pure-configuration between-process screen (**primary**, this is the shipped
  configuration): `dT_M4 = -67.6 +/- 7.9 us` on an 8.6432 ms step, `-0.782%`.
- in-process parity A/B (isolated mechanism): `dT_M4 = -95.3 us`, `-1.11%`.
- `dummy` control, directly measuring the reconstruction cost alone
  (32 B of stock bytes read through the narrow arm's 3-load pattern):
  **`F_M4 = +43 us`**.

Internal consistency of each M4 protocol, given `F_M4 = +43 us`:

| protocol | dT_M4 | implied byte win | implied BW_eff |
|---|---|---|---|
| pure-config | -67.6 us | -110.6 us | 277 GB/s (~M4 Pro peak 273) |
| parity A/B | -95.3 us | -138.3 us | 221 GB/s (~M4 achieved 209) |

Both are self-consistent; they bracket the effective bandwidth of scale-plane
traffic at **221-277 GB/s**. That is the honest resolution of the 28 us
protocol spread the advisor flagged: it is not one protocol being wrong, it is
genuine uncertainty in the effective bandwidth this traffic sees. Primary
remains pure-config, because it is the only protocol that pays every cost the
scored run pays.

**A will report:**

1. `dT_M5` and `d ln ns` with the pre-registered uncertainty;
2. `F_M5 = dT_M5 + 46.96 us` (in-situ 651.8 GB/s) and
   `F_M5 = dT_M5 + 50.18 us` (nominal 610 GB/s);
3. `F_M5 / F_M4 = F_M5 / 43`;
4. `tau_frac` against **both** M4 protocols, with the spread stated;
5. the byte-trading transfer-table cell as a sentence a future arm can use
   without rereading this document.

Prior expectation for (3): `F_M5 < F_M4`, because reconstruction is ALU and
issue work that scales with cores and clock, not with bandwidth, and M5 Max has
more of both than M4 Pro. If `F_M5 / F_M4` comes back near 1.0, that itself is
a finding: it would mean the reconstruction cost is not compute-bound.

## 7. Falsification and sanity checks, fixed in advance

- **Prefill invariance.** The mechanism is decode-only. `S` must be
  statistically identical between arms. `sigma(S) = 0.2603%` so
  `sigma_diff(S) = 0.368%`. If `|S_ON/S_OFF - 1| > 0.74%` (2 sigma) the arms
  differ by something other than the intended contrast and the pair is void.
- **Both floors.** `decode_speedup >= 0.95` and `prefill_speedup >= 0.95`
  reported for both arms.
- **Correctness.** Both arms must publish full metrics with correctness
  satisfied. A receipt with zero checked steps, null results, an `execvp` or
  permission error, or a thermal/preflight rejection is an **infrastructure
  no-result, not a datum**, and will be re-dispatched rather than reported.
- **Direction check.** `H_regression` (`d ln ns < -0.21%`) would contradict
  three independent M4 instruments and would be reported as a transfer-sign
  flip, not quietly averaged away.
- **Same-session requirement.** Any pair whose two arms land on opposite sides
  of a day boundary is uninterpretable (cross-day ranked drift ~0.3%) and will
  be discarded and re-run, not reported.

## 8. What A does not decide

A null on A **does not** cancel deliverable B (4-bit lane-major + per-row base
+ `0xFF` sentinel escape). B is a **transaction-count / load-instruction**
change, not a byte-count change: attention-qkvo QMV decode measures 802.16 MB
at 651.8 GB/s, i.e. 107% of nominal, so that traffic is cache-assisted and a
pure byte-rate model cannot see B's effect. B replaces twelve loads per row
with two, so its fixed cost amortises where this rung's does not. B proceeds
regardless of A's sign.
