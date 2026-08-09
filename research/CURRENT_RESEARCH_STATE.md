# SENPAI Research State

- **2026-08-09 ~01:40 UTC — round 92.** Campaign `mlxfast-maple-20260804`.
  Advisor branch `codex/mlxfast-maple-20260804-advisor`.
  Base = `8486638578a283de40369172f68c3a4d2d6a5365`.

> This is a **living document**. It was 7,601 lines and had become an archive.
> The full historical record through round 91 is preserved verbatim at
> [`research/RESEARCH_ARCHIVE_through-round-91.md`](RESEARCH_ARCHIVE_through-round-91.md).
> Nothing was deleted; it was moved. Keep this file short enough that a new
> agent can read all of it before acting.

---

## 1. Most recent human/operator direction

**No human message has arrived in the current window.** The campaign is running
on standing instructions.

One item is **blocked on a human channel**: the Birch relay escalation. The
sibling campaign `mlxfast-birch-20260805` has publicly attributed its failures
to a ~900 s build timeout, while every `rejectionReason` on their receipts says
"Public behavior gate", and their own submission note admits over 50
consecutive M5 failures. Relaying this needs a verified human message ID and no
`human_issue` event has been delivered. Re-check each round.

---

## 2. Where we stand

**Objective.** `score = decode_speedup^0.75 * prefill_speedup^0.25`, both floors
0.95, serial `laguna-xs-2.1-serial-v2` track, ranked on one M5 Max.

**Conversion constant, memorise it.** **0.015280 % score per µs/step of decode.**
This already bridges M4 → M5; do **not** additionally multiply by 1.48.
Practical detection bar: **≈80 µs/step decode**, **≈1.35 ms prefill**.

**Leaderboard.** Best = **2.61650354381456**, source
`Layr-Labs/mlxfast-challenge @ c5b0a13`, benchmark
`1854efdf-feba-4773-bae9-b80520881a74`. Unchanged as of the last check.
**Standing lesson #1: re-check the promoted frontier every round.**

**Our position.** We adopted the frontier at `6ada66c9` and have merged seven
experiments on top of it. Frontier-import fidelity is **CONFIRMED**: of 142
editable files, 131 are byte-identical to `c5b0a13c`, 9 modified, 2 deleted, 0
added; `LagunaRuntimeModel.swift` is byte-identical; all 51 vendor Metal and
`mlx-generated` files are byte-identical; DARKBLOOM marker count is 431 at all
three revisions; of 2,128 deleted lines, 2,079 (97.7 %) are comments and there
are **zero executable-code deletions**. The current base should therefore score
at or slightly above 2.6165.

**But we have never proven it.** The only Maple ranked datum is receipt
`25b0b722` at **2.55158458026643**, taken on a pre-adoption base. PR #486
(tanjiro) is fixing this right now — it is the highest-information experiment
in flight because every other number we hold is M4 evidence pushed through a
transfer factor of **−0.40 ± 0.24**.

**Budget at base.** `current=2895390/3000000 headroom=104610 growth=0/262144
files=141`. `LagunaRuntimeModel.swift` = 402,887 B against a 524,288 B per-file
cap ⇒ **121,401 B per-file headroom**. The per-file gate that blocked the
norm→QKV lever for several rounds is **dissolved**.

**Merged chain since frontier adoption.** `6ada66c9` → #458 → #460 → #457 →
#473 → #456 → #469 → #481 → #475 = `84866385`.

---

## 3. Current research focus and themes

### Theme A — the M4/M5 regime split is the organising fact of this campaign

**M4 Pro is bandwidth-bound. M5 Max is instruction-bound at ~89 % utilization.**
These are different machines with different bottlenecks, and we measure on the
one we are not scored on.

The measured consequence: PR #137 delivered **−63.7 µs/token on M4** and
**+24.6 µs/token on M5** (receipt `99b71258`). Transfer factor **−0.40 ± 0.24**.
Byte-reduction levers *hurt* on the ranked host.

Two live responses:

1. **Declare a mechanism class for every decode lever** (binding rule). A lever
   whose mechanism is "move fewer bytes" should be expected to transfer
   negatively. A lever whose mechanism is "issue fewer instructions", "remove a
   dispatch boundary", or "hide latency" should not.
2. **Read the M5 directly.** `xcrun applegpu-nt -arch applegpu_g17s` compiles
   for the M5 generation from an M4 host, offline. This is the only instrument
   in the campaign that touches the ranked architecture. See rule 42 (rewritten
   this round) in
   [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).

The specific asymmetry it exposes: **float ALU encodes identically on both
architectures; integer ALU does not** (uint MAD 12.0 B/op g16s vs 14.0 B/op
g17s, **+16.7 %**, on an operation that touches no memory). On an
instruction-bound host, integer-ALU density is a first-order cost that is
nearly free on our rig. **This is the only lever class we have found whose
M4→M5 transfer is expected to be positive.** PR #490 is the map-making round.

### Theme B — the decode byte pool is finished; the remaining prize is latency and boundaries

Round-87b census, M4 Pro, 8,234 µs session:

| component | µs/step | share | character |
|---|---|---|---|
| weight streaming | 5,700–5,900 | ~70 % | 86.9–98.2 % of achievable 239.7 GB/s |
| fused SDPA | ~880 | ~10.5 % | issue/latency-bound |
| glue | ~640 | ~7.6 % | latency-bound, floor ≈152 µs |
| boundaries/gaps | 25–450 | — | scheduling |

Byte floor ≈5,582 µs ⇒ **≈338 µs of headroom in the streaming pool, which is
effectively finished**. Decode moves ≈1.69 GB/step at ≈1.0× amplification
(attention 763.5 MB, MoE 590.4 MB, dense L0 MLP 100.7 MB, LM head ~111 MB, KV
read 86.5 MB, router 40.9 MB).

So the remaining M4-visible money is in **glue latency, dispatch boundaries and
overlap** — which is where #475, #483 and #488 all live.

### Theme C — measurement doctrine is now the campaign's main asset

Three rounds in a row, the headline finding was about the *instrument*, not the
model. This is not wasted work; it is why our numbers are now trustworthy.

- **#473** proved the "42 % kernel-local → end-to-end give-back law" was an
  artefact of `DARKBLOOM_GPU_PROFILE_SPLIT=1`. The profiler costs **1,642
  µs/step — 24× the effect it measures**. Prereg `c ≈ 0.58` rejected
  (t = 4.51, p ≈ 0.003); the true conversion is **c = 1.247 [0.90, 1.59]**.
  Rule 38 (discount every result by 40 %) was **withdrawn**.
- **#475** established the **overlap ceiling** as a routine instrument: a
  phase-split probe measures how much latency is available to hide before you
  build anything. The router site's ceiling was 12.80 µs/step and the shipped
  lever captured 54 % of it. My prior had been ~4× optimistic. **Latency-hiding
  levers cap far below naive arithmetic** — always measure the ceiling first.
- **#481** refuted my own rule-42 calibration and showed that the compiler
  canonicalises distinct source formulations to byte-identical native code.

### Theme D — the assignable surface is now genuinely small

Two lever families closed this round, both by measurement rather than by
exhaustion:

- **Frontier Lever 2 (router tournament comparators) — CLOSED.** Transform C
  already shipped as `active64_v2`. Only D remains at ~1 %. Obituary and
  reopening conditions in
  [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).
- **The `bfeil` / bit-manipulation family — DEAD.** All MSL spellings compile
  to byte-identical native code; Apple's compiler already fuses.

Also closed earlier: the comment-relocation family (#320), the "`_nax` M=1 qmv
kernel" lead (`get_qmv_batch_limit:88–129` returns ≥10 in every branch and
`GatherQMM::eval_gpu` needs `B≥16` while decode is `B=8`, so the scored decode
routed path never calls `MLX.gatherQuantizedMM`), and expert streaming / disk
I/O as a scored cost.

---

## 4. In flight — round 92

| PR | student | assignment | thesis | state |
|---|---|---|---|---|
| [#483](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/483) | maple-fern | `maple-r91-a-input-norm-fusion-price` | Price the input-RMSNorm→QKV fusion. Prize ≈193 µs/step ≈ 2.95 % undiscounted. Stage 1 is a numerically-wrong ceiling probe with a **stop at < ~80 µs/step**. | wip |
| [#486](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/486) | maple-tanjiro | `maple-r91-b-ranked-base-receipt` | **Get a ranked M5 receipt for the current base.** Arm R = base, arm F = pure adopted frontier `6ada66c9` (fidelity control), arm C = `84866385`. Priority R → F → C. | wip |
| [#488](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/488) | maple-nezuko | `maple-r92-a-barrier-hoist-generalization` | Generalise #475's barrier hoist across the 28 barrier sites. **+0.13 % per round is not a viable cadence**; needs ≈9.4 equivalent sites to clear the detection bar. Stage-1 stop if < 6 qualifying decode sites. | wip |
| [#490](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/490) | maple-frieren | `maple-r92-b-m5-encoding-census` | Differential g16s-vs-g17s census of the decode-busy top-16. Find the levers that are **invisible on M4 and material on M5**. Map, not territory — no implementation this round. | wip |

Sequencing caution: #483, #488 and the router work all touch the decode
glue/router pool. Keep them attributable; do not merge two overlapping levers
without a fresh paired measurement.

---

## 5. Potential next research directions, ranked

1. **Integer-ALU density reduction on the M5** — pending PR #490's map. The
   only lever class with expected-positive M4→M5 transfer. If #490 finds a
   top-16 kernel with material g17s excess localised to index arithmetic, that
   becomes the next round's headline assignment.
2. **Barrier-hoist family aggregate** — pending PR #488. If ≥6 sites qualify
   and their ceilings sum past 80 µs/step, this is a ~1 %-class win assembled
   from bit-exact-by-construction pieces.
3. **Input-norm→QKV fusion** — pending PR #483. Largest single arithmetic prize
   still on the board (≈2.95 % undiscounted) but gated on whether the producer
   cost times the redundancy factor eats it.
4. **L1** — algebraic epilogue normalization at full grid.
5. **L4** — prefill async-ladder stride/placement (`LRM:733`).
6. **L5** — full-attention SDPA N/capacity constexpr specialisation.
7. **L7** — prefill `_nax` A-fragment N-tile reuse. Note: `_nax` is
   **unreachable on student M4 Pro hosts**, so this needs a ranked receipt to
   evaluate at all.
8. **Routed head-latency family** (from #469) — ≤ −83.64 µs/step available but
   byte-confounded; needs a design that separates latency from bytes.
9. **L3 threadgroup packing — DO NOT ASSIGN YET.** #308 measured −36.9 µs/step
   CI [−61.0, −12.9] ⇒ +0.56 %, +29 B, and rule-39 reachability is confirmed.
   **But** #48's mode-2 8× threadgroup collapse on this same QKV grid earned M5
   receipt `285f79fa` at **−0.1488 %, a loss**. L3 does a 4× collapse
   (5,120 → 1,280 TGs). Geometry neutrality is treated as absolute until a
   ranked receipt says otherwise. Revisit after #486 lands.
10. **L6** lossless entropy recode of BF16 planes · `patch_lane` peel · routed
    down-reduce prefetch port · full-attention decode params memo
    (`LRM:2301–2303`, called `:6054`) · decode intra-CB concurrency (#174) ·
    prefill glue · shared-expert overlap.
11. **Housekeeping with real value:** three flags have documentation that
    contradicts the code — `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` and
    `…_SIGN_CARRY` are documented "default OFF" but parse `!= "0"` and are
    **ON**; `DARKBLOOM_DECODE_ASYNC_STAGE` is documented as 6 points but
    defaults to 7. Any experiment that reads those docstrings will be wrong.

---

## 6. Standing rules index

Full text of the older rules is in the archive; the ones that bind current
assignments are summarised here.

- **24** — one mechanism per arm.
- **33** — kernel-name suffix for every variant.
- **35** — the oracle must be blind to the fused-weight family.
- **36** — ORDER confounding.
- **37** — mine competitor notes every round.
- **38** — ⛔ **WITHDRAWN by #473.** No result may be discounted by 40 %.
- **39** — verify in code that a positive control is *reachable on the default
  configuration* before mandating it; cite guard, env default, and line number.
- **40** — state the rig's resolvable floor with arithmetic. σ is
  **estimator-specific**; never import one estimator's σ into another's power
  calculation. Table in §7.
- **41** — a **dispatch boundary** costs **1.4064 µs** flat (WIDE 1.4064
  [1.3163, 1.4964]; TINY 0.7258 [0.5275, 0.9241]; ratio 1.94×). Decomposition:
  bytes at 4,096 B = 0.018 µs (1.3 %), `c_fixed` 0.315 µs (22.4 %),
  serialization/ordering 1.073 µs (76.3 %). **Scope limit (#469): an in-kernel
  `threadgroup_barrier` costs 0.0293 µs/barrier/dispatch and saturates after
  ~8 — about 48× cheaper. Rule 41 applies to DISPATCH boundaries only.**
- **42** — ⭐ **rewritten round 92**, see
  [`research/advisor-r92-rule42-rewrite-and-lever2-obituary.md`](advisor-r92-rule42-rewrite-and-lever2-obituary.md).
  The AGX census measures **static `__compute` code bytes**, admissible only as
  a matched-null difference within one opcode class and loop structure.
  `(bytes − floor)/8` is **retired**.
- **43** — end-to-end magnitude comes from a `nat`-regime paired ABBA census
  (report wall **and** absolute busy, n ≥ 8 duplexes). `SPLIT=1` is
  attribution-only; no SPLIT=1 total, ratio, or cross-kernel accounting may
  enter a standing rule or a merge decision. **Adopted interpretation (#475):**
  a single-label, name-matched, control-differenced SPLIT=1 delta converted
  through #473's `c = 1.247 [0.90, 1.59]` **is** admissible. Dispatch *counts*
  are not timings and are unaffected.
- **44** — ⭐ **new, from #475.** Every SPLIT=1 per-kernel comparison must be
  **name-matched and residency-matched** via an A4-style placement control.
  Treated-vs-baseline SPLIT=1 deltas are inadmissible alone: changing a
  kernel's JIT name measurably perturbs 4–7 of 28 *untouched* labels. This
  retro-explains #469's physically impossible +8.80 µs/step on the untouched
  `sliding_fused_attn_ring_v1`.
- **Binding** — declare a mechanism class for every decode lever (Theme A).
- **Doctrine (#469b)** — a revision request specifies a verifiable **end
  state**, not a git incantation.
- **Geometry neutrality** — treated as absolute. #48 receipt `285f79fa`
  = −0.1488 %.

---

## 7. σ table (rule 40)

| estimator | σ (µs/step) | ±95 % at n=8 |
|---|---|---|
| per-run wall medians, cross-process | 48.0 / 49.0 | — |
| per-run wall medians, within-process | 19.5 | ±16.3 |
| paired ABBA census, `nat` ratio-adjusted busy | 10.65 | ±8.91 |
| paired ABBA census, `nat` absolute busy | 14.74 (#475 rig 15.86) | ±12.3 (±13.26) |
| paired ABBA census, `nat` wall | 29.96 (#475 rig 12.19) | ±25.0 (±10.19) |
| paired ABBA census, `nat` median (#475) | 6.25 | ±5.23 |
| paired ABBA census, `s1` ratio-adjusted | 9.62 | ±8.05 |
| paired ABBA census, `s1` wall | 105.0 | unusable |
| per-kernel labels under SPLIT=1 | 0.4 – 4.9 (pooled 3.51; #475 rig 3.34) | ±0.3 – 4.1 (±2.78) |

⚠️ #460's GREEN verdict came from a 3-run comparison and **does not exclude a
38 µs/step regression**.

---

## 8. Operational facts an agent needs before acting

- **Hosts.** Advisor is M4 Pro (`applegpu_g16s`), **no model checkpoint** — it
  can compile-verify but cannot time or inspect weights. Students are M4 Pro
  too, so **`_nax` kernels are unreachable locally**; decode fused-attention
  kernels are reachable.
- **Model constants** (`LagunaConfig.swift:10–45`): vocab 100,352 · hidden
  2,048 · dense intermediate 8,192 (layer 0) · 40 layers · 8 KV heads ·
  headDim 128 · **full attention 48 query heads on layers 0,4,…,36 (10
  layers)**, **sliding 64 heads (30 layers)** · rmsNormEps 1e-6 · sliding
  window 512 · 256 experts, top-8 · moeIntermediate 512 · sharedExpert 512 ·
  routedScalingFactor 2.5 · bos 2 · eos [2,24] · 912 tensors.
- **`mlxfast sync -f` does a HARD CHECKOUT** — never run it on a working
  branch.
- **`rejected` ≠ gate failure.** Read `rejectionReason`. A `rejected` receipt
  can simply mean the score did not beat the current best.
- **Submissions use `--model "senpai"`**, campaign-wide, with fallback only on
  an explicit rejection of that value. The submission account is shared with
  the Birch campaign; the discriminator is the **note body**, which must carry
  `Maple campaign`, the student name, assignment id, revision id, arm letter,
  and the exact commit SHA.
- **Byte price** (PR #110 ledger): **0.015224 % per MB** of submitted surface.
- Preserved branches — fetch, do not delete: `maple-fern/fused-norm-qkv-gate`
  `f4c86e44`, `maple-fern/router-top8-fusion` `e92d09eb`,
  `maple-frieren/shared-scale-halving` `d1cd8e91`.

---

## 9. Where the detail lives

| topic | file |
|---|---|
| everything through round 91, verbatim | `research/RESEARCH_ARCHIVE_through-round-91.md` |
| rule 42 rewrite + Lever 2 obituary | `research/advisor-r92-rule42-rewrite-and-lever2-obituary.md` |
| AGX census instrument + encoding tables | `research/maple-frieren-r90-agx-instruction-census.md`, `research/maple-frieren-pr481-census.tsv` |
| census probe tooling | `senpai/tools/agx-census-probe/` |
| the give-back artefact / profiler cost | archive §"ROUND 89c" |
| decode byte census + M4/M5 regime split | archive §"ROUND 87b" |
| frontier adoption + import-fidelity audit | archive §"FRONTIER ADOPTION" |
| dataset / workload characterisation | `research/DATASET_ANALYSIS.md` |
| experiment runbook (branches, sync, promotion) | `senpai/experiment-runbook.md` |
