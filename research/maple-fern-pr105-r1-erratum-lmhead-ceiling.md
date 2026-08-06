# Erratum — the lm-head cascade is not at 61 % of the M4 ceiling

**Voids:** `research/maple-tanjiro-pr73-decode-kernel-census.md` §6.4 (table
row, `:526`) and §8.3 (`:666`), where the lm-head cascade is described as
reading "112.4 MB at 61 % of the M4 ceiling" with a recoverable excess of
**200.1 µs M5-equivalent ≈ 2.97 % of score**, and is thereby ranked the
largest unclaimed slack pool after `sliding_fused_attn_ring_v1`.

**Status:** the 61 % figure and the 200.1 µs / 2.97 % slack attribution are
withdrawn. The census's own table refutes them.

## 1. The census contradicts itself

§6.4 row, quoted verbatim:

| family | n | M4 µs | M5-eq µs | MB | floor µs | excess µs | % of score |
|---|---:|---:|---:|---:|---:|---:|---:|
| lm-head cascade (6 kernels) | 6 | 508.1 | 384.4 | 112.4 | 184.3 | 200.1 | 2.97 |

Its own M4 columns give the achieved bandwidth directly:

```
112.4 MB / 508.1 µs = 221.2 GB/s
221.2 / 260.2 GB/s  = 85.0 % of this host's measured M4 Pro ceiling
```

Not 61 %. Whatever ceiling produces 61 % implies `221.2 / 0.61 ≈ 363 GB/s`,
which is not the ceiling of the machine the census was measured on. The
`floor µs` column is separately computed against the **M5** 610 GB/s figure,
so the row mixes an M4 achieved time with an M5 roofline; that is legitimate
for pricing an M5 opportunity, but the prose then reports the ratio as if it
were an M4 utilisation, and it is not.

## 2. The dominant stage is at the ceiling, not at 61 % of it

The six-kernel aggregate hides the shape of the cascade. One stage is 91 % of
its bytes:

```
laguna_lmhead_int5_base_coarse_delta_bf16_v1
  109.18 MB / 418.9 µs = 260.6 GB/s = 100.2 % of the 260.2 GB/s M4 Pro ceiling
```

Independently reproduced on the pre-#20 tree at **264.0 GB/s = 101.5 % of
ceiling** — see `research/nezuko-decode-roofline.md:253` and
`research/nezuko-m1-cascade-result.md:20-21,41`. Two separate measurement
campaigns put this kernel at or fractionally above a STREAM-style ceiling
estimate, which is the ordinary signature of a pure sequential streaming read.

The aggregate looks slack because the other five kernels are small, latency-
and dispatch-bound stages averaged into the same row. Averaging a saturated
100 MB stream with five sub-µs dispatches produces a number that describes
neither.

## 3. What follows for programme strategy

1. **There is no 200.1 µs instruction-side slack pool in the lm-head cascade.**
   Stage 1 is byte-bound and saturated. Occupancy work, unrolling, threadgroup
   geometry, and register pressure have nothing to recover there.
2. **Bytes are the only lever on this cascade.** Any proposal must remove
   bytes from the stage-1 stream or it is pre-refuted, and §0.9.36's byte
   channel is the applicable pricing band.
3. The §8.3 characterisation — "not obviously closed" — inverts. It *is*
   closed to everything except a narrower read. That is precisely why the
   4+1 → 3+2 re-split (this PR) is the shape of the only remaining move on
   this kernel, and why the 25.69 MB it removes is the whole of its expected
   value.
   **Superseded by the PR #105 census.** The 25.69 MB is gross, not net: the
   re-split pushes 85.7 % of the vocabulary into tier 2, which costs more than
   it saves. See `research/maple-fern-pr105-r1-result.md`. The correct reading
   of this erratum is 1 and 2 only — stage 1 is saturated and bytes are the
   only lever — and the census then shows there are no bytes left to take.
4. Any future census row that averages a large streaming kernel with small
   dispatch-bound kernels should report per-kernel achieved bandwidth, not an
   aggregate ratio. The aggregate is what produced this error.

## 4. Provenance

Numbers in §1 and §2 are read from the cited files; no new measurement was
taken for this erratum. The M4 Pro ceiling of 260.2 GB/s and the M5 figure of
610 GB/s are the constants the census itself uses.
