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

_(filled in from `research/armg-runs/b5`)_

## 4. Reading

_(filled in)_
