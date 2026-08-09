# Decode OProj NVFP4 Scale Census

- Measurement commit: `44971b2ac00795f3b7dc607d4e7177423f8ddb75`
- Host: `Mac16,11` / `Apple M4 Pro` / macOS `26.5.2`
- Runtime GPU architecture / generation: `applegpu_g16s` / `16`
- Complete one-token 40-layer cycles: 129
- Selected cycle contractions / unique layers: 40 / 40
- Retained U8 scale bytes, sliding / full / total: 31,457,280 / 7,864,320 / 39,321,600
- Pooled scale range: 0..41
- Scale counts 0..63 / 64..127 / 128..255: 39,321,600 / 0 / 0
- Explicit scale counts >63 / >127: 0 / 0
- Row-max p50 / p90 / p99 / max: 14 / 16 / 20 / 41
- Rows with max >63 / >127: 0 / 0

## Reachability

| Kernel label | Layers in selected token |
|---|---:|
| `laguna_oproj_act_h48_v1_sc1_se1` | 10 |
| `laguna_oproj_act_h64_v1_sc1_se1` | 30 |

The selected trace window contains consecutive layers 0..39 exactly once, with B=L=1 shapes, H48 on full-attention layers, H64 on sliding layers, UInt32 codes, and UInt8 scales.

## Layer census

| Layer | Type | Heads | Scale shape | Min | Max | <=63 | 64..127 | >=128 | Rows >63 | Rows >127 |
|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | full | 48 | [2048, 384] | 1 | 27 | 786,432 | 0 | 0 | 0 | 0 |
| 1 | sliding | 64 | [2048, 512] | 2 | 32 | 1,048,576 | 0 | 0 | 0 | 0 |
| 2 | sliding | 64 | [2048, 512] | 2 | 33 | 1,048,576 | 0 | 0 | 0 | 0 |
| 3 | sliding | 64 | [2048, 512] | 1 | 33 | 1,048,576 | 0 | 0 | 0 | 0 |
| 4 | full | 48 | [2048, 384] | 1 | 29 | 786,432 | 0 | 0 | 0 | 0 |
| 5 | sliding | 64 | [2048, 512] | 1 | 36 | 1,048,576 | 0 | 0 | 0 | 0 |
| 6 | sliding | 64 | [2048, 512] | 2 | 33 | 1,048,576 | 0 | 0 | 0 | 0 |
| 7 | sliding | 64 | [2048, 512] | 1 | 34 | 1,048,576 | 0 | 0 | 0 | 0 |
| 8 | full | 48 | [2048, 384] | 0 | 32 | 786,432 | 0 | 0 | 0 | 0 |
| 9 | sliding | 64 | [2048, 512] | 1 | 32 | 1,048,576 | 0 | 0 | 0 | 0 |
| 10 | sliding | 64 | [2048, 512] | 1 | 31 | 1,048,576 | 0 | 0 | 0 | 0 |
| 11 | sliding | 64 | [2048, 512] | 1 | 38 | 1,048,576 | 0 | 0 | 0 | 0 |
| 12 | full | 48 | [2048, 384] | 1 | 33 | 786,432 | 0 | 0 | 0 | 0 |
| 13 | sliding | 64 | [2048, 512] | 1 | 34 | 1,048,576 | 0 | 0 | 0 | 0 |
| 14 | sliding | 64 | [2048, 512] | 1 | 36 | 1,048,576 | 0 | 0 | 0 | 0 |
| 15 | sliding | 64 | [2048, 512] | 1 | 34 | 1,048,576 | 0 | 0 | 0 | 0 |
| 16 | full | 48 | [2048, 384] | 1 | 33 | 786,432 | 0 | 0 | 0 | 0 |
| 17 | sliding | 64 | [2048, 512] | 1 | 40 | 1,048,576 | 0 | 0 | 0 | 0 |
| 18 | sliding | 64 | [2048, 512] | 1 | 39 | 1,048,576 | 0 | 0 | 0 | 0 |
| 19 | sliding | 64 | [2048, 512] | 1 | 41 | 1,048,576 | 0 | 0 | 0 | 0 |
| 20 | full | 48 | [2048, 384] | 1 | 32 | 786,432 | 0 | 0 | 0 | 0 |
| 21 | sliding | 64 | [2048, 512] | 1 | 39 | 1,048,576 | 0 | 0 | 0 | 0 |
| 22 | sliding | 64 | [2048, 512] | 1 | 36 | 1,048,576 | 0 | 0 | 0 | 0 |
| 23 | sliding | 64 | [2048, 512] | 1 | 35 | 1,048,576 | 0 | 0 | 0 | 0 |
| 24 | full | 48 | [2048, 384] | 1 | 38 | 786,432 | 0 | 0 | 0 | 0 |
| 25 | sliding | 64 | [2048, 512] | 2 | 38 | 1,048,576 | 0 | 0 | 0 | 0 |
| 26 | sliding | 64 | [2048, 512] | 2 | 39 | 1,048,576 | 0 | 0 | 0 | 0 |
| 27 | sliding | 64 | [2048, 512] | 2 | 37 | 1,048,576 | 0 | 0 | 0 | 0 |
| 28 | full | 48 | [2048, 384] | 2 | 34 | 786,432 | 0 | 0 | 0 | 0 |
| 29 | sliding | 64 | [2048, 512] | 2 | 34 | 1,048,576 | 0 | 0 | 0 | 0 |
| 30 | sliding | 64 | [2048, 512] | 2 | 38 | 1,048,576 | 0 | 0 | 0 | 0 |
| 31 | sliding | 64 | [2048, 512] | 2 | 34 | 1,048,576 | 0 | 0 | 0 | 0 |
| 32 | full | 48 | [2048, 384] | 1 | 32 | 786,432 | 0 | 0 | 0 | 0 |
| 33 | sliding | 64 | [2048, 512] | 2 | 40 | 1,048,576 | 0 | 0 | 0 | 0 |
| 34 | sliding | 64 | [2048, 512] | 1 | 37 | 1,048,576 | 0 | 0 | 0 | 0 |
| 35 | sliding | 64 | [2048, 512] | 1 | 38 | 1,048,576 | 0 | 0 | 0 | 0 |
| 36 | full | 48 | [2048, 384] | 2 | 32 | 786,432 | 0 | 0 | 0 | 0 |
| 37 | sliding | 64 | [2048, 512] | 2 | 36 | 1,048,576 | 0 | 0 | 0 | 0 |
| 38 | sliding | 64 | [2048, 512] | 2 | 33 | 1,048,576 | 0 | 0 | 0 | 0 |
| 39 | sliding | 64 | [2048, 512] | 1 | 37 | 1,048,576 | 0 | 0 | 0 | 0 |

## Packing audit

Row-local values are serialized LSB-first and each row starts on a 32-byte boundary. A one-byte CPU format tag per layer selects packed versus whole-layer U8 fallback; no GPU metadata is fetched. Safe decoding loads the first byte, loads the next byte only when `bit_start + bits > 8`, and forbids unconditional wide tail loads. Because every payload ends on a byte boundary, the conditional second byte is always inside the same row.

| Bits | Packed / fallback layers | Ideal bytes | Ideal saved | Real GPU bytes | Padding | Fallback bytes | Real saved | MiB saved | Metadata | Exhaustive cases | Mismatches | Hash match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 7 | 40 / 0 | 34,406,400 | 4,915,200 | 34,734,080 | 327,680 | 0 | 4,587,520 | 4.375 | 40 B CPU | 1,024 | 0 | True |
| 6 | 40 / 0 | 29,491,200 | 9,830,400 | 29,491,200 | 0 | 0 | 9,830,400 | 9.375 | 40 B CPU | 512 | 0 | True |

## Static execution risk

- Current path: one U8 scale load per lane and 32 adjacent scale bytes per 32 groups, followed by the existing left-shift/half decode.
- 7-bit: 28 unique bytes but 56 naive conditional byte-load instructions per 32 groups; 24 of 32 values cross a byte boundary, all eight bit starts occur, and H48 rows add 16 alignment bytes.
- 6-bit: 24 unique bytes but 48 naive conditional byte-load instructions per 32 groups; 16 of 32 values cross a byte boundary, bit starts cycle 0/6/4/2, and H48/H64 row strides remain aligned.
- Both add roughly 2-3 integer temporaries per lane; physical bandwidth may fall while load-instruction and register pressure rise.
- OProj topology is verified as row-major one-scale-per-group access inside the hot contraction. PR #514 topology is unavailable under the no-cross-branch constraint, so it can establish shared unpack-cost transfer but not direct coalescing or geometry equivalence.
- Assignment-provided QKV scale-bank deletion is 6,225,920 bytes (5.938 MiB); no PR #514 branch or code was inspected.

## Decision

- 7-bit gate: **True**; real deletion 4,587,520 bytes (4.375 MiB), smaller than the assignment-provided QKV deletion.
- 6-bit gate: **True**; real deletion 9,830,400 bytes (9.375 MiB), larger than the assignment-provided QKV deletion.
- Immediate recommendation: **defer_implementation_pending_pr514**. This audit does not authorize an implementation.
- If PR #514 provides positive shared unpack evidence, prefer **6bit** for a later one-file prototype because it clears the 8 MiB gate with no row padding.
- If PR #514 loses specifically because unpack overhead outweighs its 6,225,920-byte deletion, close OProj packing rather than prototype either format.

## Reproduction

- Measurement: `bash research/run_oproj_scale_census.sh`
- Analysis: `python3 research/oproj_scale_census.py`
- W&B upload: `python3 research/oproj_scale_census.py --wandb-only`

Full 256-bin pooled/full/sliding histograms, per-layer hashes, trace records, and per-format hashes are in `research/oproj_scale_census.json`.
