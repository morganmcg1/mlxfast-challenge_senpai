# Rule 105.24 — MLX already runs the dispatches we were going to merge concurrently, which reprices the whole night; plus the integration hazard map for the 06:00Z handoff

**Advisor** meridian · **campaign** maple · **written** 2026-08-10 ~16:45Z ·
**base** `adfca1e5fd3b1aa7645538fd0f924cb3164c99a7`
**Generator** `research/advisor_r105_24_concurrency_repricing.py` (deterministic, six self-checks, no receipts)
**Trigger** maple-tanjiro's R108-L (`874e4917`, PR #663), delivered 3.5 h early with verdict `N-NO-MERGEABLE-PAIR`

---

## 0. One-paragraph summary

Tanjiro refused the adjacent-pair merge programme on **price**, not structure:
he priced dispatch removal at `k = 0.0872` from #483's directly measured
0.108 µs/dispatch (CI [−0.221, +0.438], spanning zero) against the `k = 1.890`
that rules 105.17, 105.20 and 105.23 all assumed — a **21.7× disagreement**. He
proposed instead a "stop serialising the independent pairs" lever worth ≈1.83 %.
I went looking for the mechanism behind his number and found, in the vendor
source, that **both halves of his report resolve to the same fact**: MLX creates
every compute encoder with `MTL::DispatchTypeConcurrent` and inserts a
`memoryBarrier` **only on a true read-after-write hazard**. His three `NONE`
pairs therefore already run concurrently — so his 1.83 % is already banked and
not harvestable, *and* the dispatches we planned to merge away are already free,
which is precisely why removing them refunds almost nothing. Five previously
unrelated null results collapse into one mechanism. The merge programme's
expected value falls from `P(≥1 of 2 draws) = 0.529` to **0.000**, unless
frieren's 45-minute barrier-region probe says otherwise — which makes that probe
the single highest-value action available to the campaign tonight, and reverses
105.23(c)'s finding that resolving the price was worth zero.

---

## 1. The four source facts

All verified at `adfca1e5` in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/`.

**(1) The encoder is concurrent, and always was.**

```
device.cpp:545-548
MTL::ComputeCommandEncoder* CommandEncoder::get_command_encoder() {
  if (!encoder_) {
    encoder_ = NS::RetainPtr(
        buffer_->computeCommandEncoder(MTL::DispatchTypeConcurrent));
```

This closes #617's open handle — "whether the Metal compute encoder is
`MTLDispatchTypeSerial` where the dependency DAG does not require it" — with a
flat **no**. It never was.

**(2) A barrier is emitted only on a true RAW hazard.**

```
device.cpp:325   (CommandEncoder::set_input_array)
  needs_barrier_ =
      needs_barrier_ | (prev_outputs_.find(r_buf) != prev_outputs_.end());

device.cpp:363-375
void CommandEncoder::maybeInsertBarrier() {
  if (needs_barrier_) {
    get_command_encoder()->memoryBarrier(MTL::BarrierScopeBuffers);
    needs_barrier_ = false;
    prev_inputs_  = std::move(next_inputs_);
    prev_outputs_ = std::move(next_outputs_);
  } else {
    prev_inputs_.insert(next_inputs_.begin(), next_inputs_.end());
    prev_outputs_.insert(next_outputs_.begin(), next_outputs_.end());
  }
  next_inputs_.clear();
  next_outputs_.clear();
}
```

`maybeInsertBarrier()` is called from `dispatch_threadgroups` (`:380`) and
`dispatch_threads` (`:388`), *after* the current dispatch's inputs and outputs
have been registered. So the rule is exactly: **barrier iff this dispatch reads
a buffer written by some dispatch since the last barrier.**

**(3) Trace family E through that policy and the merge target evaporates.**

| step | action | `prev_outputs_` after | barrier? |
|---|---|---|---|
| RMSNorm | writes `normalized` | `{…, normalized}` | — |
| QKV (`LRM:5027`) | reads `normalized` ⇒ `needs_barrier_` | barrier fires; `prev_outputs_ = std::move(next_outputs_)` ⇒ **`{qkv}`**, `normalized` **dropped** | **yes** |
| gate_sp (`LRM:4539`) | reads `normalized`; not in `{qkv}` | `{qkv, gate_values}` | **no** |

**QKV and gate_sp are already members of the same barrier-free region of a
concurrent encoder.** The `move` on the barrier path is what does it: the barrier
*resets* the hazard set rather than accumulating into it, so a second consumer of
an already-consumed producer is free.

**(4) The policy is not ours to change.** `device.cpp` and `device.h` are **not**
in `benchmark.json`'s `editablePaths`. The editable metal-backend surface is
`matmul.cpp`, `jit_kernels.cpp`, `kernels.h`, `quantized.cpp` and the kernel
sources — no encoder, no scheduler.

---

## 2. Five null results become one mechanism

Nothing in our record contradicts fact 3; five separate results now *require* it.

| result | what it measured | reading under 105.24 |
|---|---|---|
| **#483** (fern, R91) | +80 input-norm dispatches cost **0.108 µs each**, CI [−0.221, +0.438] | those 80 joined barrier-free regions ⇒ nearly free |
| **#158** | null, −0.12 ± 0.22 µs | same |
| **#218** | router family 0.00 ± 0.12 µs/call | same |
| **105-D §4** | ≥68.4 % overlapped; "the first ~480 added dispatches are free"; production ~408 | the free-absorption region *is* the concurrent region |
| **#48** | 8× threadgroup collapse **reduced** dispatch count, scored **−0.1488 %** | merging already-concurrent work into one kernel trades free parallelism for an occupancy loss |
| **rule 65** | added dispatch = **+2.3403 µs [2.2766, 2.4040]** on M5 | measured with **dependent** probes (rule 67 corollary) ⇒ it priced a *serialising* boundary, not a dispatch |

Rule 65 and #483 were never in conflict. They measured two different regimes:
rule 65 measured additions that **forced a barrier**; #483 measured additions that
**did not**. Rule 68 ("do not apply rule 65's addition price in the removal
direction") was the right prohibition for the wrong reason — the real
discriminator is not direction, it is **whether the dispatch sits inside or at
the edge of a concurrent region.**

This also corrects **frieren's R107-F §11.4** ("one merge = +2.19–2.31 %"), which
summed a dispatch term and a barrier-drain term. Tanjiro's §3.2 is right that
these are the same money; 105.24 says *why*: rule 65 already **is** the barrier
price, so `dispatch_gain + drain_gain` counts the barrier twice. The two agree to
10 % (0.0202–0.0232 %/boundary vs 0.0188 %/dispatch at `k = 1.0`) exactly as a
quantity and its own decomposition must.

**Adjacent family already closed, independently.** nezuko's `6cc93da9` (r3-C,
5 Aug) swept `max_mb_per_buffer` from 12 to 2048 MB and found median inter-buffer
GPU idle **0.87–1.00 µs at every cap**; `H_encode` REFUTED. Command-buffer
segmentation (`device.cpp:576-593`, `needs_commit()` at `buffer_ops_ > 40` or
`buffer_sizes_ >> 20 > 40`; `MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` in
`utils.h:178-187`) is therefore **not** a lever either, despite the decode step
using ~47 command buffers. Both halves of the "the runtime is serialising us"
family are now closed.

---

## 3. Repricing (generator §(a))

`Δ%cs = n × 1.2382 [M4 µs] × k × 0.015228`.

| k | µs/dispatch [M4] | n=40 (one merge) | n=79 (two) | n=158 (everything removable) | P(≥1 of 2 draws), n=40 | provenance of k |
|---|---|---|---|---|---|---|
| **0.0872** | 0.1080 | **0.0658 %** | 0.1299 % | 0.2598 % | **0.0000** | **#483, measured, CI spans 0** |
| 0.2000 | 0.2476 | 0.1508 % | 0.2979 % | 0.5958 % | 0.0000 | tanjiro's prior |
| 0.3000 | 0.3715 | 0.2263 % | 0.4469 % | 0.8937 % | 0.0000 | my "dead" threshold |
| 0.5000 | 0.6191 | 0.3771 % | 0.7448 % | 1.4896 % | 0.0000 | β, latency transfer |
| 0.8000 | 0.9906 | 0.6034 % | 1.1917 % | 2.3833 % | 0.0006 | my "alive" threshold |
| 1.0000 | 1.2382 | 0.7542 % | 1.4896 % | 2.9791 % | 0.0035 | 105.17 floor |
| 1.3950 | 1.7273 | 1.0521 % | 2.0779 % | 4.1559 % | 0.0522 | 105.17 midpoint |
| 1.8900 | 2.3402 | **1.4255 %** | 2.8153 % | 5.6306 % | 0.4265 | rule 65 reversed |

Two corrections folded in:

- **`n = 40`, not 30.** 105.20 priced family E over the 30 h64 layers only;
  `T2b′ gate_sp h48` is the identical kernel family for the other 10. Every
  family-E number in 105.17/105.20/105.23 is **33 % low**. At `k = 1.890` one
  merge is 1.4255 %, not 1.069 %.
- **0.787 %, not 0.803 %,** at `k = 1.395`, `n = 30` — my arithmetic slip,
  caught by tanjiro's reproduction.

**Even the optimistic correction cannot save the programme if `k` is small.**
Removing *every removable dispatch in the step* at the measured price is
**0.2598 %**, which is 1.5× below the 0.4 % draw bar and 6.3× below `g0`.

---

## 4. What frieren's probe has to return (generator §(b))

Let `s` = the arm-F slope in **M4 µs/step per added barrier-free dispatch**.
Then `Δ%cs = n × s × 1.890 × 0.015228`, and `k = s / 1.2382`.

| programme | `s` for 0.4 % | `s` for 1.0 % | `s` for `g0` = 1.6359 % |
|---|---|---|---|
| one merge (n = 40) | **0.3475** | **0.8686** | 1.4210 |
| two merges (n = 79) | 0.1759 | 0.4398 | 0.7195 |
| everything (n = 158) | 0.0880 | 0.2199 | 0.3597 |

The thresholds I sent frieren were chosen before I ran this and land almost
exactly on the two bars — `s = 0.30` ⇒ 0.3454 % (bar 0.4 %); `s = 0.80` ⇒
0.9210 % (arming threshold 1.0 %). Keep them.

**The probe design** (relayed to PR #660): one no-op kernel, two arms, identical
bytes/grid/threadgroup, differing only in the dependency edge.
- **Arm F** — each no-op reads a buffer *not* in `prev_outputs_` ⇒ by fact 2 no
  barrier ⇒ slope = the price of a dispatch **in the regime the merge operates
  in**.
- **Arm S** — each no-op reads the previous one's output ⇒ barrier every time ⇒
  slope = the price of a **serialising boundary**.

`Arm S − Arm F` is the first clean separation of rule 65's confounded
launch-plus-drain and retires all three of 105.17's unverified assumptions
(removal symmetry, drain generality, barrier re-import) in one experiment.
Frieren was also asked to *verify* fact 2 rather than trust it: if the two slopes
come back equal, my source reading is wrong and that is the more important
finding.

---

## 5. Value of information — this reverses 105.23(c) (generator §(c))

105.23(c) concluded that *resolving the route* (which of three prices A/B/C is
right) was worth **0**, because you should merge twice under every route. That
held because all three routes were ≥0.756 %. `H_free` is outside that envelope,
so the conclusion does not survive.

| programme | `H_free` (k = 0.0872) | P(≥1 of 2) | `H_priced` (k = 1.0) | P(≥1 of 2) |
|---|---|---|---|---|
| one merge | 0.0658 % | 0.0000 | 0.7542 % | 0.0035 |
| two merges | 0.1299 % | 0.0000 | 1.4896 % | **0.5291** |
| everything removable | 0.2598 % | 0.0000 | 2.9791 % | 1.0000 |

| `P(H_free)` | `E[P(≥1 of 2 draws)]` from the two-merge programme |
|---|---|
| 0.00 | 0.5291 |
| 0.25 | 0.3968 |
| 0.50 | 0.2645 |
| 0.75 | 0.1323 |
| 0.90 | 0.0529 |
| 1.00 | 0.0000 |

**The spread between the hypotheses is 0.529 of a campaign win, and a
45-minute probe collapses it.** That is the highest value-of-information figure
this campaign has produced. My own prior after reading the source is
`P(H_free) ≈ 0.8`; five independent nulls and a mechanism that explains all of
them is strong evidence, but I have not measured it, and I will not spend the
night on a source reading.

**Note the asymmetry.** `H_free` does not merely reduce the merge programme's
value; it makes the merge programme's value **numerically zero to four decimal
places**, because 0.13 % is 5.2 σ short of the record. There is no "small win"
branch. This is a binary.

---

## 6. Consequences for the other live rules

| rule | status after 105.24 |
|---|---|
| **105.16** (N-BYTES-EVERYWHERE, slack ceiling 1.232 % for the whole programme) | **strengthened.** Its five-family ceiling was 4.86× below 105.17's dispatch accounting; 105.24 explains the gap in 105.16's favour. |
| **105.17** (39 dispatches ⇒ +0.735…1.390 %) | **suspended pending arm F.** Its three named unverified assumptions are all downstream of the regime question. |
| **105.20** (the family-E merge) | design work stands and remains correct; `n` corrected 30 ⇒ 40; §(f) "IDENTICAL by verbatim copy" now also has tanjiro's §7 F3 refutation of the `_v3` template as a bit-exact donor; §(h)'s register-union warning is promoted from a caveat to **the predicted dominant term**. |
| **105.21 / 105.22** (draw table, scheduling) | unaffected — they price `x`, they do not produce it. Two draws, 08:00Z and 08:25Z, never split, never unused. |
| **105.23** (merge portfolio) | (a), (b), (d) stand conditional on `k ≥ 1`; **(c) is reversed** — resolving the price is now worth up to 0.529, not 0; **(e)'s critical test is superseded** by the arm-F probe, which is cheaper and discriminates better; **(f)'s 21:00Z decision rule is replaced** by the 19:00Z probe rule. |
| **105.19** (α-free bound, fern's bandwidth probe) | unaffected and still wanted. |
| **rule 68** | reinterpreted: the discriminator is region membership, not direction. |

---

## 7. Integration hazard map for the 06:00Z handoff

Independent of the pricing question, the integration facts below are verified and
were the original reason for this note.

**(a) There has been no behavioural base drift at all since nezuko's base.**
`git diff --stat fc66172b adfca1e5 -- . ':(exclude)research'` is **empty**. The
squash-merges of #597 (frieren), #625 (fern) and #648 (tanjiro), and rules
105.16–105.23, were **research-only**. Every live arm is therefore developing on
a behaviourally identical tree, whatever base SHA its PR is bound to.

**(b) Only edward carries any editable drift, and it is inert.**
`2454cc01 → 705484b9` (alphonse) is **empty**. `3241e5e5 → 705484b9` (edward) is
a single 25-line addition to
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`:
`darkbloom_expert_down_bn()` reading `DARKBLOOM_EXPERT_DOWN_BN` with **default 64
= the existing value**, plus one gated `bn = darkbloom_expert_down_bn()` inside
`gather_qmm_rhs_nax` for the down shape only (K=512, N=2048, group 16, 4 bits,
transposed, M ≥ 64, bm == 64, wm == 4, wn ∈ {1,2}). **Behaviourally inert at
default.** ⇒ **Neither edward nor alphonse needs to rebase for correctness.**
Both must rebase before the 06:00Z handoff for clean integration only.

**(c) The real hazard is intra-file, in one file.** Every live decode arm edits
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (12,147 lines at `adfca1e5`,
unchanged since `705484b9`). Verified coordinates:

| symbol | line | claimed by |
|---|---|---|
| `lagunaUseNativeAffineOProj(layer:)` | 429 | alphonse |
| `lagunaNativeAffineGProjWeight` | 482 | (context for the format stranding) |
| `lagunaNativeAffineWeight` | 3092 | (context; tanjiro's F2 correction) |
| `lagunaFusedGatedAffineOProjEnabled` | 4110 | alphonse |
| `lagunaGateSoftplusSource(heads:)` | 4467 | **frieren** |
| `lagunaDecodeNVFP4QKVR1Source` | 4810 | **nezuko** |
| `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:)` | 4922 | **frieren + nezuko — same function** |
| `foldGateIntoBank` | 5713 | frieren (refused branch) |
| `fusedTailGateLogits` (landing site) | 5947 | **frieren** |
| `gateProjectionActivated` decl / set / read | 5973 / 5998 / 6031, 6039 | frieren |
| o-proj guard cluster | 6027, 6330, 6343, 6359, 6373, 6389 | **alphonse** |

🚨 **frieren (family-E merge) and nezuko (QKV lane-major packing replication)
edit the same kernel-source function.** alphonse's o-proj arm sits in the
adjacent guard cluster. edward's arm is in `quantized.cpp` and MoE paths and does
not collide.

**(d) Merge order for fern, highest-value and most central first:**
**frieren → nezuko → alphonse → edward.** Rationale: frieren's edit is the most
structural (it changes the kernel's grid and adds outputs); nezuko's replaces the
body of the same function and is far easier to re-apply onto frieren's than the
reverse; alphonse touches only guards; edward touches a different file entirely
and can go last or first with no interaction.

**(e) Bytes are not binding.** `senpai/check-editable-budget.sh 1bc1c895…` at
`adfca1e5`: `current=2681206/3000000 headroom=318794 growth=−302643/262144
files=142`. `LagunaRuntimeModel.swift` is 384,245 B against the **hard per-file
abort at 524,288 B** ⇒ 140,043 B of headroom ⇒ ~34 merges at ~4 KiB. `research/`
is not in `editablePaths` and costs nothing. **The clock is the only binding
resource.**

---

## 8. What I am doing about it

1. **frieren, PR #660** — build order reversed: run the barrier-region probe
   **first**, report at **19:00Z** not 21:00Z. Merged-kernel construction is
   conditional on `s ≥ 0.8`. She was also given both corrections to her own
   R107-F §11.4 and to 105.20's `n`.
2. **tanjiro, PR #663** — `r108-l-rev2`: the **decode overlap audit**, due
   18:00Z, mostly from artifacts he already holds. Busy-sum vs busy-union for one
   decode step; the barrier map for one layer; `region_wall_time` vs
   `sum(member durations)`; and a repricing of his own §5 ledger against the
   region structure. **If busy-sum ≈ busy-union for decode, §1 fact 3 is
   contradicted by the hardware and the merge programme is alive again.** This is
   an independent second route to the same answer, on a different instrument,
   arriving an hour earlier.
3. **fern, PR #664** — the integration hazard map and merge order in §7.
4. **edward, alphonse** — told they need not rebase for behavioural correctness,
   but must rebase before 06:00Z.

Two independent probes on two instruments, both reporting before 19:00Z, both
capable of falsifying §1. That is the correct amount of redundancy for a fact
that swings 0.529 of a campaign win.

---

## 9. Caveats

1. **§1 is a source reading, not a measurement.** Metal may serialise
   concurrently-encoded dispatches for reasons invisible in the encoder (single
   queue depth, register pressure, threadgroup-slot exhaustion). A kernel that
   already saturates the GPU leaves nothing to overlap into — and tanjiro's own
   rule-100 finding that fused attention is **ISSUE-bound at 97.7 % of peak
   issue** says at least one family is in exactly that state. `H_free` may be
   true for gate_sp-sized dispatches and false for large ones. Arm F measures the
   small-dispatch regime, which is the one the merge programme lives in.
2. **`prev_outputs_` is tracked at buffer granularity**, and MLX recycles
   allocations from a pool. A recycled buffer can therefore create a *false* RAW
   hazard and an unnecessary barrier. I have not bounded how often. This is the
   one direction in which a real, editable-surface lever might still exist — but
   the fix would live in `device.cpp`, which is not editable.
3. **The 0.015228 %/µs-step price and `k_dispatch = 1.890` are M5 constants**
   carried onto an M4 measurement. If arm F lands near a threshold, the transfer
   uncertainty matters; if it lands at 0.108 µs, it does not.
4. **Draw arithmetic assumes** `g0 = 1.6359 %`, `σ = 0.3016 %`, gains additive
   with the current tree's certified `x = 0`. Rows above ~3 % are extrapolation.
5. **§7(a)'s "no behavioural drift" is a diff over `editablePaths` only.** It is
   the right test for integration, but it does not mean the three merged PRs were
   worthless — they were research, and research is what produced this note.
