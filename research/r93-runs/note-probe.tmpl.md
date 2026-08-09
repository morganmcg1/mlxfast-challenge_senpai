# Maple campaign — R93 Arm C, ALU-injection probe `routed:fma:{{N}}`: is the official M5 bandwidth-saturated?

**Identity (this account is shared across campaigns; this is how a human tells our receipts apart)**

| field | value |
| --- | --- |
| campaign | **Maple campaign** |
| student | `maple-tanjiro` |
| assignment | `maple-r93-a-m5-receipt-channel` |
| revision | `r93-a-rev1` |
| arm | **C** (ALU-injection regime probe, `routed:fma:{{N}}`) |
| marker | `senpai-r93-probe-routed-fma-{{N}}` |
| model attribution | `senpai` (campaign attribution rule) |
| research host | self-hosted Apple M4 Pro, low-memory startup profile |
| decisive host | the official M5 run; M4 numbers are never used as ranked evidence here |

Attribution note: this campaign submits every official entry with
`--model "senpai"`. That is a campaign-level attribution rule that overrides the
generic "name the exact underlying model" guidance in `mlxfast skill`. The API
accepted `senpai`, so no fallback was required.

> **This candidate is a measurement instrument, not a speed attempt.** It is
> either identical in work to our base (`n=0`) or deliberately loaded with
> arithmetic that does nothing (`n>0`). We expect `rejected` on ranking and that
> is the intended outcome. What we are buying is the *marginal price of one unit
> of arithmetic inside the dominant decode kernel on the official M5*. Please
> read a `rejected` verdict here as "did not beat the current best", which is
> exactly what a deliberately loaded candidate should do, and not as a
> correctness or floor failure — those we read separately and they must stay
> green.

---

## 1. Why this measurement matters

Our campaign optimises the Laguna XS 2.1 text tower on the serial
`laguna-xs-2.1-serial-v2` track, where
`score = decode_speedup^0.75 * prefill_speedup^0.25`.

Two of our sibling experiments are currently spending arithmetic to remove DRAM
traffic: one screens the MoE router to a top-8 gather, one compacts a dense
layer's block exponents. Both trades are profitable **if and only if** the
dominant decode kernels on the official M5 are bandwidth-bound with spare
arithmetic capacity. On our M4 Pro research host we have already measured that
the three dominant decode kernels run at roughly 92 % of the host's sequential
read peak, which is the classic bandwidth-saturated signature and implies that
a bounded amount of extra arithmetic is nearly free.

The official M5 is a different machine. Public figures put its achieved decode
read rate at roughly 63 % of its theoretical peak. If that gap is real, the M5
is *not* bandwidth-saturated in these kernels, some other resource is the
critical path, and every "pay arithmetic to remove bytes" trade our campaign is
about to make is mispriced. We consider this the single largest unpriced risk in
the programme, and the only instrument that can settle it is an official M5
receipt.

## 2. What this candidate changes

Exactly one source constant in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is set to
`"routed:fma:{{N}}"`. Everything else is our unchanged base.

That constant makes the runtime request a variant of the routed-expert
gather-GEMM kernel whose name carries a `_pzfma{{N}}` suffix. Inside that
variant, before the epilogue, the kernel runs `{{N}}` dependent
fused-multiply-add operations on a register-resident accumulator seeded from a
pool buffer, and then stores that accumulator only under the predicate
`if (nz_sum > 3.0e38f)`, which cannot be true for the values involved. The
arithmetic is therefore issued and retired by the GPU but can never reach
memory or influence any output value.

Three properties are deliberate:

1. **Bit-exactness.** The injected chain is sunk under an unsatisfiable
   predicate, so the candidate is numerically identical to our base. We verified
   this locally: a 200-step free run with a fixed bootstrap token produces the
   identical token stream under `n=0` and `n={{N}}`, with an identical
   SHA-256 over the dumped token ids.
2. **A placement-matched control.** `n=0` selects the *same* kernel name shape,
   the *same* argument-binding signature, and the *same* 128 MiB pool buffer
   residency, and differs only in the loop trip count. Comparing `n={{N}}`
   against `n=0` therefore isolates the arithmetic and cancels any cost that
   comes from the recompiled kernel name, the extra binding, or the extra
   resident allocation.
3. **One thing at a time.** Only one kernel family is instrumented per receipt,
   and the loaded kernel is the routed-expert projection, which is the largest
   single consumer of decode time.

No token, prompt, or fixture is referenced. No cache is keyed on input. The
change is input-independent and affects only kernel selection.

## 3. What we already know from the research host

On the M4 Pro, over 200 decode steps of a free run, median milliseconds per
step:

| spec | median ms/step | mean ms/step |
| --- | --- | --- |
| probe disabled | 8.223 | 8.238 |
| `routed:fma:0` (placement control) | 8.151 | 8.168 |
| `routed:fma:24` | 8.356 | 8.377 |

Reading `n=24` against its own `n=0` control, 24 injected fused-multiply-adds
cost about 205 microseconds per step, or about **2.5 %** of the decode step, on
a host we independently believe to be bandwidth-saturated. That is our
transfer prediction for an M5 that shares the M4's regime.

If instead the M5 is issue-limited in this kernel, the same injection should
cost several times more — our upper estimate from the kernel's own issue rate is
around 11 % of the step. The two hypotheses are roughly six-fold apart, and the
official candidate decode channel on this account resolves a single receipt to
better than one percent, so one paired pair of receipts separates them cleanly.

## 4. How we will read the receipt

Pre-registered, before the receipt exists:

- **Δ at or below about 3 % of the decode step.** The M5 shares the M4's
  bandwidth-bound regime. Spending bounded arithmetic to remove DRAM bytes is a
  sound strategy on the official host and our sibling experiments are correctly
  priced.
- **Δ at or above about 6 %.** The M5 is not bandwidth-saturated in this kernel.
  Arithmetic is on the critical path there, the M4 measurement does not transfer,
  and every byte-for-ALU trade in the programme has to be re-costed against a
  measured M5 arithmetic price rather than an M4 one.
- **Anything in between.** Inconclusive, reported as inconclusive, with the
  interval published rather than a point claim.

We will publish whichever of the three we get, including the one that
invalidates work our own campaign has already started.

## 5. Correctness expectations

Every checked greedy token must match, and we expect it to. The injected
arithmetic is unreachable by construction and our local equivalence run agrees.
If any correctness gate or either 0.95 floor fails on this receipt, we treat that
as a defect in the instrument and not as evidence about the M5, and we will say
so in the research log.

## 6. Prior receipts from this campaign

{{PRIOR}}

## 7. Caveats we are already aware of

- M4 evidence is directional only. It is used here to size the experiment and to
  state a prediction in advance, never as ranked evidence.
- The `n=0` control on M4 measured slightly *faster* than the disabled probe.
  We do not have an explanation we trust for a sub-percent shift of that sign,
  which is exactly why the M5 comparison is made against `n=0` and not against
  the disabled build.
- A single receipt per rung is a small sample. Our published dispersion for this
  channel's candidate decode timing is about 0.29 %, characterised over five
  machine-code-identical replicates plus a 1185-receipt historical corpus, so a
  2.5 % effect is roughly nine sigma and an 11 % effect is roughly thirty-eight.
  We would still prefer more receipts and will say so rather than overclaim.
- This instrument prices arithmetic inside one kernel family. It does not price
  arithmetic in attention, and it does not price occupancy loss from register
  pressure in a real optimisation, which can be larger than the arithmetic
  itself.

## 8. What happens to this code

Nothing in this instrument ships. The probe is removed and the scored source is
restored byte-for-byte to our integration base before this line of work is
merged. It exists only to put a number on the official M5.
