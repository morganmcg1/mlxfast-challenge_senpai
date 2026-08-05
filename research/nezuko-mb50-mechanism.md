# Deliverable C — why a smaller `MLX_MAX_MB_PER_BUFFER` makes decode faster

## The paragraph

The per-command-buffer *host*-cost model is refuted twice over. Host gap per
decode step is flat across the setting (0.249 ms at 200 MB versus 0.250 ms at
50 MB) even though the command-buffer count per step triples from ~48 to ~140,
so the ~2% wall-time saving lives entirely inside the GPU-busy region; and the
model's sign is wrong, because it predicts that fewer, larger buffers are
cheaper. What the byte cap actually controls is *where the serialization
happens*. MLX encodes each command buffer as one concurrent-dispatch compute
encoder and inserts a `memoryBarrier(BarrierScopeBuffers)` before every
dispatch that consumes something written earlier in the same encoder
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:317-392`); when
`needs_commit()` trips the byte cap the encoder ends and that barrier state
resets, so the first dependent dispatch of the next buffer needs no in-encoder
barrier and cross-buffer ordering rides on the encoder-end fence plus in-order
kick execution. For a serial decode chain this makes the cap a 1:1 converter:
Δ(in-encoder barriers) = −Δ(command buffers), with total ordering events pinned
near the ~406 dispatches per step. An in-encoder barrier's drain-and-flush is
booked inside `[GPUStartTime, GPUEndTime]`, whereas a buffer seam is measured
free — this runtime's own probe finds `gpu_busy_sum == gpu_busy_union` to 6 ns,
i.e. adjacent buffers neither overlap nor leave a measurable gap, because the
firmware prepares the next kick's control stream and pipeline state while the
previous kick executes. Converting ~92 barriers into ~92 free seams at ~2 µs
each accounts for the observed ~180 µs/step. That model also predicts the
reversal I measured below 50 MB: once buffers get short enough that kick
preparation no longer hides behind the previous kick, and once the encoder is
cut so finely that genuinely independent dispatches (Q/K/V after one norm,
gate/up in the MLP) can no longer run concurrently inside one encoder, the
conversion stops paying. Hence the interior optimum at 50 MB rather than a
monotone trend, and hence the fact that 50 MB is also the byte cap MLX ships
for Max- and Ultra-class parts. Residency and wired-memory mechanisms are
excluded by construction here: MLX allocates
`StorageModeShared | HazardTrackingModeUntracked`, creates command buffers with
unretained references, and keeps one persistent queue-attached
`MTLResidencySet`, so there is no byte-proportional per-buffer driver work to
save, and any that existed would surface in the flat host gap.

## Ranked mechanisms (frontier advisor review, `db865ac6`)

Given the measured facts — host gap flat, effect inside GPU busy, ~48 → ~140
command buffers, ~2.0% faster at 50 MB, ~2.5% slower at 400 MB — the review
ranked:

1. **M1 barrier → seam conversion (high, primary).** In-encoder
   `memoryBarrier` forces the compute front-end to stop launching, drain prior
   dispatches, and flush caches, all inside the GPU-busy interval. The same
   drain at a kick boundary is hidden because the next kick's control stream,
   pipeline states, and bind tables are fetched while the previous kick runs
   (that preparation sits between `kernelStartTime` and `GPUStartTime`, outside
   the command-buffer stamps). ~2 µs per conversion × ~92 conversions ≈ the
   observed ~180 µs/step.
2. **M2 kick-prep and instruction-cache prefetch overlap (medium-high).** The
   same effect seen from the setup side: pipeline-state load and bind
   processing for a new kick overlap the previous kick, while a post-barrier
   dispatch inside one long encoder serializes behind the drain. Scales with
   boundary count, so M1 and M2 behave as one family for dose-response.
3. **M3 DVFS / power-state cadence (medium-low).** More frequent completions
   could hold GPU-core or fabric p-states higher. Discriminated by whether
   *every* kernel shrinks uniformly and macmon frequency covaries, versus the
   saving being localized at boundaries.
4. **M4 allocator recycling and first-touch faults (low).** Temporaries are
   released in the completion handler, so larger buffers recycle pool memory
   later. Predicts a warm-up-only effect and a ~zero steady-state slope, which
   contradicts the steady −2%.
5. **M5 per-command-buffer residency / wired memory (very low, refuted by
   code).** Untracked shared buffers, unretained references, and a persistent
   residency set leave no byte-proportional per-buffer driver work; and it
   predicts the wrong sign anyway.
6. **M6 preemption / external-client insertion points (very low on a quiet
   bench host).**
7. **M7 union-metric artefact (closed, kept as hygiene).** The feared artefact
   — large buffers bracketing internal idle as "busy", so splitting merely
   reclassifies it — would show union down with gap **up** and wall flat.
   Measured: gap flat, wall down, and `sum == union` to 6 ns. Wall clock is the
   verdict and agrees. Note the profiling instrumentation adds a per-buffer
   completion handler, so its overhead grows with buffer count and biases the
   instrumented decomposition *against* small caps.

The single most decisive follow-up measurement the review identified: one
GPU-profiled sweep in which, at 12–25 MB, most command buffers hold a single
dispatch, so the per-buffer table becomes a per-kernel table. Comparing a given
kernel's µs/call **alone in a buffer (no barrier)** against the same kernel
**post-barrier inside a large buffer**, while logging GPU frequency, separates
M1/M2 (saving localized at boundaries, frequency flat) from M3 (uniform
multiplicative shrink, frequency rises).

## Cross-generation risk, M4 Pro → M5 Max

- Toward transfer: the change moves *toward* Apple's shipped default. MLX picks
  stock caps by GPU architecture suffix — 20/40 phone, 40/40 base and Pro,
  50/50 Max, 50/50 Ultra (`device.cpp:574-597`) — so 50 MB is exactly what the
  ranked Max-class box would use without our override, and the 200 MB override
  is the deviation. The Δbarriers = −Δbuffers identity is source-level and
  hardware-independent.
- Against transfer: the M5 Max has roughly twice the bandwidth and core count,
  so each buffer executes faster at a fixed byte cap and firmware kick
  preparation has less time to hide — the seam-cost floor moves toward *larger*
  caps, plausibly shifting the optimum from ~25–50 MB toward ~50–100 MB. The
  concurrency counterweight also scales with GPU width: a wider machine leans
  harder on concurrent same-encoder dispatch groups to stay filled at batch 1,
  and every extra seam cuts one such window. Barrier cost, kick pipelining, and
  the power governor are all per-generation firmware. The review's point
  estimate for the M5 Max is −0.5% to −1.5% decode, i.e. a real but smaller
  effect than the M4 Pro −2.0%.
- Prefill exposure: prefill touches essentially all experts, so a 50 MB cap
  implies far more buffers there than in decode (order 430 versus 110). Per
  boundary costs that are free in decode could bite in that denser stream, and
  prefill carries its own 0.95 floor. The ranked receipt measures both axes, so
  this is checked rather than assumed.

## Post-receipt revision (M5 refuted the paragraph above)

The ranked M5 Max receipt came back **REFUTE**: renormalised `ns` 2.503448
versus control 2.544360, **−1.608%**, with prefill `S` **+2.193%** and decode
`T` **+1.316%**. Both halves of the M4 prediction are wrong — decode got slower
rather than faster, and prefill moved rather than staying flat. The paragraph
above is therefore an accurate account of an **M4 Pro** effect and an incorrect
account of the ranked machine. This section replaces its cross-generation
reasoning; the phase-2 diagnostics below also correct the command-buffer counts
that the earlier text quoted from a coarser instrumented run.

### Measured command-buffer accounting (`DARKBLOOM_GPU_PROFILE_SPLIT=0`)

Decode, 199-step probe, per steady step; every arm reported `dispatches=406.0`
and `0 divergences`, so the kernel set and order are identical at all caps:

| MB | cbs/step | wall ms | busy_sum | union | gap ms | gap% |
|---|---|---|---|---|---|---|
| 200 | 34.0 | 8.614 | 8.359 | 8.359 | 0.255 | 3.0 |
| 100 | 52.0 | 8.501 | 8.248 | 8.248 | 0.253 | 3.0 |
| 50 | 85.0 | 8.427 | 8.174 | 8.174 | 0.253 | 3.0 |
| 25 | 86.0 | 8.598 | 8.305 | 8.305 | 0.292 | 3.4 |
| 12 | 86.0 | 8.468 | 8.184 | 8.184 | 0.284 | 3.4 |

Prefill, by differencing total buffers with and against a 512-token prefill
(decode counts reproduced exactly across the two runs, which validates the
subtraction):

| MB | C_prefill | local prefill wall ms |
|---|---|---|
| 200 | 81 | 544.93 |
| 100 | 84 | 546.38 |
| 50 | 160 | 545.73 |
| 25 | 202 | 548.37 |
| 12 | 234 | 547.33 |

Three facts matter. First, `gpu_busy_sum == gpu_busy_union` at every cap, and
the host gap is flat at 0.253–0.255 ms across 34 → 85 buffers per step, so a
seam costs under ~0.04 µs of *host* time and the entire M4 effect sits inside
the GPU-busy union. Second, cbs/step **saturates at 86** for both 25 MB and
12 MB: below roughly 50 MB the byte cap stops binding on decode, so the
phase-1 reversal at 25/12 MB is not a buffer-count effect at all (the residual
candidates are the widened gap and allocator churn). Third, buffer boundaries
are a deterministic function of the op stream and its input/output byte counts,
neither of which depends on the host, so **these counts are also the M5
counts** — the only thing that changes across generations is what a boundary
costs.

### The decode/prefill inconsistency, and what resolves it

Applying the M5 deltas to the host-independent counts:

| axis | Δcbs (200 → 50) | M5 Δtime | per added cb |
|---|---|---|---|
| decode (`T`) | +51 | +56.3 µs | **+1.10 µs** |
| prefill (`S`) | +79 | +2147 µs | **+27.2 µs** |

These differ by ~25×, so **no fixed per-command-buffer cost can explain both**.
A uniform +27 µs seam would have added +1.4 ms to a 4.3 ms decode step, i.e. a
+32% decode regression; the measured decode regression is +1.3%. The
per-boundary cost is therefore not a constant — it scales with the amount of
work in the dispatches whose overlap the boundary destroys.

That single amendment makes every observation consistent. Treat a boundary as
two opposing terms: a **benefit** *B*, the in-encoder `memoryBarrier` drain that
is avoided and instead hidden behind the next kick's preparation; and a **cost**
*C*, the intra-encoder concurrency window that is lost because dispatches
separated by a commit can no longer run together. *B* is roughly fixed per
boundary and shrinks on a faster fabric (less to flush, quicker drain). *C* is
proportional to the size of the independent dispatches that were overlapping,
and it only exists when the GPU is wide enough that one dispatch does not
already saturate it.

- **M4 Pro decode**: −3.63 µs per added buffer (−185 µs for +51). Narrow GPU,
  batch-1 kernels are tiny, so *C* ≈ 0 and *B* dominates. This is the effect
  the original paragraph described, and it is real.
- **M4 Pro prefill**: flat, 0.6% spread with no trend. A 512-token GEMM already
  saturates a 14-core-class part, so there is no concurrency to lose (*C* ≈ 0)
  and, with large kernels, little relative barrier drain to win (*B* small
  relative to the work) — the two cancel.
- **M5 Max decode**: +1.10 µs per added buffer. Roughly twice the bandwidth
  makes *B* cheaper, and a wider machine leans harder on concurrent
  same-encoder groups even at batch 1, so *C* rises. The two nearly cancel and
  the residual **flips sign**. A near-tie flipping across generations is exactly
  the regime the guide warns about, and it is why an M4 decode win is not
  evidence for M5.
- **M5 Max prefill**: +27.2 µs per added buffer. Here *C* is at its maximum —
  512-token expert GEMMs are large, several are genuinely independent, and the
  M5 selects the `_nax` kernel family that an M4 Pro (Apple GPU generation 16)
  never reaches. Prefill has 2.4× the buffer growth of decode *and* the most
  expensive boundaries, which is why the prefill half of the score degrades
  twice as fast in percentage terms (+2.19% versus +1.32%).

### Consequences

1. **The 200 MB override in the base is not a deviation to be corrected.** The
   original argument that 50 MB is "what a Max-class box would pick anyway" is
   true about MLX's stock table and irrelevant to this score: the stock table
   is not tuned for a serial batch-1 decode plus a single 512-token prefill on
   a 21.6 GB resident MoE.
2. **The sign of the per-boundary residual is the thing to test, on the ranked
   machine, before spending a slot on anything that changes buffer counts.**
   M4 command-buffer *counts* transfer exactly; M4 command-buffer *timing* does
   not transfer even in sign.
3. **This is a positive signal for the dispatch-reduction family.** Fusion
   removes a dispatch *and* its in-encoder barrier without adding a seam, so it
   collects *B* while leaving *C* untouched — the opposite trade to the byte
   cap. The +27.2 µs/cb prefill sensitivity says the prefill dispatch stream on
   M5 is where ordering overhead is actually concentrated, which is where a
   gate/up fusion would land.
4. **Raising the cap above 200 MB is now a live one-token candidate, with a
   caveat.** If prefill really pays +27 µs per boundary on M5, removing
   boundaries should pay back symmetrically; 81 prefill buffers is already few
   enough that the headroom is limited (order 20–40 buffers), and the M4 sweep
   found 400 MB *worse* for decode by ~2.5%. The M4 decode result carries no
   weight after this receipt, but the prefill upside is small enough that it
   should be judged against cheaper candidates rather than assumed.

The cheapest decisive follow-up remains a same-session paired probe of one
alternative cap on the ranked machine rather than any further M4 sweeping; M4
has now told us everything it can, which is the buffer counts and nothing about
their price.

## External review of the inversion (frontier, `2e3268ac`)

An independent review with web/publication access was asked to rank causes for
the sign inversion. It was briefed with the earlier coarse counts (+92 decode,
+320 prefill buffers), so its per-buffer numbers read 0.6 µs and 6.7 µs where
the corrected counts give **+1.10 µs** and **+27.2 µs**. The correction makes
the discrepancy 25× rather than 11×, so its central conclusion — a constant
per-buffer cost is decisively rejected and the dominant seam cost must scale
with the work in flight at the boundary — survives a fortiori. What it added,
and what it got wrong against the corrected data:

**Confirmed hardware context.** 128 GB is only sold with the 40-core M5 Max, so
the ranked host is 40 cores at 614 GB/s against this box's 16–20 cores at
273 GB/s. M5 is `MTLGPUFamily.apple10` (`applegpu_g17s`); M4 is Apple9 —
consistent with this host reporting Apple GPU generation 16 and never selecting
`_nax`. Apple's M5 tech talks confirm larger GPU caches, second-generation
Dynamic Caching, and a **redesigned occupancy management unit** that throttles
occupancy on live-register residency and queue depth. No public numbers exist
for M5 barrier cost, command-buffer commit cost, SLC size, or GPU DVFS. The
bandwidth ratio 614/273 = 2.25× brackets the measured decode-step ratio
8.88/4.28 = 2.07×, i.e. decode is mostly bandwidth-bound on both hosts with a
somewhat larger non-bandwidth residue on M5.

**Sharpened split of the two terms.** Solving `net = C − B` per boundary on both
hosts puts M4 at B ≈ 1.9–2 µs with C ≈ 0.2–0.3 µs, and M5 at B ≈ 0.3–0.8 µs
with C ≈ 0.9–1.4 µs on decode. Two independently plausible gen-17 changes each
suffice on their own: 2.25× bandwidth drains an in-flight barrier
proportionally sooner (1.7 µs → ~0.75 µs if the stall scales with bandwidth),
and a 40-core wait-for-idle plus per-command firmware bookkeeping costs more
than a 16–20-core one. Asahi's AGX reverse-engineering describes each
firmware-level command as a Start / write-timestamp / **wait-for-idle** /
write-timestamp / Finish microsequence in a single serialized compute firmware
queue, which is the concrete shape of the seam's fixed component and grows with
core count.

**A cache-flush story is downgraded, not adopted.** Asahi reports the AGX fabric
is coherent with no cache-management instructions required, so "seams flush L2/
SLC" is not the mechanism; M5's larger caches would amplify it if it were real.

**Traffic-equivalence sanity check, recomputed.** 27.2 µs × 614 GB/s ≈ 16.7 MB
of traffic-equivalent per prefill seam, against ~4.2 MB for one 512-token bf16
activation set at hidden 4096 — so a few activation tensors' worth, or ~4.3% of
the 0.63 ms average prefill buffer at 50 MB. That is the right order for a
drain-and-re-ramp serialization of a 40-core machine on a large kernel, but it
is a weaker coincidence than the review's 4.1 MB figure suggested, and it should
not be quoted as a tight identification.

**One of its mechanisms is refuted by the corrected counts.** The review
attributed the M4 U-shape below 50 MB partly to submission-rate saturation, on
the premise that 12 MB approaches ~1 dispatch per buffer, i.e. ~400 buffers per
step. Measurement says decode buffers **saturate at 86** at both 25 MB and
12 MB — the byte cap simply stops binding, so there is no submission-rate
regime and no additional conversions to exhaust. The M4 reversal has to be
explained by the widened host gap (0.253 → 0.29 ms) or allocator behaviour, not
by buffer count.

**Its estimate for the fusion family.** With M5's exposed per-boundary stall at
~0.3–0.8 µs rather than M4's ~2 µs, removing a dispatch (barrier + launch +
ramp) should be worth ~0.5–1.5 µs on M5 decode; fusing ~100 of the 406
dispatches per step would be ~50–150 µs, i.e. **1.2–3.5% of `T`**. It also
bounds the available pool: active weights per decode step are ~1.5–2 GB, so the
bandwidth floor is 2.4–3.3 ms against `T` = 4.28 ms, leaving **~25–45% of
decode as non-bandwidth time**. Fusion deletes a boundary rather than
converting one, so it carries no sign-inversion risk analogous to the byte cap,
and the +27.2 µs/seam prefill sensitivity is direct evidence that M5 prefill
pays for exactly this class of cost. Caveat: gate/up fusion removes a launch, a
barrier and an intermediate but no weight traffic, so in decode it is an
overhead win only, and fused kernels raise register pressure into a gen-17
occupancy manager that now throttles on it.

**Follow-ups it recommends, in its order.** (a) free and local: an M4 prefill
A/B at 200 versus 50 MB with per-buffer union, to test the work-scaled seam
term independently of the decode sign flip — note the flat M4 prefill wall
already measured here is that test at n=1, and it came out null, which is itself
evidence that the M4 Pro has no concurrency to lose in prefill; (b) free: mine
the ranked corpus for receipts that predate the 200 MB pin and therefore ran
MLX's stock 50/50, for a free M5 dose-response point — heavily confounded with
whatever else those candidates changed, so at best suggestive; (c) one ranked
receipt: **raise the byte cap to 400–512 MB with the ops cap unchanged**,
predicted at roughly −0.4% `T` and −0.4 to −1% `S`, composite ≈ +0.4–0.8%, and
decision-relevant either way; (d) an ops-cap probe (e.g. ops = 5 at 200 MB)
places seams at byte-*light* boundaries and separates a placement-sensitive cost
from a fixed one. It warns against pushing the byte cap so high that the ops cap
becomes the only splitter: `needs_commit` is also MLX's only mid-evaluation
CPU→GPU kick, and ~3 buffers per step would risk exposing host encode time as
GPU idle. Keep 10 or more buffers per step; 400–512 MB stays interior.

That composite estimate survives the corrected score conversion. Using
`d ln score = −0.148620` per ms of `T` and `−0.0037134` per ms of `S` (derived in
`research/nezuko-mb50-receipt.md`), −0.4% of `T` is `−0.0171` ms = **+0.254%**
and −0.7% of `S` is `−0.686` ms = **+0.255%**, for a composite of about +0.51% —
inside the quoted +0.4–0.8% band. The corrected conversion does change the
attribution though: it underweights nothing on decode but roughly *doubles* the
score value of a prefill millisecond relative to a naive 0.25/0.75 split of
percent changes, because `S` also enters decode through the `S/128` seed term.

**Its policy recommendation, which I endorse.** Treat this host as directionally
unreliable for *overhead-class* changes — boundaries, barriers, synchronization,
submission — and gate any sub-2% overhead-class candidate on a ranked receipt.
It remains usable for bandwidth-class mechanisms, which scaled cleanly here
(2.07× measured against a 2.25× bandwidth ratio).

## Which mechanism this arm claims: encode overhead, not dispatch count

These are now known to be separable, so the paragraph has to name one.

**This arm claims submission/encode overhead — the *type* of boundary between
adjacent dispatches — and explicitly not dispatch count.** The dispatch count
was held fixed by construction: `DARKBLOOM_GPU_PROFILE` reports
`dispatches = 406.0` and `0 divergences` at 200, 100, 50, 25 and 12 MB. Exactly
the same 406 kernels run per step in every arm, in the same order, on the same
inputs. What the byte cap moves is where those 406 dispatches are cut into
command buffers: 34 buffers per step at 200 MB, 85 at 50 MB. A boundary that was
an in-encoder `memoryBarrier` becomes a buffer seam, and nothing else changes.

The other mechanism — the marginal cost of *adding* a chained dispatch — is
tanjiro's, and his `n = 0` / `n = 400` injection pair measures it directly at
`c_M5 = 1.980 ± 0.044 µs` per chained dispatch, linear with zero slack and no
sign of saturation on the ranked M5. That result is orthogonal to this one:

- his treatment changes 406 → 806 dispatches at a fixed boundary policy;
- mine changes 34 → 85 boundaries at a fixed 406 dispatches.

Neither explains the other, and neither can be used as evidence for the other.
In particular, `c_M5 = 1.980 µs` per dispatch is not the per-buffer figure: the
per-buffer figures implied by this receipt are `+1.10 µs` (decode) and
`+27.2 µs` (prefill), and the 25× spread between them is itself the argument
that a boundary is not a fixed-cost object.

The earlier M4 knee at 1,209 dispatches was a `max_ops_per_buffer` host-encode
crossover (`device.cpp:576-593`) — a third, distinct mechanism, and one this arm
never touches because the ops cap stayed at 200 in every arm. tanjiro's
injection pair falsified the `H_cpu` knee-at-1200 reading at 34.8 σ, and the
`H_gpu` knee-at-461 variant died with it.

Practical consequence for the fusion family: D-FUSE-GATESP reduces dispatch
count, so it collects against tanjiro's linear, unsaturated `c_M5`, and it
deletes a boundary rather than converting one, so it also avoids the cost C term
identified above. Those are two independent reasons to expect it to win, and
they should be attributed separately when it is measured.
