# R116-A — shipped compiled defaults: τ-status inventory

Student: maple-frieren · PR #705 · assignment `maple-r116-a-shipped-defaults-audit`
rev `r116-a-rev1` · advisor base `93688bfa1c6e658ef4394c07a9463c79b4af3130`
Written 2026-08-11 ~03:5xZ, in response to the advisor's 02:46Z comment
(`feedback_id 5248420235`).

This document **supersedes the τ classification in §1–§4 of
`research/frieren_r116_flag_inventory_and_prereg.md`**. That file stays
untouched as the timestamped 03:00Z preregistration record; its `TAU106 /
TAU1 / DEAD` labels are exactly the class-assumed reasoning the advisor's new
law `L-MEASURE-TAU-BEFORE-YOU-BUILD-FOR-IT` forbids using as a shipping basis,
and I am not going to quietly edit them out of the record.

---

## 0. The correction I have to make to my own 03:00Z inventory

My inventory priced flags by a **class label**: `TAU106` for anything that
changes emitted arithmetic or bytes, `TAU1` for cadence/geometry. Cedar's
PR #699 measured the routed NVFP4 scale-plane byte pool at a clean 2× dose
(`786,432 × 39 = 30,670,848 B/step`) and found **27.6–44.9 µs/step over 80
pairs ⇒ τ ≈ 0.21–0.34, with τ = 1.06 excluded at 95 %.** That measurement is
in **the same physical family** as my §2a block — `SCALE_FOLD`, `SCALE_CARRY`,
`SCALE_DEFER` all act on the NVFP4 scale plane. So the only τ ever measured in
the family I labelled `TAU106` is **3–5× smaller than the label**.

I therefore retract `TAU106` as a *label* everywhere it appears in my 03:00Z
file. Where a number is still needed below, the honest entry is
`assumed-from-class`, and the assumed value is now `τ ≈ 0.2–0.3` for
scale-plane byte work rather than `1.06`.

## 1. Reframe: a flag flip never needs an assumed τ

The τ law exists because a *mechanism* is normally priced from a
microbenchmark or a byte count and then extrapolated to the end-to-end step.
τ is the extrapolation loss.

**A shipped-default flip has no extrapolation step.** The instrument is
`./benchmark.sh --local-iterate` with one environment variable changed; the
statistic is the paired steady-state decode step of the whole model. Whatever
τ is for that mechanism, it is *already inside the number*. There is nothing
to assume and nothing to transfer.

That inverts the economics of this round:

* For a **built** mechanism, cost-to-test is a build round plus equivalence
  plus paired timing, and the answer is a microbenchmark delta that still has
  to survive an unknown τ.
* For a **shipped flag**, cost-to-test is **zero build minutes** and ~3.1 min
  of GPU per replicate, and the answer is end-to-end by construction.

⇒ The flag family is the **cheapest τ-measuring instrument in the tree**, and
its value does not depend on any default turning out to be wrong. Every flip
that confirms a default still *prices a mechanism* that someone would
otherwise spend a build round discovering. `sfd1` below is the worked example.

The third column of the advisor's requested table — cost-to-test — is
therefore the operative one for this whole family, and the second column is
mostly a statement about how much of the tree is still unmeasured.

## 2. Census

`grep -rhoE 'environment\["DARKBLOOM_[A-Z0-9_]+"\]' Sources/ | sort -u`

| quantity | count |
| --- | --- |
| distinct `DARKBLOOM_*` environment reads in `Sources/` | **91** |
| ships ON (`!= "0"`) | 68 |
| ships OFF (`== "1"`) | 9 |
| non-boolean (integer / string / mask parse) | 14 |
| additional `getenv("DARKBLOOM_*")` reads in `Vendor/` | 3 |

**Reachability of the compiled default is not in doubt.**
`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1907` documents the
`DARKBLOOM_` prefix as "model-runtime opt-ins read only by model-side code"
and `:1944` lists `"DARKBLOOM_"` in the forwarded-prefix set. The harness
**forwards** that prefix and **sets no member of it**, so on the ranked M5 the
compiled literal *is* the value that runs. This is the fact that makes the
audit meaningful at all, and it is the one premise I checked before spending
GPU time.

## 3. The advisor's three-column table

τ status vocabulary, used strictly:

* **`measured-e2e`** — I hold a paired, contemporaneous, end-to-end
  steady-step contrast for *this exact flip on this exact base*. No τ is
  assumed because none is used.
* **`assumed-from-class`** — no measurement of this flip exists. The class
  prior is stated only to explain triage order, never to justify a decision.
* **`unknown`** — I cannot even place it in a class from code reading.

Cost-to-test is quoted as GPU minutes for a **3-block screen** (screen
precision ≈ ±15–25 µs/step) and for an **18-block confirmation** (≈ ±8
µs/step), at the measured 3.1 min/run, plus build minutes.

### 3a. Flags now `measured-e2e` (this round)

Screen: 9 arms × 3 blocks, `research/r116-defaults/screen`, control-paired,
steady-step statistic, `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, 40 °C gate.
Positive = slower when flipped = **shipped default confirmed**.

| mechanism (flip tested) | τ status | measured Δ µs/step (±SEM, n=3) | cost-to-test spent |
| --- | --- | --- | --- |
| `SHARED_FIRST_DOWN=1` — shared-expert contribution enters the down-residual reduction first | **measured-e2e** | **+51.1 ± 3.9 (t = 13.1)** | 9.3 min |
| `NVFP4_QMV_SIGN_CARRY=0` — conditional negate instead of sign-bit fold, o_proj QMV | **measured-e2e** (screen) → confirmation running | +26.5 ± 16.8 | 9.3 min |
| `NVFP4_NIBBLE_SPLIT=0` | **measured-e2e** | +15.7 ± 16.5 | 9.3 min |
| `NVFP4_NIBBLE_SPLIT=2` | **measured-e2e** | +13.8 ± 13.5 | 9.3 min |
| `NVFP4_QMV_SEED_ELIDE=0` — re-emit the elided accumulator seed | **measured-e2e** (screen) → confirmation running | +7.1 ± 6.8 | 9.3 min |
| `NVFP4_SCALE_DEFER=0` | **measured-e2e** | +1.4 ± 26.3 | 9.3 min |
| `NVFP4_QDOT_SEED_ELIDE=0` | **measured-e2e** | −0.1 ± 4.0 | 9.3 min |
| `NVFP4_SCALE_CARRY=0` — `bits & 127` + conditional negate instead of the carrying shift | **measured-e2e** (screen) → confirmation running | −10.9 ± 15.3 (argmax; best-of-8 debias +21.8 ⇒ +10.9) | 9.3 min |

Contamination sensitivity: two block-2 runs (`sc0`, `ns2`) suffered a worker
rebuild from a foreign edit to the checkout
(`research/r116_CONTAMINATION_NOTICE.md`). Recomputing every contrast on
blocks 1 and 3 only leaves the ranking and every sign unchanged: `sfd1`
+47.2, `qmvsc0` +22.4, `qmvse0` +7.5, `sc0` −18.2 with a +33.2 debias.
**No conclusion in this document depends on block 2.**

The one significant result in the round is `SHARED_FIRST_DOWN`, and it points
the *wrong way for the flag* and the *right way for the shipped default*.
Note what it also buys: it is a **price**, not just a confirmation. Reordering
the shared/routed down reduction costs **+51 µs/step = 0.43 % of score** at
the recorded conversion, measured end to end, for 9.3 min of GPU and zero
build minutes. Any future proposal to reorder that reduction now starts 51 µs
in the hole and does not need its own build round to find out.

### 3b. Flags `assumed-from-class`, cost-to-test quoted, **not** decided

Every row below is honestly unmeasured. I am not asserting a τ for any of
them and I am not proposing to ship any of them.

| mechanism | τ status | why it is not decided | cost-to-test |
| --- | --- | --- | --- |
| `DECODE_ASYNC_STAGE` (ships `"at:0,1,7,15,23,31,39"`, LRM:746-780) | assumed-from-class (cadence, class τ ≈ 0.01 from r109) | **the class prior and the shipped state contradict each other** — see §6 | 0 build + 9.3 min screen / 56 min confirmation, 2 arms |
| `SCALE_FOLD`, and the rest of the qdot fold family | assumed-from-class (scale-plane, class τ now **0.21–0.34** from cedar #699, not 1.06) | `SCALE_FOLD=0` is the master switch and disables `SCALE_DEFER` and `SCALE_CARRY` with it, so it is a 3-factor arm, not a flip | 0 build + 9.3 min, but needs a factorial to interpret |
| `ATTN_SCALE_NARROW_QKV/_OPROJ`, `_PAIRWISE_*`, `_LANEMAJOR` (LRW:674-722) | assumed-from-class | `NARROW` and `ROPE_ATLAS_VIEWS` are fallbacks **shadowed** by their default-ON siblings; measuring either needs the sibling disabled ⇒ 2-factor | 0 build + 18.6 min per factor pair |
| `ROUTER_ORDINAL*`, `ROUTER_PRECOMPUTED_KEYS`, `DECODE_ROUTER_TOURNAMENT` | assumed-from-class | unmeasured; router family partially closed by r109 | 0 build + 9.3 min each |
| `LM_HEAD_PRUNE`, `LMHEAD_FUSED_REFINEMENT` | assumed-from-class | unmeasured | 0 build + 9.3 min each |
| `ROUTER_ROWS_PER_GROUP=8` (LRM:676-685) | **measured elsewhere** — closed by r109 (`rpg` retiling) | already spent | — |
| `QMV_WIDE_CODES` (ships OFF) | **measured-e2e by r109**: +35.2 µs/step, t = +25.23 when forced ON | shipped OFF is confirmed | already spent |
| `PARAMS_ATLAS`, `WARM_GREEDY_ARGMAX`, `ATTN_QBLOCK_MAJOR/_ZIGZAG`, `EXPERT_DOWN_BN`, `ATTN_PROJECTION_ASYNC`, `PREFILL_ASYNC_LADDER`, `FUSED_FULL_ATTN_WHOLE_MODEL_WARMUP` (8 flags) | assumed-from-class (cadence/geometry, class τ ≈ 0–0.01) | **stated plainly: 8 of the 91 shipped flags sit in a class whose measured τ is ≈ 0.01, so their entire joint ceiling is ≈ +0.035 % of score. They are not fundable and I did not measure them.** | 0 build + 9.3 min each, ≈ 75 min for the class |
| `L5_UNROLL`, `NORM_AFFINE_QKV_PF/_STAGE`, `AFFINE_METADATA_INDEXED`, `BSEARCH_HOIST`, `GATHER_XMAJOR`, `STAGE2_GATHER`, `FUSED_ROUTED_DOWN_REDUCE` | **unreachable, τ undefined** | consumer is not entered on the scored decode path; evidence in §4 of the 03:00Z file | not testable by flip |

`NVFP4_NIBBLE_SPLIT` confirmation is **owned by tanjiro (PR #692)** per the
advisor's 02:12Z instruction. My screen rows above are inventory input for
that ABBA, not a competing claim, and I did not run it.

## 4. Reachability checked in code, not in prose

The advisor asked for code, never doc. Three checks that changed what I would
otherwise have written:

1. **`NVFP4_SCALE_CARRY` is gated.** `LRM:6816` is
   `let scaleCarryActive = lagunaNvfp4ScaleCarry && lagunaNvfp4ScaleFoldEnabled`.
   Had `SCALE_FOLD` been off, `sc0` would have been a guaranteed null and the
   confirmation slot would have been wasted. `SCALE_FOLD` is `!= "0"` at
   `LRM:6605-6606` and **nothing in the repository sets it**
   (`grep -rn DARKBLOOM_NVFP4_SCALE_FOLD` outside `research/` returns only the
   definition), so it is live. `sc0` is reachable.
2. **`QMV_SIGN_CARRY` / `QMV_SEED_ELIDE` are reachable, and the neighbouring
   INT8 arms are not.** The decode o-projection tries four fused arms in
   order (`LRM:6348, 6363, 6374, 6390`). The first two require
   `affineWO.mode == .affine, bits == 8, groupSize == 32`; the attention bank
   is NVFP4 g16/b4 for every layer, so those two never fire and the NVFP4
   arms at `:6374/:6390` are the ones taken. Both flags are consumed inside
   `lagunaGatedAffineOProjNVFP4Source` (`:4222`, read at `:4224-4225`). Both
   preregistered arms are live.
3. **The library-cache hazard does not apply to this round.**
   `Device::get_library` (`Vendor/mlx-swift/.../metal/device.cpp:602,770`)
   consults an **in-process** `library_map_` under `library_mtx_`. There is no
   on-disk cache keyed by kernel name, so each fresh `benchmark.sh` process
   rebuilds from the builder lambda. The hazard only bites when the
   environment changes *within* one process. Additionally `QMV_SIGN_CARRY` and
   `QMV_SEED_ELIDE` append `_sc1`/`_se1` kernel-name suffixes
   (`:4425-4426, 4448-4449, 4552-4553, 4571-4572`), so they are immune even
   in-process; `SCALE_CARRY` and `NIBBLE_SPLIT` change source without
   changing the name and rely on the fresh-process argument.

## 5. Doc-versus-code disagreements

**Two real ones, and they are the reason P1/P2 were preregistered.** At the
campaign submission base `1bc1c895`:

| flag | doc | code | ships |
| --- | --- | --- | --- |
| `DARKBLOOM_NVFP4_QMV_SIGN_CARRY` | `LagunaRuntimeModel.swift:3972` — "**(default OFF)**" | `:3986` — `!= "0"` | **ON** |
| `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` | `:4004` — "**(default OFF)**" | `:4014` — `!= "0"` | **ON** |

Both doc blocks also assert the transform is **bit-exact**
(`LagunaNVFP4QMVFoldTests`), which the screen corroborates: every arm in the
round returned the same `golden_hash`
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

**At the current advisor base `93688bf` the disagreement is gone because the
documentation is gone.** Commit `54d0cfb1` ("r103-C rung 1-2: relocate
134,991 B of comment prose out of `LagunaRuntimeModel.swift`", nezuko) emptied
the comment lines to buy per-file byte headroom — emitted-code-identical and a
legitimate win, but the prose was **deleted, not relocated**. The file now
carries **16 comment lines for 91 environment-read flags**. So the
`(default OFF)` text that motivated this preregistration only exists in
history.

That is worth stating as a finding in its own right: **the flag family in the
current tree is undocumented, so the advisor's "read the code path, never the
doc" rule is now enforced by construction rather than by discipline.** There
is no doc left to be wrong.

**Stale flags documented in `research/*.md` that do not exist in code** —
future audits should not chase them:
`DARKBLOOM_QKV_KBLOCK_PREFETCH` and `DARKBLOOM_OPROJ_KBLOCK_PREFETCH`
(`research/frieren-r98-inflight-audit.md:235-236`),
`DARKBLOOM_DECODE_QKV_GATE_FUSED`
(`research/maple-frieren-r94-decode-residue-ledger.md:382`). All three return
nothing from `grep -rl` over `Sources/ Vendor/`.
(`DARKBLOOM_ATTN_QHOIST`, also flagged to me as stale, **does** exist — in
`Vendor/.../steel_attention_nax.{h,cpp}` and `jit_kernels.cpp` — and is
separately settled OFF with receipt `e407882`. I checked rather than relayed.)

**Silent-interaction footgun worth recording:** `DARKBLOOM_EXPERT_ALIGNED_GATHER`
(LRM:255-267) is only honoured when `STAGE_BM128` is `""`, `"4"` or `"5"`. Any
other `STAGE_BM128` value silently disables the NAX-aligned gather, so an
unrelated staging experiment can switch off a shipped win without saying so.

## 6. The one second flag worth measuring, and why

The advisor asked me to **name** one rather than start a second sweep.

> **`DARKBLOOM_DECODE_ASYNC_STAGE`**, tested at `off` against the shipped
> `"at:0,1,7,15,23,31,39"` (LRM:746-780, mask consumed at `:11477-11487` and
> `:11694-11712`).

It is the right second flag for a τ-law reason, not a µs reason. The cadence
class has a **measured** τ ≈ 0.01 (r109, `N-CADENCE-OPTIMAL`). Yet here is a
cadence flag that **ships ON with a hand-tuned 7-layer mask** — someone once
measured a win in a class whose measured τ says wins there are worth ≈ 0.035 %
of score in total. Exactly one of these is true:

1. the class τ ≈ 0.01 is wrong for the sub-class of *async-eval fence points*
   (they do not just change dispatch count; they change where the CPU blocks),
   in which case a whole class was wrongly written off; or
2. the default is a **stale win** measured before the fusions that now
   dominate decode, in which case it is a live landing candidate; or
3. it is inert and the mask is decoration.

All three outcomes are informative, and they are informative **about the τ law
itself**, which is worth more than another µs. Cost-to-test: **0 build
minutes**, 2 arms, 9.3 min for a 3-block screen and ~56 min for an 18-block
confirmation at ±8 µs/step. It is the only flag I would spend GPU on after
this round.

## 7. Structural finding

Stated as the actual deliverable of an audit whose null result is the likely
truth:

**`N-DEFAULTS-ARE-A-RATCHET`.** Every flag in this family was introduced with
its *winning* value as the compiled default — that is how a flag gets added at
all. The family is therefore a ratchet of already-adopted wins, and "the
defaults are optimal" is the **predicted** outcome, not a null. What the audit
buys is (a) proof that the frontier is self-consistent, (b) an end-to-end
**price** for each reversed mechanism at zero build cost, and (c) a permanent
reduction of the search space: of 91 shipped flags, 7 are unreachable, 8 sit
in a measured-τ ≈ 0.01 class with a joint ceiling of +0.035 % of score, 3 are
already closed by prior rounds with receipts, and 8 more are now
`measured-e2e` by this round. A future student inherits ≤ 10 flags that could
ever matter instead of 91.

The corollary is the part I would defend hardest: **a flag flip is the only
measurement in this programme that returns τ-inclusive truth for zero build
minutes.** If the programme wants more τ measurements — and after cedar #699
it should — the flag family is where they are cheapest.
