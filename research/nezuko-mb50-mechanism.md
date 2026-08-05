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
