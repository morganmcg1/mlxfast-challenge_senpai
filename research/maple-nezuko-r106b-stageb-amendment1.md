# R106-B Stage B — Preregistration Amendment 1

Student: `maple-nezuko`. PR #616, assignment `maple-r106-b-revert-residual-forensics`,
revision `r106-b-rev3`. Amends `research/maple-nezuko-r106b-stageb-preregistration.md`.

**This amendment is committed before any arm it introduces is measured.** The H4
triage numbers quoted below were already on disk when it was written; every arm
declared *new* here (K, P) is unmeasured at commit time.

---

## 1. Trigger: the H4 rung of the preregistered ladder is refuted

Preregistered mechanism (Stage B primary): the sliding decode-attention kernel
`laguna_sliding_fused_attn_ring_v1` maps 2 query heads per threadgroup, so the 8
query heads sharing one KV head are spread over 4 threadgroups and each KV byte is
*requested* 4x. Packing 4 query heads per threadgroup (`H4`) halves that to 2x,
cutting requested bytes per call from 8 MiB to 4 MiB against 2 MiB unique. The
mechanism predicted a win if and only if the kernel is request-bandwidth-bound.

Triage (`research/maple-nezuko-r106b-h4-triage.sh CHCHCH`, `--local-iterate`,
**not evidence** per Rule 86 — sign only), decode seconds/token:

| idx | arm | decode s/token | correctness |
|-----|-----|----------------|-------------|
| 1 | C (2 heads/TG, shipped) | 0.0129654143828125 | true |
| 2 | H (4 heads/TG, H4) | 0.0130461884765625 | true |
| 3 | C | 0.012956862953125 | true |
| 4 | H | 0.01297028353125 | true |
| 5 | C | 0.0129566861953125 | true |
| 6 | H | 0.0130565983046875 | true |

Paired against the bracketing control(s):

* pair 1 (H2 vs mean(C1,C3)): +85.1 us/step
* pair 2 (H4 vs mean(C3,C5)): +13.5 us/step
* pair 3 (H6 vs C5): +99.9 us/step
* mean **+66.2 us/step** (~+1.0 % of `cs` at 65.67 us/step per 1 %), sign
  positive (slower) in all three pairs, correctness `true` in both arms.

The kernel costs 670 us/step (22.34 us/call x 30 calls), so H4 is **+9.9 % on the
kernel it replaces**.

### 1.1 Wave arithmetic makes this a clean refutation, not a null

Threadgroup memory is 18,432 B for `v1` and 20,992 B for H4; both exceed half of
the 32,768 B limit, so at most one threadgroup is resident per GPU core on this
host (Apple M4 Pro, 20 cores).

* `v1`: 64 heads / 2 = **32 threadgroups** over 20 cores => 2 dispatch waves,
  wall time ~= 2 x T1 (the second wave leaves 8 cores idle).
* `H4`: 64 heads / 4 = **16 threadgroups** => 1 wave, wall time = T4.

Pure work-scaling (T4 = 2 x T1) therefore predicts *parity*, and the halved KV
request volume was the only source of a win. Measured:

    T4 / T1 = 2 x 1.099 = 2.20   (range 2.04 - 2.30 over the three pairs)

So doubling the independent work resident in a core **doubled its time**, and
halving requested KV bytes bought nothing measurable.

**Conclusion (recorded as a closed family):** the sliding decode-attention kernel
is *not* request-bandwidth-bound on M4 Pro. The 4x KV request amplification is
effectively free. This independently confirms the roofline interim in
`research/nezuko-decode-roofline.md` (DRAM floor 8.1 us/call vs 22.0 us/call
measured; "the 95-112 GB/s figure is not a bandwidth defect") and **closes the
follow-up recorded there** ("a follow-up would map four query heads per
threadgroup, cutting the 4x/3x logical KV re-read to 2x").

## 2. Corollaries refuted a priori by the same measurement (not implemented)

The H4 datum is a general statement about how this kernel responds to *more
independent work per core*, so it kills two further levers that were on my list:

* **H-OCC (threadgroup-memory reduction for occupancy).**
  `research/nezuko-decode-roofline.md` proposed halving `outputs4[BN*BDP]`
  (16,896 B of the 18,432 B total) by doing the cross-simdgroup transpose in two
  barrier-separated half-passes, dropping to ~9,984 B so that 2 threadgroups fit
  per core, "removing the wave tail". Refuted twice over:
  1. H4 shows that adding a second independent unit of work to a core costs a
     full 2x in time. Co-residency of 2 threadgroups is the same experiment with
     a different spelling, so it cannot hide latency that is not there.
  2. The tail arithmetic does not close anyway. With 32 threadgroups on 20 cores,
     co-residency assigns 12 cores two threadgroups and 8 cores one; the loaded
     cores still take 2 x T1, so wall time is unchanged. Fixing the tail needs a
     threadgroup count that is a multiple of 20, which the head geometry
     (64 heads, 8 KV heads => 64/32/16 threadgroups) cannot produce, and the only
     other route is KV-range splitting, a family already closed by #196/#566.
  3. It is not even free: the split epilogue doubles the epilogue's cross-lane
     reduction latency while half the machine idles.
* **ILP / latency-hiding levers inside this kernel** (deeper software pipelining
  beyond the current depth 4, more independent heads or rows in flight). Same
  argument: measured work-scaling is linear-to-slightly-superlinear, so there are
  no idle issue slots to fill.

## 3. Demotion of the H4/d2 rung

The preregistered fallback ladder was "H4/d4 -> H4/d2 only". H4/d2 (pipeline
depth 2 instead of 4) can only remove the ~7 % superlinearity that I attribute to
register pressure (~64 live registers vs ~44 in `v1`, and 8 barriers vs 4); its
own best case is therefore *parity with the control*, never a win, because the
2x work-scaling term survives untouched. The rung is therefore **demoted from
candidate to optional confound attribution** and will only be run as triage if
time remains after the primary evidence campaign. Its omission is a declared
deviation, not a silent one.

## 4. New Stage B primary candidate: H-PACKRED (packed cross-lane reduction)

### 4.1 Mechanism

The kernel's lane mapping is: each of 32 simdgroups owns 16 of the 512 window
rows; within a simdgroup each lane owns 4 of the 128 head dimensions. A QK dot
product is therefore 4 lane-local FMAs followed by a **32-lane `simd_sum`**, and
the online-softmax epilogue transposes through `outputs4` and reduces again. Per
threadgroup, per lane, the cross-lane reduction count is:

| site | reductions | butterfly steps |
|------|-----------|-----------------|
| main loop (16 rows x 2 heads, 4 unrolled slots x 4 iterations) | 32 x `simd_sum` | 160 |
| epilogue (2 x `simd_max`, 2 x `simd_sum` for the softmax sums, 8 x `simd_sum` for the 2 x float4 output planes) | 12 | 60 |
| prologue RMSNorm + RoPE | 1 `simd_sum` + 4 `simd_shuffle` | 9 |
| **total** | | **~229** |

Against that, the *useful* arithmetic per row per head per lane is 4 QK FMAs plus
4 output FMAs. Measured throughput is 0.75 TFLOP/s = ~10 % of this host's ~7.2
TFLOP/s peak, and section 1 has now excluded bandwidth, occupancy and ILP. The
remaining suspect is the reduction/shuffle instruction stream itself.

`simd_sum` reduces one scalar. Every site above reduces **two or four scalars at
the same program point**, so the shuffle traffic can be shared by reducing a
`float2`/`float4` in a hand-rolled butterfly (`simd_shuffle_xor` masks
16/8/4/2/1). The adds are unchanged in count; only the shuffles are shared:

| site | shuffles now | shuffles packed |
|------|--------------|-----------------|
| main loop | 160 | 80 (`float2`, both heads) |
| epilogue outputs | 40 | 10 (`float4` per head) |
| epilogue max + sums | 20 | 10 (`float2` each) |
| **total** | **220** | **~100** |

### 4.2 Cost model and prediction

Two-sided prediction so the arm can fail cleanly:

* If `simd_sum` lowers to a 5-step shuffle+add butterfly (the usual lowering),
  H-PACKRED removes ~120 shuffle instructions per lane per call out of a stream
  whose useful FMA content is ~256 instructions per lane per call. Even at a
  conservative 1 issue slot per shuffle this is a **10-25 % cut on the 670 us/step
  kernel = 67-168 us/step = 1.0-2.6 % of `cs`**.
* If `simd_sum` lowers to a native hardware reduction instruction (Apple 7+ has
  quad/simd reduction primitives), the packed butterfly is *more* instructions and
  H-PACKRED must lose. That is a real possibility and the reason for the probe in
  section 5.

Dispatch count, grid, threadgroup size, threadgroup memory and every device
memory access are **unchanged** (Rule 65's +2.3403 us/dispatch does not apply; no
new dispatch). The change is confined to how already-loaded values are reduced.

### 4.3 Bit-exactness

**Not guaranteed, and declared as such in advance.** `simd_max` packing is exact
(max has no rounding). `simd_sum` packing is exact **iff** the vendor's `simd_sum`
uses the same association as my xor butterfly; the association is unspecified, so
this is an empirical question. Decision rule, fixed now:

* Zero-tolerance oracle `research/run_upstream_equivalence.sh` passes with the
  gate on => the variant is bit-exact and shippable on its own.
* Oracle fails => the variant is reported as **requiring frieren's #597 margin
  certificate before it can ship**, its measured delta is still published, and it
  is *not* proposed for fern's #625 integration tree in this assignment.

### 4.4 Arms and protocol

* **C** — control: `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED` unset, shipped kernel.
* **K** — candidate: `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1`.

The control kernel's Metal source is refactored so that both arms share one source
string and differ only in the reduction macro definitions supplied through the
`header:` argument; the control macro expands to exactly the `simd_sum`/`simd_max`
spelling that ships today. The refactor is behaviour-preserving by construction and
is checked by (i) the zero-tolerance oracle with the gate off and (ii) the control
arm's own timing in the triage table.

Triage `C K C K C P` on `--local-iterate` (sign only, never evidence). Evidence
campaign, only if the triage sign is favourable: `research/maple-nezuko-r106b-h4-paired.sh`
retargeted to the PACKRED gate, `--local-submit`, order **`CKCKCK`**, 3 paired
differences, declared dof = 2, t(0.975, 2) = 4.3027, primary metric
`decode_us_per_step` converted to % of `cs` at 0.015228 %/us.

### 4.5 Outcome labels (same scheme as the parent preregistration)

* **V-RECOVER** — K faster than C, 95 % CI excludes 0, oracle exact.
* **V-ATTRIB** — K faster, CI excludes 0, oracle *fails* => real speedup that is
  blocked on a margin certificate; handed to #597/#625 rather than shipped.
* **N-RECOVER** — CI covers 0 (no resolvable effect).
* **N-CORRECT** — K faster but correctness or equivalence broken in a way that is
  not a mere last-bit association difference.
* **N-RESIDUAL** — Stage 0's unexplained-residual finding stands unchanged
  (it does; see section 7).

## 5. New diagnostic probe D-SIMDSUM (non-evidence, deliberately incorrect)

To decide between the two branches of section 4.2 *before* spending the evidence
budget, and to bound the payoff of the Stage C proposal in section 6, I declare a
counterfactual probe:

* **P** — `DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1` deletes the 8 main-loop
  `simd_sum` calls and uses each lane's partial dot product as if it were the full
  one. Every device load, every FMA, every barrier and the whole epilogue are
  untouched, so the *only* difference is the removed reduction.
* This produces **numerically wrong attention output on purpose**. It is a
  measurement instrument, not a candidate. It is run only under
  `--local-iterate`, is never evidence, is never submitted, and the arm is
  **deleted from the final patch**. `passed_correctness` is expected to be
  `false` for arm P and that expectation is recorded here in advance.
* Reading: the P-vs-C delta is the total cost of the main-loop cross-lane
  reduction. H-PACKRED can capture at most half of it (it halves shuffles but
  keeps all adds). If P-vs-C is smaller than ~2x the 15 us/step `--local-iterate`
  noise scale, the reduction is cheap, `simd_sum` is likely native, H-PACKRED is
  abandoned without spending evidence runs, and Stage B closes as N-RECOVER on the
  H4 arm alone.

## 6. Stage C proposal P-ROWLANE (described, deliberately not implemented here)

If D-SIMDSUM shows the reduction is expensive, the structural fix is larger than
this assignment should attempt in the time remaining, so it is handed over as a
costed proposal rather than an unvalidated patch:

Re-lay-out the kernel so that **phase 1 gives one thread one window row** (1024
threads = 512 rows x 2 heads exactly, each thread reading a full 128-dim K row and
computing its score with 128 lane-local FMAs and *zero* cross-lane traffic, then
writing the score to threadgroup memory: 512 floats x 2 heads = 4 KiB), and
**phase 2 keeps the current dim-per-lane layout** for `o = sum_j p_j v_j`, which
needs only FMAs and one final transpose reduction. This removes all 32 main-loop
`simd_sum` calls instead of halving their shuffles.

It is explicitly **not bit-exact**: the QK dot product changes from a 4-element
lane-local partial plus a 32-lane tree to a 128-element sequential accumulation,
and the softmax changes from online-rescaled to two-pass. It therefore requires
frieren's #597 margin certificate and a full golden-set re-baseline, and it
overlaps nothing currently held by tanjiro #620 (prefill), edward #629 (QKV
projection) or alphonse #630 (routed K-loop).

## 7. What does not change

* Stage 0's **N-RESIDUAL** finding stands: residual D = +19.405 us/step, pooled
  sd 11.920, dof 10, 95 % CI [-18.156, +56.966], z = +1.151; T = D - 4P =
  +20.149, CI [-17.877, +58.175]. Both CIs cover zero.
* No official submission is made by this assignment; `senpai/submit-official.sh`
  is not invoked. No receipts are spent.
* Closed families listed in the parent preregistration remain closed, and
  sections 1 and 2 above *add* three: head-packing / KV-request-amplification
  reduction in the sliding decode-attention kernel; threadgroup-memory reduction
  for occupancy in that kernel; and ILP/latency-hiding levers in that kernel.
