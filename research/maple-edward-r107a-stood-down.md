# R107-A — terminal note: verdict `N-T2C-STOOD-DOWN` (PR #629)

Host: Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, macOS 26.5.2,
`applegpu_g16s` (gen 16), low-memory startup profile. All quantities below are
**[M4-WALL]** at epoch **`base_sha` `3241e5e5`** unless tagged otherwise
(rule 105.6). Full evidence: `research/maple-edward-r107a-routed-packing.md`.

## Verdict

`N-T2C-STOOD-DOWN`. Both stages of R107-A are terminal and neither is worth
carrying into the integrated tree.

| stage | site | verdict | basis |
|---|---|---|---|
| Stage B | T2c routed MoE gate+up threadgroup packing | **`N-SITE1`** | measured here: 216 slots / 54,000 teacher-forced steps, S ∈ {2,4,8,16} |
| Stage A | T0b(a) QKV lane-major width flip ("L3") | **`N-L3`** | measured here at K = 12, agreeing with fern's `N-PACK` (#625) |
| both | — | **`N-T2C-STOOD-DOWN`** | superseded by tanjiro's R107-G regime census (#648) |

Stood down on the advisor's instruction at 2026-08-10T15:51:32Z
(PR #629 comment `5242627442`). No run was started after that instruction; the
one block in flight was cancelled at the next slot boundary (§4b of the main
report). **Zero receipts consumed by this assignment.**

## Why it is dead

The advisor's comment cites maple-tanjiro's R107-G decode-family regime census
(PR #648, merged as `705484b9`,
`research/maple-tanjiro-r107g-decode-family-regime-census.md`). I have **not**
fetched or independently reviewed that file — this branch is based on
`3241e5e5`/`4e9a8e16` and the merge post-dates it — so the figures below are
quoted at second hand from the advisor's comment and are attributed to him, not
verified by me:

- T2c is his **family D**; exposed ALU measured at **1.10 % of the dispatch**;
- families A (T3b `oproj` h64), B (T2d down+residual), C (T0b(a) qkv h64) and
  D (T2c) are **all** byte-bound at **85–91 % of measured DRAM ceiling**, with
  **0.71 bars of total non-byte slack** at T2c;
- clearing the 0.4 % draw bar on the *instruction* axis in T2c would require
  removing **466 instructions per thread against a base load of 128** — 3.6× the
  entire arithmetic content of the kernel;
- headline verdict **`N-BYTES-EVERYWHERE`**, with the byte axis itself pricing at
  **15.10 MiB/step per 0.4 %** = 4.5–7.7 % of each family's own traffic.

## Do my T2c numbers agree with his 1.10 % exposed-ALU figure?

Yes, on every point where the two instruments overlap — and the arithmetic that
follows from combining his figure with my measured family cost is the single most
useful thing on this page.

**1. His figure, priced through my family cost, is already sub-bar.** The T2c
routed gate+up family costs **1497.7 M4 µs/step** at this epoch (§6 of the main
report). If exposed ALU is 1.10 % of that dispatch, the *entire* arithmetic
content exposed to the critical path is **≈16.5 M4 µs/step**. Converting at rule
105 (`Δ%cs = Δ_M4 × k × 0.015228`, k = α = 0.4369):

```
16.5 M4 µs/step × 0.4369 × 0.015228 %/µs  =  0.110 %cs  =  0.27 draw bars
```

So even a hypothetical instruction-axis lever that removed **100 % of the exposed
ALU at T2c** would land at roughly a quarter of the 0.4 % bar. That is
independent of any packing mechanism and it is the cleanest statement of why the
family is closed. It also sits comfortably inside his 0.71 bars of *total*
non-byte slack, as it must — ALU is only one component of the non-byte term — so
the two accounts are consistent rather than merely compatible.

**2. My packing-specific ceiling is ~7× tighter still, and it is measured.** The
routed site issues 2,048 threadgroups per dispatch × 39 dispatches =
**79,872 TG/step** at the shipped S = 2. My paired `base → sg8` contrast bounds
the saving from removing 59,904 of them at **≤ 2.49 M4 µs/step** (95 %), giving a
reusable Apple-Silicon threadgroup-launch cost bound of **≤ 0.042 ns/TG**. The
largest saving available at *any* S (S = 16 removes 69,888 TG/step) is therefore

```
69,888 × 0.042 ns  =  2.9 M4 µs/step  =  0.020 %cs  =  0.19 % of family cost
```

i.e. **under 5 % of the 60.1 M4 µs/step that the 0.4 % bar requires**. The
occupancy/launch sub-lever of the instruction axis holds about 7 % of the ALU
budget in (1) and about 3 % of his non-byte slack. Nothing there.

**3. My instrument could not have resolved his budget even in principle, and
that is worth recording.** My 95 % exclusion band at the best candidate dose is
`|base → sg4| ≤ 18.4 M4 µs/step`, which is **1.23 % of the 1497.7 µs/step family
cost**. His entire exposed-ALU budget is 1.10 % of the dispatch — *smaller than
my own detection floor*. A full-decode in-situ paired palindrome at this site is
structurally incapable of certifying or refuting an effect of that size, however
many repetitions it runs; only a residency-defeated dose ladder with an exposed-ALU
decomposition can. My flat S-curve is therefore consistent with his census by
construction and adds no evidence against it. Stated plainly, as the advisor
asked: **this arm's S-curve was showing 0.02–0.2 % effects against a 0.4 % bar,
and it should have said so earlier and louder.**

**4. Where the two framings differ, I cannot adjudicate it.** The Stage-B
assignment described this kernel as *issue-bound* (114.2 GB/s = 42.9 % of M4 Pro
spec peak); tanjiro reports the family as *byte-bound at 85–91 % of measured DRAM
ceiling*. Both can be true at once if the attainable GEMV bandwidth on this
dispatch shape is roughly half of spec peak, which is the ordinary situation for
a gather-GEMV with 4-bit codes and per-32 scales. I have no bandwidth-ceiling
measurement of my own, so I record the difference rather than resolving it, and
note that my results are insensitive to which framing is right: the packing knob
moves **zero bytes** (identical row set, identical operand fetches, identical
qdot order — §2.2), so it is a pure non-byte-axis intervention and it measured
null-to-negative under either reading.

**5. Nothing in my data disagrees with him.** The one signed effect I found is a
*regression*: S = 16 costs **+63.49 M4 µs/step, 18/18 positive,
CI95 [+55.66, +71.32] = +0.422 %cs**, which is a tail-starvation penalty
(12.8 TG/core on the ranked M5) exactly as rule 67 / #528 predict, and it is
prefill-flat (§4b: `base → sg16` prefill +0.138 % [−0.144, +0.420], below the
+0.771 % the same arm costs on decode). Corroboration from the other direction:
maple-alphonse's kernel-local arm on the same site with residency properly
defeated (rule 98.9, `FERN_DEFEAT_SLOTS=64`) reads **−0.038 %
[−0.104, +0.028]**, the same null. His *resident* rung read +1.224 %, the ~30×
inflation rule 98.9 exists to catch.

## Correctness

Every timed slot in this assignment compared greedy token IDs against the golden
fixture on every step (`Sources/MLXFastCore/Golden.swift:387`, `:535`) and the
ABBA harness asserted a single token-stream checksum across arms. Stage 1: 216
slots / 54,000 steps, 0 divergences, one checksum. Stage A: 105 slots, 0
divergences. §4b prefill: 24 slots, 0 divergences, one checksum (`3656350139`).
Against a deliberate store-row fault control that fired **96/96**. Per rule
105.15 this is a *token-identity* claim on this fixture and this host, not a
numeric-distance claim: `max_abs_diff` is a hard-coded literal `0` at every emit
site and `golden_hash` is the SHA-256 of the loaded fixture, so neither is cited
anywhere in this assignment's reporting. Rule 75 passed on every block
(digests in §9.1 of the main report).

## State of the branch

`Sources/MLXFastModel/LagunaRuntimeModel.swift` is the only submitted file
touched: two **default-inert** selectors, `DARKBLOOM_ROUTED_GATEUP_SG` and
`DARKBLOOM_QKV_LM_SG`, +3,655 B net (45 % of the 8 KiB per-review growth cap;
file at 387,900 / 524,288 B). With neither variable set, the dispatch, the
pipeline name and the emitted Metal source are byte-identical to `4e9a8e16`, so
default timing is the base's. They are cheap to delete and I have no objection to
deleting them; the only argument for keeping them is that `sg16` is a calibrated
+0.422 %`cs` **negative control** of bar size on the scored decode path, which is
useful for proving that a new instrument on this host has sign discipline and
bar-scale resolution (nezuko's #657, for example).

## Disposition

No further work on T2c or on the QKV lane-major width flip. Moving to **PR #665**
(T3a sliding fused-attention instruction axis) as instructed.
