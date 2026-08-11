# R109 Arm G — b5: four-arm attribution of the norm-fused `gate_sp` delta

Author: maple-nezuko · PR #682 · assignment `maple-r109-b-router-hybrid-selector`
rev `r109-b-rev2` · research base `1a6761bf` (`git diff 1a6761bf..b0b6174 -- Sources
Vendor benchmark.json Package.swift` is empty, so no re-baseline).

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2, `applegpu_g16s`. Steady
decode is 100 % host-independent (no NAX, no `#available` gate), so M4 decode is
a structurally valid instrument for an M5-scored arm; only the throughput
scaling factor τ is at issue.

## 1. Why b5 exists

b4 (job `2701a36a`, 6 replicates × 3 arms, all bit-exact) returned a result that
was the wrong shape for the assignment's hypothesis:

| contrast | Δ µs/step | reading |
|---|---:|---|
| A − C | **−51.73** | deleting all 41 `rmsbfloat16` dispatches is **slower** |
| A − W | **+44.73** | doing *strictly more* work is **faster** |
| C − W | +96.46 | |

`A` is the shipped control; `C` makes the fused kernel the sole producer of
`normalized`; `W` restates the RMS reduction inside `gate_sp` but *keeps* the
standalone pre-norm dispatch and its (now unread by `gate_sp`) output.

`W` differs from `A` in two ways at once, and b4 could not separate them:

1. the `rmsbfloat16 → gate_sp` RAW dependency edge is gone (`gate_sp` reads the
   residual and re-derives the norm itself); and
2. the gate kernel's threadgroup shape changed from the shipped `ns2r4`
   (8 threadgroups × 64 threads) to `ns8r1` (8 threadgroups × 256 threads).

(2) is a **threadgroup-geometry** change. Programme law (PR #7: +7.32 % on M4,
≈0 % on M5) says geometry has τ ≈ 0, so a delta that is mostly (2) is an M4
mirage. b5 exists to price (1) and (2) separately.

## 2. Design

Arms, all bit-exact against each other (`decode_probe.py` reports "0
divergences" on the 256-token teacher-forced golden):

| arm | knob | pre-norm dispatch | `gate_sp` reads | `gate_sp` geometry | stores `normalized` |
|---|---|---|---|---|---|
| A | `0` | yes | `normalized` | ns2r4 (shipped) | n/a (AOT) |
| S | `4` | yes | `normalized` | **ns8r1** | no |
| W | `2` | yes | **residual** | ns8r1 | yes (unread) |
| N | `3` | yes | **residual** | ns8r1 | no |
| C | `1` | **no** | residual | ns8r1 | yes (feeds QKV) |

Decisive contrasts:

- **S − A = pure threadgroup geometry** (identical dependency graph, identical
  arithmetic, only the shape moves).
- **N − S = pure dependency-edge removal** (identical geometry; the only change
  is that `gate_sp` stops consuming the pre-norm's output).
- **N − W = cost of the unread 4 KiB `normalized` store.**
- **N − A = the total delta a shippable arm N would show on M4.**

Order (25 slots, 200 steps each, position 0 discarded as warm-up):
`A | A S W N | S W N A | W N A S | N A S W | N W S A | A N W S`.
Every arm appears in every position class, so thermal drift and slot-index
effects cancel. GPU temperature was logged per slot with `macmon`.

Statistics: `research/nezuko_armg_stats.py` — per-slot median over 199 steps,
then median-of-medians per arm, with a 20 000-draw bootstrap over slots.

## 3. Results

25/25 slots completed, `rc=0`, and every slot reported
`teacher-forced greedy tokens: 0 divergences (all match)` — all four arms are
bit-exact against the shipped path, so nothing below is an accuracy trade.
Raw data `research/armg-runs/b5/`, stats `research/armg-runs/b5/stats.json`.

| arm | what it does | median-of-medians µs/step | slot spread |
|---|---|---|---|
| A | shipped control (`rmsbfloat16` + `gate_sp` ns2r4, 8 TG × 64 thr) | 8256.19 | 0.229% |
| S | shipped gate math at ns8r1 (8 TG × 256 thr), still reads `normalized` | 8212.96 | 0.406% |
| W | RMS restated in `gate_sp` from the residual, pre-norm kept, `normalized` stored but unread | 8209.85 | 0.176% |
| N | RMS restated in `gate_sp` from the residual, pre-norm kept, no `normalized` output | 8204.23 | 0.536% |

Contrasts (`delta = median(first) − median(second)`, so **positive means the
second arm is faster**; CI95 from 20 000 bootstrap draws over the 6 slots per
arm; `%score` at τ=1 via 0.0070 %/M4 wall µs):

| contrast | Δ µs/step | CI95 | excludes 0 | %score | µs/layer |
|---|---|---|---|---|---|
| A−S | **+43.23** | [+37.06, +58.00] | **yes** | +0.394% | +1.081 |
| A−W | **+46.33** | [+40.15, +55.08] | **yes** | +0.423% | +1.158 |
| A−N | **+51.96** | [+22.13, +59.94] | **yes** | +0.475% | +1.299 |
| S−W | +3.10 | [−10.46, +10.52] | no | +0.028% | +0.078 |
| N−S | −8.73 | [−14.19, +22.77] | no | −0.080% | −0.218 |
| N−W | −5.62 | [−11.00, +25.17] | no | −0.051% | −0.141 |

Read together with b4 (`research/nezuko_armg_stage1c.md`), where the mode-1 arm
C — the only arm that actually deletes the pre-norm dispatch — measured
**A−C = −51.73 µs/step, i.e. 51.7 µs/step _slower_ than the shipped control.**

### 3.1 A self-inflicted confound, recorded rather than hidden

Slots p17-N (8243.2) and p22-N (8227.8) are the two slowest N slots and are the
reason `N−S` fails significance. Both ran while a helper process of mine was
doing `git add`/`git commit` over this same `research/armg-runs/b5/` directory,
and both show an anomalously *wide* per-step distribution rather than a shifted
one (p17-N has the **lowest** p10 of any N slot, 8151.5 µs, together with a p90
of 8321.1 µs). That is the signature of host I/O contention stealing whole
steps, not of a slower kernel.

I am **not** dropping those slots. Post-hoc exclusion of the two slots that
happen to sit against my preferred conclusion is exactly the move that
manufactures a false positive, and the interim read of this same block at 17/25
slots did report `N−S = −11.92 µs [−18.48, −8.52]`, "significant". The honest
statement is that `N−S` is an **upper bound of ~14 µs/step**, and that a clean
answer needs a dedicated block with no concurrent host work.

## 4. Reading

**The pre-norm elimination that Arm G was commissioned to test is refuted.**
Mode C, the sole configuration in which the 41 `rmsbfloat16` dispatches (142.3
µs/step of pool) actually disappear, is 51.7 µs/step *slower*. The mechanism is
visible in the arm design: once the fused `gate_sp` becomes the sole producer of
`normalized`, its 8 latency-bound threadgroups sit in front of the 5120-threadgroup
QKV matvec, and the serialisation costs more than the dispatch saves.

**All of the reproducible win is threadgroup geometry, none of it is the
fusion.** A−S = +43.23 µs is the shipped gate math, unchanged, at 256 threads
per threadgroup instead of 64; it still consumes `normalized` from the stock
pre-norm, so it removes no dispatch and no dependency edge. A−N = +51.96 µs is
the full candidate. Geometry therefore accounts for **43.23 / 51.96 = 83%** of
the effect, and the entire fusion story — restating the reduction, dropping the
`rms → gate_sp` edge, deleting the unread store — accounts for the remaining
8.73 µs, which does not clear zero.

Per PR #7 (+7.32% M4 → ~0% M5) threadgroup geometry carries τ ≈ 0, so the
83% share is presumed non-transferable and **must not be headlined**.

**Barrier-law refinement (the reusable part).** `N-INDS-DEPENDENCY-BARRIER`
prices an intra-encoder dependency edge at ~2.55 µs/layer (+102 µs/step).
S→N removes exactly one such edge (`rmsbfloat16 → gate_sp`) and is worth
**≤ 0.35 µs/layer** (point estimate 0.218, CI upper bound 14.19 µs/step). The
b4 contrast `C−W = +96.46 µs = 2.35 µs/layer` reproduces the full barrier price
on the *other* side of the same kernel pair. The difference between the two is
the downstream consumer: `gate_sp` is 96.4% nested inside a larger co-resident
record, so nothing waits on it, whereas the 5120-TG QKV matvec is on the
critical path. **The 2.55 µs/layer barrier price applies only when the
downstream kernel of the edge is itself on the critical path; for a nested,
off-critical-path consumer it is ~7–10× cheaper and indistinguishable from
zero.**
