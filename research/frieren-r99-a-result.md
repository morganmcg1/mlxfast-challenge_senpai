# r99-A — did the frontier rebase drop the 4-deep ring on purpose?

**Student:** maple-frieren · **PR:** #539 · **assignment_id:**
`maple-r98-a-decode-attn-qmv-mlp` · **revision_id:** `r99-a-rev1` ·
**base_sha:** `c240616a4924285f44bbb2f7410802920351c7ff` ·
**host:** AWS Apple M4 Pro, 20 GPU cores, 48 GB, `applegpu_g16s`

Preregistration: [`research/frieren-r99-a-prereg.md`](frieren-r99-a-prereg.md),
committed before any timing. Superseded r98-A record:
[`research/frieren-r98-decode-qmv-result.md`](frieren-r98-decode-qmv-result.md).

---

## 0. Answer to the question you actually asked

> Was the frontier's 2-deep ring a deliberate M5-measured improvement, or a
> reconciliation casualty?

**A reconciliation casualty, and it took a third mechanism down with it.**
Two independent lines of evidence:

1. **Static.** `research/nezuko_r96_gen4deep.py 2` regenerates the *shipped*
   frontier kernel from our old 4-deep source byte for byte. A deliberate
   M5-measured redesign does not land on the exact text an automatic depth
   rewriter emits. Separately, the "unexplained +227 B" you flagged on
   `laguna_full_fused_attn_grow_v1` is **exactly and only** the r85-c `float4`
   merge epilogue, which the rebase also dropped — from *both* attention
   kernels, not one.
2. **Dynamic.** Restoring the 4-deep ring makes the kernel **1.505 % ± 0.065 %
   faster** at the ranked-M5 occupancy proxy (t = −23.0, 20 sweeps, both arm
   orders, base-vs-base null −0.082 % ± 0.082 %). Nobody deliberately ships a
   1.5 % regression at the occupancy the ranked part actually runs at.

**But it is not worth a receipt, and I am not asking for one.** The full
restoration (ring + epilogue) is worth **at most +0.206 % of score** on the
ranked M5 — at most, because the 636 µs/step pool is a *census* figure and this
kernel's marginal efficiency has never been measured (§4.4); every family in the
programme that has been measured discounts by 0.35–0.75. Even the undiscounted
top of that interval is 0.33 σ(score) and one fifth of our 1.0498 % deficit. My
preregistered GO bar was +0.61 % of score and the result misses it by a factor
of three. **Receipts declined: 0 of 6 spent.** Recommendation is *merge on
merit*, not *submit*.

Independent corroboration arrived while I was writing this: tanjiro's #541
revert census, built from M5 receipts and a different anchor, prices the same
shipped pair at ≈ +0.248 % additively. My joint M4 probe says +0.206 %. Two
hosts, two instruments, two methods, ~20 % apart — and both far under the bar.
§11 works through the comparison, including why the census could not see the
ring at all.

---

## 1. A pricing error in my own preregistration, corrected

I have to open with this because it changes the headline by 2.19×.

`CURRENT_RESEARCH_STATE.md:996` gives the sliding-attention pool on **both**
hosts: **636.0 µs/step measured on this M4 Pro**, **≈290 µs/step projected on
the ranked M5**. The decode price of **0.015280 % score per µs/step** is
defined against *M5* µs/step (`:119`, from our M5 decode of 4893.7 µs/step,
so 1.00 % = 48.94 µs/step).

My prereg §4 converted probe percentages through the **M4** pool and then
applied the **M5** price. Every predicted score in that table is therefore
**2.19× too large**. The prereg's own GO bar of "+40 µs/step" carries the same
defect. I report the bar under both readings below, and it fails under both, so
the decision is not sensitive to the error — but the numbers in prereg §4 are
wrong and should not be quoted.

The same mixing is visible in the brief's "±0.5 % ≈ ±3.2 µs/step" probe
resolution: 0.005 × 636.0 = 3.18, i.e. that figure is in **M4** µs/step.
Everything below carries both columns explicitly.

---

## 2. Static audit — the rebase dropped three mechanisms, not two

All three live in `Sources/MLXFastModel/LagunaRuntimeModel.swift`. Byte deltas
are against the shipped base blob `c6c66344:LagunaRuntimeModel.swift`
(511,418 B).

| # | mechanism | in `e510bb3d` | in frontier | reproducer | Δ bytes |
|---|---|---|---|---|---|
| 1 | sliding load ring depth | 4-deep (`pipe_kc/kd`, `pipec_*`, `piped_*`) | 2-deep + `pair_planes = 2` | `nezuko_r96_gen4deep.py 4` | **+4,086** |
| 2 | `float4` merge epilogue, **sliding** kernel | present | gone | `frieren_r99_epilogue.py float4 laguna_sliding_fused_attn_ring_v1` | **−227** |
| 3 | `float4` merge epilogue, **full** kernel | present | gone | same, `laguna_full_fused_attn_grow_v1` | **−227** |
| — | `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` | present | gone | see §7 | ≈ +4,000 |

Byte-identity checks, all exact:

- `gen4deep.py 2` applied to `e510bb3d`'s kernel reproduces the **shipped**
  frontier sliding kernel byte for byte. The frontier text is a mechanical
  depth rewrite of ours.
- `gen4deep.py 4` + `frieren_r99_epilogue.py float4 <sliding>` applied to the
  frontier base reproduces `e510bb3d`'s sliding kernel byte for byte.
- adding the full-kernel epilogue reproduces `e510bb3d`'s full kernel byte for
  byte.

So the whole 349-line divergence between the two lineages on this file is
accounted for by mechanisms 1–3 with **zero residue**. Your "+227 B I cannot
explain" is mechanism 3.

**Deviation from the brief, declared in the prereg before measuring.** The
brief's rung 1 is "restore the 4-deep ring". The ring and the epilogue are
textually disjoint, and comment 4 demands that mechanism be separated from
codegen quality, so I measured them as **separate rungs** (1 = ring, 1b =
epilogue, 1c = both) rather than porting the old kernel wholesale. That turned
out to matter: they are **super-additive**, and at one occupancy the epilogue
*rescues* a ring regression (§4).

---

## 3. Instrument

`research/nezuko_r98_ab_kernel_probe.swift` (your zero-receipt probe),
driven by `research/frieren_r99_run_probe.sh`, aggregated by
`research/frieren_r99_agg.py`. Raw log and aggregate are committed under
`research/r99-logs/`.

- 20 sweeps × 12 legs; each leg = 15 alternating rounds × 200 dispatches per K.
- K ladder {8, 16, 20, 24, 32, 40, 60} threadgroups on 20 cores.
  **K = 16 is the headline**: 0.8 TG/core, matching the ranked M5's 32
  threadgroups over 40 cores. K = 20 (1.0 TG/core) is the secondary headline.
- Threads per threadgroup: 1024, fixed, for every arm and every K.
- Every contrast is run in **both arm orders**; the estimate is
  `(FWD − REV)/2`. The first sweep's base-vs-base null showed ~1 % of position
  bias favouring the second timing slot, so a fixed order is not trustworthy.
- The **first leg of the process is run and discarded**: on a cold shader cache
  it lands −14.5 % of garbage in its K=8 row.

**Null control (base vs base, identical file, 20 sweeps).** This is the
resolution floor of the instrument as configured:

| K | 16 | 20 | 24 | 32 | 40 | 60 |
|---|---|---|---|---|---|---|
| null est % | −0.082 | −0.014 | −0.049 | −0.006 | +0.069 | −0.035 |
| sem | 0.082 | 0.029 | 0.066 | 0.081 | 0.086 | 0.048 |

K = 8 is **not reportable** (null −1.365 % ± 1.209 %, sd ≈ 8 %); 8 threadgroups
on 20 cores is dominated by launch and clock behaviour. I exclude it
everywhere. At K ≥ 16 the instrument resolves ~0.1 %, five times better than
the ±0.5 % the brief assumed.

**Sign control.** The FWD and REV columns of every leg are near-exact mirrors
(e.g. `d4` at K=20: FWD −1.48 %, REV +1.51 %; `d4epi` at K=20: −4.45 % /
+4.84 %). Rung 1d's inversion requirement is satisfied by construction and is
visible in every row of the aggregate.

---

## 4. Results

`est%` is percent of base kernel time, negative = candidate faster.
`µs_m4` uses the measured 636.0 µs/step M4 pool; `µs_m5` and `score%` use the
projected 290.0 µs/step M5 pool with the M5 decode price.

### 4.1 Headline, K = 16 (0.8 TG/core, ranked-M5 proxy)

| rung | variant | est % | sem | t | µs_m4 | µs_m5 | score % |
|---|---|---|---|---|---|---|---|
| 0 | null (base vs base) | −0.082 | 0.082 | −1.00 | −0.52 | −0.24 | +0.004 |
| 1 | `d4` ring depth 4 | **−1.505** | 0.065 | **−23.0** | −9.57 | −4.36 | **+0.067** |
| 1b | `epi` float4 epilogue | **−1.619** | 0.106 | **−15.2** | −10.30 | −4.70 | **+0.072** |
| 1c | `d4epi` **shipped** | **−4.650** | 0.077 | **−60.7** | −29.58 | −13.49 | **+0.206** |
| 1e | `d8` ring depth 8 | −0.030 | 0.093 | −0.33 | −0.19 | −0.09 | +0.001 |
| 1f | `full` epilogue, full kernel | −2.691 | 0.074 | −36.1 | −6.18\* | −2.82\* | +0.043\* |

\* rung 1f is **evidence only and is not in the shipped candidate**, per your
instruction not to touch `laguna_full_fused_attn_grow_v1`. It is also priced
against a different pool: the full-attention twin is 229.7 µs/step on M4 /
≈104.8 µs/step on M5, not the sliding pool's 636.0 / ≈290. Every other row in
this table uses the sliding pool.

### 4.2 The whole ladder, K = 20 and above

| rung | K=20 | K=24 | K=32 | K=40 | K=60 |
|---|---|---|---|---|---|
| null | −0.014 | −0.049 | −0.006 | +0.069 | −0.035 |
| `d4` | **−1.490** | **+0.637** | −0.272 | −0.789 | −0.800 |
| `epi` | −1.706 | −2.686 | −2.575 | −1.780 | −2.044 |
| `d4epi` | −4.647 | −1.776 | −2.848 | −3.409 | −3.427 |
| `d8` | +0.218 | +0.793 | +0.371 | −0.065 | +0.798 |
| `full` | −2.680 | −1.014 | −0.327 | −2.390 | −2.130 |

Three things in that table are worth more than the headline.

**(a) The ring is occupancy-conditional and changes sign.** `d4` is −1.49 % at
1.0 TG/core and **+0.637 % (slower, t = +7.9)** at 1.2 TG/core. Depth-4
pipelining helps exactly while a core has spare latency to hide and hurts once
threadgroups start queueing. The ranked M5 runs at 0.8 TG/core, on the helping
side — but this is a direct instance of the standing warning that threadgroup
geometry can flip sign across core counts, and it is the single largest reason
not to over-trust this M4 result.

**(b) The epilogue is unconditional.** `epi` is negative at every reportable K,
−1.6 % to −2.7 %, with |t| from 15 to 71. It is a pure work reduction (one
`float4` store and reload instead of scalar merge traffic) and does not depend
on occupancy. It is also **−227 bytes**. If only one of the three mechanisms is
ever restored, it should be this one.

**(c) The two are strongly super-additive.** At K=16, −1.505 + −1.619 = −3.124
predicted if independent; measured **−4.650**. The extra **−1.53 %** is real
(sem 0.077). At K=24 the epilogue does not merely add, it **reverses** the
ring's +0.637 % into −1.776 %. Reading: the 4-deep ring raises live-register
and merge pressure at the end of the loop, and the `float4` epilogue is
precisely what pays for that; separating them, as the rebase did, is worse than
either. This is why the two must be restored together, and it is an argument
the assignment's rung structure could not have produced.

### 4.3 Dose–response: the falsifier, and what it says about codegen

My prereg made depth-8 the falsifier: a genuine latency-hiding effect should
saturate, while a codegen tax should grow with the amount of restructuring.

`d8` nearly doubles the generated kernel (549 source lines vs 285 base, 373 for
`d4`) and is **flat**: −0.030 % at K=16, +0.218 % at K=20, worst +0.798 %. So
the response is **base < depth-4 ≫ depth-8**, i.e. it peaks and decays. That is
the signature of a real pipeline-depth effect against a fixed load-latency
budget, not of a compiler cliff.

**Codegen-quality control (comment 4's hazard), explicit.** PR #540 found every
prefetch-expressing rewrite of *this exact kernel* regressing the base by +4 to
+7 % with a flat dose–response at unchanged occupancy. My variants report
identical pipeline reflection:

| variant | src lines | `staticThreadgroupMemoryLength` | `maxTotalThreadsPerThreadgroup` | `threadExecutionWidth` |
|---|---|---|---|---|
| `base` | 285 | 18432 | 1024 | 32 |
| `d4` | 373 | 18432 | 1024 | 32 |
| `epi` | 268 | 18432 | 1024 | 32 |
| `d4epi` | 356 | 18432 | 1024 | 32 |
| `d8` | 549 | 18432 | 1024 | 32 |
| `epiboth` | 320 | 18432 | 1024 | 32 |

Occupancy is invariant across a 2× swing in generated source, so the register
cliff my prereg worried about (1024 → 896 threads/core) never fires. Combined
with the peaked dose–response and the *negative* sign, this rung is not a
#540-style codegen-tax case: #540's rewrites lost the fused predicated `T_LOAD`
diamond and regressed; `gen4deep.py` emits the diamond in each of its four
slots and improves. The distinction the brief asked for — mechanism vs codegen
quality — resolves in favour of mechanism.

**How far that control actually goes.** Not as far as the paragraph above
sounds, and I would rather say so than have it found. "Peaked versus flat"
compares my depth axis against #540's *rewrite-style* axis; those are different
axes, and a peaked curve is not by itself proof that codegen quality is
constant along mine. Two of my own rows argue the opposite: `d8` is not merely
saturated but *worse than base at four of six K values*, and `d4` flips sign to
**+0.637 % (t = +7.9)** at K = 24. Both are in-family codegen/occupancy
sensitivity, not mechanism. The regime story I believe for K = 24 is two-wave
imbalance — one 18,432 B threadgroup per 32 KB core means 20 cores hold 20
groups, so K = 24 leaves a four-group tail wave whose cost swamps an
8.5 µs/step effect — but "I believe" is the right verb.

The cheap controls that would actually separate the axes, neither of which I
ran: (a) apply the sibling's fused predicated-load-diamond diagnostic from #540
to `d2`/`d4`/`d8` and confirm the diamond survives at each depth; (b) a finer
ladder at `d3`/`d5`/`d6` to show the peak is smooth rather than a two-point
artefact. I list both in §10.

The operative shipping evidence is not `d4` alone — which is regime-fragile —
but `d4epi`, which is negative at **every** K in the ladder (−4.650, −4.647,
−1.776, −2.848, −3.409, −3.427 for K = 16…60). Folding the regime spread and
the M4→M5 timescale ratio into the estimate, the defensible M5 band for the
shipped pair is **[+0.08 %, +0.21 %] × E**, not a point estimate at the top of
it. The launch geometry on the ranked M5 (40 cores) is not the geometry I
probed; verifying the real dispatch's K/core ratio there is the single most
useful thing anyone could add to this section.

### 4.4 The +0.206 % is an **upper** bound: the pool is a census figure

I want to be explicit about a discount I cannot measure, because it cuts
against my own number and you should see it before you read §9.

The 636.0 µs/step I price against is a **census** cost:
`research/r94-artifacts/r94-dispatch-ledger.tsv:6` records 30 calls × 21.20
µs/call, i.e. the sum of per-dispatch GPU time. The probe likewise measures the
kernel in isolation, 200 back-to-back dispatches with nothing to overlap. What
the score actually pays for is the **marginal** contribution to the step, and in
this codebase those two differ a lot:

| family | E = marginal ÷ census | source |
|---|---|---|
| router GEMV | **0.349** | `RESEARCH_ARCHIVE_through-round-91.md:5044` |
| `T2d_down_residual` | 0.617 | ledger `:665` |
| `T0b` KV stream | 0.741 | ledger `:665` |
| `T2c` routed QMV | 0.754 | ledger `:665` |
| `T1c` lm_head | 1.111 | ledger `:667` |

**E for this kernel is unmeasured.** The decode marginal-cost ledger excludes
the attention family on purpose: "attention and o-proj
(`sliding_fused_attn_ring_v1`, `full_fused_attn_grow_v1`, `oproj_act_h64/h48`)
carry ~27 % of the census between them and are **deliberately unwired** here
because their kernels mutate KV in place and advance the cache clock, so a
duplicate is not side-effect-free" (`maple-fern-decode-marginal-cost-ledger.md:630-636`).
Pricing them needs a copy-on-write KV scratch buffer, which nobody has built.

So `+0.206 %` is what this rung is worth **if E = 1**. Every measured E on a
weight- or KV-streaming family in this programme is below 1, between 0.617 and
0.754. If the sliding kernel sits in that band the rung is worth **+0.13 to
+0.15 %**; if it behaves like the router's 0.349 it is worth **+0.07 %**. I
have no evidence for any particular value and I am not going to invent one.

This does not change the sign or the decision — it makes the decision easier,
because the honest interval is `(0, +0.206 %]` and its top end is already
0.33 σ(score). It does mean nobody should later quote +0.206 % as a realized
gain. The cheapest way to close this hole is the copy-on-write KV scratch
buffer the ledger names; I list it in §10.

---

## 5. End-to-end paired local benchmark

<!--E2E-->

---

## 6. Correctness

<!--CORRECTNESS-->

---

## 7. Rung 2 (`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`) — not run, and why

I did not build rung 2, and I want to be direct that this is a deviation from
the assignment.

1. **It is not screenable on your zero-receipt probe.** The probe binds eleven
   attention-shaped buffers (`dRawQ/K/V`, `dQW/dKW`, `dAngles`, `dKCache`,
   `dVCache`, `dParams`, `dScale`, `dAttended`) at
   `nezuko_r98_ab_kernel_probe.swift:184-192` and dispatches
   1024 threads/threadgroup. `laguna_residual_rms_router_bf16_2048_rpg*` has a
   different signature and a different launch geometry, so screening rung 2
   means writing a second binding, not passing a different kernel name. The
   brief's own instruction is to screen every rung before spending a receipt;
   with the instrument as it stands, rung 2 cannot be screened.
2. **The pool cannot rescue the decision, because the pool is two-thirds
   shadowed.** The census figure for
   `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` is 305–313 µs/step
   (`r94-artifacts/r94-dispatch-ledger.tsv`: 39 calls × 8.02 µs = 312.8), but
   its *chained marginal* cost is **106 µs/step (2.73 µs/call), E = 0.349**
   (`RESEARCH_ARCHIVE_through-round-91.md:5044-5047`, citing
   `maple-fern-decode-marginal-cost-ledger.md:311-341`). The marginal pool is
   what a latency-hiding change can move, and it is one sixth of sliding
   attention's 636.0 µs/step. Even a *5 %* prefetch win there is ≈5 µs/step M4
   ≈ 2.4 µs/step M5 ≈ **+0.037 % of score**. Rung 1c already misses the receipt
   bar by 0.40 % of score; rung 2 is an order of magnitude too small to change
   that.
3. **The family is formally closed, and the closest measured neighbour of this
   mechanism is ~0.15 %.** Round-36 recon A
   (`RESEARCH_ARCHIVE_through-round-91.md:5020-5070`, indexed at `:1821`) closed
   `residual_rms_router` with "every lever is dead", and two of the dead levers
   are scheduling levers of exactly rung 2's shape: splitting the redundant
   norm prologue out is **net negative** (+1 dispatch × 39 layers ≈ +140 µs
   against a ≈44 µs ceiling), and **weight-hoist depth 1→16 moves the step
   13 µs = 0.15 %**. I do not claim that last figure *is* rung 2 — comment 6 is
   right that HEAD's surviving `vec<bfloat,4> rw[4]` unroll is the in-loop
   batching arm and not the cross-barrier hoist — but it is the nearest
   measured point on the same knob in the same kernel, and it sits an order of
   magnitude below the bar.
4. **Rung 3 is therefore moot.** The brief gates rung 3 on rung 1 or 2 being
   non-negative in isolation. Rung 1 is strongly positive, so rung 3 is
   licensed — but rung 3's purpose was to reach a receipt-worthy total, and
   1c + a generous rung 2 is ≈ +0.24 % against a +0.61 % bar.

Provenance from comment 6 is settled and I re-verified it: the restore is the
`prefetch:` parameter on `lagunaResidualRMSNormRouterSource`, the
`lagunaRouterPrefetchGroups` helper, the `_pf{n}` / `_pf1c` name suffixes, the
`flatMap` kernel dictionary keyed `rowsPerGroup * 8 + prefetch`, and the
dispatch-site lookup — **≈ +4,000 B**, which does fit (§8). It is a real,
cheap follow-up; it is just not the reason this arm does or does not get a
receipt. I would rather hand you a clean unscreened rung than an unscreened
receipt.

---

## 8. Byte report

`senpai/check-editable-budget.sh c240616a4924285f44bbb2f7410802920351c7ff`:

```
current=2987708/3000000 headroom=12292 growth=3859/262144 files=142
```

| quantity | value |
|---|---|
| shipped growth (rung 1c) | **+3,859 B** |
| `LagunaRuntimeModel.swift` | 515,277 / 524,288 B (**9,011 B** spare) |
| total surface | 2,987,708 / 3,000,000 B (**12,292 B** spare) |
| growth this review | 3,859 / 262,144 B |

The binding constraint is the **whole-surface** 3,000,000 B cap, not the
per-file cap. The numbers above are measured *with* rung 1c applied: the
surface was 2,983,849 B at `c240616a` with 16,151 B free, and rung 1c leaves
**12,292 B**. So this rung spends **3,859 B = 31 % of the headroom that
remains after it**, or 24 % of what was free before it. That is a real cost and
I am not going to bury it: a ≈4,000 B rung 2 would still fit, but only just,
and the two together would leave the surface with roughly 8 KB of slack. No
rung was resized to fit a budget.

Component byte costs, for the record: ring +4,086, sliding epilogue −227,
net **+3,859**. The full-kernel epilogue would be a further **−227**, i.e.
restoring mechanism 3 *buys back* bytes as well as time — which, given how
tight the surface now is, is an argument for taking mechanism 3 first.

---

## 9. Decision against the preregistered bars

| bar | preregistered | measured | verdict |
|---|---|---|---|
| GO to receipt (literal units) | ≥ +40 µs/step | +29.58 µs/step (M4 basis) | **fail** |
| GO to receipt (intended score) | ≥ +0.61 % score | +0.206 % score | **fail** |
| whole 95 % CI improving | required | yes ([−4.80, −4.50] % at K=16) | pass |
| occupancy control clean | required | yes, invariant | pass |
| sign control inverts | required | yes, every K | pass |
| REVERT rung if non-improving at K=16 **and** K=20 | — | 1c improves at both | keep |
| STOP after two clean negatives or rung 3 | — | stopping at rung 1c/1e | — |

**Receipts spent: 0 of 6.** The honest expected outcome recorded in my prereg
was "a kernel-level result with receipts declined", and that is what happened.

What I am asking for instead: **merge rung 1c on merit**, with one precondition
stated below. It is worth at most +0.206 % of score by the programme's own
price list, it costs 3,859 B, and it is now the only part of the 4-deep
lineage's advantage that has been isolated and measured rather than asserted.

**The precondition, and a claim I want to weaken.** I have described this rung
as a restoration of previously shipped code. That framing is fully earned for
the ring (mechanism 1): `nezuko_r96_gen4deep.py 4` regenerates it from the same
rewriter that produced the shipped 2-deep body, so the arithmetic is the same
arithmetic in a different order of *issue*, not of *reduction*. It is weaker
for the epilogue (mechanism 2). The float4 merge epilogue re-associates the
two-partial merge across a vector width; on the source lineage it was bit-exact
on M5, but "bit-exact on the host that measured it" is not the same claim as
"bit-exact on every target", because fast-math reassociation is a per-target
codegen decision and the argmax on this model has known near-ties. I am not
going to assert bit-exactness by construction.

So: **treat a clean `research/run_upstream_equivalence.sh` plus the 64-step
drift tripwire and the golden hash as a merge precondition, not as a
formality**, and read §6 rather than the exit codes. Those are M4 results; a
near-tie that survives here can still flip on M5, which is why I would rather
mechanism 2 ride into an official receipt alongside a real record attempt than
be merged and forgotten. And nobody should book +0.206 % against the 1.0498 %
deficit as if it were realized: §4.4 explains why the honest interval is
`(0, +0.206 %] × E` with E unmeasured for this family.

---

## 10. Suggested follow-ups I did **not** implement

1. **Restore mechanism 3** (float4 epilogue on `laguna_full_fused_attn_grow_v1`).
   −2.691 % ± 0.074 % on that kernel, ≈ **+0.043 % score** (priced against the
   full-attention pool, 229.7 µs/step M4 / ≈104.8 µs/step M5), and **−227 bytes**.
   I left it out only because the brief said not to touch that kernel in the
   shipped candidate. It is negative-cost; it should go into the frontier.
2. **A router-shaped binding for the probe.** ~80 lines against
   `nezuko_r98_ab_kernel_probe.swift`, and it unlocks screening for rung 2 and
   for every future MoE-router rung. This is the highest-leverage tooling item
   I hit.
3. **Occupancy-conditional depth.** `d4` is −1.49 % at ≤1.0 TG/core and
   +0.64 % at 1.2 TG/core. The runtime knows the GPU core count and the
   threadgroup count at dispatch time, so a depth-2/depth-4 selection on
   `TG/core ≤ 1` is input-independent and legal. On the ranked M5 it is a no-op
   (0.8 TG/core), so it buys robustness, not score — worth it only if the
   programme ever needs one kernel to be good on both parts.
4. **Ask why depth-8 is flat rather than bad.** Depth-8 doubles the source and
   costs ~0.5 %; depth-4 gains 1.5 %. The optimum is between them, and nobody
   has tried the asymmetric ring (4 K-stages, 2 V-stages) that the load pattern
   actually suggests.
5. **Re-audit the rebase for a fourth casualty.** The 349-line divergence is now
   fully accounted for on `LagunaRuntimeModel.swift` — but I only audited that
   one file. The same reconciliation touched other editable paths.
6. **A copy-on-write KV scratch buffer, to price the attention family at all.**
   Per §4.4 this is the single largest hole in decode pricing: the attention and
   o-proj kernels are ~27 % of the census and their marginal efficiency `E` has
   never been measured, because the duplicate-injection probe cannot duplicate a
   kernel that mutates KV in place and advances the cache clock
   (`maple-fern-decode-marginal-cost-ledger.md:630-636`). Every attention-side
   µs/step this programme has quoted — mine included — is a census figure being
   used as if it were marginal. The ledger already calls this "the single
   highest-value extension"; I agree, and it now blocks honest pricing on the
   biggest pool we have.
7. **A ledger of unverified merged deltas, reconciled on the next record
   receipt.** The structural problem this round exposes is not that +0.206 % is
   small; it is that we now merge sub-σ mechanisms whose realized value is never
   confirmed, which is exactly how three of them got silently reverted in the
   first place. Keep a running list of every merged-but-unreceipted delta with
   its claimed µs/step, and when the next genuine record attempt spends a paired
   receipt — which it must anyway — check the accumulated claim against the
   realized paired decode time. That costs zero extra receipts and turns a pile
   of unverified point estimates into one measured aggregate.
8. **Separate the codegen axis properly** (per §4.3): run #540's fused
   predicated-load-diamond diagnostic on `d2`/`d4`/`d8`, then a `d3`/`d5`/`d6`
   ladder. Both are zero-receipt probe work and would convert "peaked, therefore
   mechanism" from an argument into a measurement.
9. **A pairwise transitivity matrix for the super-additivity claim.** The probe
   compares each variant against base; it has never compared `d4epi` against
   `d4` and against `epi` directly. Three extra legs would confirm the −1.53 %
   interaction is real rather than an artefact of composing percentages across
   separately compiled binaries.
10. **Verify the ranked M5 launch geometry for this dispatch.** Everything in
    §4.3 hangs on K/core, and I inferred the M5 ratio (0.8 TG/core) rather than
    observing it. One reflection dump from a ranked-shaped run would anchor the
    whole regime analysis.

---

## 11. Reply

Point by point against the seven comments on #539, newest first.

### `#541 revert census` (2026-08-09T15:43:25Z) — "did you lift the epilogue too?"

Yes, deliberately, and the clean split you asked for already exists in the
measurement. This is the ⚠️ in your note, so I will answer it with bytes first
and then with numbers.

**Bytes.** I built six independent copies of `LagunaRuntimeModel.swift` and
measured them:

| variant | size (B) | Δ vs base | region touched |
|---|---|---|---|
| `v_base` (frontier as shipped) | 511418 | +0 | — |
| `v_d4` | 515504 | **+4086** | sliding main loop only |
| `v_epi` | 511191 | **−227** | sliding merge epilogue only |
| `v_d4epi` (**this candidate**) | 515277 | **+3859** | both |
| `v_epiboth` | 510964 | −454 | both kernels' epilogues |
| `v_d8` | 523668 | +12250 | sliding main loop only |

These land exactly on the regions you measured independently: sliding main loop
OLD `e510bb3d:LRM:1640-1818` (8,058 B) → NEW `LRM:1548-1638` (3,972 B) =
**+4,086 B**, and merge epilogue OLD `LRM:1819-1872` → NEW `LRM:1639-1709` =
**−454 B for both kernels**, i.e. −227 B each. `4086 + (−227) = 3859`, which is
the shipped candidate byte-for-byte. Two independent constructions agreeing to
the byte is the strongest evidence I can offer that the regions are disjoint and
that I did not smear one mechanism into the other.

**Numbers.** Because the regions are disjoint I measured them *separately* on
the probe, so both mechanisms are individually attributable — at K = 16,
`d4` = −1.505 % (t = −23.0) and `epi` = −1.619 % (t = −15.2) against a null
control of −0.082 %. The shipped pair is −4.650 % (t = −60.7), which is
**super-additive**: additivity predicts −3.124 %, so there is an extra −1.53 %
of interaction at t ≈ −12. §4.1 and §4.3 carry the full ladder.

**Your prices versus mine.** Your M5-receipt-derived prices are consistently
about 2× my M4-probe-derived ones per mechanism:

| mechanism | your census | my probe (K=16, E=1) |
|---|---|---|
| r96-a 4-deep ring | ≈ +0.13 % | +0.067 % |
| r85-c epilogue, both kernels | +0.2358 % [+0.1347, +0.3368] | +0.115 % (0.072 sliding + 0.043 full) |

That factor-of-two is the expected direction for an M4 → M5 extrapolation
through a fixed 0.456 timescale ratio on a kernel that does not select the same
codegen, and I do not claim my absolute numbers over yours. What is worth
noting is that on the **shipped pair** the two methods nearly meet: your
additive estimate for `d4epi` is ≈ 0.13 + ~0.118 ≈ **+0.248 %**, and my joint
measurement — which captures the super-additivity your additive census cannot —
is **+0.206 %**. Two instruments, two hosts, two methods, ~20 % apart. I take
that as independent corroboration that the shipped candidate is worth roughly a
fifth of a percent, and *not* the ~0.43 % the full three-mechanism census
implies, because rung 3 (`_pf1`) is not in my candidate.

**On your pricing instruction.** Agreed and adopted: I do **not** price the
ring off end-to-end wall. §5 reports the paired local e2e benchmark as an
expected null and says so explicitly — a clean 4-deep restore is ≈ 8.5 µs/step,
against an M4 e2e detection bar around 80 µs/step. The pricing instrument in
this report is the per-kernel probe against the matched `c6c66344` anchor
(§3), which is the per-kernel counter census you asked for, run against a
matched base rather than against wall time.

**On the third mechanism.** Your census found the epilogue and `_pf1` but not
the 4-deep ring, because the 636.0 µs/step anchor traces to `maple-nezuko-r92`
at base `d549d318`, already 2-deep. That is exactly the blind spot §2 predicts:
a census anchored after a silent revert cannot see the reverted thing. §2's
static proof is the complement — `nezuko_r96_gen4deep.py 2` reproduces the
shipped frontier kernel byte-for-byte from our 4-deep source, so the ring went
from 4 to 2 by *rewriter output*, not by an M5-measured decision.

**Submit-path provenance.** Noted and unchanged; it does not bind this rung
because §9's recommendation is *merge on merit, do not submit*, and 0 of 6
receipts are spent.

### `r99-a-fb-router-prefetch-provenance` — router prefetch

Your provenance trace is right and I verified the restore shape independently:
the diff is the `prefetch:` parameter on `lagunaResidualRMSNormRouterSource`,
the `lagunaRouterPrefetchGroups` helper with its `rowsPerThread == 1` guard,
the `_pf{n}` / `_pf1c` name suffixes, a `flatMap` dictionary keyed
`rowsPerGroup * 8 + prefetch`, and the dispatch-site lookup. ≈ +4,000 B, which
fits. `DARKBLOOM_ROUTER_ROWS_PER_GROUP` still defaults to 8, so the peel is
reachable.

**I did not run it, and §7 gives the full reasoning.** The short version is
that your own instruction — screen on the probe before spending a receipt —
is not currently satisfiable for this kernel. `nezuko_r98_ab_kernel_probe.swift`
binds eleven attention-shaped buffers (`:184-192`); a router GEMV needs a
different binding, and writing it is ~80 lines of probe work, not a rung.

The arithmetic also does not justify doing it out of order. The router
kernel's census cost is 312.8 µs/step but its **chained marginal** cost is
106 µs/step at E = 0.349 — two-thirds shadowed — against 636.0 µs/step for
sliding attention, so a *5 %* router win is ≈ +0.037 % of score. And the
family was formally closed by round-36 recon A with "every lever is dead",
including two scheduling levers of rung 2's shape: the norm-prologue split is
net negative (+140 µs against a 44 µs ceiling) and weight-hoist depth 1→16
moved the step 13 µs = 0.15 %. Rung 3 is licensed by rung 1's positive result,
but rung 1c at +0.206 % plus a generous rung 2 still does not reach the
+0.61 % receipt bar.

Spending the session on an unscreenable rung that cannot clear the bar was the
wrong trade; I spent it on the codegen control you asked for instead. If you
want rung 2 measured, assign the probe binding first — I have listed it as
follow-up 2. I would also want §4.26's closure explicitly reopened before
anyone builds it, because right now rung 2 and rule §4.26 contradict each
other and the assignment did not reconcile them.

### `r99-a-submission-wrapper-and-byte-sequencing` — bytes and the wrapper

Byte pressure did not shape the kernel: I wrote the full restoration and then
measured it. `senpai/check-editable-budget.sh c240616a…` gives
`current=2987708/3000000 headroom=12292 growth=3859/262144 files=142`, with
`LagunaRuntimeModel.swift` at 515,277 / 524,288 (9,011 B spare). §8 has the
per-limit table. Note the binding limit **flipped**: at your base the per-file
cap bound at 12,870 B; after +3,859 B the whole-surface cap binds at 8,433 B
while the per-file cap still has 9,011 B. So nezuko's #548 reclamation matters
to arm A only if it takes bytes out of the *surface*, not merely out of this
file. It does, so sequencing after it is strictly better, but rung 1c does not
require it.

I did not use `senpai/submit-official.sh`, because I declined all six receipts.
The wrapper's constraints are recorded here so the next person on this branch
does not rediscover them: full 40/64-char `BASE_SHA` that is an ancestor of
HEAD, no `--model`, clean tree under `benchmark.json` + `editablePaths`.

### `r99-a-codegen-tax-and-probe` — the codegen control

This is the comment that changed the experiment, and it is the reason the
result is trustworthy. Two answers:

**(a) Does the restructuring lose codegen quality?** No, and I can separate it
from load depth three ways. §4.3 has the detail; the summary is:

- *Occupancy / pipeline reflection is invariant.* All six variants report
  `staticThreadgroupMemoryLength = 18432`,
  `maxTotalThreadsPerThreadgroup = 1024`, `threadExecutionWidth = 32`,
  srcLines 268–549 — identical to base and identical to what #540 saw. No
  cliff, no spill, no occupancy explanation available in either direction.
- *The dose–response is not flat.* #540's signature for a codegen tax was a
  cost that appears at depth 1 and does not scale: 1/8/28/32 simdgroups →
  +4.23/+4.28/+3.80/+4.79 %. Mine is the opposite shape: depth 2 (base) → 0,
  depth 4 → −1.505 %, depth 8 → −0.030 %. A tax paid on *expressing* the
  transform would already be visible at depth 4 and would not vanish at depth
  8. A mechanism with an occupancy/ILP optimum peaks and decays, which is what
  I measure.
- *A pure codegen contrast exists and is positive.* The `epi` variant is the
  float4 merge epilogue **at unchanged depth 2** — same loop structure, same
  ring, only the epilogue's store shape differs. It is −1.619 % ± 0.106 %.
  That is a codegen-quality change measured in isolation, and it *gains*.

So (a) moved, but in our favour, and I priced it separately rather than
folding it into the load-depth claim.

**(b) The interaction is the finding I did not expect.** `d4` alone −1.505 %,
`epi` alone −1.619 %, additive prediction −3.124 %, measured together
−4.650 % ± 0.077 %. The extra −1.53 % is super-additive at t ≈ −12 against
the additive model. And at K = 24 the ring *alone* regresses (+0.637 %,
t = +7.9) while `d4epi` is −1.776 %: the epilogue rescues the ring's one bad
occupancy point. That is a direct, measured example of the thing #540 warned
about — two source-level changes to this kernel are not separable by addition
— and it argues that the rebase's decision to drop them *together* is what
made the loss invisible to a single-mechanism audit.

On the instrument itself: it is as good as advertised. Base-vs-base null at
K ≥ 16 is |est| ≤ 0.082 % with sem ≤ 0.086, i.e. ~0.1 % resolution, better
than the ±0.5 % you quoted, once I added a discarded warm-up leg — the first
timed leg of a fresh process is cold-cache contaminated by −14.5 % at K = 8.
That fix is in `research/frieren_r99_run_probe.sh` and anyone reusing the
probe should take it. **K = 8 is not reportable** on this host (null
−1.365 % ± 1.209 %); K = 16 and above are.

I also applied nezuko's standard on receipts, but I want to state the reason
precisely, because the obvious phrasing is wrong. The tempting sentence is "the
instrument cannot resolve +0.206 % against σ(score) = 0.6172 %, so a receipt is
uninformative at 0.33 σ." That is true only on the *score* channel, and the
score channel is the wrong channel: on that axis you would need ≈36 receipts.
The efficient channel is candidate decode time, where σ(cand_dec) = 0.2939 %
and the shipped effect is 0.2757 % of decode — **0.94 σ per receipt**. Five
receipts reach t ≈ 2; all six pooled reach t ≈ 2.3. A receipt is *not*
information-free here.

The reasons I still declined are different and, I think, stronger:

1. **VOI ≈ 0 at the decision that matters.** Our best common-baseline is
   2.589321 against a record of 2.61650354381456, a deficit of 1.0498 %. A solo
   +0.206 % candidate cannot be promoted no matter how tight its error bar, so
   confirming it to t = 2.3 changes no action.
2. **The preregistered bar says NO-GO.** §1 fixed the GO bar at +40 µs/step
   ≈ +0.61 % before any data. Measured is at most +0.206 %. Spending on a
   preregistered failure is exactly the discipline the bar exists to enforce.
3. **Opportunity cost.** Six receipts is the whole budget, and a rung that
   cannot win alone should not consume the budget a record attempt needs.

The constructive version, which I put in §10: carry this as a *ledger of
unverified merged deltas* and reconcile the accumulated set against the paired
receipt of the next genuine record attempt, which we have to spend anyway.

### `r99-a-rev1` (the revision brief) — the central question

Answered in §0 and §2, with the correction that **three** mechanisms went
missing, not two. The third is your own "unexplained +227 B" on
`laguna_full_fused_attn_grow_v1`: it is exactly the r85-c float4 merge
epilogue, dropped from *both* attention kernels. That closes the loose end in
your note on the full-attention twin — it was not "something else changed
there too", it was the same something, and the byte sign is negative because
the epilogue is *smaller* than what it replaces.

`nezuko_r96_gen4deep.py 2` reproducing the shipped frontier kernel byte for
byte is the decisive static evidence. An M5-measured redesign does not land on
the exact output of an automatic depth rewriter.

Two places where I departed from the evidence contract, both flagged in the
body: rung 2 was not run (§7), and prefill was not separately attributed
because this kernel is decode-only and the probe measures the kernel, not the
score. `f` is recomputed from my own score JSON in §5, not carried.

### `r98-a-hold-frontier` and `r98-a-base-moved` — holds

Both obsolete and both correctly resolved by you before I acted on them. For
the record: I branched from `c240616a` as instructed, did not rebase, and the
r98-A measurements against `e510bb3d` are retained only as the historical
footnote in `research/frieren-r98-decode-qmv-result.md`. `e510bb3d` is still
load-bearing here, but as a *source* for the dropped kernel bodies, not as a
measurement base.

### Tooling

`get_prs` now works from the student role — the HTTP 403 you flagged is gone,
and I read all six comments through the typed tool rather than through this
file. I am keeping `## 11. Reply` anyway because it is the deliverable your
brief named.
