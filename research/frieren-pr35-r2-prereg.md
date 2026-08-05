# PR #35 r2 deliverable A — pre-registration

Assignment `maple-2026-08-04j-scale-code-width`, revision `r2`, student
`maple-frieren`. Committed and pushed **before** any official submission in
this round, so the prediction, estimator, power, and falsification checks are
timestamped ahead of the data.

Base: `d18ebbb` (verified docs-only from the r2 anchor `279b6e24`;
`git diff --stat 279b6e24..d18ebbb -- Sources Vendor benchmark.json Package.swift`
is empty and `git diff --name-only 279b6e24..d18ebbb | grep -v '^research/'` is
empty).

Branch head under test: the pushed tip of `maple-frieren/scale-code-width`
containing **this revision of this document**, whose parent chain is
`528bc17` (merge of `d18ebbb`) -> `b3e9387`. The exact SHA is quoted in the PR
comment that requests the submission slot, and again in the result document.

**Revised 2026-08-05 for the one-receipt channel rule.** The first version of
this document specified a two-submission ON/OFF pair. The advisor's ranked
channel accepts exactly **one in-flight submission per account** and all four
students share `morganmcg1`; the standing policy is now that **no receipt may
carry a control arm**. Section 2 is rewritten accordingly: A is one receipt of
the candidate tree, differenced against the advisor's **permanent control**.
Sections 3, 4, 6 and 8 are unchanged in substance; sections 5 and 7 gain the
extra caveats an unpaired difference incurs.

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

## 2. Arms: one candidate receipt against the permanent control

**Candidate (the only submission).** The branch tip described above, unmodified.
`DARKBLOOM_ATTN_SCALE_NARROW` defaults to enabled and the official runner sets
no environment variables, so the narrow planes are live.

**Reference (already paid for).** The advisor's permanent control submission
`c3ce66e` (git commit `e82d6cf`, submitted 2026-08-05 09:33), **`ns = 2.544360`**.
No control arm is dispatched by me.

### 2.1 Why one receipt still isolates the mechanism

An unpaired difference is only a mechanism measurement if the reference tree is
the candidate tree minus the mechanism. That is the claim this section
establishes, because it is the design's single load-bearing assumption.

**(a) My editable diff against the current base is exactly two files.**
`git diff --stat d18ebbb..HEAD` over the submitted surface is
`Sources/MLXFastModel/LagunaRuntimeModel.swift` and
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`, `+360 / -17`.
`git diff --diff-filter=D --name-only d18ebbb..HEAD` is empty (verified after
merging `d18ebbb` forward), so I delete nothing the base ships.

**(b) The base scored surface has not moved since 2026-08-04 21:03, before the
control was submitted.**
`git log --date=iso d18ebbb -- Sources Vendor benchmark.json` has as its two
newest entries `279b6e2` (2026-08-05 09:30, "Fix competition research
mechanics") and `6f1289a` (2026-08-04 21:03, "[maple-fern] De-amplify the
decode attention core (#30)"), and
`git diff --stat eaedee84..279b6e24 -- Sources Vendor benchmark.json` touches
**only the two non-editable `LagunaRuntimeLocalIterate.swift` harness files**
(-116 lines). So the last change to the *scored editable* surface is
`6f1289a`, and the control's tree and `d18ebbb`'s tree carry the same scored
code.

**(c) The control's own public note says it is the inert base.**
`mlxfast submission-note c3ce66e` states "The final commit of the research
branch resets those literals to zero, at which point the file is byte-identical
to the promoted base and the instrument is inert", and tabulates
`injected empty dispatches per single-token decode step | 0`,
`injected dispatches per multi-token prefill forward | 0`, and
`~406 (unchanged)` dispatches.

**(d) The PR #27 hardware-constant instrument is present and inert in *both*
trees, not added by me.** `d18ebbb:Sources/MLXFastModel/LagunaRuntimeModel.swift`
line 10975 is `// BEGIN M5 HARDWARE-CONSTANT INSTRUMENT` and line 11223 is the
matching `// END`; in my head the same block sits at 11158-11406, shifted only
by my `+217` lines, and no hunk header in my diff enters that range. Every
injection literal is identical in the two trees and all are zero:
`DARKBLOOM_INJECT_PREFILL_MATMULS 0`, `DARKBLOOM_INJECT_DECODE_EMPTY 0`,
`DARKBLOOM_INJECT_PREFILL_EMPTY 0`. `DARKBLOOM_INJECT_EMPTY_TG` is 160 in my
head and 160 in the base, and it is read only when an injection count is
non-zero, so it is unreachable in both.

**(e) My diff adds exactly four environment reads, and three of them *are* the
mechanism.** All in `LagunaRuntimeWeights.swift`: `DARKBLOOM_ATTN_SCALE_NARROW`
(master, `!= "0"` so default **on**), `..._QKV` (on), `..._OPROJ` (on),
`..._LOG` (`== "1"` so default off). There is no `DARKBLOOM_SCALE_ALTERNATE`
anywhere in `Sources/`; the in-process parity harness was local-only and never
landed on this branch.

**Residual caveat, stated before the data.** `e82d6cf` is on another branch and
is not in my object store, so I cannot diff it locally. Claim (c) rests on the
control note's own assertion, corroborated by the independent commit timeline in
(b). If the advisor knows the control was built from a different base commit,
this design is void and I need a different reference.

### 2.2 What the difference contains beyond "21 B vs 32 B"

The contrast is "mechanism present vs absent", which is the right contrast for
scoring, but it is not purely a steady-step byte trade. In the reference tree
`lagunaNarrowNVFP4ScaleBank` (`LagunaRuntimeWeights.swift:726-734`) returns
`nil` on its first guard, so the reference additionally:

1. never allocates the ~60 MB of narrow-plane MLX arrays
   (`peak_ram_gb` 20.7190 off vs 20.7213 on; MLX active 33.38 vs 33.44 GB);
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

### 4.1 Conversion coefficient at the *control's* operating point

The table above uses `D = 5.135160 ms`, measured on the 2026-08-04 base. The
current base is faster, so the coefficient must be restated at the reference
receipt's own operating point. Inverting `ns` for the control at
`ns = 2.544360`, holding `S = 97.711 ms` (prefill is untouched by this
mechanism):

```
norm_prefill_su**0.25 = (0.0003845 / (97.711/512000))**0.25 = 1.191410
norm_decode_su        = (2.544360 / 1.191410)**(1/0.75)     = 2.749990
D                     = 0.013890 / 2.749990 = 5.050918 ms
T                     = D - S/128           = 4.287551 ms
=> dT = -(5.050918 / 0.75) * d ln ns = -6.734558 ms * d ln ns
```

That is a **1.6% shift** in the conversion factor (6.7346 vs 6.8469 ms), which
moves every `dT` in the table by 1.6% and moves `sigma(dT)` from +/-14.4 us to
**+/-14.2 us**. It is far inside the +/-20-25% systematic on the byte term
(section 6.1), so the hypothesis table is left as published and
**`dT = -6.734558 ms * d ln ns` is the conversion I will actually apply.**

## 5. Power, stated honestly before the fact

One candidate receipt differenced against one control receipt has **exactly the
variance of an ON/OFF pair**: both sides contribute one independent draw. With
`sigma(ns) = 0.149%`,

```
sigma_diff = 0.149% * sqrt(2) = 0.211%   =>   sigma(dT) = +/-14.2 us
```

| discrimination | separation | this receipt | + a second candidate receipt |
|---|---|---|---|
| `H_transfer1_parity` vs `H_null` | 1.392% | 6.6 sigma | 7.6 sigma |
| `H_transfer1_pureconfig` vs `H_null` | 0.987% | 4.7 sigma | 5.4 sigma |
| `H_bytes_only` vs `H_null` | 0.686% | 3.3 sigma | 3.8 sigma |
| `H_advisor` vs `H_null` | 0.058% | **0.28 sigma** | 0.32 sigma |

The last column assumes the control side stays at n=1, which is why replication
buys less than sqrt(2): the control's own 0.149% never averages away until the
advisor accumulates more control receipts. If the control ever reaches large n,
`sigma_diff` falls to 0.149% and `sigma(dT)` to +/-10.0 us.

So this receipt **can** decisively reject "the M4 byte win transfers to M5", and
**cannot** resolve -4 us from zero. That is declared up front: if the result
lands inside +/-0.21% I will report it as *consistent with `H_advisor` and
statistically indistinguishable from null*, and I will **not** claim to have
measured -4 us. The informative content is the **upper bound on transfer**,
which is what the transfer-table cell needs.

### 5.1 This is estimation, not hypothesis testing

An independent review of the design (frontier critique, 2026-08-05) made a point
I am adopting verbatim as a framing constraint: **no achievable replication count
separates the overlapping hypotheses at 3 sigma.** `H_advisor` is not a sharp
prediction of -4 us; it is -4 us with an uncertainty of **at least +/-8 us**,
inherited from the M4 `dummy` control's +/-7.9 us on its +43 us fixed term. That
interval already overlaps `H_regression` (`dT > 0`) and `H_null`. Chasing
significance against `H_null` is therefore the wrong objective.

The correct objective is to **estimate `dT_M5` with a stated interval** and
publish the decomposition in section 6, so that a future arm can price its own
byte trade. Accordingly:

- the headline number is `dT_M5` in us/step **with its confidence interval**,
  followed by `dT_M5 / T` as a percentage;
- no p-value or sigma count is reported *for* `H_advisor`; sigma counts appear
  only where they do real work, i.e. rejecting the large-transfer hypotheses;
- a result of `dT_M5 = -5 +/- 14 us` is a **successful** execution of A, not a
  failed one, because the transfer-table cell it fills is an interval, not a
  point.

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

### 6.1 Two systematics and one identifiability limit, declared in advance

**Systematic 1: average bandwidth is not marginal bandwidth (+/-20-25%).**
The 651.8 GB/s figure is an *average* over the whole decode step, derived from
802.16 MB of attention-qkvo QMV traffic. What the byte term needs is the
*marginal* value of the 30.61 MB actually removed. The two are not equal, and
the discrepancy is visible in my own M4 arithmetic: the 106% DRAM-traffic
transfer endpoint combined with `T_M4/T_M5 = 2.0` implies `v5/v4 = 0.53` and a
byte term of **-58.6 us**, whereas the in-situ 651.8 GB/s gives **-47.0 us**.
That is a 25% spread on the same quantity, and the fact that 651.8 GB/s is
"107% of nominal" is itself a hint that some of the counted traffic is being
served by SLC rather than DRAM, or is attributed differently by the counter.
I will therefore publish the byte term as **-47.0 +/- ~10 us** and carry that
interval into every derived quantity, rather than quoting -47.0 us as exact.

**Systematic 2: the sum is measured, the parts are not (under-identification).**
One net `dT_M5` constrains only the **sum** `-B*v5 + C5`, where `B` is the byte
count and `C5` the M5 fixed reconstruction cost. No amount of replication
separates them from this receipt alone. To break the degeneracy I will
cross-check the byte term against the receipt's own memory diagnostics
(`bytes_read` style fields in the published JSON) rather than treating the
in-situ bandwidth as ground truth.

**The reporting form, fixed now.**

```
primary   dT_M5  in us/step, with CI, plus dT_M5 / T as a percentage
byte term -47.0 +/- ~10 us  (assumptions listed above)
inferred  C5 = dT_M5 + 47.0 us            # the M5 fixed reconstruction cost
inferred  f_fixed = C5 / (43 +/- 8) us    # M5:M4 fixed-cost ratio
class rule  dT = -B' / BW_eff5 + f_fixed * C4'
```

The class rule is offered to future arms **only if `dT_M5 <= 0`**. A positive
`dT_M5` falsifies the additive decomposition itself, and in that case I will
report the raw `dT_M5` and nothing derived from it.

**`tau` is demoted to a footnote.** A scalar
`tau = (dT/T)_M5 / (dT/T)_M4` is unsound as a class predictor and I will not
present it as one. It is (i) mix-dependent - the transfer-table endpoints span
1.06 for DRAM traffic and 0.01 for dispatch overhead, two orders of magnitude,
so a blended `tau` is meaningless without the mix; (ii) arithmetically
contaminated - relative normalisation bakes `T_M4/T_M5 = 2.0` into the ratio, so
a purely fixed cost scores `tau = 2.0` by arithmetic alone; and (iii) unstable -
the net effect here is ~8% of the byte term, so `tau` changes sign under small
perturbations of either term. It will appear once, labelled mix-specific and
non-transferable, and the `F`/`f_fixed` decomposition is what I ask future arms
to reuse.

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
- **Same-day requirement.** The control receipt is dated 2026-08-05 09:33.
  Cross-day ranked drift is ~0.3%, i.e. larger than every effect below
  `H_bytes_only`. If my receipt lands on a later calendar day I will report the
  difference with an explicitly widened interval and flag it, and I will not use
  it to reject anything smaller than `H_transfer1_pureconfig`.

### 7.1 Confounds this design cannot remove

Pairing removes some between-receipt variance; an unpaired difference against a
fixed control removes none of it. These are the residuals, listed so that the
result document does not get to discover them late:

1. **Between-receipt drift.** The two receipts are hours apart on the ranked
   host, not back-to-back. There is no ABBA structure to cancel a linear trend,
   so any real drift enters the difference at full weight. This is the single
   largest cost of the one-receipt rule and it is a channel constraint, not a
   design choice.
2. **Arm-dependent thermal coupling.** The candidate is ALU-hotter in attention
   than the control, so the two trees do not leave the host in the same thermal
   state. Estimated at 0.01-0.1%, which is negligible against
   `H_transfer1_*` and **material at `H_advisor` scale** (0.058%). It is a
   second reason `H_advisor` cannot be resolved here.
3. **Flip-inertness is assumed, not proved.** The default-on flag is compiled
   into both trees, but the two trees are not the same binary: inlining, code
   layout, and Metal function-constant specialisation of shared kernels can each
   move a few microseconds, which is exactly `H_advisor` scale. Additional
   narrow pipelines can also evict kernel cache entries. None of this affects
   the large-transfer rejections.
4. **Artifact identity.** Both receipts must load the same pinned weight files.
   The official runner supplies them, so I assert rather than verify this, and I
   record the assertion.
5. **sigma estimation.** `sigma(ns) = 0.149%` is the advisor's larger-n figure,
   deliberately chosen over my own n=3 value of 0.0765% precisely because a
   3-point sd has a 95% interval spanning roughly half to several times the true
   sigma. If the true sigma is larger than 0.149%, every sigma count above is
   optimistic in the same direction.

## 8. What A does not decide

A null on A **does not** cancel deliverable B (4-bit lane-major + per-row base
+ `0xFF` sentinel escape). B is a **transaction-count / load-instruction**
change, not a byte-count change: attention-qkvo QMV decode measures 802.16 MB
at 651.8 GB/s, i.e. 107% of nominal, so that traffic is cache-assisted and a
pure byte-rate model cannot see B's effect. B replaces twelve loads per row
with two, so its fixed cost amortises where this rung's does not. B proceeds
regardless of A's sign.
