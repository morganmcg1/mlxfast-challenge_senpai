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
| decode — attention (`q_len ≤ 8`) | `sdpa_vector`, `sdpa_vector_2pass` | **no** | **yes** |
| prefill — quantized matmul | `qmm`, `gather_qmm`, `gather_qmm_rhs`, `GatherQMM` | **yes** | **no** |
| prefill — dense GEMM | `steel_matmul_regular_axpby_nax`, `steel_gemm_splitk_axpby_nax`, `steel_gemm_segmented_nax`, `gather_mm_rhs_nax` | **yes** | **no** |
| prefill — attention | `sdpa_full_self_attention_nax` | **yes** | **no** |

**Decode is locally measurable. Prefill is not measurable anywhere.** Decode is
0.638 of the score's elasticity and prefill 0.362, so the larger half of the
score is the observable half — which is lucky, and which should decide where the
remaining effort goes.

Three consequences, in descending order of how much work they cancel:

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

---

## 4. The correction this forces on the companion document

`maple-fern-r109f-instrument-collapse.md` §8 recommendation 2 says "move arm
adjudication onto the local iterate". That is right for decode and **wrong for
prefill**, and I would rather state the exception than let the recommendation be
applied where it silently returns 0.00 %.

The corrected form:

> Move **decode** arm adjudication onto the local iterate, where the kernels are
> identical to the ranked host's and repeatability is 0.05–0.10 %. Do not
> attempt to adjudicate **prefill** arms at all on this host: the ranked prefill
> path is NAX and this GPU cannot run it, so a local A/B returns 0.00 % whatever
> the arm does. Prefill arms are adjudicable only on the ranked host, at a cost
> (≈10² receipts/arm) that the shared single-slot channel cannot fund.

This also puts a floor under a claim I should be careful about. In the companion
I wrote that local iterate is a "4–7× better instrument" than ranked. That
comparison was computed on the *decode* leg and it holds there. It does not
transfer to prefill, where the honest ratio is not a number: one instrument
reads 0.00 % by construction and the other needs hundreds of receipts.

A second, smaller correction. My local 2×2 ledger recorded prefill legs as
"≈0.001122 s across all arms", which I read as "prefill is unaffected by these
arms". The stronger and more accurate reading is that local prefill is *inert
by construction* for any NAX-touching arm — a constant there is not evidence of
no effect, it is evidence of no measurement. None of the four arms in that 2×2
touched `_nax` code, so no conclusion changes, but the reasoning was luckier
than it was sound.

---

## 5. What to do instead

1. **Retire A1 and A2 as measurement dead ends** and say so explicitly at the
   05:00Z checkpoint, with §1 and §2 as the evidence. A1 additionally does
   nothing at default env.
2. **Ask #693 which kernel family its port targets** before it spends effort. A
   ping-pong staging change to `sdpa_vector` or the `gather_qmv` path is
   locally measurable and worth having; the identical idea applied to
   `sdpa_full_self_attention_nax` is not adjudicable by anyone in this campaign.
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

- It does not claim the ranked prefill path is already optimal. It claims
  nobody in this campaign can measure whether a change to it helps.
- It does not claim NAX makes the ranked host faster in some unfair way. The
  baseline legs also run on NAX, and the score is a ratio, so NAX cancels to
  first order in the published number. What does not cancel is *observability*:
  a solver on a gen-16 host is editing code they cannot execute.
- It does not explain the residual local/ranked decode ratio of 2.63×. That is
  hardware — clocks, bandwidth, cache — and it is a scale factor, not a change
  of kernel, which is exactly why the decode leg transfers and the prefill leg
  does not.
- It says nothing about correctness. All local arms passed the golden gate
  (`b9509697c08a2cf3`), and the fallback kernels are the reference
  implementations, not approximations.
