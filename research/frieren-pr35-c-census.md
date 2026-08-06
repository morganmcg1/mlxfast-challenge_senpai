# PR #35 r3 Step 1 — the C census of every NVFP4 decode scale plane

Answers the r3 Step 1 ask: measure the routed gate/up, routed down and shared
planes **before** any Metal, and decide whether the 4-bit lane-major dictionary
(per-row base + `0xFF` sentinel escape) is representable on each of them.

**Verdict: the design passes on every plane.** No plane declines.

## Provenance

- Instrument: `DARKBLOOM_SCALE_CENSUS=1`, an init-time census that reads each
  plane exactly as its consumer sees it. It has been **removed from
  `Sources/`** again and is preserved as
  `research/frieren-pr35-census-instrument.patch`; it never has to run twice.
- Driver: `research/frieren_census_run.sh` →
  `python3 research/decode_probe.py --steps 2`, with
  `DARKBLOOM_ATTN_SCALE_LANEMAJOR=0` (so the census reads stock planes, not a
  re-encoding of them) and `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.
- Host: M4 Pro `Mac16,11`, 48 GiB. The census is a property of the checkpoint
  bytes, not of the GPU, so this is not a cross-machine inference.
- 365 `scale-census` records = 355 planes + 9 families + 1 global.
- Per-plane detail: `research/frieren-pr35-c-census.csv` (355 rows).
  Tables below are `research/frieren_pr35_census_parse.py` output.

## Family and global aggregates

| plane | n | min | max | distinct | rows | row_span_max | row_le15 | row_le31 | blk_le15 | blk_le31 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `attn.q` | 39321600 | 0 | 35 | 36 | 307200 | 31 | 0.994395 | 1.000000 | 0.998465 | 1.000000 |
| `attn.k` | 5242880 | 0 | 30 | 31 | 40960 | 25 | 0.986353 | 1.000000 | 0.996716 | 1.000000 |
| `attn.v` | 5242880 | 2 | 26 | 25 | 40960 | 22 | 0.995776 | 1.000000 | 0.999133 | 1.000000 |
| `attn.o` | 39321600 | 0 | 41 | 42 | 81920 | 35 | 0.981372 | 0.999854 | 0.999055 | 1.000000 |
| `routed.gate_up` | 1308622848 | 2 | 73 | 58 | 10223616 | 39 | 0.998359 | 0.999998 | 0.999491 | 1.000000 |
| `routed.down` | 654311424 | 1 | 42 | 42 | 20447232 | 35 | 0.999795 | 0.999998 | 0.999795 | 0.999998 |
| `routed.packed` | 1308622848 | 2 | 73 | 58 | 40894464 | 39 | 0.999491 | 1.000000 | 0.999491 | 1.000000 |
| `shared.gate_up` | 5111808 | 1 | 43 | 38 | 39936 | 37 | 0.961113 | 0.999775 | 0.987205 | 0.999950 |
| `shared.down` | 2555904 | 1 | 41 | 40 | 79872 | 34 | 0.994028 | 0.999962 | 0.994028 | 0.999962 |
| `global` | 3368353792 | 0 | 73 | 60 | 72156160 | 39 | 0.999338 | 0.999999 | 0.999505 | 0.999999 |

`routed.down` and `shared.down` have `rows == blocks`: their scale rows are a
single 32-group block (`scale_row_bytes = 32`, `LagunaRuntimeModel.swift:6709`),
so per-row and per-32-block are the same statistic for the down projections.

## Escape rate per plane (1 - row_le15)

| plane | escape rate | note |
| --- | --- | --- |
| `routed.down` | 0.02% | |
| `routed.packed` | 0.05% | |
| `routed.gate_up` | 0.16% | |
| `attn.v` | 0.42% | |
| `attn.q` | 0.56% | |
| `shared.down` | 0.60% | |
| `attn.k` | 1.36% | |
| `attn.o` | 1.86% | |
| `shared.gate_up` | 3.89% | smallest plane (5.1M of 3.37G elements) |

The worst escape rate sits on the *smallest* plane, so the traffic-weighted
escape rate is far below the unweighted worst case: the two routed families are
2.62G of the 3.37G elements and escape at 0.05-0.16%.

## The two facts that decide the design

1. **A global 4-bit dictionary is dead, and this census confirms it again.**
   60 distinct codes globally, max 73. Only a *per-row base* makes 4 bits
   sufficient.
2. **An escape path is mandatory, not optional.** `row_span_max` is 39 globally
   and `row_le15 < 1` for every single family. The `0xFF` sentinel is what makes
   the representation exact rather than approximate; a 4-bit form without it
   would be wrong on 0.02-3.89% of rows depending on the plane.

`L39.routed.gate_up` and `L39.routed.packed` are the only planes containing a
code above 63 (min 2, max 73, 57 distinct, `row_span_max` 39) — the known
escape case, and the reason the sentinel is `0xFF` rather than a low value: real
bases top out at 43 across every plane, so the sentinel cannot collide.

Lowest `row_le15` outliers, for the stop-rule diagnosis: `L31.shared.gate_up`
0.916992, `L27.shared.gate_up` 0.920898, `L19.shared.gate_up` 0.921875,
`L24.k` 0.943359, `L0.o` 0.945312, `L39.shared.down` 0.966309, `L24.q` 0.975586,
`L25.routed.gate_up` 0.992195, `L39.routed.down` 0.996199.

Global code mass is concentrated in seven codes (~97.9%): 6 = 28.72%,
7 = 24.21%, 8 = 15.91%, 5 = 15.47%, 9 = 6.73%, 4 = 3.77%, 10 = 3.07%.

## Bytes per row under the r3 representation

`1 + groups/2` against the stock plane's `groups`:

| row shape | planes | stock | lane-major | delta |
| --- | --- | --- | --- | --- |
| 128 groups | `attn.q/k/v`, `routed.gate_up`, `routed.packed` | 128 B | 65 B | -49.2% |
| 384 groups | `attn.o` | 384 B | 193 B | -49.7% |
| 32 groups | `routed.down`, `shared.down` | 32 B | 17 B | -46.9% |

**Implementation caveat the census exposes.** The builder requires
`groups % 64 == 0` so a lane's nibble run is a whole number of bytes and no byte
straddles two lanes (`lagunaLaneMajorNVFP4ScaleBank`,
`LagunaRuntimeWeights.swift:850-853`). The 128- and 384-group rows satisfy it;
the **32-group `down` rows do not**. Extending to the down projections therefore
needs either a relaxed guard with a half-byte-aware lane map or a row-pair
packing, and is strictly more work than gate/up. It is not blocked on the
census — the span statistics are the best of any family — only on that layout
detail.

## Relation to the r1 census

`research/frieren-pr35-scale-census.md` remains valid and complementary. It
established that a 4-bit *global* dictionary is dead, that 4-bit-without-escape
is not exact, and that the r1 5-bit form (nibble + 1-bit plane + per-32-block
base = 21 B vs 32) is exact for all attention with no escape at all. The r3
form trades r1's escape-free exactness for ~2x fewer bytes and, more
importantly, two loads per output row instead of twelve.
