# Routed-MoE rows-per-expert artifact (512-token prefill)

Produced by `research/lpt_expert_queue_sim.py` from the already-measured probe
`research/prefill-512-route-histogram.txt`. Landed by PR #142 (Round 22 H3) so
other experiments can join against a single citable routing census rather than
re-deriving one. PR #143's expert-slab dedup census is the first consumer.

## Files

| file | content |
| --- | --- |
| `route-histogram-prefill512.csv` | tidy long form, one row per `(layer, expert)` |
| `route-histogram-prefill512-stats.json` | per-layer + pooled statistics and dispatch-tile counts |

Regenerate with:

```bash
python3 research/lpt_expert_queue_sim.py --no-sim
```

## Provenance

- Probe: `DARKBLOOM_ROUTE_HISTOGRAM`, commit `3e8e435` (PR #11), since reverted.
- Workload: one 512-token prefill, 38 MoE layers, 256 experts, top-8 routing
  (`LagunaConfig.swift:30-31`), so `sum(rows) == 4096` per layer.
- Host: Apple M4 Pro. **Host independent**: routing is a function of the model
  weights and the prompt, not of the GPU. It transfers to the ranked M5.
- The raw probe holds 76 records = two forwards. The two forwards are
  **bit-identical** (verified), so the "drop the first forward as warmup"
  convention used by `research/route_histogram.py --skip-forwards 1` changes
  nothing here. The artifact covers 38 layers = one forward.

## CSV schema

| column | type | meaning |
| --- | --- | --- |
| `layer_index` | int, 0..37 | MoE layer, in forward-pass emission order |
| `expert_id` | int, 0..255 | routed expert slot |
| `rows` | int, >=0 | tokens routed to this `(layer, expert)` pair |
| `chunks_bm64` | int, >=0 | `ceil(rows / 64)`; threadgroup chunk-loop trips at `BM=64` |

9728 data rows (38 x 256).

## JSON schema

Top level:

| key | meaning |
| --- | --- |
| `schema_version` | `1` |
| `source_probe`, `source_commit`, `host`, `workload` | provenance, as above |
| `warmup_forwards_dropped`, `layers` | `1`, `38` |
| `geometry` | dispatch constants the counts are derived under |
| `pooled` | statistics over all 9728 pairs |
| `per_layer` | list of 38 stat blocks, `layer_index` 0..37 |
| `dispatch_tiles` | per-gather-call threadgroup counts |

A stat block (`pooled` and each `per_layer` entry) carries `n`, `sum`,
`zero_count`, `zero_frac`, `min`, `median`, `mean`, `p90`, `p99`, `max`,
`stdev` (population), `mean_nonzero`, `nonzero_experts`, `chunks_bm64`.
Percentiles are nearest-rank on the sorted vector. `pooled` additionally
carries `max_over_mean_per_layer`, the mean across layers of
`max(rows) / mean(rows)`.

`geometry` records the constants the derived columns assume:
`expert_groups=256` (`quantized.cpp:1379`), `BM=64`, `BN=64`, `BK=64`,
`group_size=16`, `bits=4` (tiling variant 5 -> `bm=64 wm=4 wn=1`, `SM=16`).
The expert-aligned grid is `(N/BN, expert_groups)`, i.e. **one threadgroup per
`(expert, column tile)`** (`quantized.cpp:1917-1923`).

`dispatch_tiles` has one entry per routed gather call certified by the
expert-aligned accept gate (`quantized.cpp:1659-1671`):

| key | `gate_up` | `down` |
| --- | --- | --- |
| `K`, `N` | 512, 2048 | 2048, 1024 |
| `column_tiles` = `N/BN` | 32 | 16 |
| `dense_threadgroups` (38 layers) | 311296 | 155648 |
| `compacted_threadgroups` | 248224 | 124112 |
| `launch_reduction_ratio` | 1.2541x | 1.2541x |
| `chunk_threadgroup_iterations` | 268128 | 134064 |
| `chunk_dram_bytes` = `BN*K*(1/2 + 1/16)` | 18432 | 73728 |

## Headline numbers

Pooled over 38 x 256 = 9728 `(layer, expert)` pairs, 155648 row assignments:

```
zero-row pairs   1971  (20.26%)
min 0   median 7   mean 16.00   p90 39   p99 142   max 505   stdev 28.77
mean over nonzero pairs      20.07
chunks at BM=64              8379   (re-read factor 1.0802 over 7757 nonzero pairs)
mean per-layer max/mean      15.19x
```

Per forward, summed over both gather calls: **466944 dense threadgroups, of
which 94608 (20.26%) are empty**, and 804384 chunk-iterations of work when
weighted by DRAM bytes into `gate_up`-chunk units.

These reproduce the earlier census in
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md` exactly (20.26% zero,
mean 16.00, max 505, re-read 1.080, max/mean 15.19x), which cross-validates
both derivations.

## Caveats for consumers

- Single prompt. The distribution is prompt-dependent; treat tail statistics
  (`p99`, `max`) as one draw, not as a bound.
- `rows` is a prefill-time count at sequence length 512. Decode routes one
  token through 8 experts per layer, so the decode distribution is a different
  object entirely and this artifact does not describe it.
- An empty `(layer, expert)` pair costs **zero weight DRAM**: the threadgroup
  exits at the run-bounds binary search before staging anything. Do not price
  `zero_frac` as removable bytes.
