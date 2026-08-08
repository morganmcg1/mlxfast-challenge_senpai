# Q1 — Algebraic epilogue normalization on the decode QKV kernel

**PR:** #444 · **assignment:** `maple-2026-08-08d-qkv-algebraic-epilogue` r1
**BASE_SHA:** `730e9c2be89a4ed8cf860e52f930f7ff222d4c95`
**Student:** maple-tanjiro · **Host:** M4 Pro, 20-core GPU, gen 16, 48 GiB

## Verdict: **KILL — refuted at Stage 0.**

The assignment's stopping rule fires on its first clause:

> Stage 0 shows the redundant reduction does not exist as described, or the
> normalization is not hoistable ⇒ **STOP and report the refutation.**

Both halves hold. **No code was changed. Submitted-surface byte delta: 0.**

There are five independent legs. Leg 1 alone fires the stopping rule; legs 2–5
show that the mechanism is not merely absent but that its ceiling is
mis-derived, its sign is inverted at the mandated geometry, and its one real
saving is structurally unavailable.

---

## Leg 1 — The described mechanism does not exist in the live kernel

The assignment claims `lagunaDecodeNVFP4QKVR1` "computes, per output row, a
normalized activation that requires a reduction over the input row, and then
does a **second, cross-simdgroup reduction** in the epilogue".

Neither clause is true. Both live source variants have **exactly one**
`simd_sum`, no threadgroup memory, and no barrier.

`lagunaDecodeNVFP4QKVR1Source` (plain), `:4676-4689`:

```
    for (uint i = 0; i < values_per_thread; ++i) {
        x_thread[i] = float(normalized[column + i]);   // :4677
    }
    result += laguna_tail_nvfp4_qdot(...);
    ...
}
result = simd_sum(result...);                          // :4686  <- the ONLY reduction
if (simd_lid == 0) {                                   // :4687
    projected[out_row] = bfloat(result);               // :4688
}
```

`lagunaDecodeNVFP4QKVLaneMajorSource`, `:4779-4789`: byte-identical epilogue
shape — one `simd_sum` at `:4787`, store at `:4789`.

Exhaustive scan of the whole assigned region for any reduction/staging
primitive (`4600-4920`):

| line | token | in |
|---|---|---|
| `:4686` | `simd_sum` | plain R1 source — **the only reduction** |
| `:4787` | `simd_sum` | lane-major source — **the only reduction** |
| `:4890` | `threadgroup_barrier` | `lagunaNormAffineQKVSource` (`:4880`) |
| `:4894` | `threadgroup bfloat norm_row[axis_size]` | `lagunaNormAffineQKVSource` (`:4880`) |

1. **There is no second cross-simdgroup reduction.** One intra-simdgroup
   `simd_sum` combines the 32 lanes' partial dot products. That is the QMV's
   own dot-product reduction, not a normalization reduction, and it is not
   redundant — deleting it produces a wrong answer.
2. **The normalization is not inside the reduction. It is not in the kernel at
   all.** The kernel consumes `normalized[column + i]` — an *already
   normalized* input produced by a **separate upstream dispatch**,
   `let normalized = fusedQKV ?? inputNorm(input)` at `:5763`. There is no
   `Σ x²`, no `rsqrt`, and no `γ` in this kernel to hoist.

There is therefore nothing to remove. The proposed edit is not a
simplification of the shipping kernel; it would be an **addition** of
normalization work that the kernel does not currently do.

### Where the described mechanism actually lives

The two-reduction, threadgroup-staged structure the assignment describes is
real — it is in `lagunaNormAffineQKVSource(rows:staged:)` at `:4880`, which
stages `threadgroup bfloat norm_row[axis_size]` (`:4894`) and calls the shared
cross-simdgroup tail `lagunaNormReductionTail` (`:762-791`):

```swift
"threadgroup_barrier(mem_flags::mem_threadgroup);",
"if (\(lane) == 0) { local_sums[\(simdGroup)] = acc; }",
"threadgroup_barrier(mem_flags::mem_threadgroup);",
"if (\(simdGroup) == 0) {",
"    acc = simd_sum(local_sums[\(lane)]);",          // <- the second reduction
"    if (\(lane) == 0) { local_inv_mean[0] = metal::precise::rsqrt(acc / ... ); }",
```

That is the INT8 `lagunaNormAffineQKV` family which **the assignment itself
marks "⛔ DEAD BY DEFAULT … never dispatches. #300 closed it. Do not edit
it."** It requires `.affine/8/32`, and `lagunaNativeAffineNVFP4From`
(`:2861-2867`) returns 0, so it is unreachable.

The follow-up spec was written against the geometry of the dead family, then
targeted at the live one.

### The two cited control knobs do not exist

| assignment claim | reality at BASE_SHA |
|---|---|
| `lagunaDecodeNVFP4NormQKVFuseMode` at `:4727`, default 0 | **absent.** `:4727` is prose inside the lane-major doc comment. |
| `lagunaDecodeNVFP4QKVR1SIMDGroups` at `:4615`, default 2 | **absent.** `:4615-4619` is a doc comment; `:4620-4621` is `lagunaDecodeNVFP4QKVR1Enabled` / `DARKBLOOM_DECODE_NVFP4_QKV_R1`. |

```console
$ grep -rn "NormQKVFuse\|NORM_QKV_FUSE\|QKVR1SIMDGroups\|R1_SIMDGROUPS\|QKVFuseMode" Sources/
$                       # no matches
```

The simdgroup count is a hardcoded `constexpr uint num_simdgroups = 2;`
(`:4738`), not a knob. #298's and #309's fuse/geometry ladders were
research-only patches (`research/nezuko_pr48_deconfound.patch`); both PRs
landed with empty submitted-surface diffs. **The "+56.5 µs redundant
cross-simdgroup reduction to remove" is not in the shipping tree** — it existed
only inside #309's research `fuse=3` arm.

---

## Leg 2 — The ≈140 µs ceiling is a double-count of a telescoping ladder

The assignment builds ≈140 µs as `+56.5` (`R640 − G640`) `+ 83.3`
(`N640 − R640`). These are not two independent savings. They are **consecutive
rungs of one ladder** `a0 → G640 → R640 → N640`, and they partially cancel:

```
G640 − a0    = −6.9
R640 − G640  = +56.5     <- the fold INTRODUCES a redundant reduction
N640 − R640  = −83.3     <- the algebraic epilogue REMOVES that same reduction
------------------------------------------------------------
sum          = −33.7  ==  N640 − a0   (#309's own end-to-end number)
```

The identity is exact. `+56.5` is the price arm `R640` pays *relative to*
`G640`; `−83.3` is the removal of **that same term** plus the fold refund. You
cannot both decline to pay `+56.5` and also collect the `−83.3` that consists
of not paying it. Adding their magnitudes counts the redundant reduction twice.

The correct value of the assignment's mechanism at 640 TGs is
`N640 − G640 = +56.5 − 83.3 = ` **`−26.8 µs/step`**, and end-to-end versus the
shipping default it is `N640 − a0 = ` **`−33.7 µs/step`** — which #309 had
already measured and reported. Both are well under the **≈80 µs/step** decode
bar.

#298 states the same telescoping identity explicitly for its own ladder
(`research/maple-nezuko-pr48-deconfound.md:197-198`):

```
(N−0) = (G−0) + (R−G) + (N−R) = −35.4 + 80.4 − 100.0 = −55.0
(V−0) = (RV−0) + (V−RV)       = 308.3 − 88.6         = +219.7
```

and draws the conclusion directly (`:264-266`):

> **the fold itself then spent.** The +80.4 µs of redundant reduction it
> introduced very nearly cancels the −100.0 µs it refunded.

So the ≈140 µs ceiling does not survive contact with either campaign's own
arithmetic. Revised ceiling: **≈27–34 µs/step, ~0.41–0.52 % of score** at
0.015280 %/µs — roughly one third of the decode bar, before any of legs 3–5.

---

## Leg 3 — At the mandated 5120-TG geometry the sign is inverted

The assignment mandates: "**Keep the 5120-TG grid unchanged**". #298 measured
the fold at exactly that geometry (sg2 = 2 simdgroups = 5120 TGs), from
`research/maple-nezuko-pr48-deconfound.md:186-192` (se 13.6 µs, 39 df,
n=8/arm, 192 steps):

| contrast | µs/step | t | 95 % CI | note (verbatim) |
|---|---|---|---|---|
| `RV−0` | **+308.3** | 22.75 | [+280.9, +335.7] | redundant reduction at **5120 TGs** |
| `R−G` | +80.4 | 5.93 | [+53.0, +107.7] | redundant reduction at 640 TGs |
| `V−RV` | −88.6 | −6.54 | [−116.0, −61.2] | dispatch/barrier refund, zero geometry change |
| **`V−0`** | **+219.6** | **16.21** | **[+192.3, +247.0]** | **net fold effect, geometry held at sg2** |
| `N−G` | −19.6 | −1.45 | [−47.0, +7.8] | net fold effect, geometry held at **sg16** |

**The net fold at the assignment's mandated geometry was measured
`V−0 = +219.6 µs/step SLOWER`, t = 16.21.** It only stops being catastrophic
once the grid is widened to sg16 — a geometry change the assignment forbids
(rule 32) — and even there it is `N−G = −19.6`, **statistically NULL**
(CI spans zero).

This is rule 23 operating as designed: the redundant reduction costs +80.4 µs
at 640 TGs and +308.3 µs at 5120 TGs (≈0.64 scaling exponent), because a
per-threadgroup cost is paid 5120 times instead of 640. A per-*simdgroup*
algebraic fold at the mandated geometry pays the `Σ x²` redundancy **10,240×**
(5120 TGs × 2 simdgroups), each recomputing the same 2048-element row sum.

#298 calls `RV−0` "the single largest effect in the study" (`:234-235`).

---

## Leg 4 — The dispatch refund is structurally unavailable (new finding)

Even setting legs 1–3 aside and building the fold as an *addition*, the only
real saving on offer is deleting the 40 standalone RMSNorm dispatches. #298
isolates that refund as `V−RV = −88.6 µs/step` and is explicit that RV and V
"differ only in whether the 40 standalone RMSNorm dispatches still exist"
(`:243-245`).

**That refund cannot be collected here, because `normalized` has a second live
consumer on all 40 layers.**

```swift
let normalized = fusedQKV ?? inputNorm(input)                    // :5763
let decodeNVFP4QKVR1 = fusedQKV == nil
    ? lagunaDecodeNVFP4QKVR1(normalized: normalized, ...) : nil  // :5766-5770  consumer 1
...
let activated = lagunaGateSoftplus(input: normalized,            // :5808       consumer 2
                                   bank: affineGate, heads: nHeads)
```

`fusedQKV` is always `nil` on the shipped path (`lagunaNativeAffineNVFP4From`
`:2861-2867` returns 0), so on **every one of the 40 layers** both
`lagunaDecodeNVFP4QKVR1` (`:5767`) and the per-head INT8 g_proj gate
`lagunaGateSoftplus` (`:5808`) read `normalized`. Folding the norm into QKV
alone leaves the gate needing a device-visible normalized row, so
`inputNorm(input)` **must still dispatch**.

That is why #298's `V` arm could collect the refund and this arm cannot: `V` is
the *fused norm+QKV+gate* kernel — the `lagunaNormAffineQKV` family at
`:4880-5017` that folds the gate too, and which is dead by default and
explicitly out of scope for this PR.

Net effect for the assignment as scoped: pay a fraction of the +308.3 µs
redundancy, refund **nothing**. Ceiling ≤ 0.

The norm dispatches are also cheap per rule 27: the census
(`research/nezuko-a2-roofline.txt:38`) shows `rms bfloat16 41 × 3.00 µs =
124.6 µs/step` total, and an *off-chain* removal is worth only ≈0.12–0.22 µs
each.

---

## Leg 5 — The follow-up was scoped to 640 TGs; the assignment transplants it to 5120

`research/maple-nezuko-persistent-gridstride-qkv.md:392-397`, verbatim:

> 1. **Algebraic epilogue normalization at full coverage.** Accumulate `Σ w·γ·x`
>    and `Σ x²` in the same loop and divide by the RMS after `simd_sum`, **keeping
>    the 640/512-TG full-coverage grid**. This removes the redundant reduction
>    *without* coarsening the grid — the opposite trade to this stage.

The spec's "full coverage" means **640/512 TGs** inside #309's persistent
scheme, and "the redundant reduction" means the one **#309's own fuse arm
introduced**. The assignment instead mandates "keep the 5120-TG grid" — a
grid 8× finer, where no such reduction exists and where rule 23 says the
introduced redundancy costs 3.8× more (+308.3 vs +80.4).

The two documents are in direct contradiction about the target geometry, and
the transplant lands on precisely the case #298 measured at +219.6 µs/step
slower.

---

## Evidence contract

**1. Preflight — identical before and after; byte delta 0.**

```console
$ BASE_SHA=730e9c2be89a4ed8cf860e52f930f7ff222d4c95
$ senpai/validate-assignment-scope.sh "$BASE_SHA" Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 1 submitted path(s) against BASE_SHA=730e9c2be89a4ed8cf860e52f930f7ff222d4c95
$ senpai/check-editable-budget.sh "$BASE_SHA"
editable budget OK: current=2857088/3000000 bytes headroom=142912 growth=0/262144 files=140 (file count is diagnostic only; base=140)
$ git diff --stat "$BASE_SHA" -- Sources/ Vendor/
                        # empty
```

**Exact byte delta: 0 B.** The 48,641 B of per-file headroom on
`LagunaRuntimeModel.swift`, shared with three other students this round, is
returned untouched.

**2. Stage 0 code verification.** Leg 1 above — quoted code refuting both the
"second cross-simdgroup reduction" and the "normalization inside the reduction"
claims, plus the location of the real mechanism in the dead INT8 family and the
absence of both cited knobs.

Guard chain to a default (rule 1), confirmed reachable for the *live* kernel:
`DARKBLOOM_DECODE_NVFP4_QKV_R1 != "0"` (`:4620-4621`, default ON) →
`guard lagunaDecodeNVFP4QKVR1Enabled` (`:4820`) → shape guards (`:4823-4838`)
→ dispatched at `:5767` on all 40 layers, 30 calls at `h64` + 10 at `h48` =
40 calls/step.

Grid arithmetic verified independently at `:4845`/`:4861`/`:4872`
(`grid: ((rows / 2) * 64, 1, 1)`, `threadGroup: (64, 1, 1)`) with
`rows = (heads + 2 * numKeyValueHeads) * headDim` (`:4821`):

- sliding `h64`: `rows = (64+16)·128 = 10240` ⇒ 327,680 threads ⇒ **5120 TGs**
- full `h48`: `rows = (48+16)·128 = 8192` ⇒ 262,144 threads ⇒ **4096 TGs**

64 threads/TG with `num_simdgroups = 2` (`:4738`) ⇒ 2 simdgroups × 1 row each
⇒ `rows/2` TGs. ✓ matches the assignment's table. This confirms residency
(rule 6) — the kernel is live and hot; it simply does not contain the claimed
defect.

**3. Ceiling reconciliation.** Legs 2, 3 and 5. Revised ceiling ≈27–34 µs/step
before leg 4, and ≤ 0 after it, against a ≈80 µs/step bar.

**4–7. Not run — the stopping rule fired at Stage 0.** No arm was built, so
there is no numerical characterisation, no token-level gate, no fault
injection and no ABBA timing. Reporting these as anything other than absent
would be dishonest. Per **rule 35** I also did not run
`research/run_upstream_equivalence.sh`: with a zero-byte diff it is guaranteed
byte-identical and, as the assignment itself states, its verdict would not
cover this change in any case.

**8. Verdict: KILL.** The number that decides it is `V−0 = +219.6 µs/step`
[+192.3, +247.0], t = 16.21 — the net fold measured at the exact geometry this
assignment mandates. The mechanism to be removed does not exist (leg 1); its
≈140 µs ceiling double-counts a telescoping ladder and is really ≈27–34 µs,
under the bar (leg 2); at the mandated 5120-TG grid the sign is inverted
(leg 3); and the only genuine saving is blocked by a second consumer of
`normalized` (leg 4).

---

## Recommendations

1. **Do not re-fund this strand at the 5120-TG grid.** Legs 3 and 5 make the
   expected sign negative. #298 and #309 have now both priced it.
2. **Correct the ledger.** #309's `research/maple-nezuko-persistent-gridstride-qkv.md:398-399`
   asserts the removal is worth "up to ~56 µs/step *on top of* the −83.3 µs
   fold refund". That is the double-count refuted in leg 2; the ladder
   telescopes to `N640 − a0 = −33.7`, which #309 already reported. Suggest
   amending the spec so the next reader does not re-derive a 140 µs ceiling.
3. **Proposed new rule:** *a contrast between two adjacent rungs of a ladder is
   not an independent saving; sum only disjoint contrasts, and check the
   telescoping identity before quoting a ceiling.* This error survived one
   student report and one advisor assignment.
4. **The one live strand this exposes** is leg 4's converse: the reason the
   norm dispatch cannot be deleted is that `lagunaGateSoftplus` (`:5808`) and
   `lagunaDecodeNVFP4QKVR1` (`:5767`) each independently re-read the same
   2048-element normalized row on all 40 layers. Any future attempt at the
   −88.6 µs refund must fold **both** consumers, which is the dead INT8
   `lagunaNormAffineQKV` family (`:4880-5017`) — i.e. it needs an NVFP4
   re-derivation of a path #300 already closed. I did **not** implement this;
   flagging it only so the refund is not re-costed as if it were reachable
   from a QKV-only fold.
5. **#309's follow-up item 2 ("bit-identical prefetch") is untouched by this
   refutation** and, unlike item 1, involves no rounding change. If the
   advisor wants a replacement for this slot, that is the adjacent candidate —
   though note it too was written against the 640-TG persistent geometry and
   would need the same reachability check performed first.
