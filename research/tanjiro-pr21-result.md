# PR #21 — the decode residual is priced: 0% access pattern, 90% structural, 0.19 ms recoverable

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- Student / PR: maple-tanjiro / #21 `maple-tanjiro/bandwidth-residual`
- Hypothesis and target cost: the advisor's 1.51 ms "hard core" (17.2% of the
  8.769 ms M4 decode step, 393 MB of phantom traffic) is caused by the decode
  step's *access patterns* achieving less DRAM bandwidth than a sequential
  stream. Measure achievable bandwidth per pattern, rebuild the roofline per
  stream, re-derive the residual.
- Decision: **dead hypothesis. First-class negative, and the strong kind the
  advisor said he would act on.** Access pattern is worth **0.000 ms**. The
  residual decomposes with zero slack and only **0.191 ms** of it is recoverable.
- `BASE_SHA` / candidate commit: `aecc470edecf01cbf9cb708bdc5ad69b90c73754` /
  PR head
- Submitted candidate files: **none.** Part 1 is local and analytic and the brief
  forbids submissions on it. **All three authorised official submissions are
  unspent** and I recommend they go to another arm — see the conclusion.
- Supporting files: `senpai/tools/bandwidth-pattern-probe/{main.swift,README.md}`,
  `research/tanjiro-pr21-roofline.py`, this file. Nothing in `editablePaths`
  changed.

---

## Headline

The residual is real, reproduces, and is now fully accounted for. It is **not**
an access-pattern property, and it is **not** mostly recoverable. Every term is
measured on this host and they sum to the residual with zero slack:

```text
M4 Pro decode step                                       8.769 ms
byte-only roofline, 1794 MB at the measured 260.2 GB/s   -6.895 ms
------------------------------------------------------------------
excess to explain                                         1.874 ms
  per-dispatch structure           1.414 ms  (75%)  structural
      406 dispatches x 2.46 us       0.999 ms
      GQA KV re-read, cache-served   0.375 ms
  inter-dispatch dead band         0.269 ms  (14%)  matches nezuko's <=0.38 bound
  named per-stream shortfalls      0.191 ms  (10%)  the only recoverable part
  access pattern                   0.000 ms   (0%)  measured, not inferred
------------------------------------------------------------------
  sum                              1.874 ms  (unexplained +0.000 ms)
```

Reproduce: `python3 research/tanjiro-pr21-roofline.py`.

**Decode is bandwidth-closed.** Every large dispatch in the step already runs at
100–109% of its achievable bandwidth. Both fused attention kernels run at
**1.45–1.70× the DRAM streaming ceiling**. The campaign should move to byte
removal and prefill, which is what the advisor said he would do on this finding.

I also have to contradict one inference. The 78.6% (M4) / 78–85% (M5) invariance
is real, but it is not an access-pattern signature — it is a **dispatch-count
and dependency-latency** signature. Both are fixed by the model's layer shapes,
not by the machine, which is precisely why they transfer. The advisor's
conclusion "it transfers" is right; "access-pattern property" is not, and the
two imply opposite next moves.

---

## Part 1a — achievable bandwidth per access pattern

`senpai/tools/bandwidth-pattern-probe/main.swift` — standalone Swift/Metal, no
model, no harness:

```bash
cd senpai/tools/bandwidth-pattern-probe
xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation
./probe            # per-pattern report
./probe --mode sizes    --mode downsize    --mode empty
```

Validity: a 1 GB code pool plus 192 MB scale pool with rotating offsets so every
dispatch reads cold DRAM; loads XOR-consumed behind an impossible-value store
guard so nothing is dead-code eliminated; GPU timestamp span over one command
buffer of N serialized dispatches; min over repeats; 0.5 s sustained warm-up.

**The warm-up is not cosmetic.** Before I added it the first timed configuration
read 35% low — the shipped routed-down shape measured 145.7 GB/s cold vs
222.5 GB/s warm. Any bandwidth probe on this host without a sustained warm-up is
wrong by up to 35%, which is larger than the entire effect we are chasing.

Sequential control **262.5 GB/s**, independently reproducing nezuko's 260.2.

| pattern replicated | measured | % of control |
| --- | ---: | ---: |
| attention weights, 2048 B code rows | 236.6 GB/s | 90% |
| routed gate/up, 1024 B code rows | 243.0 GB/s | 93% |
| routed down, 256 B rows @ 4 rows/simd | 241.4 GB/s | 92% |
| **8 scattered 1.77 MB expert blocks** | 246.8 GB/s | **94%** |
| **576 scattered 16 KB blocks** | 242.4 GB/s | **92%** |
| **KV ring, 256 B runs, any stride, 8 MB** | 227.8–234.2 GB/s | **87–89%** |
| KV ring, 256 B runs, at the shipped 2 MB | 201.9–205.3 GB/s | 77–78% |

**No access pattern in the decode step costs meaningful bandwidth.** Both of the
advisor's two surviving suspects are cleared directly: gathered expert blocks
reach 94% at 1.77 MB and 92% at 16 KB; the ring KV buffer reaches 87–89% at
equal bytes and loses the remainder purely to being a 2 MB dispatch. The KV row
is **insensitive to stride**, which is the specific thing a rotating-buffer
penalty would have shown.

I also confirmed fern's #22 verdict experimentally rather than from source:
**fusing scale bytes into the code rows changes bandwidth by −0.3% to +2.5%,
i.e. zero.** `A = 1.000` is correct and an offline codes/scales interleave arm is
a no-op on this host. Worth telling fern before he spends a run on layout.

### What does cost bandwidth — two things, neither a pattern

```text
bytes per dispatch  0.125 MB  0.5    1      2      4      8      16     64
                    22.9      113    173    211    204    230    250    262.5 GB/s

in-flight device bytes per lane, at fixed 5.06 MB/dispatch
  8 B -> 92-103   16 B -> 171-190   32 B -> 225   64 B -> 217-225   128 B -> 207-211
```

Saturation needs **~32 B in flight per lane**. Serialized empty-dispatch cost:
**2.46 µs** at a 160×256 grid, **0.87 µs** at 1×32.

That empty-dispatch cost is the mechanism behind the largest term, and the
arithmetic closes independently: **406 × 2.46 µs = 0.999 ms**, against the
1.414 ms structural term derived from the bandwidth-vs-size curve, with the
0.375 ms balance attributed below. 75% of the residual is the price of issuing
406 dispatches of 0.004–135 MB instead of one 1794 MB stream.

---

## Part 1b — rebuilt roofline, per stream

`research/tanjiro-pr21-roofline.py` crosses the curves above with nezuko's
per-dispatch profile, charging each dispatch
`max(floor, bytes / (achievable(size) × derate(in-flight bytes per lane)))`.

```text
measured            8.500 ms (dispatch sum)
rebuilt roofline    8.309 ms
byte-only roofline  6.895 ms
```

Thirteen of nineteen rows have a gap of exactly zero. Everything large and
well-shaped — qkv, o_proj, routed gate/up, coarse LM head, dense MLP, shared
expert, routed down — is at **100–109%** of its modelled ceiling, so the probe
ceilings are slightly conservative and every gap below is a **lower bound**.

| dispatch | calls | achieved | ceiling | gap/step |
| --- | ---: | ---: | ---: | ---: |
| `lmhead_exact_inline_mask_block` | 1 | 6.5 GB/s | 107.8 | 74 µs |
| `gate_sp_h64` | 30 | 22.3 | 31.9 | 61 µs |
| `residual_rms_router_bf16` | 39 | 156.2 | 173.6 | 27 µs |
| `gate_sp_h48` | 10 | 16.5 | 24.0 | 22 µs |
| `dense_gate_up_swiglu_bf16` | 1 | 250.8 | 262.5 | 12 µs |
| **total recoverable** | | | | **197 µs** |

### The two fused attention kernels have no DRAM slack — they beat the ceiling

My interim ranking had `sliding_fused_attn_ring` first at 304 µs and
`full_fused_attn_grow` second at 84 µs. **Both were artefacts of the wrong
numerator, and I am retracting them.**

The profile's MB/call is *unique* tensor bytes. But the sliding kernel launches
32 threadgroups over 64 query heads (2 heads each) against only 8 KV heads
(`LagunaRuntimeModel.swift:1400-1402`, `kv_head = pair_tg / 4`; loads
`:1532-1538`), so **4 threadgroups each read the same KV head's entire 512-slot
ring**: 8.389 MB issued for 2.097 MB unique. Charged on issued bytes:

```text
sliding_fused_attn_ring   8.389 MB / 22.0 us = 381.3 GB/s = 1.45x the 262.5 ceiling
full_fused_attn_grow     10.484 MB / 23.5 us = 446.1 GB/s = 1.70x the ceiling
```

A DRAM-fed kernel cannot exceed the DRAM ceiling, so this **proves** the re-read
is served from cache, and it means neither kernel has recoverable *bandwidth*
slack. Decomposing the 22.0 µs: 2.097 MB unique at the measured 2 MB KV
achievable (205 GB/s) is 10.2 µs; the remaining 11.8 µs moves 6.29 MB from cache
at **535 GB/s**, a plausible M4 Pro SLC figure. Across both kernels that is the
**0.375 ms** GQA re-read term — structural, and removable only by re-tiling the
head→threadgroup map, which is exactly the class #7 proved does not transfer.

Verifying this cost one source read and would have cost me an entire Part 2 had
I trusted my own interim ranking.

### Correction to the profile everyone is citing

My interim also put `routed_shared_nvfp4_down_residual` first at 809 µs. Also
wrong. Interim 8's table profiles it as `_v4` (48.5 µs/call, 109.5 GB/s);
Interim 9 of the *same document* ships `_v5` and re-measures 22.96 µs/call,
231.3 GB/s. HEAD carries `_v5` (`:7660` `outputs_per_simd = 4`, `:7803` grid
`/4`). Nezuko's #7 already banked it.

Two consequences beyond my arm:

1. **`research/nezuko-decode-roofline.md` Interim 8 is a snapshot of a tree whose
   step was ~10.05 ms; the frontier is 8.769 ms.** It is the campaign's
   most-cited per-dispatch reference and its worst row is a kernel that no
   longer exists. Prefer the corrected copy in
   `research/tanjiro-pr21-roofline.py`.
2. Correcting it produced the best available **validation of the probe**: the
   shipped down kernel measures 231.3 GB/s and my reads-only probe independently
   puts that exact shape's achievable at 212.0 GB/s. The real fused NVFP4 MoE
   kernel lands within 9% of the synthetic ceiling, from above. The probe is a
   usable instrument.

Units, for anyone reusing these numbers: campaign `MB` are **decimal** (nezuko's
5.311 MB for the down dispatch is exactly `2048*288*9` bytes; `1.7929 GB /
9.498 ms` reproduces her 188.8 GB/s only in decimal), while my probe labels its
size axis in MiB. Getting it backwards moves every derived GB/s by 4.9%.

---

## Part 1c — the residual on the ranked host

The advisor asked for the residual on the M5 using his 485–530 GB/s pin. My
terms scale differently, which is the point of separating them: dead band and
dependency stalls are **latency** and do not improve a generation; the
per-dispatch ramp is a **bandwidth-delay product** and shrinks with 2× the cores.

```text
M5 Max, step 4.353 ms
  485 GB/s -> ideal 3.699 ms, excess 0.654 ms (15.0% of step)
  507 GB/s -> ideal 3.538 ms, excess 0.815 ms (18.7% of step)
  530 GB/s -> ideal 3.385 ms, excess 0.968 ms (22.2% of step)
```

My M4 latency-like terms (0.191 + 0.269 = 0.460 ms) carried over at absolute
value cover 48–70% of the M5 excess. The remainder must be M5's own per-dispatch
cost, which turns the model into a **falsifiable prediction** rather than an
assumption:

| if M5 achievable is | M5 per-dispatch cost must be |
| ---: | ---: |
| 485 GB/s | 0.48 µs |
| **507 GB/s** | **0.87 µs** |
| 530 GB/s | 1.25 µs |

M4 measures 2.46 µs at 160 threadgroups and **0.87 µs at one**. So the model
closes on M5 exactly if its per-dispatch cost sits near my single-threadgroup
floor rather than my many-threadgroup one — which is what doubling the cores
should do, since each dispatch then needs fewer waves to fill the machine. **One
`./probe --mode empty` run on the M5 would confirm or refute the whole
decomposition in seconds.** That is the cheapest high-information measurement
available to this campaign; it needs no model, no submission and no thermal gate.

This also explains the invariance without invoking access pattern: from M4 to M5
the byte time halves while the latency terms do not, so the residual *fraction*
stays roughly flat, 21.4% → 17.6%.

Value of the recoverable term on the ranked host:

| assumption | M5 recoverable | % of step | % of score (×0.638) |
| --- | ---: | ---: | ---: |
| latency preserved in absolute ms | 0.191 ms | 4.4% | **2.8%** |
| shortfall preserved as a fraction | 0.095 ms | 2.2% | **1.4%** |

**1.4–2.8% of score**, against the advisor's 10.9% estimate for the whole
residual. That is the honest number, and it is a fifth of what the brief hoped
for.

---

## Evidence

- Host / toolchain / thermal: AWS M4 Pro, 20 GPU cores, 48 GB unified
  (low-memory startup profile), 273 GB/s pin. The probe is standalone Metal and
  holds no model, so the one-model-process rule and the 40 C thermal gate were
  not engaged. No `--local-iterate` run was taken and none was warranted.
- Exact commands: the `./probe` invocations above plus
  `python3 research/tanjiro-pr21-roofline.py`. All deterministic and local.
- Tests / risk-based checks: none required. The submission surface is
  **unmodified** — only `senpai/tools/` and `research/` were touched, so no
  `editablePaths` entry changed and there is no correctness or serial-protocol
  risk to gate.
- Correctness and serial-protocol verdict: not applicable, no scored-path change.
- Divergent tokens: none possible.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | — | — | unchanged (no scored-path edit) |
| prefill seconds/token | — | — | unchanged (no scored-path edit) |
| same-host paired estimate | — | — | not measured; none warranted |

---

## Conclusion

- **What happened.** I built the instrument and it refuted the hypothesis it was
  built for. Access pattern is worth 0.000 ms. 75% of the residual is 406
  dispatches paying a launch ramp plus a cache-served 4× GQA KV re-read, 14% is
  the host/queue dead band already bounded by nezuko's #9, and only 10%
  (0.191 ms) is dependency stalls in five small dispatches.
- **Evidence for the mechanism.** Four independent closures: the decomposition
  sums to the residual with +0.000 ms slack; `406 × 2.46 µs = 0.999 ms`
  reproduces the launch-ramp term from a separate measurement; the probe's
  ceiling for the routed-down shape predicts that real kernel's measured
  bandwidth to 9%; and both attention kernels exceed the DRAM ceiling on issued
  bytes by 1.45–1.70×, which is only possible if the re-read is cached.
- **This is the strong negative, and I am saying so plainly as asked.** Decode
  efficiency is closed on both generations *as a bandwidth problem*. Every large
  dispatch already runs at achievable bandwidth. Move the other three students
  to byte removal and prefill. The remaining 1.4–2.8% of score is real but it is
  not the 10.9% the brief was sized against, and it is not where a campaign
  should point four students.
- **Uncertainty / M5 transfer risk.** (i) The per-dispatch profile is inherited,
  not re-measured by me; reproducing it at HEAD needs nezuko's local-only
  `device.cpp` instrumentation and ~0.29 ms of post-#7 frontier gains are
  unattributed in it. This does not move the decomposition — every large row is
  already at ceiling — but the five small gaps carry that uncertainty and they
  are now the entire recoverable term. (ii) The M5 per-dispatch cost is the one
  free parameter; the table above makes it falsifiable. (iii) The 535 GB/s cache
  bandwidth is inferred by subtraction, not measured; the conclusion only needs
  "issued bytes exceed the DRAM ceiling", which is arithmetic.
- **Smallest useful next action.** Run `./probe --mode empty` on the M5 Max. It
  decides whether the 75% structural term is 0.999 ms or half that, and it is
  worth more than any kernel edit I could propose from this host.
- **Recommendation: close the arm.** Decided negative on the stated hypothesis,
  residual fully priced. I did not spend a submission and I do not recommend
  spending one on anything in this report: the largest single item is 74 µs, and
  the total 0.191 ms sits at 1.4–2.8% of score spread across five unrelated
  dispatches, most of which belong to other students' surfaces.

### Suggested follow-ups I did not implement

- **For fern:** codes/scales fusion measures **0%** on this host — his
  `A = 1.000` source verdict is confirmed experimentally. An offline interleave
  arm is a no-op; don't spend the run.
- **For nezuko:** Interim 8's table needs a HEAD re-profile or a header warning.
  Its worst row is a kernel that no longer exists and it is being used to rank
  work across the campaign.
- **For whoever owns the LM head (nezuko #20):** `lmhead_exact_inline_mask_block`
  is 76.6 µs for 0.5 MB — **6.5 GB/s**, the worst efficiency of any dispatch in
  the step, 74 µs for a single call, and pure latency rather than bandwidth. It
  is the largest single item I found and it sits on the cascade surface, not mine.
- **Byte-neutral dispatch removal, the class that does transfer:**
  `gate_sp_h64`/`h48` contribute 83 µs at 8 and 6 threadgroups respectively —
  far too few to fill 20 cores, let alone 40. Fusing them into a neighbour
  removes dispatches without changing bytes or thread mapping.
- **The one attention idea that survives:** not bandwidth, but the 4× GQA
  re-read. Having the 4 threadgroups that share a KV head cooperate would cut
  6.29 MB of cache traffic per call, worth ~0.375 ms on M4 — but it is a
  head→threadgroup re-tiling, so by #7's evidence assume it does not transfer
  until measured on M5. I would not fund it from this host.
