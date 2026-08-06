# PR #35 Part 0 — NVFP4 uint8 scale-code census

Assignment `maple-2026-08-04j-scale-code-width`, revision `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `eaedee8430f1e2779b235a7fbc296ee20ef3e44b`.

This is the census the assignment requires **before** any Metal is written. It
answers one question: how many distinct E4M3 scale codes actually occur, and
over what local span, in every uint8 scale plane the runtime builds?

## Method

`DARKBLOOM_SCALE_CENSUS=1` (default OFF, research-only) walks every fused /
native-affine weight bank right after `eval(fusedArrays)` inside
`prepareFusedRuntimeWeights()`, i.e. at init on the real shipped banks, not on a
synthetic sample. For each uint8 scale plane it records the exact code
histogram plus `max-min` span histograms at three granularities: per row, per
32-group block (the 512-value `block_size` a decode simdgroup covers), and per
16-group half block. `attn.g` is correctly skipped: `g_proj` is INT8 group-32
with **bfloat16** scales, so it has no uint8 code plane.

Runs: 3 × `research/decode_probe.py --steps 2` via `run_training`, exit 0,
40 s each. M4 Pro `Mac16,11`, 48 GiB, `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`.

## Code occupancy per family

| family | plane bytes | min | max | distinct |
| --- | --- | --- | --- | --- |
| `attn.q` | 39,321,600 | 0 | 35 | 36 |
| `attn.k` | 5,242,880 | 0 | 30 | 31 |
| `attn.v` | 5,242,880 | 2 | 26 | 25 |
| `attn.o` | 39,321,600 | 0 | 41 | 42 |
| `routed.gate_up` | 1,308,622,848 | 2 | 73 | 58 |
| `routed.down` | 654,311,424 | 1 | 42 | 42 |
| `shared.gate_up` | 5,111,808 | 1 | 43 | 38 |
| **global** | 2,057,175,040 | 0 | 73 | **60** |

Mass is extremely concentrated — global codes 4..11 are 99.7% of all 2.06e9
scale bytes — but the tails are real and reach code 73.

### First decision: the 4-bit global dictionary is dead

60 distinct codes globally, 42 in `attn.o` alone. A 16-entry global (or even
per-family) dictionary cannot represent the observed alphabet, and the
assignment forbids an approximation: every checked token must match. A 6-bit
raw field is legal for attention (max 41 < 64) but only buys 25%.

## Local span per 32-group block (`max-min`)

The decode kernels read scales in units of 32 contiguous bytes per simdgroup
(`block_size = 512` values / group 16 = 32 groups, one byte per lane). That is
exactly the unit a per-block base can amortise.

| family | blocks | ≤3 | ≤7 | ≤15 | ≤31 | max |
| --- | --- | --- | --- | --- | --- | --- |
| `attn.q` | 1,228,800 | 0.3983 | 0.9450 | 0.9985 | **1.0000** | 30 |
| `attn.k` | 163,840 | 0.3913 | 0.9194 | 0.9967 | **1.0000** | 25 |
| `attn.v` | 163,840 | 0.1675 | 0.9418 | 0.9991 | **1.0000** | 22 |
| `attn.o` | 1,228,800 | 0.0833 | 0.8340 | 0.9991 | **1.0000** | 31 |
| `routed.gate_up` | 40,894,464 | 0.1798 | 0.9625 | 0.9995 | 1.0000 | 39 |
| `routed.down` | 20,447,232 | 0.2180 | 0.9801 | 0.9998 | 1.0000 | 35 |
| `shared.gate_up` | 159,744 | 0.5107 | 0.9118 | 0.9872 | 0.9999 | 37 |

Two facts carry the design:

1. **All four attention families have block span ≤ 31 for 100.00% of blocks**
   (worst single block: 31 in `attn.o`). A 5-bit index plus a per-32-block
   uint8 base is therefore *exact* for every attention block, with no escape
   path, no fallback row, and no data-dependent branch.
2. A 4-bit index is **not** exact: 0.09%-0.15% of attention blocks exceed span
   15, and half-blocks still reach span 28-30, so 4-bit+base would need an
   escape mechanism. Rejected for this rung.
3. Routed/shared exceed 31 (max 39) so they cannot use the same 5-bit form
   globally. They are out of scope here; also `routed`/`shared` on-disk scales
   are read by prefill, so only a decode-only side bank could ever be narrowed.

## Chosen representation (attention only)

Three row-contiguous planes replacing the 32-byte uint8 group, per 32 groups:

| plane | shape | bytes / 32 groups |
| --- | --- | --- |
| `scale_nibbles` (index bits 0-3) | `[rows, G/2]` | 16 |
| `scale_high_bits` (index bit 4) | `[rows, G/8]` | 4 |
| `scale_bases` (block min) | `[rows, G/32]` | 1 |
| total | | **21 vs 32** |

`code = base + nibble + (bit << 4)` reconstructs the **original uint8 byte**,
which is then fed to the unchanged `laguna_tail_nvfp4_scale`. Nothing about the
scale decode, the sign-domain fold, or the `2^22` epilogue changes; the kernel
reads fewer bytes to produce the identical byte it reads today. The packing
mirrors the in-tree `LagunaLmHeadPrune.buildInt5Planes` idiom (nibble plane +
1-bit plane via `.view(dtype:)` masks).

## Predicted effect

Attention q/k/v/o scale planes are 89,128,960 B/step of the ~1794 MB/token
decode budget. 21/32 of that is 58.5 MB, so the saving is **30.6 MB/step =
1.71% of decode bytes**.

* M5 (ranked): 1.71% × elasticity 0.638 = **+1.09% score** vs the `0c21dc18`
  frontier receipt (T 4.3181 ms, S 98.029 ms, ns 2.52973). Comfortably inside
  the 5% calibration band.
* M4 (local screen, 260.2 GB/s measured ceiling): **-118 µs/step** —
  `qkv_h64` -52, `oproj_act_h64` -42, `qkv_h48` -14, `oproj_act_h48` -10.
  That is ~3x the 40 µs/step per-dispatch detection gate, so the byte-roofline
  claim is falsifiable locally.
* RAM: +60 MB (originals retained so an MLX fallback stays possible), against
  the 25 GiB cap at ~20.7 GiB today.

The Part 3 screen therefore has a hard pass/fail: per-dispatch µs must fall by
at least 30 µs/step total and land within 30% of the -118 µs prediction.
Otherwise the mechanism is not bandwidth-limited where the census says it is
and the rung stops.
