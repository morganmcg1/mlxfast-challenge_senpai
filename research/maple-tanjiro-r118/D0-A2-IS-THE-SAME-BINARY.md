# R118-A Deliverable 0 — A2 and receipt `be958bcd` are the same binary. A2 is a spent ticket; fire A1.

Written 2026-08-11T03:5xZ by maple-tanjiro. Answer to the "due immediately" item in
PR #709. Fern's fire order is unblocked by this file: **A2 is spent, A1 goes first.**

## The one-paragraph answer

**They are the same binary, and the `wn` 4 -> 2 half does not make A2 different — it
is the half that makes A2 *land on* `(64, 64, 256, 2, 2)` in the first place.** My
branch-head A2 (`maple-tanjiro/r110-prefill-nax-arm-factory`, head `6fcc18a1`, the
17-line `DARKBLOOM_FUSED_NAX_NARROW_BN` hunk in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`) AOT-instantiates the
tuple **`(bm, bn, bk, wm, wn) = (64, 64, 256, 2, 2)`** for `M >= 64 && N <= 1024` on
this `devc` in `{s, c, d}` architecture class, versus the incumbent
`(64, 128, 256, 2, 4)`. The two knobs are not separable: halving `bn` *alone* would
emit `(64, 64, 256, 2, 4)`, whose `SN = bn / wn = 16` is not one of the
AOT-instantiated shapes and would force a JIT path with a different `tile_matmad_nax`
branch; halving `wn` with it keeps `SM x SN` at `32 x 32` and `TN` at 2, so the *same*
compiled kernel runs with twice the threadgroups on N. That is exactly the tuple in
receipt `be958bcd-eac1-4a0c-92e6-d41f699b2ec7`. There is no residual "second half" of
A2 left unfired. **A2 is a spent ticket. Fire A1 (`darkbloom_expert_down_bn()` 64 -> 32).**

## The evidence, so you do not have to take my word for it

Three independent confirmations, in increasing order of strength:

1. **Source.** `matmul.cpp:229-241` on my branch head. The incumbent block sets
   `bm = 64; wm = 2;` and `bk = (K >= 8192 && K > (M + N)) ? 64 : 256;` leaving
   `bn = 128, wn = 4`. My hunk adds, inside that same block:

       if (darkbloom_fused_nax_narrow_bn() && M >= 64 && N <= 1024) {
         bn = 64;
         wn = 2;
       }

   Both assignments are inside one `if`. There is no build in which one fires without
   the other. `bk` is untouched and resolves to 256 for every prefill `wk`/`wv` shape
   in this model, so the emitted
   `base_name = steel_gemm_fused_nax_nt_bf16_bf16_bm64_bn64_bk256_wm2_wn2`.

2. **My own commit message on the hunk** already states the tuple verbatim: *"the
   emitted kernel is the AOT-instantiated (64, 64, 256, 2, 2) tuple running the same
   gemm_loop template as the incumbent."* I wrote that before the receipt existed.

3. **Your own record closes it.** `research/CURRENT_RESEARCH_STATE.md` §0P.20 says the
   fired tree for `be958bcd` was *"advisor HEAD `711c1404` **plus exactly** tanjiro's
   17-line `DARKBLOOM_FUSED_NAX_NARROW_BN` hunk"*, with the same gate
   (`M >= 64 && N <= 1024`) and the same tuple `(64,64,256,2,2)`. The receipt did not
   fire a look-alike; it fired this file. So the comparison is not "same tuple, maybe
   different gate" — it is byte-identical provenance.

The only way the two could have differed is if the receipt had applied the tuple
without the shape gate, which would also have changed decode coverage. §0P.20's decode
leg rules that out from the other side: A2 decode is **+0.023 %** vs the HEAD-class
mean, i.e. the `M >= 64` gate demonstrably held, which is what my hunk encodes.

## What I accept as a consequence

`N-FUSED-NAX-NARROW-BN-BELOW-BAR` is correct and I adopt it. My predicted band
(+0.44 ... +1.20 % of candidate prefill) sits entirely above the receipt's 95 % upper
bound of +0.361 %. The arm is refuted **at the size it was designed to produce**, which
is a stronger statement than "inconclusive", and I will not re-propose the
under-filled-dispatch tile-shape axis on the `wk`/`wv` fused-NAX family.

One methodological correction I owe you, since it is the reason my band was wrong:
my +0.44 ... +1.20 % came from a **profiled-busy** occupancy argument (more threadgroups
=> better tail fill on the 78 `wk`/`wv` dispatches) with **no tau correction applied**.
Under my own `L-PROFILED-BUSY-OVERPREDICTS-WALL-2X` (tau = 0.54 [0.29, 0.79]), and
under the campaign default tau ~ 0.4 after cedar's independent [0.27, 0.43], that band
should have been published as **+0.18 ... +0.48 %** at tau = 0.4. The receipt's upper
bound of +0.361 % does *not* exclude the tau-corrected band. So the honest reading is
narrower than "the physics was wrong": **the physics may have been directionally right
and simply too small for the channel to see** — which is exactly the regime shift you
describe in this brief (the binding constraint moves from size to verifiability). I am
recording it as refuted anyway, because a tau-corrected +0.3 % arm the channel cannot
resolve is operationally identical to no arm, and because re-firing it would cost a
slot to learn nothing.
