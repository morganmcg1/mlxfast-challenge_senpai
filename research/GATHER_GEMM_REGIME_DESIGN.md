# The gather-GEMM 15.4 ms has no surviving mechanism. Stop proposing mechanisms; test the régime.

Advisor design note, 2026-08-05 ~14:20 UTC. Author: meridian (advisor).
Source claims read out of the tree at `07d214d83e60ac31f47235492630afa58bbbc210`;
line numbers are that commit.

**Why this note exists.** I sat down to write the assignment brief for round-9
unowned queue **item 1**, "gather-GEMM mechanism #2 — SM=16 banding, +1.9 to
+2.6%", which the queue table calls "the largest sized defect anywhere in the
programme" and hands to the next free student. Reading the kernel first, item 1
is **not a lever at all**, and this document's own §item 8 and §item 15 in
`CURRENT_RESEARCH_STATE.md` already said so. The queue table contradicted the
prose of the same file. I nearly spent a student slot and a ranked receipt on a
closed item.

The correction is worth more than the brief would have been. Recorded here in
full so the next reader cannot re-make the mistake.

---

## 1. Item 1 is closed. Independent source confirmation.

The claim was: the gather-GEMM issues 453,120 MMA rows for 311,296 useful
(**1.456×**); recover ~5-7 ms by matching band granularity to the routed run
length.

The 1.456× is real. It is also **exactly at the floor**, and it is not tunable.

Geometry derivation, appearing four times in the file
(`kernels/fp_quantized_nax.h:580-586`, `:735-739`, `:1277-1281`, gather-GEMM at
**`:1634-1641`**):

```
constexpr short SM = BM / WM;     // :1634
constexpr short SK = 32;
constexpr short TM = SM / 16;     // :1637   <-- integer division
constexpr short TN = SN / 16;
```

Three independent locks:

1. **`TM = SM / 16` is integer division.** Any `SM < 16` gives `TM = 0` and the
   simdgroup issues no MMA whatsoever. 16 rows is the NAX MMA row quantum
   (`kFragRows`). `SM = 16` is the *smallest legal band*, not a choice.
   `SM = 32` is strictly worse (the document already prices it at a flat +41%).
2. **`SM` is not independently settable.** `SM = BM / WM`, and the host dispatch
   guard at `quantized.cpp:1662` pins `bm == 64 && wm == 4 &&
   (wn == 1 || wn == 2)`. The kernel re-asserts it for its own fast path at
   `:1657`: `kSwigluRegLocal = (WN == 1) && (BN == 64) && ((BM / WM) == 16)`,
   with the shipped geometry spelled out in the `:1649` comment. BM=64 and WM=4
   force SM=16 force TM=1.
3. **The band skip already exists.** `:1699-1701`:
   ```
   const short sgp_sm = min(int(SM), max(0, int(chunk_rows) - int(tm)));
   const bool sg_active = sgp_sm > 0;
   ```
   A simdgroup whose 16-row band lies wholly past `chunk_rows` issues nothing.
   Fully-empty bands are **already free**. What remains is the *partial* band,
   where `0 < sgp_sm < 16` still issues a full 16-row tile because that is the
   hardware granularity.

So 1.456× is a property of the **routed-row distribution** — 4096
row-assignments (512 tokens × top-8) over 256 experts, mean 16 rows/expert,
measured against a 16-row quantum — and `453,120 = Σ ceil(n_e/16)·16` is
identically the `kFragRows` floor. Rows cannot be co-banded across experts
because different experts need different weights.

**There is no geometry edit that recovers any of it.** The only route below
1.456× is the two-régime dispatch of §item 15, which would have to break
per-expert weight exclusivity and does not yet have a mechanism proposal.

**Consequence for the programme ledger: the banked "+1.9 to +2.6% unowned" must
come out.** The unowned total was overstated by roughly its largest single
entry.

---

## 2. Item 2's sibling has already been tried twice, including the obvious fix

Before writing this note I designed a replacement mechanism — split the weight
loader into a device→register phase and a register→threadgroup phase, then
prefetch iteration k+1's weight bytes into registers before iteration k's MMA,
buying intra-threadgroup D/M overlap for ~2 registers per thread and **zero**
threadgroup bytes. The structure is already latent in `load_unsafe_wide`
(`:392-500`), which stages device bytes through a thread-local `uint8_t
sb[kSrcBytes]` at `:411-440` before touching `dst`; `kSrcBytes = 8` at the live
instantiation (`:339`, `:356`, and the shipped `:1749` comment "8 scalar 1B
device loads -> 1 8B load per thread"); `next()` is a bare pointer bump
(`:502-503`). The bit-exactness argument would have been the shipped
A-operand hoist's own argument at `:1730-1745` applied to the B operand.

**fern already ran it.** PR #40's *v2 arm was register prefetch*, measured
`dS = +0.4626 ms` — the wrong sign, against a predicted −2.4 to −15.4 ms. Her
v1 arm (double-buffered `Ws`) measured `+0.1150 ms`. Both inside
`σ_dS = 0.2536 ms`. `ns` ranked control (2.544360) > v2 (2.539719) >
v1 (2.538013). Her PR carries the explicit instruction: *"Do not reopen with a
deeper prefetch, a wider `Ws`, or a different barrier placement."*

That instruction is correct and I am restating it. My §2 design is a *deeper
prefetch*. It is dead.

### 2.1 But the double null now has a mechanism, and it is the useful part

The k-loop (`:1725-1765`) is:

```
for (int k = 0; k < K_it; ++k) {
    Atile[..] = device x loads          // A-operand hoist, registers
    threadgroup_barrier(...)            // barrier 1
    loader_w.load_unsafe[_wide]()       // device -> registers -> Ws
    threadgroup_barrier(...)            // barrier 2
    if (sg_active) { MMA over Ws }
}
```

Two unconditional barriers per k-iteration, so **inside one threadgroup weight
traffic and MMA cannot overlap** — barrier 2 stands between them by
construction. Every bit of observed overlap comes from *other* threadgroups
resident on the same core sitting at a different loop phase.

The same residency is also what keeps the MMA units fed. On the **median**
chunk (`chunk_rows ≈ 16`, mean routed rows per expert = 16), exactly **one of
the four simdgroups** has `sg_active == true`; the other three wait at the
barriers. A core therefore needs ~4 co-resident threadgroups just to fill its
simdgroup slots. Inter-threadgroup residency is doing **two** jobs at once:
D/M overlap *and* MMA-unit utilisation.

Now price both of fern's arms in that currency:

| arm | resource spent | occupancy effect | predicted |
|---|---|---|---|
| v1 double-buffered `Ws` | threadgroup memory (a second `BN×BK_padded` stage on top of the ~8.4 kB `Ws_storage`) | **down** | gain ≈ loss ⇒ null |
| v2 register prefetch | registers (`sb`, extra `Dtile`-adjacent live range) | **down** | gain ≈ loss ⇒ null |

**Both arms bought intra-threadgroup overlap by spending the resource that
supplies inter-threadgroup overlap.** That is a self-cancelling trade, and it
predicts *two* nulls of the observed size and sign — which is what happened.
The programme recorded the double null as a bare fact; this is the mechanism.

**The load-bearing generalisation: on this kernel, any arm that increases
per-threadgroup resource use to buy overlap is fighting itself. Only arms that
*reduce* per-threadgroup resource use can move it.**

Current footprint, read from `:1610-1621`:
```
constexpr int kWsElems = BN * BK_padded;
threadgroup NAXWsChunk16<Wtype> Ws_storage[(kWsElems + kWsPerChunk - 1)/kWsPerChunk];
threadgroup Wtype*  Ws            = (threadgroup Wtype*)Ws_storage;
threadgroup bfloat* gate_up_stage = (threadgroup bfloat*)Ws_storage;   // ALIASED
threadgroup int bounds[experts / expert_groups + 1];                   // BSEARCH_HOIST
```
`gate_up_stage` is already aliased onto `Ws_storage`, so that economy is taken.
`Ws_storage` is ~8.4 kB at BN=64, BK_padded≈66, `Wtype = bfloat`. `bounds`
scales with experts-per-group and is the only allocation nobody has audited.
128 threads (`WM*WN*SIMD_SIZE = 4*1*32`) = 4 simdgroups per threadgroup.

---

## 3. What the next arm should actually be

After §1 (banding closed at the floor) and §2 (both staging arms null, with a
mechanism explaining why), **the 43.26 ms measured versus the 27.9 ms weight-DRAM
floor has no surviving mechanism at all.** 15.4 ms of scored prefill — worth
+5.7% of score at the measured 0.371 %/ms exchange rate — is unexplained and
unowned.

That is not a reason to invent a third mechanism. Two mechanism-first arms have
now failed, and both failed because the *model of the kernel's régime* was
wrong. The next arm must test the régime.

### D1. The pure-D arm: is the floor real?

The 27.9 ms floor assumes the kernel streams its 15.22 GB of net weight bytes at
~546 GB/s. The kernel *achieves* 408.4 GB/s overall (23.23 TFLOP/s against a
34.7 ceiling). Two readings fit the same 43.26 ms:

- **Schedule-limited:** reads run at ~546 GB/s during D phases, but D and M
  are serialised, so `43.26 ≈ 54.0 − 0.41 × 26.1`. Overlap is the lever
  (and §2 says only resource *reduction* can get it).
- **Bandwidth-limited:** reads run at ~408 GB/s inherently, because of the
  access pattern — strided per-expert slabs, `bytes_per_pack` granularity,
  scale planes interleaved. Then D alone is ≈ 37 ms, the "15.4 ms recoverable"
  is mostly *not* recoverable, and the lever is the access pattern.

**Discriminator.** Build a compile-time arm that keeps the loop, both barriers,
and **every device read**, and predicates out only the MMA. It must be a
compile-time arm, not a runtime branch, and the student must confirm from the
generated MSL that the loads survive dead-code elimination (store `sb` into a
`volatile`-equivalent sink or accumulate it into `Dtile` with a zero
multiplier — whichever the compiler cannot fold; **verify, do not assume**).
That arm's prefill time is D alone.

- D-alone ≈ 27.9 ms ⇒ schedule-limited. Go after occupancy (D2).
- D-alone ≈ 37 ms ⇒ bandwidth-limited. The 15.4 ms figure is largely fictitious,
  the residual belongs to the access pattern, and **item 2 (the `x` re-read,
  ~1-3 ms) is mispriced too** because it assumes the same floor.

Either answer is a first-class programme result. This is the cheapest question
on the board with the largest fan-out: it retires or revalues ~5.7% of score.

**This is a correctness-free arm** — it deliberately computes wrong outputs, so
it can never be submitted as a candidate and cannot be measured on the ranked
channel. It needs an M5 host with `--local-iterate`, or it needs to be built as
a *diagnostic ranked receipt* whose token check will fail by design (wasting
the ticket). **Flag for the operator: if any M5 access exists outside the ranked
submission path, this arm is the single highest-value use of it.** Absent that,
D2 below is the M4-legal substitute and should run first.

### D2. The occupancy audit — and it is M4-legal

§2 says occupancy is the currency. Nobody has measured it.

Occupancy is a **static compiler property**, not a timing measurement, so the
M4 TRANSFER LAW does not block it and neither does `_nax` execution gating.
`is_nax_available()` (`device.cpp:913-931`) requires Apple GPU generation ≥ 17
and M4 Pro probes 16, so the `_nax` gather-GEMM never *runs* locally — but it
**compiles** locally, which fern's own merged
`research/nax_msl_compile_check.sh` already demonstrates.

Deliverables, all local, no ranked receipt:

1. **Exact threadgroup-memory bytes** for the shipped instantiation:
   `Ws_storage` (`BN × BK_padded × sizeof(Wtype)`, rounded up to
   `NAXWsChunk16` granularity) plus `bounds[experts/expert_groups + 1]`.
   Resolve `BK_padded`, `Wtype` and `expert_groups` from the host call site in
   `quantized.cpp`, do not guess them.
2. **`maxTotalThreadsPerThreadgroup`** from the compiled
   `MTLComputePipelineState` for the shipped gather-GEMM. The driver lowers
   this when register pressure is high; if it reports < 128 the kernel cannot
   even launch its own 128-thread threadgroup at full width and register
   pressure is *already* pathological. If it reports ≥ 128, record the margin.
3. **Occupancy arithmetic:** threadgroups/core from threadgroup memory
   (`core_tgmem / bytes_per_tg`) versus from simdgroup slots
   (`24 / 4 = 6` on Apple cores) versus from registers. Name the binding term.
   This single answer tells the programme whether §2's currency is threadgroup
   memory or registers — and therefore which of the two reduction directions is
   even available.
4. **One reduction candidate, priced.** The unaudited allocation is `bounds`.
   Under `DARKBLOOM_BSEARCH_HOIST` it is `experts/expert_groups + 1` ints; at
   `expert_groups = 1` that is ~1.0 kB, at 8 it is ~132 B. If it is the large
   case, note that the non-hoisted arm needs only `bounds[2]` — i.e. the hoist
   trades ~1 kB of threadgroup memory for one barrier per expert slot, and
   nobody has checked which side of that trade the shipped configuration is on.
   Do **not** flip it on this arm; price it and report.

D2 costs no ranked receipt, resolves the mechanism question §2 raises, and its
answer is a hard prerequisite for any future gather-GEMM arm. **Assign D2
first.** It is the round-9 unowned item 1 replacement.

---

## 4. Discipline this note is enforcing

Three arms have now been proposed against this residual (banding, `Ws`
double-buffer, register prefetch). One was closed in-tree before it was
proposed, two were measured null, and all three shared one defect: they assumed
a régime instead of measuring it. The pattern matches the standing critique in
`CURRENT_RESEARCH_STATE.md` — *"the programme has staffed measurement of both
big residuals but mechanism ownership of neither, while treating 'GPU busy' as
'GPU useful'"* — and the fix is the same ordering that tanjiro's #47 uses (D2
knee before D5 bracket): **diagnostic arm before mechanism arm.**

Applied here: **D2 (free, local, static) before D1 (needs M5) before any third
mechanism.** No student should receive a gather-GEMM mechanism assignment until
D2 has named the binding occupancy term.
