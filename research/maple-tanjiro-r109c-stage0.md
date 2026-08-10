# R109-C Stage 0 — routed gate/up extract-round elimination

Deadline 2026-08-10T23:30Z. Committed 2026-08-10T21:05Z.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s` (gen 16, pre-NAX).
Base `1a6761bf`; instrument commits `618e7b86`, `02376a4a`.

## Verdict: GATE PASSED — proceed to implementation

* **(a) Equality holds**, by an order-statistic identity plus a bitwise GPU gate.
  The two producers do not disagree, so no escalation is due.
* **(b) Ceiling = 1.52 us per gate/up dispatch** at the shipped 2048-threadgroup
  geometry, reproduced in two independent sessions (t = −59.7 and −60.5 against
  an instrument floor of |t| ≤ 2.7). Over 40 layers that is **60.9 us/step**
  = **0.439 %** of this host's 13 890 us/token baseline decode step
  = **+0.329 % normalized score** raw, **+0.16 %** after the ×0.5 optimism
  discount adopted from edward's #629. Both are above the 0.15 % stop
  threshold, so `N-EXTRACT-ROUND-CHEAP` is *not* written.

One decisive negative is already in hand, and it changes the mechanism story —
see §3.1.

## 1. Stage 0(a) — the extract-round selector equals the tournament `inds`

The scored decode path has two independent selectors over the same 256 router
scores. All line numbers are `Sources/MLXFastModel/LagunaRuntimeModel.swift` at
base `1a6761bf`.

**Producer of `router_keys` (fused residual+RMS+router kernel, :960-967).**

```metal
bfloat logit = bfloat(router_result[r]);
router_logits[...] = logit;
float x = float(logit);
float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
float score = x < 0.0f ? y : 1.0f - y;
router_keys[router_row + r] =
    laguna_router_key_ordinal(-(score + float(correction_bias[router_row + r])));
```

**Producer of `inds` on the scored decode path**
(`lagunaDecodeRouterOrdinalKernelSource`, :9370-9413; pipelines :9443-9476):

```metal
float x = float(logits[lane]);
float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));
float score = x < 0.0f ? y : 1.0f - y;
float key = -(score + float(correction_bias[lane]));
uint my_ordinal = laguna_router_key_ordinal(key);
uint my_index = lane;
// full 256-element bitonic sort under laguna_router_ordinal_before
...
if (lane < 8) { router_indices[lane] = my_index; }
```

`logits` here *is* the `router_logits` array the fused kernel wrote, so `x` is
bit-identical in the two kernels; every subsequent op is the same expression in
the same order, so `my_ordinal` equals the stored `router_keys` word for every
expert. No re-derivation, no different rounding path.

**Shared comparator** `laguna_router_ordinal_before(a, a_idx, b, b_idx)`
(:9431-9442) returns `a < b`, then `b < a`, then `a_idx < b_idx`. Expert
indices are distinct, so this is a **strict total order** on the 256
`(ordinal, index)` pairs — no ties, no implementation-defined outcome.

Under that single order the two selectors are the same order statistic:

* the decode producer sorts all 256 pairs and writes lane `s` → `inds[s]` is
  the `s`-th smallest (0-based);
* the prologue (`lagunaRouterTop8PrecomputedPrelude` :7879-7890 with
  `laguna_router_top8_extract_round`, header literal from :7846, function body
  :7847-7875) runs `expert_slot + 1` rounds
  of masked argmin. Lane `l` owns exactly the eight experts `l + 32j`; the
  round's winner is masked out afterwards by the single lane that owns it
  (`if ((best_index & 31u) == lane) mask |= 1u << (best_index >> 5u);`), so
  round `r` returns the `r`-th smallest of the *remaining* set. After
  `expert_slot + 1` rounds `top8_winner` is the `expert_slot`-th smallest.

Same order, same order statistic ⇒ `top8_winner(slot) == inds[slot]`, exactly,
for every input, including adversarial ties. The identity does not depend on
the number of experts, on `numExpertsPerToken`, or on any normalization flag
(the `normalizing` variants change `router_scores`, not `router_indices`).

The prefill tournament (:9977-10110) shares the same key expression and the
same comparator and is likewise a full 64-candidate bitonic sort of the
per-block top-8s, so the identity holds there too; the decode kernel above is
the one that matters for a `x.dim(1) == 1` candidate.

**Empirical confirmation.** The ceiling probe's arm B reads a *host*-computed
`(key, index)` sort in goodness order out of the router-key buffer instead of
running the prologue. Bitwise gate over the whole 65 536-byte output, at
TG = 1024 and TG = 2048, in both sessions:

```
  TG=1024  B_inds  diff      0 /  65536 bytes
  TG=2048  B_inds  diff      0 /  65536 bytes
  VERDICT: all arms bitwise identical to the reference.
```

winners (index order) `[39, 88, 99, 110, 114, 184, 216, 239]`;
winners (slot/goodness order) `[184, 239, 110, 88, 99, 216, 39, 114]` — the two
differ, so the gate is a real test of the ordering and not of a coincidence.

## 2. Stage 0(b) — ceiling

Instrument: `research/maple_tanjiro_r109c_gateup_probe.swift` (fork of
`research/fern_r99_qmv_probe.swift`; the only behavioural change is that the
router-key buffer is 264 words instead of 256, with the top-8 in goodness order
in words 256..263, and the first 1024 bytes are bit-identical to r99's because
the generator is sequential). Arms from
`research/maple-tanjiro-r109c-gateup-arms.py`; `A_base.metal` is md5-identical
to the shipped-text dump `research/artifacts/maple-tanjiro-r107g/qmv_dose0.metal`.
Driver `research/maple-tanjiro-r109c-ceiling-run.sh`, `FERN_DEFEAT_SLOTS=64`
(residency defeated — production re-reads cold expert weights every step),
`FERN_ROUNDS=41`, `FERN_REPS=200`, ladder 128…2048 threadgroups × 64 threads.

**Instrument floor (NULL control, same file in both slots, session s2):**

```
    TG    ref_min    var_min    d_mean     d_sd    d%_ref   t_paired
   128       4.89       4.87    -0.005    0.028    -0.107      -1.19
   256       7.17       7.16    -0.010    0.025    -0.143      -2.66
   512      12.47      12.31    -0.046    0.254    -0.368      -1.15
  1024      21.78      21.98    -0.025    0.232    -0.116      -0.70
  2048      37.66      38.00    +0.072    0.292    +0.191      +1.58
```

**Arm B (`uint expert = router_keys[256u + expert_slot];`, prologue deleted):**

| TG | TG/core | ref_min us | var_min us | d_mean us | d_sd | d%_ref | t_paired |
|---|---|---|---|---|---|---|---|
| 128 | 6.4 | 4.88 | 3.22 | −1.650 | 0.021 | −33.83 | −495 |
| 256 | 12.8 | 7.16 | 4.95 | −2.228 | 0.030 | −31.12 | −471 |
| 512 | 25.6 | 12.43 | 9.32 | −3.426 | 0.193 | −27.55 | −114 |
| **1024** | **51.2** | 21.99 | 20.86 | **−0.904** | 0.247 | **−4.11** | −23.4 |
| **2048** | **102.4** | 38.65 | 37.24 | **−1.505** | 0.159 | **−3.89** | −60.5 |

Session s1 (independent process, same config) gave TG = 2048
`ref_min 38.73, d_mean −1.544, d_sd 0.166, −3.99 %, t −59.7`. The two sessions
agree to 2.6 %.

TG = 1024 (51.2 TG/core) is the *occupancy* the ranked 40-core M5 sees for the
shipped 2048-threadgroup dispatch; TG = 2048 (102.4 TG/core) is what this
20-core host sees. The saving is −3.9 % to −4.1 % at both, so the **fraction**
brackets the M5 even though the absolute microseconds do not transfer.

**Memory regime at TG = 2048:** 274 MiB unique per round, amplification 6.2,
230.1 GB/s achieved = 86.4 % of the measured 266.3 GB/s peak → `SATURATED`.
The 38.7 us/dispatch also matches my independent ~40 us/layer production
estimate for routed gate/up, so the probe is measuring the shipped work.

**Pricing.** 1.52 us × 40 layers = 60.9 us/step. Baseline decode on this host
is 0.013890 s/token (the assignment's own reference constant), so the decode
speedup is 1.00441×, and
`ns = 1.00441^0.75 = 1.00329` → **+0.329 %** normalized score. Applying the
×0.5 probe-optimism discount from edward's #629 gives **+0.16 %**. Both clear
the 0.15 % gate; the discounted figure clears it only narrowly, which is why
§3 matters as much as the ceiling does.

(For the record: I could not reproduce the "0.01642 % score per M4 us/step"
constant I had noted earlier — the only 0.01642 in the repo is a leaderboard
score delta in `senpai/competition_notes/`, not a conversion factor. The
derivation above is from first principles and should be used instead.)

## 3. Flags for the advisor

### 3.1 The dependency-free fallback is measured dead — and that tells us the mechanism

I added a third arm at no extra cost. `C_sg0` keeps the selection in-kernel but
runs it in **one** simdgroup instead of two: the 64-thread threadgroup's two
simdgroups share `expert_slot` and read the same `router_keys`, so simdgroup 0
can compute the winner, publish it through threadgroup memory, and both
simdgroups read it after one `threadgroup_barrier`. It is bit-exact by
construction, needs no new buffer, no producer change and **no cross-kernel
dependency**, and it halves the redundant work.

| TG | TG/core | d_mean us | d%_ref | t_paired |
|---|---|---|---|---|
| 128 | 6.4 | −0.531 | −10.89 | −168 |
| 256 | 12.8 | −1.018 | −14.28 | −209 |
| 512 | 25.6 | −2.850 | −23.20 | −120 |
| 1024 | 51.2 | −0.522 | −2.36 | −14.7 |
| **2048** | **102.4** | **−0.017** | **−0.045** | **−0.62** |

At the shipped occupancy this is **null** — inside the NULL control's own
floor. Record it as `N-SG0-BROADCAST-NULL-AT-OCCUPANCY`.

The interesting part is *why*, because it re-reads the whole arm. If the
prologue's cost were redundant ALU throughput, halving it would recover half
the ceiling; it recovers 1 %. What the prologue actually costs is
**critical-path latency in front of address generation**: up to eight rounds,
each a 5-step `simd_shuffle_xor` butterfly, must retire before `expert` — and
therefore before the expert weight and scale addresses — exists. Running it in
one simdgroup does not shorten that chain; simdgroup 1 simply waits on
simdgroup 0 plus a barrier. Only *removing* the chain captures the ceiling.

Two useful corollaries:

* the remaining candidate space is exactly one item — gate/up reading a
  precomputed index — so the arm lives or dies on §3.2;
* the barrier + threadgroup-memory round trip is bounded at ≲0.2 us by C_sg0's
  TG = 2048 row, and at low occupancy C_sg0 captures 83 % of B's saving
  (−2.85 vs −3.43 at TG = 512), which confirms the arm's plumbing works and
  that the null is an occupancy fact, not a broken variant.

### 3.2 The arm's expected value is negative unless a new barrier drains almost nothing

This is the number that decides the arm, the probe cannot see it, and on the
campaign's own measured constants it is **larger than the prize**. I am not
hiding that behind the passed gate.

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`: the compute
encoder is always `MTLDispatchTypeConcurrent` (:545-549), and
`maybeInsertBarrier` (:363-373) emits an **encoder-global**
`memoryBarrier(BarrierScopeBuffers)` on a RAW hit in `set_input_array`
(:315-328) or a WAR hit in `register_output_array` (:338-349), then **clears**
the pending-write set.

Today: the router kernel writes `router_logits` + `router_keys`; the decode
ordinal selector's read of `router_logits` is itself a RAW hit, so it takes a
barrier and clears the set; gate/up's read of `router_keys` therefore emits
**no** barrier and gate/up overlaps freely with the selector (1 threadgroup,
256 threads) and with any other router-independent work in flight — the shared
expert included. The first read of a selector *output* is the routed
down/reduce stage.

Adding `inds` to gate/up's inputs creates a fresh RAW on the selector's output
⇒ one new encoder-global barrier per layer, in front of the 38 us kernel.
`research/RESEARCH_ARCHIVE_through-round-91.md:1355-1430` prices this on this
exact host: **fixed part 1.3003 ± 0.0597 us per barrier** (t = 21.8, CI
[1.183, 1.417]), independently corroborated by real removal
(+1.233 us, CI [0.920, 1.545]), with property (2) *"a barrier costs what it
drains"* — 157 barriers that drained nothing cost −42.8 us total.

So the cost is `40 × (1.30 + drain)` us/step against a `60.9` us/step prize:

| drain per layer | cost us/step | net vs +60.9 |
|---|---|---|
| ~0 (nothing in flight) | 52 | **+9** |
| selector only, ~2-3 us | 132-172 | **−71 to −111** |
| selector + serialized shared expert | worse still | dead |

The break-even drain is **0.22 us/layer**. A 256-thread bitonic sort is
plausibly an order of magnitude more than that, and today it is fully hidden
behind a 38 us kernel. **The most likely outcome of this arm is therefore
`N-INDS-DEPENDENCY-BARRIER`, not a win.** The ceiling gate is about whether the
prize is worth measuring; it is, because the kill test is cheap and the answer
generalizes to every future "gate/up consumes a router product" arm.

**Kill test first, and it is bit-exact.** P1 does not need a wrong-output
probe:

* **P1 — barrier-only.** New pipeline, `inputNames` gains `"indices"`, body
  **unchanged** (`uint expert = top8_winner;`). The extra buffer is bound and
  unused, so MLX still calls `set_input_array` and still emits the barrier,
  while traffic, arithmetic and output stay byte-identical to baseline. `P1 −
  baseline` is the barrier price and nothing else, and P1 passes the same
  correctness gates as baseline.
* **P2 — the candidate.** Same binding, `uint expert = uint(indices[expert_slot]);`,
  prologue deleted. `P2 − P1` should reproduce the −60.9 us/step ceiling;
  `P2 − baseline` is the ranked claim.

Order of work: implement both behind one env flag, run P1 vs baseline paired
ABBA first, and stop at `N-INDS-DEPENDENCY-BARRIER` if P1 alone loses more than
the ceiling. P1 is also reusable campaign infrastructure: it is the first clean
in-situ price of *one* added barrier in front of a large decode kernel, as
opposed to the archive's injected-pair estimate.

### 3.3 Publishing the top-8 from the router kernel is closed

The obvious way to avoid §3.2 — have the fused router kernel emit the top-8
itself — is not available. Its dispatch (:1224-1232) is 32 threadgroups of 512
threads with `rowsPerGroup = 8`, so **no threadgroup ever sees all 256 keys**,
and the env validator (:679) rejects `rowsPerGroup = 256`. Changing that
geometry is a different, much larger arm and is outside this assignment.

### 3.4 Deconfliction note for nezuko

Nothing here changes the `inds`/`weights` layout, the tournament, or
LRM:9977-10190. The candidate only *reads* `inds[slot]` for `slot < 8` in its
existing `[1, 1, 8] uint32` form. If nezuko's tournament selector work changes
the slot ordering of `inds`, my §1 identity is what breaks, so please flag any
ordering change in your PR.

## 4. Artifacts

* `research/maple_tanjiro_r109c_gateup_probe.swift`
* `research/maple-tanjiro-r109c-gateup-arms.py`
* `research/maple-tanjiro-r109c-ceiling-run.sh`
* `research/artifacts/maple-tanjiro-r109c/{A_base,B_inds,C_sg0}.metal`
* `research/artifacts/maple-tanjiro-r109c/null-s{1,2}-slots64.txt`
* `research/artifacts/maple-tanjiro-r109c/ceiling-s{1,2}-slots64.txt`

Reproduce:

```bash
xcrun swiftc -O research/maple_tanjiro_r109c_gateup_probe.swift -o /tmp/tanjiro_r109c
python3 research/maple-tanjiro-r109c-gateup-arms.py
BIN=/tmp/tanjiro_r109c bash research/maple-tanjiro-r109c-ceiling-run.sh s3 64
```

Whole session is ~5 s of GPU time and holds no model, so it does not contend
with a benchmark run.
