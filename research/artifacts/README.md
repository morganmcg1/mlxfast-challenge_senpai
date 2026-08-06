# `research/artifacts/` — checked-in instrument output

Every file here is regenerable output from a research-only instrument. Nothing
here is on the submitted surface and nothing here is read by the runtime.

## `nezuko_slab_census_{full,rows,entropy}.md`

Produced by `research/nezuko_slab_census.swift` (offline, CPU-only, no GPU, no
benchmark lock, no thermal gate). Build and run:

```bash
swiftc -O research/nezuko_slab_census.swift -o /tmp/slab_census
/tmp/slab_census --mode full    --weights weights   # exhaustive byte identity
/tmp/slab_census --mode rows    --weights weights   # sub-slab row identity
/tmp/slab_census --mode entropy --weights weights   # per-role code alphabets
/tmp/slab_census --mode probe   --weights weights --probe-bytes 4096
```

A *slab* is one contiguous byte range that the runtime could in principle
address independently: for the stacked routed experts
(`mlp.switch_mlp.{gate,up,down}_proj.{weight,scales}`, shaped `[256, R, C]`)
that is one expert's sub-range of the stacked tensor; for every other tensor it
is the whole tensor. The checkpoint decomposes into 60,582 slabs over 5
safetensors shards, 912 tensors, 20.08 GiB = 21,561,408,512 B.

### Column meanings

| column | meaning |
| --- | --- |
| `role` | canonical tensor role, e.g. `routed.gate_proj.weight`, `attn.q_proj.weight` |
| `slabs` | number of slabs carrying that role |
| `bytes` | total bytes in those slabs |
| `classes` | distinct byte-identity classes; class key is `(SHA-256 128-bit prefix, slab length)` |
| `removable slabs` / `removable bytes` | `slabs - classes`, i.e. what a perfect dedup would delete |
| `distinct-offsets` | `YES` when every member of a duplicate class sits at its own `(shard, offset)`; `ALIASED` if two members are the same bytes |
| `memcmp` | full byte-for-byte re-verification of each duplicate class, independent of the hash |
| `dup rows` / `index bytes` / `net` | row mode only: duplicate rows found, the cost of the indirection table at 4 B/row, and the signed net saving |
| `byte H` / `nibble H` | Shannon entropy of the byte and 4-bit-nibble code distribution |
| `distinct codes` | how many of the 256 byte codes (or 16 nibble codes) actually occur |
| `LUT bits` | `ceil(log2(distinct codes))`, the width of the narrowest *fixed-width* recode |

### Soundness of the numbers

1. **Prefix screening is a sound upper bound.** Byte-identical slabs share
   every prefix, so `--mode probe` can only ever *over*-count duplicates. It
   never misses one. `--mode full` removes the bound by hashing every byte.
2. **Class identity includes slab length**, so a truncated probe cannot merge
   slabs of different sizes.
3. **Every reported duplicate class is re-verified with `memcmp`** over the full
   slab, so the result does not rest on hash collision resistance.
4. **The enumerator self-checks.** Before hashing it proves that the 60,582
   slabs occupy 60,582 distinct `(shard, offset)` sites with zero repeated,
   zero overlapping and zero out-of-range slabs, using each mapping's real
   `Mapped.size`. Without this a dedup rate can be manufactured by hashing the
   same bytes twice.
5. **Sampling is declared per mode.** `full`, `probe` and the `.scales` roles of
   `entropy` are exhaustive. `rows` samples 1 slab in 8 for the routed roles and
   is exhaustive within a sampled slab. Mantissa roles in `entropy` use a 1/19
   strided whole-slab sample. Percentages in the artifacts state which.
6. **A built-in positive control.** `router.e_score_correction_bias` is
   byte-identical across all 39 sparse layers, so a run that reports zero
   duplicate classes anywhere is a bug, not a result.

### Representation caveat

Attention weights are **BF16 on disk** and are re-quantized to NVFP4 g16 at
load, so the disk census is not evidence about the runtime attention
representation. Routed expert weights **are** NVFP4 on disk, so the disk census
is valid evidence for the MoE arm. The routed *scale* plane on disk is the
un-halved plane; PR #72 (merged at `9e8c719f`) halves it at load time, so
runtime routed scale traffic is 30.67 MB/step, not 61.34.

## `nezuko_feed_wall_census.txt`

Produced by `research/nezuko_feed_wall_census.py` from the official submission
feed. Answers "how much wall time does an intentionally slowed candidate add to
an official measure job" for the receipt-channel instrument in
`research/PREFILL_LEDGER_INSTRUMENT.md`. Regenerate with:

```bash
curl -sS -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
  -o /tmp/feed.json
python3 research/nezuko_feed_wall_census.py /tmp/feed.json
```

Read the era table, not the pooled regression. `benchmark_wall_seconds`,
`correctness_seconds` and `timed_benchmark_seconds` are integer-quantized and
are set by harness generation; the feed must be stratified by
`(harness_hash, checked_steps, case_count)` before any slope is interpreted.
