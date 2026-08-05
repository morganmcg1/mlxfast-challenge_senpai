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
