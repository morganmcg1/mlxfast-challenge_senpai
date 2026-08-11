# R109-F — the NAX observability gap: why the promoted arms cannot be measured anywhere

**maple-fern, PR #686, `maple-r109-f-integration-and-submission` / `r109-f-rev2`.**
Companion to `maple-fern-r109f-instrument-collapse.md`, which established that
the ranked host is a 0.370 %-sd lottery and that the local iterate is the better
instrument. This document finds the sharp exception to that advice, and it
retires most of the current arm portfolio.

---

## 0. Summary

The local host cannot execute MLX's `_nax` kernels. `is_nax_available()` needs
GPU architecture generation ≥ 17; this host is `applegpu_g16s`, generation 16.
The macOS check passes (26.5.2 ≥ 26.2), so the block is the GPU itself and
nothing can be configured around it.

That single fact splits the benchmark cleanly in two, because the `_nax` gates
sit exactly on the matrix–matrix paths and never on the matrix–vector paths:

| stage | kernel family | NAX-gated? | same kernels locally as on ranked? |
|---|---|:-:|:-:|
| decode — quantized matvec | `qmv`, `qvm`, `gather_qmv`, `gather_qvm` | **no** | **yes** |
| decode — attention (`q_len ≤ 8`) | `sdpa_vector`, `sdpa_vector_2pass` | **no** | **same path, maybe not the same kernel — see §7** |
| prefill — quantized matmul | `qmm`, `gather_qmm`, `gather_qmm_rhs`, `GatherQMM` | **yes** | **no** |
| prefill — dense GEMM | `steel_matmul_regular_axpby_nax`, `steel_gemm_splitk_axpby_nax`, `steel_gemm_segmented_nax`, `gather_mm_rhs_nax` | **yes** | **no** |
| prefill — attention | `sdpa_full_self_attention_nax` | **yes** | **no** |

**Decode is locally measurable. Prefill is not measurable anywhere.** Decode is
0.638 of the score's elasticity and prefill 0.362, so the larger half of the
score is the observable half — which is lucky, and which should decide where the
remaining effort goes.

Eight consequences, in descending order of how much work they cancel (7 and 8
were added late, and they cancel the most: 7 retracts an arm this document
previously advertised, and 8 is the audit of its replacement):

1. **Arm A2 (fused-NAX `bn` 128→64, `matmul.cpp:213-218`) has zero local
   observability.** It edits `steel_matmul_regular_axpby_nax`, reached only from
   `matmul.cpp:957` under `use_nax`. A local A/B of A2 measures exactly 0.00 %
   by construction — not "a small effect", *no effect*, because the edited code
   never runs. Adjudicating it needs ranked receipts, and §5.1 of the companion
   says ~37 per arm to resolve 0.30 %.
2. **Arm A1 (`darkbloom_expert_down_bn` 64→32) is dead twice over.** It was
   already a proven no-op at default env (the helper returns 64 and its call
   site assigns it to a `bn` already initialised to 64). It is *also* inside
   `gather_qmm_rhs_nax`, so it is unreachable on this host regardless.
3. **The local/ranked ratio asymmetry is now explained mechanistically.** Local
   decode is 2.63× the ranked decode, but local prefill is 6.0× the ranked
   prefill. That gap was unexplained. It is the NAX split: decode runs the same
   kernels on both hosts and the 2.63× is hardware, while prefill runs a
   *different kernel family* on each host, so its 6.0× is hardware × NAX.
4. **NAX is not the only host fork (§7).** Nine sites in the same backend branch
   on `d.get_architecture().back()` — the trailing letter of the architecture
   string, `'s'` here. One of them,
   `scaled_dot_product_attention.cpp:747`, chooses between `sdpa_vector_2pass`
   and `sdpa_vector` on that letter alone, with no NAX involvement.
   ~~Every local decode measurement in this campaign therefore ran the 2-pass
   kernel;~~ **wrong — the same `if` also tests `k.shape(2) >= 1024`, and the
   scored decode window never gets there; see §10 (CORRECTION 8).** The
   ranked host's letter is unknown, so it may be running the other one. Consequence:
   decode edits split into *quantised-GEMV* (best transfer) and
   *attention* (medium transfer — real local signal, sign may not carry). §7.2
   also isolates `MLX_SDPA_BLOCKS`, a run-time decode-path knob needing no
   rebuild — ~~the cheapest remaining local experiment here~~ **which has now been
   run and is a NULL; see the box in §7.2**.
5. **The no-op audit (§8).** Two portfolio knobs are arithmetically inert
   because they are already pinned at a shape-derived clamp: A1's
   `darkbloom_expert_down_bn`, and `DARKBLOOM_AOT_SDPA_PLANES` (4, capped at
   `v_per_thread = V/BD = 4`). ~~One knob is genuinely open:
   `DARKBLOOM_AOT_SDPA_2PASS_PLANES = 1` against a cap of 4, on the 2-pass
   kernel this host actually runs.~~ **RETRACTED in §10 — that knob is
   unclamped but unreachable, which is worse.** The generalisable rule: before
   spending a build or a slot on a tunable, read the expression that
   *consumes* it — and then check that anything ever calls it.
6. **The fusion census (§9): the INT8 fused norm+affine QKV suite is
   *shadowed*, not dead.** A `DARKBLOOM_TRACE_FUSION=1` census over three
   configurations (24 / 26 / 22 distinct dispatch sites) shows the suite's four
   sites are absent from the shipped configuration and appear only once the
   NVFP4 bank is disabled — which costs **+25.4 % local decode**, the largest
   effect measured anywhere in this campaign. So
   `DARKBLOOM_FUSED_NORM_AFFINE_QKV` is a no-op at default settings, and the
   suite should be neither retired nor tuned. §9.4 also corrects the kernel
   names in circulation: `rmsbfloat16` / `gate_sp_h64_v1` / `gate_sp_h48_v1`
   are **not in this tree**; the real symbol is `laguna_gate_sp_h{48,64}_v1`,
   JIT-minted at `LagunaRuntimeModel.swift:4512-4522`, and it is shadowed twice
   over. This adds a fourth question to §8's checklist: *is the path shadowed at
   runtime by a better path that is on by default?*

7. **CORRECTION 8 (§10): the SDPA *vector* family is not on the scored path at
   all, and consequence 5's "one genuinely open knob" is retracted.** Two
   independent gates, either one sufficient. (a) *Shape.* The scored decode
   window is a 512-token seed prefill plus 128 steps
   (`Constants.swift:123`, `:109`), so the KV length runs 512 -> 640, while the
   2-pass branch at `sdpa.cpp:748-749` needs `k.shape(2) >= 1024` on a `'d'`/`'s'`
   device or `>= 4096` under GQA. 640 < 1024 on **every** host, whatever its
   architecture letter. (b) *Interception.* Decode attention never leaves the
   model: `LagunaRuntimeModel.swift:6152`/`:6178` serve it with the fused
   `laguna_sliding_fused_attn_ring_v1` / full-attention ring kernels, and the
   §9 trace census confirms both fire in the shipped configuration
   (`sliding fused attention`, `full fused attention` in `sites-A.txt`). MLX's
   `MLXFast.scaledDotProductAttention` is reached only through the `??` fallback
   at `:6276`, i.e. on **prefill**, where `q.shape(2) = 512 > 8` routes to the
   *full self-attention* family instead. Corollary, and the reason this is worth
   a section: the `MLX_SDPA_BLOCKS` null reported in §7.2 was not a weak effect,
   it was a **structural zero** — that env read lives at `sdpa.cpp:477`, inside
   `sdpa_vector_2pass`, a function this benchmark never calls.

8. **The replacement arm survives its own audit, and we already have a receipt
   inside it (§10.6).** Rather than let §10.4's nomination of the prefill
   full-attention family stand on the same kind of assertion that produced
   correction 8, I ran the five questions on it. It passes: the scored shapes reach
   `sdpa_full_self_attention_nax` (`scaled_dot_product_attention.cpp:177`), and
   the reachable code is also the *editable* code — `kernels/steel/attn/` (10
   files), `mlx-generated/steel_attention_nax.cpp` and the JIT factory
   `jit_kernels.cpp:1344` are all in `editablePaths`. Two conditions I had not
   anticipated: the tile geometry is **frozen** by the non-editable dispatch
   (`bq=64, bk=32, wm=4, wn=1` at `:31-36`; grid `(NQ,H,B)` and group `(32,wm,wn)`
   at `:160-161`), so the arm is kernel-body-only; and at `qL=512`, `kL≥512` both
   alignment function constants are true, so only the aligned specialisation is
   scored. Three JIT-injected knobs live here — `DARKBLOOM_ATTN_QHOIST`
   (default off), `DARKBLOOM_ATTN_QBLOCK_MAJOR` and `..._ZIGZAG` (both default
   on) — and **none** of them is injected into the non-NAX factory (`:1269`), so
   on this host they are not merely unmeasurable but unobservable. The decisive
   fact is historical: ticket 3 already flipped QHOIST and shipped it
   (`e4078827`, −1.36 % = −3.82 σ, localised to candidate prefill at 196.2976 µs
   vs a 187.65–188.03 µs band, +4.27 σ, reverted in ticket 4). So the claim that
   this leg adjudicates a real change in ~2 receipts is no longer a noise-model
   extrapolation — it has been demonstrated once, at 4.3 σ, in the wrong
   direction.


---

## 1. The probe

`research/fern_r109f_nax_probe.swift` replicates `is_nax_available()`
(`device.cpp:913`) and the `arch_gen_` parse (`device.cpp:560-572`) exactly, so
its answer is the runtime's answer:

```
$ swift research/fern_r109f_nax_probe.swift
device.name      = Apple M4 Pro
architecture     = applegpu_g16s
arch_gen_        = 16
arch.back()      = s
macOS >= 26.2    = true
gen requirement  = >= 17
is_nax_available = false

VERDICT: NAX kernels DO NOT run here (GPU generation 16 < 17).
```

The relevant runtime source, quoted rather than paraphrased:

```cpp
// device.cpp:913
bool is_nax_available() {
#ifdef MLX_METAL_NO_NAX
  return false;
#else
  auto _check_nax = []() {
    bool can_use_nax = false;
    if (__builtin_available(macOS 26.2, iOS 26.2, tvOS 26.2, visionOS 26.2, *)) {
      can_use_nax = true;
    }
    auto& d = metal::device(mlx::core::Device::gpu);
    auto arch = d.get_architecture().back();
    auto gen = d.get_architecture_gen();
    can_use_nax &= gen >= (arch == 'p' ? 18 : 17);
    return can_use_nax;
  };
  static bool is_nax_available_ = _check_nax();
  return is_nax_available_;
#endif
}
```

Two things worth noting. First, `arch_gen_` is parsed from the *string* —
`arch_[size-3]` and `arch_[size-2]` — so `applegpu_g16s` yields 16 and
`applegpu_g17s` would yield 17. Second, `device.cpp:560` reads
`env::metal_gpu_arch()` first, i.e. **`MLX_METAL_GPU_ARCH` can override the
architecture string**, and therefore can flip `is_nax_available()` on a host
whose GPU cannot execute the instructions.

I did not use that. It would select `_nax` kernels on hardware that lacks the
NAX units, which at best fails to compile the kernel and at worst produces
wrong numbers that still pass a timing harness. It is worth *recording* only
because it is the sort of shortcut that looks like an instrument and is not one:
it would let an A2 A/B produce two different numbers locally, and neither of
them would mean anything about the ranked host. That is the same error as
reading a lucky draw as a fast package, one layer deeper.

---

## 2. Where the gates actually are

Enumerated, not assumed. Every `is_nax_available()` call site in the two files
that matter, mapped to its enclosing function:

```
quantized.cpp:728   -> qmm(              matrix x matrix
quantized.cpp:951   -> gather_qmm(       matrix x matrix
quantized.cpp:1669  -> gather_qmm_rhs(   matrix x matrix
quantized.cpp:1906  -> GatherQMM         -> gather_qmm_rhs_nax
matmul.cpp:894/957  -> steel_matmul_regular_axpby_nax
matmul.cpp:922/925  -> steel_gemm_splitk_axpby_nax
matmul.cpp:2288/90  -> gather_mm_rhs_nax
matmul.cpp:2357/73  -> steel_gemm_segmented_nax
sdpa.cpp:177        -> sdpa_full_self_attention_metal -> _nax
```

And the functions with **no** gate at all — checked by enumerating every
`is_nax_available()` in `quantized.cpp` (there are exactly four, all listed
above) and confirming none falls inside these line ranges:

```
quantized.cpp:238   qmv(          quantized.cpp:420   qvm(
quantized.cpp:1025  gather_qmv(   quantized.cpp:1091  gather_qvm(
sdpa.cpp:329        sdpa_vector(  sdpa.cpp:418        sdpa_vector_2pass(
```

The `sdpa` dispatch decides between them on sequence length
(`sdpa.cpp:634`): `supports_sdpa_vector = (query_sequence_length <= 8) && …`.
Decode generates one token at a time, so decode takes `sdpa_vector`; prefill
takes `sdpa_full_self_attention_metal`, which immediately forwards to `_nax` on
the ranked host.

The pattern is not a coincidence. NAX is a matrix-multiply accelerator, so it
only has anything to offer where there is a matrix on both sides. At batch 1
decode the right-hand side is a vector, there is no NAX kernel to call, and both
hosts run the identical matvec. **The benchmark's decode leg is, by
construction, portable; its prefill leg is not.**

---

## 3. What this does to the arm portfolio

The standing guidance (advisor 0P.10) is that ranked prefill GEMM is
staging-bound, and it promotes register-prefetch and A2 on that basis. The
diagnosis may well be right. The problem is that every arm it promotes lives
inside the NAX families in §2, which means:

| arm | local observability | ranked cost to adjudicate | verdict |
|---|---|---|---|
| A1 `darkbloom_expert_down_bn` 64→32 | none (in `gather_qmm_rhs_nax`) | — | **dead**: also a proven no-op at default env |
| A2 fused-NAX `bn` 128→64 | **none** (in `steel_matmul_regular_axpby_nax`) | ~37 receipts/arm for 0.30 % | **unadjudicable in practice** |
| #693 ping-pong staging / register prefetch, `_nax` port | **none** if it lands in `_nax` | as above | same trap |
| atlas v3_tg128 | measured, −0.026 % | — | kept, free, invisible on ranked |
| router weight prefetch 1→0 | measured, +0.13 % (worse) | — | default 1 retained |

"~37 receipts/arm" understates the real cost, because that figure resolves
0.30 % *of the normalized score*. A prefill-only change has elasticity 0.362, so
a 0.30 % score move needs a 0.83 % prefill improvement; conversely a 0.30 %
prefill win is only a 0.109 % score move, which by the same power table needs
~280 receipts per arm. At 22 min of shared channel per receipt and two arms,
that is **~205 hours of a channel we share with the advisor and every other
maple student**. A2 is not expensive to adjudicate; it is unadjudicable.

Compare the decode side. A 0.30 % score move via decode needs a 0.47 % decode
improvement, and local decode repeatability is 0.05–0.10 %, so three replicates
per arm resolve it at high confidence in about 15 minutes of local wall clock.
**The instrument for decode work is roughly 10²–10³× cheaper than the instrument
for prefill work**, and the decode term is the bigger one.

> **⚠ BOTH halves of the comparison above are now measured, and both moved —
> in opposite directions. Net effect: the conclusion inverts.**
>
> *Prefill got cheaper, by a lot.* The "~280 receipts per arm" figure was computed
> on the **published score**. Six own receipts — including the first k=3
> identical-executable group ever measured here — give a **per-leg** gauge, and
> the candidate-prefill leg is the *quietest* axis on the host: instrument sd
> **0.0750 %** versus 0.5169 % for the published score. A 0.30 % prefill arm read
> on `officialMetrics.prefill_seconds_per_token` costs **2 receipts**, not 280.
> A2 is adjudicable after all — in under an hour of channel time. See
> `maple-fern-r109f-instrument-collapse.md` §5.3f and §8 rec-2.
>
> *Local decode got noisier.* An 8-run local sweep (§7.2) measures local decode cv
> at **≈0.35 %**, not 0.05–0.10 %. Three replicates do **not** resolve a 0.47 %
> decode change at high confidence; ~42 replicates resolve 0.1 %.
>
> So the "10²–10³× cheaper" claim is withdrawn. The honest statement: **decode is
> screened locally because local throughput is ~10× the ranked channel's, and
> prefill is adjudicated on the ranked channel because its leg is the quietest
> instrument either host provides.** Each host is best at the leg the other cannot
> measure, which is a much better situation than this section describes.

---

## 4. The correction this forces on the companion document

`maple-fern-r109f-instrument-collapse.md` §8 recommendation 2 says "move arm
adjudication onto the local iterate". That is right for decode and **wrong for
prefill**, and I would rather state the exception than let the recommendation be
applied where it silently returns 0.00 %.

The corrected form — ~~itself superseded, see the box below~~:

> ~~Move **decode** arm adjudication onto the local iterate, where the kernels are
> identical to the ranked host's and repeatability is 0.05–0.10 %. Do not
> attempt to adjudicate **prefill** arms at all on this host: the ranked prefill
> path is NAX and this GPU cannot run it, so a local A/B returns 0.00 % whatever
> the arm does. Prefill arms are adjudicable only on the ranked host, at a cost
> (≈10² receipts/arm) that the shared single-slot channel cannot fund.~~

> ⚠ **CORRECTED (twice over).** Both halves of that blockquote were wrong, and
> they were wrong in *opposite* directions, which is why the net recommendation
> survives but its justification does not.
>
> **Left half, too optimistic.** Local decode repeatability is **≈0.35 % per
> run**, not 0.05–0.10 % (§7.2, CORRECTION 5). That is *worse* than the ranked
> candidate-decode instrument sd of 0.2646 %. Local iterate is not the tighter
> instrument on decode; it is the *faster* one — ~155 s on an unowned slot versus
> a shared per-account channel that admits one submission at a time. Its real
> advantage is throughput of about one order of magnitude, and it buys tightness
> only by averaging (~50 runs to reach ~0.05 %).
>
> **Right half, far too pessimistic.** "≈10² receipts/arm" was read off the
> *published score*, whose pooled instrument sd is 0.5169 %. A prefill arm does
> not have to be read there. Read on the leg it actually targets — the
> **candidate prefill** leg, pooled sd **0.0750 %** — a 0.30 % prefill arm needs
> **2 receipts** and a 0.20 % arm needs **4**. The channel funds that easily.
> maple-tanjiro's A2 (fused-NAX `bn` 128→64) is therefore **not** a measurement
> dead end; it is one of the cheapest arms in the whole slate.
>
> Net: the *advice* still stands — screen decode locally, never screen prefill
> locally — but for a different reason. Screen decode locally because it is cheap
> and immediate, then confirm on ranked because ranked is tighter. Adjudicate
> prefill on ranked because it is the only host that can see it at all, and it
> turns out to be cheap there.

This also disposes of a claim I should have been more careful about. In the
companion I wrote that local iterate is a ~~"4–7× better instrument"~~ than
ranked, and I defended it here as a *decode* result that holds on decode even if
it does not transfer to prefill. **That defence fails too.** The 4–7× figure
divided a mis-measured local sd (0.05–0.10 %) into a ranked *score* sd; with the
local sd corrected to 0.35 % and the ranked comparison moved to the matching
decode leg (0.2646 %), the ratio inverts to roughly **0.75×** — local is
*slightly worse* per observation. The claim is withdrawn on both legs, not
narrowed to one.

The honest summary of the two hosts is that neither dominates: **each is the
better instrument at the leg the other cannot measure.** Local sees decode
quickly and prefill not at all; ranked sees prefill precisely and decode
precisely, but rations observations.

A second, smaller correction. My local 2×2 ledger recorded prefill legs as
"≈0.001122 s across all arms", which I read as "prefill is unaffected by these
arms". The stronger and more accurate reading is that local prefill is *inert
by construction* for any NAX-touching arm — a constant there is not evidence of
no effect, it is evidence of no measurement. None of the four arms in that 2×2
touched `_nax` code, so no conclusion changes, but the reasoning was luckier
than it was sound.

---

## 5. What to do instead

1. ~~**Retire A1 and A2 as measurement dead ends** and say so explicitly at the
   05:00Z checkpoint, with §1 and §2 as the evidence.~~ **Retire A1 only.** A1 is
   a genuine dead end on two independent counts: it does nothing at default env
   (the `darkbloom_expert_down_bn` 64→32 edit is dead code twice over) *and* it
   is NAX-unreachable here. A2 is a different case, and this recommendation was
   wrong about it.

   > ⚠ **CORRECTED.** A2 (fused-NAX `bn` 128→64) is a *local* measurement dead
   > end but **not** a measurement dead end. It is unmeasurable only because I was
   > reading it off `officialScore` (pooled instrument sd 0.5169 %). Read on the
   > leg it targets — **candidate prefill**, pooled sd **0.0750 %** — a 0.30 %
   > effect needs **2 receipts** and a 0.20 % effect needs **4**. That is
   > affordable on the shared channel and makes A2 one of the *cheapest* arms in
   > the R109 slate rather than an abandoned one. maple-tanjiro should be told to
   > keep it and to report `officialMetrics.prefill_seconds_per_token`, not the
   > score.
2. **Ask #693 which kernel family its port targets** before it spends effort. A
   ping-pong staging change to `sdpa_vector` or the `gather_qmv` path is
   locally measurable and worth having; the identical idea applied to
   `sdpa_full_self_attention_nax` is ~~not adjudicable by anyone in this
   campaign~~ **adjudicable on the ranked candidate-prefill leg at ~2 receipts,
   but invisible locally** — so the question still matters, because it decides
   *which host* can screen the arm, not whether the arm is knowable.
3. **Redirect the search to the non-NAX decode families**: `qmv`, `qvm`,
   `gather_qmv`, `gather_qvm`, `sdpa_vector`, `sdpa_vector_2pass`. These are
   0.638 of the score's elasticity, they are the same code on both hosts, and
   they are the only place where a +0.1 % win can be both *found* and
   *believed*. By the companion's elasticity table each +0.1 % of real code is
   worth ×1.48 on per-shot crown probability, so three such wins compound to
   ×3.2 — a better programme than one unmeasurable prefill kernel.
4. **Keep the probe in the loop.** `swift research/fern_r109f_nax_probe.swift`
   costs seconds and answers "can this host see the code I am about to edit?".
   Running it before designing an arm would have saved A2 entirely.

---

## 6. What this does *not* claim

- It does not claim the ranked prefill path is already optimal. ~~It claims
  nobody in this campaign can measure whether a change to it helps.~~
  **Corrected (§4): it claims nobody can measure that *locally*.** On the ranked
  host the candidate-prefill leg has a pooled instrument sd of 0.0750 % — the
  *tightest* axis in the whole receipt schema — so a prefill change is
  measurable there at ~2 receipts. The gap this document describes is a gap in
  *local* observability, not in knowability.
- It does not claim NAX makes the ranked host faster in some unfair way. The
  baseline legs also run on NAX, and the score is a ratio, so NAX cancels to
  first order in the published number. What does not cancel is *observability*:
  a solver on a gen-16 host is editing code they cannot execute.
- It does not explain the residual local/ranked decode ratio of 2.63×. That is
  hardware — clocks, bandwidth, cache — and for the quantised matrix-vector
  kernels it is a scale factor, not a change of kernel, which is why the decode
  leg transfers better than the prefill leg.
  **Scope correction (see §7): "not a change of kernel" is true of `qmv`/`qvm`
  but false of decode *attention*.** Nine sites in the vendored MLX backend
  branch on `d.get_architecture().back()` — the trailing letter of the
  architecture string — and one of them (`scaled_dot_product_attention.cpp:747`)
  chooses between two *different* decode-attention kernels on that letter alone,
  with no NAX involvement. Our host's letter is `'s'`; the ranked host's letter
  is unknown. So the decode leg is *mostly* transferable, not wholly.
- It says nothing about correctness. All local arms passed the golden gate
  (`b9509697c08a2cf3`), and the fallback kernels are the reference
  implementations, not approximations.

## 7. The arch-suffix fork: a second, non-NAX portability hazard

NAX is not the only host-dependent switch in the vendored backend, and it is not
even the most subtle one. `is_nax_available()` at least announces itself: it is
one named predicate, and every call site reads like a feature gate. The second
hazard is anonymous. It is the *last character of the architecture string*.

`MTL::Device` reports an architecture name like `applegpu_g16s`. The backend
parses a generation number out of it (`device.cpp:560-572`) and also, separately
and in nine different places, looks at the trailing letter:

| file | line | what the letter decides |
|---|---|---|
| `device.cpp` | 924 | second half of the NAX predicate (`'p'` needs gen >= 18, else >= 17) |
| `matmul.cpp` | 216 | steel GEMM tile selection |
| `matmul.cpp` | 378 | ditto, second shape regime |
| `matmul.cpp` | 897 | NAX-vs-classic GEMM dispatch |
| `matmul.cpp` | 2158 | gather-MM tiles |
| `matmul.cpp` | 2354 | segmented-GEMM tiles |
| `quantized.cpp` | 89 | `get_qmv_batch_limit()` -- with `get_architecture_gen()`; gens 13/14 switch on `'d'` |
| `scaled_dot_product_attention.cpp` | 443 | SDPA block-count ladder |
| `scaled_dot_product_attention.cpp` | **747** | **which decode-attention kernel runs at all** |

Static reading only -- nine `grep`-confirmed sites
(`grep -rn "get_architecture().back()" Vendor/.../backend/metal/`), no builds, no
behavioural claim beyond what the source says. `device_info.cpp:32` also reads
`get_architecture()` but only to *report* the string, so it is not a branch and
is not counted.

### 7.1 The dispatch fork at `scaled_dot_product_attention.cpp:747`

```
char devc = d.get_architecture().back();
if (((devc == 'd' || devc == 's') && k.shape(2) >= 1024) ||
    (k.shape(1) < q.shape(1) && k.shape(2) >= 4096)) {
  sdpa_vector_2pass(...);
} else {
  sdpa_vector(...);
}
```

Both branches are on the *decode* path -- the vector path, reached whenever
`query_sequence_length <= 8` (`sdpa.cpp:634`), which is every decode step.
Neither branch is NAX-gated. The only thing separating them, at our sequence
lengths, is whether the letter is `'s'`/`'d'`.

Our host's letter is `'s'` (probe output: `architecture = applegpu_g16s`,
`back() = 's'`), so **every local decode measurement in this campaign ran
`sdpa_vector_2pass`**. The ranked host is gen >= 17 (>= 18 if its letter is
`'p'`) and its letter is unknown to us. If it is not `'s'` or `'d'`, ranked
decode attention runs `sdpa_vector` -- the single-pass kernel -- a *different*
kernel, with a different reduction structure, at the same sequence length.

This is why the §6 bullet needed correcting. "Local decode runs the same kernels
as ranked, just slower" is a safe statement about `qmv`/`qvm` (not NAX-gated, not
suffix-branched). It is **not** safe about attention. A decode-attention edit
that helps the 2-pass kernel locally may land on the 1-pass kernel remotely and
do nothing, or the reverse. The 0.638 decode elasticity still holds -- the score
formula does not care which kernel produced the time -- but the *transfer
assumption* behind "measure locally, harvest on ranked" is weaker for attention
edits than for quantised-GEMV edits. Rank the arms accordingly:

1. quantised matvec / dequant / gather-GEMV edits -- same kernel both hosts,
   full local observability. **Best transfer.**
2. decode-attention edits -- same *path*, possibly different *kernel*. Local
   measurement is real but its sign may not carry. **Medium transfer.**
3. prefill GEMM / fused-NAX edits -- locally unreachable code. **No transfer;
   see §3.**

### 7.2 The block ladder and `MLX_SDPA_BLOCKS`

`scaled_dot_product_attention.cpp:440-478` picks the SDPA block count from the
same letter plus the key length `N` and the simd count:

- `'s'` -> 64; and if `N > 1024 && n_simds > 4`: 128 (`N <= 8192`), 256
  (`<= 32768`), 512 (`<= 65536`), else 1024.
- `'d'` -> 128; 256 if `n_simds <= 2 && N > 8192`; 512/1024 when `n_simds >= 6`
  at `N >= 16384` / `>= 65536`.
- anything else -> 64 if `n_simds >= 4`, otherwise 32.

The ladder is overridable at run time by the environment variable
`MLX_SDPA_BLOCKS` (`:477`). That matters operationally: it is a **decode-path,
non-NAX, no-rebuild knob**. It can be swept locally with
`research/fern_r109f_env_bench.sh <label> MLX_SDPA_BLOCKS=<n>` at ~155 s per arm
against the atlas-v3 baseline of `0.0129499915312` s/token, without touching the
build or spending a submission slot. It is the cheapest remaining decode
experiment in the workspace. (Its *transfer* is category 2 above: worth knowing,
not worth betting a ranked receipt on by itself.)

> **★ RESULT (2026-08-11T06Z): the sweep was run and it is a NULL — and it also
> produced the campaign's noise correction as a by-product.**
>
> Eight runs, all `passed: true` on golden `b9509697c08a2cf3`, sealed as
> `research/artifacts/fern-r109f/ab/score.sdpablocks-*.json`. Decode µs/token:
>
> | `MLX_SDPA_BLOCKS` | decode µs | vs default |
> |---|---:|---:|
> | default (ladder → 128) | 12934.7 | — |
> | default, replay | 12965.0 | +0.23 % |
> | 16 | 13019 | +0.65 % |
> | 32 | 12926 | −0.07 % |
> | 128 | 12935 | +0.00 % |
> | 256 | 12850 | **−0.65 %** |
> | 256, replay | 12934 | +0.00 % |
> | 512 | 12889 | −0.35 % |
>
> The −0.65 % at 256 is the only interesting number and **it did not replicate**:
> the same command 155 s later returned 12934 µs. Only 16 is plausibly *worse*
> (+0.65 %, ~1.8 σ). Verdict: **no setting beats the ladder**, which is
> unsurprising — the ladder already picks 128 for this shape and someone tuned it.
>
> **The by-product matters more than the result.** These 8 runs are the first
> replicated local measurements in the campaign, and they gauge the *local*
> instrument: σ ≈ 49 µs on a 12931.6 µs mean, i.e. **local decode cv ≈ 0.35 %**,
> with the two replicated pairs differing by 30.3 µs and 84 µs. That falsifies the
> "local iterate repeats to 0.05–0.10 %" premise that this document and
> `maple-fern-r109f-instrument-collapse.md` §5.2 both leaned on (see CORRECTION 5
> there): local is ~1.8× *noisier per observation* than the ranked normalized axis
> and ~4.7× noisier than the ranked candidate-prefill leg. Local's advantage is
> **throughput on an unowned slot**, ~1 order of magnitude, not 10²–10³×.
>
> **And it would not have been shippable even if it had won.** The dispatch site
> that reads the variable —
> `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/scaled_dot_product_attention.cpp:475-477`
> — is **not in `benchmark.json`'s `editablePaths`**; only
> `kernels/scaled_dot_product_attention.metal` and `kernels/sdpa_vector.h` are.
> Changing the default would mean calling `setenv` from editable Swift, which is a
> rules question for the advisor and not a kernel result. Recording that here so
> nobody re-derives the ladder and then discovers the file is frozen.

## 8. The no-op audit: check the clamp before you spend the build

Two knobs in the inherited portfolio are arithmetically incapable of doing
anything, and both were promoted before anyone read the clamp.

**A1 -- `darkbloom_expert_down_bn` 64 -> 32.** Already recorded: the function
returns 64 and its only call site is inside `gather_qmm_rhs_nax`
(`quantized.cpp` ~1390) where `bm = bn = bk = 64` is already fixed. Dead twice
over: no-op *and* NAX-unreachable.

**`DARKBLOOM_AOT_SDPA_PLANES` 4 -> higher.** `Vendor/.../kernels/sdpa_vector.h:8`
defines it as 4. Inside `sdpa_vector` (template at `:52`), `BN = BD = 32`,
`v_per_thread = V / BD = 4`, and

```
v_planes = min(PLANES, v_per_thread)
```

so `PLANES = 4` is *already at its cap*. Raising it changes nothing at all.
Nor does lowering it buy anything: `exchange_planes` is forced to 4 whenever
`D == V == 128 && GQA_PAIR_HEADS == 2`, so threadgroup memory is unchanged, and
a smaller `v_planes` only lengthens the reduction loop at `:476-502`. The knob is
a no-op upward and a pessimisation downward.

**~~The one that is actually open.~~ RETRACTED — see §10 (CORRECTION 8).**
The paragraph below stood here for several hours and is wrong. Everything it
says about the *clamp* is still true; everything it says about *reachability* is
not. Kept in place, struck through, because the mistake is the whole point of
this section.

> ~~`DARKBLOOM_AOT_SDPA_2PASS_PLANES` (`sdpa_vector.h:12`) is defined as **1**,
> and its clamp in `sdpa_vector_2pass_2` (template `:670`) is
> `o_planes = min(PLANES, elem_per_thread = D / BD = 4)`, so 1 sits **below**
> its bound. 1 -> 2 or 1 -> 4 is a genuinely open decode-side arm. ... it acts
> on the *2-pass* kernel, which is the one our `'s'` host actually runs, so it
> is locally measurable at full resolution.~~

The clamp reading is correct: `elem_per_thread = D / BD = 128 / 32 = 4`, so
`PLANES = 1` really is below its bound, and raising it really would collapse the
reduction at `sdpa_vector.h:744-754` (four stores, seven threadgroup barriers)
into the one-barrier form at `:724-743`, for 4 KiB -> 16 KiB of threadgroup
memory. What is wrong is the sentence after it. `sdpa_vector_2pass` is **never
dispatched in the scored window on any host**, and the shipped model does not
call MLX's SDPA *vector* family in decode at all. §10 proves both, and takes
`MLX_SDPA_BLOCKS`'s measured null with it as a corollary. I passed questions 1
and 2 of the checklist below and then failed to ask the one that mattered —
which is exactly the failure this section was written to prevent, committed by
its own author, one section later.

**Generalise it.** The failure mode is cheap to prevent and expensive to hit. It
cost this workspace two promoted arms:

> Before spending a build, a slot, or a checkpoint on a tunable, read the
> expression that consumes it and check whether the value is already pinned at
> its effective bound.

Three questions, all answerable by `grep` in under a minute (§9.6 adds a fourth
and §10.5 a fifth — the fifth is the one that caught me):
1. Where is the constant *consumed*, not just defined?
2. Is it wrapped in a `min`/`max`/clamp against a shape-derived quantity?
3. Is the code path that consumes it reachable on the host doing the measuring
   (§2's NAX gates, §7's suffix branches)?

An arm that fails any of the three is not a weak arm; it is not an arm. A census
of the editable sources found ~40 `DARKBLOOM_*`/`LAGUNA_*` environment knobs
(most-referenced: `LAGUNA_RESCALE` 16 sites, `DARKBLOOM_SWIGLU_REGLOCAL` 11,
`DARKBLOOM_ATTN_QHOIST` 11, `DARKBLOOM_TRACE_FUSION` 9,
`DARKBLOOM_RESCALE_FACTOR` 9). Each is a candidate arm and each deserves the
three questions before it deserves a slot.

§9 adds a fourth question, which the first three miss.

---

## 9. The fusion census: the INT8 fused norm+affine QKV suite is *shadowed*, not dead

The advisor asked whether the fused norm+affine QKV suite is dead code that
should be retired, and whether the kernels named `rmsbfloat16`,
`gate_sp_h64_v1` and `gate_sp_h48_v1` are worth reviving. The timing half of
that request was later withdrawn (correctly — see §5 and the companion's §5.1:
this tree cannot resolve a sub-1 % decode arm at n=1). The **structural** half
is answerable exactly, with `grep` and three no-source-change runs, and the
answer is not the one the question expects.

**The suite is not dead. It is shadowed.** Its dispatch sites do not appear at
all in the shipped configuration, and they appear the moment a *different*,
better-performing bank is switched off. "Dead" would license deleting it;
"shadowed" means it is the fallback path, and that editing it is a guaranteed
0.00 % — for a reason completely different from A2's hardware gate in §3.

### 9.1 Method

Zero source change. `DARKBLOOM_TRACE_FUSION=1` flips `lagunaTraceEnabled`
(`LagunaRuntimeModel.swift:76`), which makes `lagunaTrace()` (`:94`) emit one
`mlxfast: fusion active: <site>` line per distinct dispatch site reached. Driver
`research/fern_r109f_fusion_census.sh`, differ
`research/fern_r109f_fusion_census_diff.py`, artifacts
`research/artifacts/fern-r109f/census/{census,sites}-{A,B,C}.{log,txt}`.
Three arms, each a single `./benchmark.sh --local-iterate` (~150 s):

| arm | environment | bank actually loaded |
|---|---|---|
| **A** | default (both flags unset) | NVFP4 g16 |
| **B** | `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` | INT8 g32 affine, fused QKV live |
| **C** | B + `DARKBLOOM_FUSED_NORM_AFFINE_QKV=0` | INT8 g32 affine, fused QKV off |

The two flags are read once each: `lagunaNativeAffineNVFP4From`
(`:3044-3050` — returns `nil` for `"0"`, which removes the NVFP4 bank from every
layer) and `lagunaFusedNormAffineQKVEnabled` (`:5482`), consumed by
`lagunaNormAffineQKV` (`:5488`).

`--local-iterate` is used only because it is the cheapest invocation that runs
the real `prepareFusedRuntimeWeights` path. **No score claim is made from it.**

### 9.2 What the census found

Distinct dispatch sites: **A = 24, B = 26, C = 22.**

A → B (four sites leave, six arrive):

| direction | site | emitter |
|---|---|---|
| −A | `decode nvfp4 qkv r1 h48 lane-major` | `:5028` |
| −A | `decode nvfp4 qkv r1 h64 lane-major` | `:5028` |
| −A | `gated affine oproj nvfp4 qmv h48 lane-major` | `:4618` |
| −A | `gated affine oproj nvfp4 qmv h64 lane-major` | `:4618` |
| +B | `norm+affine qkv qmv r8240 pf4` | `:5535` |
| +B | `norm+affine qkv qmv r8240 pf4 indexed` | `:5521` |
| +B | `norm+affine qkv qmv r10304 pf4` | `:5535` |
| +B | `norm+affine qkv qmv r10304 pf4 indexed` | `:5521` |
| +B | `gated affine oproj qmv h48 indexed` | `:4197` |
| +B | `gated affine oproj qmv h64 indexed` | `:4197` |

B → C: the four `norm+affine qkv qmv r{8240,10304} pf4[ indexed]` sites leave;
the two INT8 `gated affine oproj qmv h{48,64} indexed` sites stay. 22 remain.

Two conclusions follow immediately:

1. **`DARKBLOOM_FUSED_NORM_AFFINE_QKV` is a no-op in the shipped
   configuration.** Its four sites are absent from arm A's trace; the flag only
   changes behaviour once the NVFP4 bank is already off. Anyone A/B-ing that
   flag on default settings is measuring nothing, on any host, at any n.
2. **The o-proj site is one site with two banks**, not two features:
   `gated affine oproj … nvfp4 … lane-major` (A) and `gated affine oproj …
   indexed` (B, C) are the NVFP4 and INT8 realisations of the same dispatch.

### 9.3 The row counts prove the fused kernel absorbs the gate projection

`r8240` and `r10304` are output row counts, and they decode exactly. With
`headDim = 128`, `numKeyValueHeads = 8` (`LagunaConfig.swift:21-22`),
`fullAttentionHeads = 48` and `slidingAttentionHeads = 64` (`:24`, `:26` —
note the naming is the reverse of the intuitive one):

* h48 (full-attention layers): 48·128 + 2·(8·128) + **48** = 6144 + 2048 + 48 = **8240**
* h64 (sliding layers): 64·128 + 2·(8·128) + **64** = 8192 + 2048 + 64 = **10304**

The trailing `+nHeads` is the gate projection. The fused norm+affine QKV kernel
emits Q, K, V *and* the attention-gate rows in one dispatch — which is what makes
§9.4's finding inevitable.

### 9.4 The name correction: `gate_sp_h*_v1` is not in this tree, and its real namesake is shadowed twice over

`rmsbfloat16`, `gate_sp_h64_v1` and `gate_sp_h48_v1` **do not appear anywhere in
`Sources/`, `kernels/` or `Vendor/`.** They appear only in *other students'*
notes and logs in this repo — `research/pr270-logs/*`,
`research/tanjiro-r87a-kernel-table.py:58` (`NEIGHBOUR="gate_sp_h64_v1"`),
`research/nezuko-pr158-gap.log`,
`research/artifacts/maple-frieren-r107f/stage0_gpupso.txt`, and
`research/maple-frieren-r94-decode-residue-ledger.md:122`, which spells it
correctly as `laguna_gate_sp_h64_v1`. The name in circulation is a truncation.

The real symbol is `laguna_gate_sp_h\(heads)_v1`, a JIT `MLXFast.metalKernel`
minted in `lagunaGateSoftplusKernels` (`:4512-4522`, name at `:4516`) for
`heads ∈ {slidingAttentionHeads, fullAttentionHeads} = {64, 48}`, from
`lagunaGateSoftplusSource(heads:)` (`:4467`), behind
`lagunaGateSoftplusEnabled = DARKBLOOM_AFFINE_GATE_SOFTPLUS != "0"` (`:4464`,
i.e. **on by default**).

It is nonetheless unreachable in both A and B, and the guards say why:

* `lagunaGateSoftplus(input:bank:heads:)` (`:4525-4546`) requires
  `bank.mode == .affine`, `bank.bits == 8`, `bank.groupSize == 32`, non-`nil`
  `biases`, bf16 input and exact dims — i.e. an **INT8-g32** gate bank. Under
  arm A the bank is NVFP4-g16, so the first guard clause fails and it returns
  `nil`.
* Its only call site (`:5994`) sits in the **third** branch of the gate-logits
  selection at `:5974-5988`: branch 1 takes `fusedTailGateLogits`, branch 2 takes
  the gate rows out of the fused QKV output when
  `_nativeAffineQKVGateRows == nHeads`, and only branch 3 calls the softplus
  kernel. §9.3 shows the fused QKV output *contains* those `nHeads` gate rows in
  both A (r1 NVFP4 path) and B (r8240 / r10304), so branch 2 wins in both arms.
* That same call site additionally demands `affineWO.mode == .nvfp4`,
  `bits == 4`, `groupSize == 16` for the **o-proj** bank (`:5990-5993`). So the
  configuration that would run `laguna_gate_sp_h*_v1` is a *mixed* one — NVFP4
  o-proj bank with an INT8-g32 gate bank and no fused gate rows — which neither
  A, nor B, nor C produces.

`lagunaGateSoftplusEnabled` is not idle, though: it also gates the pre-activated
o-proj kernels at `:4615` (`lagunaActivatedOProjLaneMajorKernels`) and `:4633`
(`lagunaActivatedOProjKernels`, names `laguna_oproj_act_h\(heads)_v1` plus
`_sc1`/`_se1` suffixes from `lagunaNvfp4QmvSignCarryEnabled` /
`lagunaNvfp4QmvSeedElisionEnabled`). Those *are* in arm A's trace. So the flag
is live, the softplus kernel behind it is not, and "is the flag referenced?" was
never the right question.

### 9.5 Correctness, and the one magnitude statement that survives the noise floor

All three arms report `passed: true`, `passed_correctness: true`, and
`max_abs_diff: 0` — the three dispatch configurations produce **identical**
outputs on the local golden set. The shadowed path is not merely present, it is
correct. It is only slower:

| arm | local decode s/tok | vs A | local decode floor |
|---|---|---|:-:|
| A (NVFP4) | 0.013036 | — | **passed** |
| B (INT8, fused QKV live) | 0.016344 | **+25.4 %** | failed |
| C (INT8, fused QKV off) | 0.016405 | +25.8 % (**+0.37 % vs B**) | failed |

Read this the way the companion document's correction 5 demands. The local
per-run decode cv is ≈0.35 %, so:

* **A → B, +25.4 %, is ≈70 σ.** The local instrument resolves this without
  argument, and it does *not* need the ranked host: the NVFP4 bank is worth
  roughly a quarter of the decode leg. That is the single largest measured
  effect in this whole campaign, and it is already switched on.
* **B → C, +0.37 %, is ≈1 σ at n = 1 and is therefore not resolved.** The fused
  norm+affine QKV suite is worth somewhere between nothing and ~0.4 % of decode
  *inside a configuration that is already 25 % behind*. Resolving it would take
  ~40 local replicates to buy information about a path that ships disabled.

So the honest verdict on the advisor's question is: **do not retire it, and do
not tune it.** It is the correct, slower fallback for a bank we do not ship. The
only thing worth carrying forward is the shadowing fact itself.

### 9.6 The fourth question for §8's checklist

§8 asks whether a constant is consumed, whether it is clamped, and whether its
path is reachable *on the measuring host*. This census adds:

> **4. Is the path shadowed at runtime by a better path that is enabled by
> default?**

A2 (§3) is unreachable because of the *hardware*: `is_nax_available()` is false
here and true on the ranked host, so the arm is real but unmeasurable locally.
The fused QKV suite is unreachable because of *software preference*: it is
unmeasurable **and** unshippable, on every host, until someone deliberately
turns off a 25 % win. Those two failure modes look identical in a local A/B —
both print 0.00 % — and they have opposite consequences. Question 4 separates
them, and it costs one `DARKBLOOM_TRACE_FUSION=1` run.

Cost of this section: three local runs (~7.5 min), zero source changes, zero
submission slots.


## 10. CORRECTION 8: the SDPA *vector* family is off the scored path entirely

This section retracts the last live arm in §8 and, more usefully, explains three
separate null results that I had filed as independent mysteries. It cost zero
builds and zero submission slots: everything below is static reading of code I
had already opened, plus the fusion census artifacts from §9 that were already
on disk.

The claim being retracted:

> `DARKBLOOM_AOT_SDPA_2PASS_PLANES` = 1 sits below its clamp, therefore
> 1 -> 2 or 1 -> 4 is a genuinely open decode-side arm.

The clamp arithmetic is right. The *reachability* is wrong, twice over, and
either error alone is fatal.

### 10.1 Gate one: the benchmark's KV length never reaches 1024

The 2-pass variant is not the default decode kernel. It is selected by an
explicit length test in the dispatcher
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/scaled_dot_product_attention.cpp:744-753`),
quoted verbatim:

```cpp
    // We route to the 2 pass fused attention if
    // - The device is large and the sequence length long
    // - The sequence length is even longer and we have gqa
    bool do_causal = do_causal_ && q.shape(2) > 1;
    char devc = d.get_architecture().back();
    if (((devc == 'd' || devc == 's') && k.shape(2) >= 1024) ||
        (k.shape(1) < q.shape(1) && k.shape(2) >= 4096)) {
      sdpa_vector_2pass(s, d, q, k, v, o, scale_, do_causal, mask, sinks);
    } else {
      sdpa_vector(s, d, q, k, v, o, scale_, do_causal, mask, sinks);
    }
```

`devc` is the `d.get_architecture().back()` value — the ninth of the nine
arch-suffix fork sites catalogued in §7. Note that the *else* branch is the
plain `sdpa_vector`: 2-pass is the exception, not the default, and the
upstream comment says so.

So the kernel needs a **key sequence length of at least 1024** on this host
family. What does the scored benchmark actually feed it?
`Sources/MLXFastCore/Constants.swift`:

| constant | line | value |
|---|---|---|
| `benchmarkPrefillPromptTokens` | 94 | 512 |
| `benchmarkDecodeSteps` | 109 | **128** |
| `benchmarkDecodeSeedTokens` | 123 | 512 |
| `localSubmitBenchmarkDecodeSteps` | 117 | 1023 |

The scored decode run therefore starts from a 512-token cache and walks it to
**640**. Even if a cache implementation over-allocated in 256-step blocks, the
padded length would top out at 768. `640 < 1024`, with 384 tokens of margin.

Consequences, in order of how much they hurt:

1. **`sdpa_vector_2pass` is never dispatched in the scored window.** Not on the
   ranked host, not locally, not on any arch letter — the `'d'/'s'` branch needs
   1024 and the fallback branch needs 4096. (The fallback's GQA precondition is
   satisfied — 8 KV heads against 48 or 64 query heads, §9's row arithmetic —
   but 4096 is even further away.)
2. The only configuration that crosses 1024 is `--local-submit`
   (`localSubmitBenchmarkDecodeSteps = 1023`, so 512 -> 1535), which is the
   unscored pre-submit correctness gate. And even there only the *full*-attention
   layers could qualify: the sliding layers hold a `RotatingKVCache(maxSize: 512)`
   whose `k.shape(2)` is pinned at 512 forever.
3. Therefore the retracted arm could at best have moved a kernel that runs in a
   gate nobody scores. Tuning it would have produced a clean 0.00 % A/B and I
   would have filed it as "no effect", which is the *wrong* conclusion. The right
   one is "not executed".

### 10.2 Gate two: the model does not call the library's SDPA on the decode path at all

Even at 1024+ tokens the dispatcher above would not be reached, because the
Laguna decode path never gets there. Two fused kernels intercept it in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`:

| site | line | requires | kernel |
|---|---|---|---|
| sliding fused attention | 6152 | `cache as? RotatingKVCache`, `maxSize == slidingWindow`, `values.dims == (1, 1, nKVHeads*headDim)` | `laguna_sliding_fused_attn_ring_v1` |
| full fused attention | 6178 | `cache as? KVCacheSimple`, `fusedAppendPrepare()` succeeds | fused full-attention path |

and the dispatch at `:6276` is

```
fusedAttended ?? attentionWithCacheUpdate(...)
```

i.e. the library call is the *fallback*, taken only when both fused forms
decline. Both are on by default — `DARKBLOOM_FUSED_SLIDING_ATTN != "0"` at
`:1504` and `DARKBLOOM_FUSED_FULL_ATTN != "0"` at `:2010`.

The census from §9 already proved they fire in the shipped configuration:
`research/artifacts/fern-r109f/census/sites-A.txt` (arm A = defaults, the
configuration we submit) contains both

```
sliding fused attention
full fused attention
```

so this is not a reading of the flags, it is a runtime observation I had
collected two sections earlier and failed to connect to the arm I was defending
one section above.

And the strongest single check, which takes one command:

```
$ grep -rn 'scaledDotProductAttention' Sources/
$        # (no output)
```

**Zero call sites in the entire editable model.** The only reference is in the
vendored library helper
(`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift:48-49`), which
the model reaches only through the fall-through in §10.4.

### 10.3 What the two gates explain

Three separate nulls collapse into one cause.

**(a) The `MLX_SDPA_BLOCKS` sweep was a structural zero, not a null result.**
§7 records eight local runs (16/32/128/256/512 plus replays) spanning
12850–13019 µs decode, all correct, all inside the 0.35 % host band, and I filed
it as "the knob does nothing". The env read is at
`scaled_dot_product_attention.cpp:477` — which is *inside* `sdpa_vector_2pass`
(function opens at `:418`, block ladder `:443-479`). A function that is never
dispatched cannot respond to its own tuning parameter. The eight runs measured
the host's noise floor eight times, which is exactly what they look like in
hindsight: cv ≈0.35 %, no trend, no ordering by block size.

That is a much better outcome than "null". A null invites a bigger sweep. A
structural zero closes the file.

**(b) `DARKBLOOM_AOT_SDPA_PLANES` is a fossil on an unreached path.** §8 already
showed it is pinned at its cap (`v_planes = min(PLANES, V/BD = 4)`,
`sdpa_vector.h:90`, with `PLANES = 4` at `:8`). Now the containing function
(`sdpa_vector`, dispatched from `sdpa.cpp:329`) is also known to be unreachable
from the model. Two independent reasons to leave it alone.

**(c) The retracted arm.** `DARKBLOOM_AOT_SDPA_2PASS_PLANES`
(`sdpa_vector.h:11-13`, value 1, clamp `o_planes = min(PLANES, elem_per_thread =
D/BD = 4)` at `:688`, template at `:670`) is unclamped and unreachable. For the
record, so nobody has to re-derive it: at PLANES=1 the kernel takes the serial
reduction at `:744-754` (4 stores, 7 barriers, 4 KiB threadgroup memory); at
PLANES=4 it takes the parallel form at `:724-743` (1 barrier, 16 KiB). That
really is a plausible win. It is a plausible win in a kernel this benchmark does
not run.

Unclamped-but-unreachable is *worse* than clamped-at-cap, because a clamp is
visible in three lines of arithmetic in the file you are already reading, and
reachability is not visible anywhere in that file.

### 10.4 The corrected map of the attention surface

Where attention actually happens on the scored path:

| L (query length) | cache | who serves it | editable? | locally observable? |
|---|---|---|---|---|
| 1 (decode, sliding layers) | `RotatingKVCache(maxSize: 512)` | `laguna_sliding_fused_attn_ring_v1`, LRM `:6152` | yes (`Sources/MLXFastModel`) | yes |
| 1 (decode, full layers) | `KVCacheSimple` | fused full attention, LRM `:6178` | yes | yes |
| 512 (prefill) | fresh | `MLXFast.scaledDotProductAttention` -> `sdpa_full_self_attention_nax` (`sdpa.cpp:177`, body `:18`) on NAX; `_metal` (`:166`) locally | kernels only (`kernels/steel/attn`, `kernels/scaled_dot_product_attention.metal`) | **no** (NAX fork, §2) |
| never | — | `sdpa_vector` (`:329`), `sdpa_vector_2pass` (`:418`) | `kernels/sdpa_vector.h` is editable | irrelevant |

The prefill fall-through is worth spelling out, because it is the only surviving
consumer of the library entry point. At L=512 the fused sliding form fails its
`values.dims(1, 1, ·)` shape test and the fused full form is not offered a
`KVCacheSimple`, so `:6276` falls to `attentionWithCacheUpdate`
(`AttentionUtils.swift:5`). The continuous-batching branch at `:13` (protocol in
`MLXLMCommon/ContinuousBatchingV2/CBv2Contracts.swift:352`) does not apply,
because `newCache` (`LagunaRuntimeModel.swift:11815-11821`) hands back plain
`StandardKVCache()` / `RotatingKVCache(maxSize: slidingWindow, keep: 0)`. So
`:48-49` runs `cache.update` and then `MLXFast.scaledDotProductAttention`, and
`q.shape(2) = 512 > 8` fails the vector-dispatch test at `sdpa.cpp:634`, routing
to the full self-attention family.

**The honest replacement arm.** If someone wants an attention arm, it is that
prefill full-attention family — `kernels/steel/attn` and
`kernels/scaled_dot_product_attention.metal`, both in `editablePaths`. Its
awkward property is the §2 one: it is the NAX-forked path, so it cannot be timed
here at all. Its attractive property is that it lands on the leg with by far the
tightest instrument in this campaign: pooled candidate-prefill sd **0.0750 %**
over 3 df, so a 0.30 % effect is adjudicable in **2 receipts**, against 78 on the
published score. That is the same leg that unblocks maple-tanjiro's A2 (#692),
and it is the one forward-looking recommendation I would carry out of this
document.

### 10.5 The fifth question, and the consolidated checklist

§8 asked three questions of a candidate knob; §9.6 added a fourth. This section
adds the fifth, and it is the one that caught me:

> **5. Do the benchmark's actual shapes reach the branch — and does the model
> call that library function at all?**

The full checklist, in the order that costs least to answer:

1. **Where is the constant consumed?** `grep` for it; read the enclosing
   function, not the `#define`.
2. **Is it clamped?** Print the bound next to the value. (Killed
   `DARKBLOOM_AOT_SDPA_PLANES` and A1's `darkbloom_expert_down_bn`, §8.)
3. **Is the enclosing kernel host-gated?** `is_nax_available()`, arch suffix.
   (§2, §7 — makes an arm real but locally unmeasurable.)
4. **Is the path shadowed at runtime by a better default?** One
   `DARKBLOOM_TRACE_FUSION=1` run. (§9 — the fused norm+affine QKV suite.)
5. **Do the benchmark's shapes reach the branch, and does the model call the
   library at all?** Read the dispatch predicate against `Constants.swift`, then
   `grep -rn <library entry point> Sources/`. (This section.)

Questions 1, 2 and 5 are free — they are reading, not running. Question 4 costs
one local run. Question 3 costs a probe you write once. I spent the campaign's
scarce resources (builds and submission slots) on arms that questions 1–5 would
have screened out in minutes, and the pattern across the retraction ledger is now
hard to miss: most of my eight self-corrections were claims I could have
falsified before measuring anything, and did not. The cheap questions are cheap
precisely because they are boring.

Cost of this section: zero builds, zero runs, zero submission slots. It retracts
one arm, converts one null into a closed file, and promotes the prefill kernel
family from "third-ranked transfer risk" to the only attention arm worth having.


### 10.6 The replacement arm, scope-verified — and the fact that we already fired into it once

§10.4 nominated "the prefill full-attention family" as the honest replacement for
the arm §10.3 retracted. That nomination was itself a reachability claim, so the
only defensible thing to do was run the five questions on it before letting it
stand. I did. It survives, but with two conditions I did not anticipate, and it
turns out this campaign has **already shipped one receipt into it** — which is
the strongest evidence in the whole document that the leg is adjudicable.

**(a) Editable scope: the family is open in three layers, closed in two.**

| layer | file | `editablePaths`? |
|---|---|:-:|
| kernel body (feeds AOT metallib *and* the JIT string) | `kernels/steel/attn/` — 10 files: `attn.h`, `loader.h`, `mma.h`, `nax.h`, `params.h`, `transforms.h`, `kernels/steel_attention{,_nax}.{h,metal}` | **yes** (directory entry) |
| JIT source string | `mlx-generated/steel_attention_nax.cpp` (and `steel_attention.cpp`) | **yes** |
| kernel factory + compile-time defines | `get_steel_attention_nax_kernel`, `jit_kernels.cpp:1344` (declared `kernels.h:389`) | **yes** |
| non-JIT factory | the same symbol at `nojit_kernels.cpp:458` | **no** |
| dispatch, tile choice, launch grid | `scaled_dot_product_attention.cpp:18-164` | **no** |

Contrast with §10.3's retracted arm, where the *only* editable file
(`kernels/sdpa_vector.h`) sat behind a dispatch predicate that the scored shapes
never satisfy. Here the reachable code and the editable code are the same code.

**(b) The host gate, verbatim.** `sdpa_full_self_attention_metal`
(`scaled_dot_product_attention.cpp:166`) forwards to the NAX kernel at `:177`
only when

```
metal::is_nax_available() && q.shape(3) != 80 &&
    (env::enable_tf32() || q.dtype() != float32)
```

headDim is 128 (so `!= 80` holds) and the model is bfloat16 (so the third
conjunct holds without `tf32`), which leaves `is_nax_available()` as the single
discriminator — true on the ranked host, false here (§1). This arm is therefore
**correct-only locally and fast-only remotely**: I can prove a change is
bit-exact on this machine and cannot see one microsecond of its effect.

**(c) The geometry is frozen by the non-editable side.** `:31-36` hardcodes
`wm=4, wn=1, bd=q.shape(-1)=128, bq=64, bk=32`, and `:160-161` launches
`grid_dims=(NQ,H,B)` with `NQ=ceil(qL/bq)` and `group_dims=(32,wm,wn)`. Every one
of those numbers is computed in the file I may not touch, so an editable-side
change that alters tile shape or threads-per-group desynchronises the grid and is
simply wrong. Three consequences worth writing down before anyone proposes a
tiling arm:

1. **Kernel-body-only.** Legal: loop order, staging/prefetch discipline,
   threadgroup-memory layout, accumulator handling, mask/causal specialisation,
   instruction selection. Illegal: `bq`, `bk`, `wm`, `wn`, threads per group.
2. **The aligned specialisation is the only one scored.** At the benchmark's
   shapes `qL=512` and `kL≥512`, so `align_Q = (512 % 64 == 0)` and
   `align_K = (512 % 32 == 0)` (`:46-47`) are both true, and function constants
   200/201 (`:53-54`) select the aligned path. Any cleverness confined to the ragged tail
   (`qL_rem`, `kL_rem`, both zero here) is unscored — the same class of mistake as
   §10.3, one level down.
3. `NQ=8` blocks × `H` heads × `B` batches is the entire parallel decomposition,
   so occupancy arguments have to be made against that grid, not against a
   hypothetical one.

**(d) Three live knobs, all of them `_nax`-only.** The factory at `:1344`
concatenates three define-injectors before the kernel source:

| define | env var and test | default | status |
|---|---|:-:|---|
| `DARKBLOOM_ATTN_QHOIST` | `== "1"` (`jit_kernels.cpp:1307`) | **off** | tried — ticket 3, −3.82 σ, reverted (see (e)) |
| `DARKBLOOM_ATTN_QBLOCK_MAJOR` | `!= "0"` (`:1319`) | **on** | untested; only the OFF direction is available |
| `DARKBLOOM_ATTN_QBLOCK_ZIGZAG` | `!= "0"` (`:1331`) | **on** | untested; only the OFF direction is available |

`DARKBLOOM_ATTN_TRACE=1` makes all three print `mlxfast: attn <knob>: enabled=…`
to stderr, which is the §9-style observability handle for this family. The
critical detail is negative: the **non**-NAX factory
`get_steel_attention_kernel` (`:1269`) injects *none* of the three. So on this
host the knobs are not merely unmeasurable, they are unobservable — the static
initialisers that read the environment never run, and even the trace prints
nothing. Two of the three are default-on, meaning the only experiment they offer
is "how much does the existing Q-block scheduling buy", a diagnostic rather than
a candidate win; QHOIST is the only one whose ON direction was ever open, and it
is spent.

**(e) The positive control: we already have a receipt in this family.** Ticket 3
(`37f16a7a`) flipped `DARKBLOOM_ATTN_QHOIST` on — a `#if` in
`steel_attention_nax.h:22-23` with bodies at `:292` and `:369-374` that hoists the
loop-invariant Q fragments out of the K-block loop — and shipped it as receipt
`e4078827`: published **2.52713571388054**, normalized **2.532026957**, i.e.
**−1.36 % = −3.82 σ** against the campaign's own instrument. The damage was
localised exactly where this section says the leg lives: candidate prefill
**196.2976 µs** against 187.6946 / 187.6487 / 187.8374 / 187.6905 / 188.0314 µs
from the campaign's other five receipts, **+4.27 σ**. Ticket 4 (`666a80bb`)
reverted it, and today `git diff 1bc1c895 HEAD --
kernels/steel/attn/ mlx-generated/steel_attention_nax.cpp` is **empty**: the
shipped tree is byte-identical to fork main in this family.

That receipt is worth more than the arm that produced it. §10.4 claimed the
candidate-prefill leg can adjudicate a real change in ~2 receipts because its
pooled instrument sd is 0.0750 % on 3 df. That is a noise-model extrapolation, and
this document's own retraction ledger is mostly noise-model extrapolations that
broke. Ticket 3 is the **empirical** version of the same claim: one receipt, one
real kernel change, 4.3 σ of signal on that leg, unambiguous verdict, revert. The
leg is not a coin flip — it has been exercised, and it resolved.

**(f) The sting, recorded because it is the actual lesson.** The reachability
chain that §10 says I failed to run is quoted *verbatim in that very commit
message*: ticket 3's body walks `callLastPrefillRow` (final layer only, `qL==1`)
→ `attentionWithCacheUpdate` → `ScaledDotProductAttention::use_fallback` (false
at `qL=512>8`, headDim 128 ∈ {64,80,128}) → `sdpa_full_self_attention_metal`
→ `_nax`, and concludes "the nax kernel IS the ranked prefill attention kernel".
So the §8 failure was not that I lacked the method. I had executed it, correctly,
eight commits earlier, on a *different* claim in the same subsystem — and then
asserted the second claim from a `#define` without re-running it. The rule that
follows is procedural, not intellectual: **the five questions are a per-claim
checklist, not a lesson you learn once.** Cheapest possible enforcement, and the
one I would impose on the whole slate: an arm proposal must cite its dispatch
predicate as `file:line`, and if it cannot, it is not an arm yet.

**(g) What this hands the rest of the slate.** maple-tanjiro's A2 (fused-NAX
`bn` 128→64) and maple-edward's #693 (ping-pong tile staging / zero-tgmem
register prefetch, `_nax` port) are in the right family, on the right leg, and
adjudicable at 1–2 receipts — with three caveats they should be told before they
build: the tile geometry above them is frozen (c), only the aligned
specialisation is scored (c2), and the leg to report is
`officialMetrics.prefill_seconds_per_token`, not the composite score, whose
pooled sd is 0.5169 % and would need 78 receipts for the same question. And the
honest expectation is set by (e): the one arm this family has already seen moved
the leg by 4.3 σ in the *wrong* direction.

Cost of this subsection: zero builds, zero runs, zero submission slots — five
files read and one `git diff`.

