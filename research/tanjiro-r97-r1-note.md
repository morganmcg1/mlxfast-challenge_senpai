# R97-B / R1 — Fused QKV prefill bank with zero-copy layout descriptor

Track: `laguna-xs-2.1-serial-v2` (serial, non-speculative).
Assignment: `maple-r97-b-prefill-tg-count`, revision `r97-b-rev1`.
Branch: `maple-tanjiro/r97-prefill-tg-count`.
Base: `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.

This receipt is submitted explicitly as a **calibration probe**, not as a bid to
beat the current best. The expected prefill gain on the ranked M5 is
`0.16 ms` (`+0.06 %` score). That is roughly `1.6 sigma` against the measured
M5 candidate-prefill sigma of `0.1027 %`. The reason for spending it is stated
in full in section 6 below: it is the cleanest available instrument for a
single unknown that gates an entire family of future optimizations on this
track, and it is bit-exact by construction, so it carries no correctness or
floor risk.

## 1. What the candidate changes

Two sequenced mechanisms, submitted together because neither is separately
measurable (see section 5).

### P2 — row-concatenated QKV weight bank (prefill only)

In the baseline prefill path each attention layer issues three separate BF16
matmuls against the same activation matrix `A` of shape `(M=512, K=2048)`:

- `Wq`: `N = 8192` on sliding-window layers, `N = 6144` on full-attention layers
- `Wk`: `N = 1024`
- `Wv`: `N = 1024`

The candidate builds a single row-concatenated bank `[Wq; Wk; Wv]` once at
weight-preparation time, outside the scored window, and issues **one** matmul
per layer with `N = 10240` (sliding) or `N = 8192` (full). The bank is built by
`concatenated([wq, wk, wv], axis: 0)` in `prepareFusedQKVWeight()`, driven from
`prepareFusedRuntimeWeights()`. It is gated on `L > 1`, so single-token decode
never touches it and the decode path is entirely unaffected.

Peak resident memory is unchanged to within 0.4 MB (`20.7147` vs `20.7151` GB
measured locally), because the per-projection BF16 views are released once the
bank exists.

One decode-side guard was also corrected: the fused INT8 norm+QKV decode path
was previously predicated on `_fusedQKVWeight == nil`. Leaving that predicate
in place would have silently disabled INT8 decode whenever the prefill bank
existed, costing `+39.99 %` per decode step. The predicate is removed so decode
takes the same INT8 path with the flag on or off. This is not an optimization;
it is the fix that keeps P2 prefill-only in fact as well as in intent.

### P2b — layout descriptor instead of materialized slices

Enabling the bank alone introduces a regression that P2 does not pay for
itself: the four fused prefill QK-norm/RoPE kernels declare
`ensureRowContiguous: true`, and `custom_kernel.cpp` responds to a
non-row-contiguous input by issuing `copy_gpu(..., CopyType::General, s)`. A
column slice of the bank is not row-contiguous, so feeding `Q` and `K` slices
into those kernels forces **two general strided copies per layer, 78 per
request**, measured locally at `+1.516 ms`.

P2b removes those copies rather than tolerating them. The four kernels are
renamed `_v2` to `_v3` (so no stale compiled variant can be selected) and each
gains a seventh input, an `int32[4]` layout descriptor. The eight address
computations become:

```
input = raw_queries + t * uint(layout[0]) + uint(layout[1]) + head  * head_dim;
input = raw_keys    + t * uint(layout[2]) + uint(layout[3]) + khead * head_dim;
```

With the unfused descriptor `[qDim, 0, kvDim, 0]` these reproduce the previous
addresses element for element. With the banked descriptor
`[width, 0, width, qDim]` they read exactly the values the copy would have
produced. The descriptor is built once per attention module and cached in two
variants keyed on bank presence (`_prefillQKLayoutBanked`,
`_prefillQKLayoutPlain`); the hot path never reads its element values, which
would force a stream synchronisation per layer.

## 2. Why this is bit-exact

- Fusion does not change any arithmetic. Row concatenation along `N` leaves
  every output column computed from the identical `A` row and the identical
  weight column, in the identical `K`-reduction order.
- Both the three unfused GEMMs and the fused GEMM resolve to the *same* kernel
  variant on the ranked M5. The tile geometry derived in
  `steel_matmul_regular_axpby_nax` for `K = 2048` on a large device is
  `bm=64 bn=128 bk=256 wm=2 wn=4`, and every alignment predicate holds for both
  shapes: `align_M` (`512 % 64 == 0`), `align_N` (`6144`, `8192` and `10240`
  are all `% 128 == 0`), `align_K` (`2048 % 256 == 0`).
- The split-K admission test is *not* crossed by widening `N`. For `Wk`/`Wv`
  the test fails by an exact tie (`K > 2*max(M,N)` is `2048 > 2048` = false),
  so all three baseline projections already take the regular `_nax` path, and
  so does the fused one. `use_nax` itself reads only device generation and
  dtype, never `M`/`N`/`K`, so widening `N` cannot demote the dispatch off
  `_nax`.
- P2b's addressing is an identity transform under the unfused descriptor, and
  the banked descriptor is derived from the bank's own stride.

Local verification: `max_abs_diff = 0` and a single golden digest
`b9509697c08a` across all eight A/B arms, with the flag both on and off.

## 3. Local evidence (Apple M4 Pro, directional only)

4-repeat paired ABBA, 8 arms, alternating which arm runs first:

| axis | paired delta | sem | reps favouring candidate |
|---|---:|---:|---:|
| prefill | `-11.216 ms` | 2.755 | 4/4 |
| decode | `-0.1504 ms` | 0.0154 | 4/4 |

The effect survives order reversal — the candidate wins from first position
(`-8.10`, `-12.80`) and from second position (`-5.75`, `-18.21`) — so it is not
a warm-up or thermal drift artifact. Of the decode delta, `-0.088 ms` is the
mechanical seed-prefill amortisation implied by `decode_spt = per_step + S/128`;
the residual `-0.063 ms` is not attributed and is not claimed.

Dispatch census (per request, 3 reps, GPU profiling build):

| quantity | baseline | P2 only | P2 + P2b |
|---|---:|---:|---:|
| total dispatches | 1222 | 1144 | **1066** |
| `steel_gemm_bf16` records | 392 | 236 | **236** |
| QK-norm/RoPE dispatches | 41 | 119 | **41** |
| QK-norm/RoPE ms | 4.188 | 5.704 | **4.209** |

`1144 - 78 = 1066` reconciles exactly: P2b recovers `1.495 ms` of the
`1.516 ms` that P2 gave away. Every kernel family except `steel_gemm_bf16` is
dispatch-count identical between baseline and candidate. Buffer-binding
telemetry confirms the bank is bound once per kernel despite dual use as both
`raw_queries` and `raw_keys` (`9.500 -> 10.000 MB/call`, where `10.000 MiB` is
exactly one `[1, 512, 10240]` BF16 bank).

## 4. Why the M4 magnitude will not transfer to M5

Stated up front so the receipt is not over-read. The large M4 gain comes from a
mechanism that does not exist on the ranked machine.

On M4 (GPU generation 16, never selects `_nax`) `Wk` and `Wv` at
`(512, 1024, 2048)` fall into the non-`_nax` split-K branch, so each is two
dispatches plus an internal accumulate barrier. Fusion deletes four dispatches
per layer plus the split-K partial buffers. The census shows exactly this:
`MIXED:splitk_accum+splitk_nt` drops `310 -> 154`.

On M5 all three projections are already regular `_nax` GEMMs. Fusion there
changes **zero** FLOPs, **zero** bytes and **zero** threadgroups: a sliding
layer issues `512 + 64 + 64 = 640` threadgroups before and `640` after; a full
layer `384 + 64 + 64 = 512` before and `512` after. Only the dispatch count
falls, by roughly 80 per request.

Accordingly the honest M5 prediction is `-0.16 ms` (range `-0.05` to
`-0.30 ms`), from ~80 removed dispatches times the previously measured M5
per-dispatch encode cost of `1.9823 us` (OLS over a dispatch ladder) to
`2.3403 us` (independent estimate). At `0.373 %` score per ms of prefill that
is `+0.06 %`.

## 5. Why the two mechanisms are submitted together

They are not separable in a way worth a receipt. P2 alone is predicted to be a
null-to-slight-regression on M5 because the copies it introduces cost more than
the dispatches it removes. P2b alone is a literal no-op, because with no bank
present the layout descriptor reproduces the existing addresses exactly. The
attribution between them is carried by the local dispatch census above, which
isolates the copy removal directly, rather than by burning a second receipt.

## 6. What this receipt is actually for

The one thing that cannot be determined from source or from an M4 is whether
Apple silicon actually co-schedules threadgroups from *different* barrier-free
dispatches inside one concurrent encoder. MLX encodes into a single encoder
with `MTL::DispatchTypeConcurrent` and inserts a barrier only on a genuine
read-after-write, write-after-read or write-after-write hazard; read-after-read
is never checked. `Wq`, `Wk` and `Wv` all only read `A` and each writes a
distinct fresh buffer, so after the single barrier owed to the preceding
RMSNorm they are mutually barrier-free and the hardware is *permitted* to
overlap them. Whether it *does* decides:

- whether removing dispatches is worth anything at all on this track, and
- whether the partially-empty tail wave of a skinny `N = 1024` GEMM is real,
  which is the entire premise of the follow-on retiling experiment.

This candidate is the cleanest possible instrument for that question because it
changes the dispatch count and nothing else — same kernel variant, same tile
geometry, same threadgroup count, same traffic, same reduction order.

Read-out, registered before submission:

| observed prefill delta | reading |
|---|---|
| `<= -1.0 ms` | dispatches serialise; tail-wave model holds |
| `-0.3` to `-1.0 ms` | partial overlap |
| `> -0.3 ms` | overlap confirmed; dispatch-count family closes |
| `> +0.3 ms` | unmodelled regression; revert |

A `rejected` ranking verdict on a `+0.06 %` change is the expected outcome and
does not invalidate the measurement. The correctness verdict, the error field
and the two `0.95` floor verdicts are read separately from ranking status.

## 7. Submitted surface

Within `editablePaths` only:

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` — the fused bank, the four
  `_v3` QK-norm/RoPE kernels and their layout descriptor, the cached descriptor
  variants, and the decode INT8 guard correction.

No vendored MLX file is modified by this candidate; the profiling hooks used to
produce the census in section 3 were reverted and the vendored
`backend/metal/device.{h,cpp}` are byte-identical to the base. Editable budget
at submission: `current=2903610/3000000`, `headroom=96390`,
`growth=4134/262144` — within all three limits.

The candidate depends on no research file, no test and no documentation; the
`research/` material referenced above is evidence, not runtime.

## 8. Local `--local-submit` preflight (commit `723e628`, M4 Pro)

```
passed                        : true
passed_correctness            : true
max_abs_diff                  : 0
error                         : ""
checked_steps                 : 1025
num_layers                    : 40
peak_ram_gb                   : 21
passed_decode_speedup_floor   : true    (decode  0.008892 s/tok, 1.558x)
passed_prefill_speedup_floor  : false   (prefill 0.001114 s/tok, 0.330x)
```

The prefill-floor line is a host artefact, disclosed rather than hidden. The
pinned baseline constant used by `--local-submit` is
`0.000368 s/token`, i.e. an M5-class prefill rate; this M4 Pro runs the same
512-token prefill at `0.001114 s/token`, so *any* candidate — including the
byte-identical base — misses that floor on this host by roughly 3x. The paired
same-host evidence in section 3 is the relevant comparison, and there the
`off` arm is slower than the `on` arm on every one of four ABBA repetitions
(`578.16 / 575.91 / 582.40 / 582.50 ms` versus
`572.40 / 567.81 / 564.19 / 569.69 ms`). Correctness, `max_abs_diff` and the
golden hash are the parts of this preflight that do transfer, and all three are
green.
