# R118-A, second ask: is prefill adjudicable at all? — **Partly. Fern's conclusion is right for the wrong reason, and the right reason is stronger.**

maple-tanjiro, 2026-08-11, PR #709 comments 2 and 3. Half a page as asked, plus the
threadgroup counts you asked me to print.

## The yes-or-no

**Close A1 / A2 / A3 / A4. But do not close prefill.**

The discriminator is not *prefill vs decode* and it is not *noisy vs quiet*. It is
**NAX-gated vs not**, and for my queue specifically the answer is not statistical at
all:

> `is_nax_available()` is **false** on this host (`applegpu_g16s`, generation 16 < 17),
> so **no `_nax` kernel is ever selected here**. Every arm in A1–A4 changes only
> `_nax` tile/geometry selection. The code those arms edit **does not execute on this
> machine.** (`research/maple-tanjiro-r110/GATES.md:391`, and the six AOT-instantiated
> tuples at `steel_gemm_fused_nax.metal:23-29`.)

That is a *deterministic* unmeasurability, not a coin flip. A coin flip you can beat
with more samples; this you cannot beat with any number of local runs, because the
local run is not a noisy measurement of the ranked quantity — it is a measurement of a
**different kernel**. So fern's operational conclusion for my queue is correct and I
endorse it, and I am giving you a stronger justification than hers: more official
draws would not fix it either, because the receipt's per-draw sd is 0.4938 % against a
τ-corrected arm of a few tenths of a percent.

## Where I disagree with the general form of the claim

Fern's argument as written generalises from "the ranked host's baseline prefill leg
carries cv 1.9327 %, i.e. 87 % of leaderboard variance" to "a prefill arm can be fired
but never verified". The second clause does not follow from the first, because
**verification does not have to happen on the ranked host.** Alphonse's +0.45 % decode
arm was verified locally and fired afterwards; the landing rule says *a verified
positive interval excluding zero*, not *a verified receipt*. So the real question is
only whether the **local** prefill instrument can resolve the arm, and whether the code
path is the same on both hosts.

On the local instrument, my two numbers are usually quoted against each other, so let
me settle them, because you asked precisely this:

* **1.87812e-4 ± 2.607e-7 s/token, n = 14 — cv 0.139 %.** These 14 runs share a build.
* **2.52 % prefill drift across four provably-identical trees.** These do not.

**The dispersion figure survives as a paired within-binary instrument, and it is tight
*because* the runs share a build — which is exactly the condition a one-binary env-var
arm satisfies.** The 2.52 % is the *two-build* noise: it is the cost of rebuilding, not
the cost of measuring. Quoting 2.52 % against a single-binary arm is the same error as
quoting profiled busy without τ. Concretely, a paired interleaved single-binary prefill
contrast has per-pair noise ≈ √2 × 0.139 % ≈ 0.20 %, so ~n = 16 pairs resolves 0.1 %
and ~n = 64 pairs resolves 0.05 %. **Prefill is locally adjudicable to about a tenth of
a percent.** It is the *ranked* leg that is unadjudicable, and the *NAX* arms that are
unexecutable.

So the campaign rule you drafted — *paired, interleaved, single-binary, env-var
switched, or it is unmeasurable* — is right, and I would add one clause:

> **…and the edited code must execute on the measuring host.** A local green on a gate
> that `is_nax_available()` switches off proves the tree compiles and the non-NAX path
> is unperturbed. It proves nothing about the arm.

## If anyone is to spend hours on prefill, here is the only place worth spending them

From my own prefill census: 237 steel dispatches plus 117 split-K accumulations,
48,368 threadgroups, `steel_gemm_bf16` already at 52.5 TFLOP/s and **87.5 % of
reference**, and **~27.88 ms (28.5 %) of the prefill leg unattributed to dense GEMM at
all**. That residue is not matrix×matrix steel, therefore not NAX-gated, therefore it
**executes identically on gen 16 and gen 17**; it is 28.5 % of a leg that carries 25 %
of the score exponent. It is the one prefill region where a local paired single-binary
measurement would both resolve and transfer. The dense-GEMM tile-shape axis, by
contrast, is 87.5 % of reference already and invisible here. If you reopen prefill,
reopen it there and nowhere else.

## The threadgroup counts you asked me to print

You asked for the TG count next to any null I report on #709, because of alphonse's
third cell (*fewer threadgroups than cores ⇒ absorption candidate regardless of how
flat the work probe is*). For the R118-A target and its control, read off the dispatch
sites in `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

| kernel | grid | threadgroup | **threadgroups** | TG per core (20) |
|---|---|---|---:|---:|
| `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` (target) | `(256*64, 1, 1)` | `(64,1,1)` | **256** | 12.8 |
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (positive control) | `(8*256*64, 1, 1)` | `(64,1,1)` | **2048** | 102.4 |
| alphonse's `gate_sp` (for contrast) | — | — | **8** | 0.4 |

**The R118-A target is not in alphonse's absorption cell.** 256 threadgroups on 20
cores is 12.8 per core, 32× more than `gate_sp`. Whatever the shared gate+up QMV's
58 %-of-peak shortfall is, it is not "the machine is idle because the dispatch is too
small to fill it". That kills the most attractive explanation before I spend a run on
it, and it is why my prior for this assignment is pessimistic rather than hopeful.

## The sentence you asked me to add to `L-NVFP4-ALU-CONVERTS-AT-5-PERCENT`

Added verbatim to the law file on this branch:

> **Scope note (R118-A, after alphonse's R114-E).** This law says the *work* is not the
> constraint on the NVFP4 families; it does **not** say the *time* is unrecoverable. On
> any kernel in this family that launches fewer threadgroups than the machine has cores
> (20 here), the time remains an absorption candidate — recoverable by appending the
> dispatch to a neighbouring kernel's grid rather than by making the kernel cheaper —
> and the flat work probe is not evidence against that. Always print the threadgroup
> count next to a null from this law.
