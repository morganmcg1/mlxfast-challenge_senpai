# R106-G — Redundant-read / fusion census of the decode step

**Verdict: N-ONCE.** At DRAM-traversal granularity the decode step reads
**1.00177 bytes per distinct byte touched (upper bound; point estimate 1.0000003
if only above-SLC bytes are priced as DRAM).** 99.4205 % of `B` is *provably*
read exactly once. The byte-reduction-by-fusion family closes: the entire
addressable redundancy, redundant reads plus every intermediate round trip
summed together, is **9,140,392 B/step = 0.547 % of `B` = 15.16 µs/step =
0.231 % of `cs`**, which is **2.19× below the 1.2 %-of-`B` gate**. The single
largest fusion candidate is 20× below the gate. No receipt is warranted and none
was spent (channel allocated to frieren this round, Rule 88).

- PR #619 · assignment `maple-r106-g-redundant-read-fusion-census` rev
  `r106-g-rev1` · base `9d424c167eae0a98e4c8c03e57be2f937ae0744a`
- Host: Apple M4 Pro 48 GiB (`applegpu_g16s`, gen 16). **Structural** result —
  the quantities measured are dispatch operand bindings and grid geometry, which
  are architecture-independent; the *pricing* uses the M5 constants below.
- Constants: `B` = 1,671,402,432 B/step; `BW_M5` = 602.7e9 B/s; 1 % of `B` =
  16,714,024 B = 27.73 µs/step = 0.4223 % of `cs`; M5 decode step 4141.5 µs
  (`research/CURRENT_RESEARCH_STATE.md:382`).
- Gate: 1.2 % of `B` = 20,056,829 B ≈ +0.5 % of `cs`.

---

## 0. Instrument, and the one thing it does not measure

Rule 58/83: I did not build a new tracer. `grep -rn "note_in_buf" research/`
finds exactly one instrument, the R106-C patch
`research/r106c/scripts/trace_dag.patch`, and its raw per-dispatch byte-range
log survived on disk from the #617 session. I preserved it rather than re-running
the model:

| artifact | bytes | sha256 |
|---|---|---|
| `research/artifacts/fern-r106g/dispatch_raw.tsv` | 2,792,366 | `0a82cc1ac9b156c9242b40da888613d105beabbea96a57e4262ef46314fc2834` |
| `research/artifacts/fern-r106g/trace_report.json` | 815 | `b9c8fb6fc10ad8b03c4ba812148ab46871826c4231d9f4149f1f87736b3efb0b` |

The trace report's own contents record correctness of the traced step: golden
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`, token 902 =
expected token, `actual_expected_logit_delta = 0`, `matched_prefix_steps = 6`.

Derived artifacts, all produced from `dispatch_raw.tsv` by the four scripts in
`research/r106g/scripts/`:

| artifact | bytes | sha256 |
|---|---|---|
| `research/artifacts/fern-r106g/read_census.json` | 825,981 | `e17218c6d05bebd83355ec2232149da2f16e6e5458b1834cc996cd3bfe53ee8c` |
| `research/artifacts/fern-r106g/roundtrip_census.json` | 284,107 | `643937f230543caead7f01329068af283a7aaa1e2ca9f6f6c129890c744f3918` |
| `research/artifacts/fern-r106g/family_breakdown.json` | 8,661 | `9617d708ea67d31340549cf13f68d1f0bf01eb3035ad9fc99e7c68e1489d88ef` |
| `research/artifacts/fern-r106g/stage3_triage.json` | 26,706 | `f5eb96cf66aff00781ec3d92b48cfe8493da415c5b282c34a4dc516e609469fa` |

Instrument continuity with #617 is confirmed exactly: the extracted decode step
is **408 dispatches / 47 command encoders / 247 barriers**, identical to the
#617 ledger. 11,254 rows total.

**The decisive caveat.** `note_in_buf` records `a.data_size() * a.itemsize()` —
the whole bound array, the *binding extent*, not the bytes the kernel traverses.
A routed-MoE dispatch binds all 256 experts (268,435,456 B) and reads 8 of them.
Summing binding extents gives 19,199,493,156 B/step against a true `B` of
1,671,402,432 B — an 11.5× over-count. **Every number in this report is labelled
BINDING or TRAVERSAL and the two are never mixed.** The headline ratio is only
meaningful at traversal granularity.

Two smaller caveats, both handled in code:

- `set_output_array` calls `set_input_array` first
  (`Vendor/mlx-swift/.../device.cpp:330-336`), so every output also appears in
  the `ins` column. Ranges on both sides are read-modify-write, not pure reads;
  `read_census.py:reads_writes()` subtracts them.
- The `offset` argument to `set_input_array` is dropped by `note_in_buf`
  (patch line 101), so sub-buffer slicing is invisible. This is the one place
  N-INSTRUMENT could have fired — see §5.

### 0.1 Two questions the advisor asked directly

**Did this census inherit the `fern_r101_byte_audit.py` `g_proj` bug? No — it
never touches that script.** Lines 172-176 there price `g_proj` as BF16 at
4,096 B/head; HEAD uses affine INT8 group-32 at 2,304 B/head, a −4,300,800 B
error over 2,400 heads. The four scripts in `research/r106g/scripts/` import
only `research/r106c/scripts/dag_ledger.py` (for step extraction) and read only
`dispatch_raw.tsv`, `research/artifacts/fern-r105d/decode-byte-census.json`,
and `benchmark.json`. `grep -rn "fern_r101" research/r106g/` is empty. The
advisor's warning that a *partial* fix is worse than none — because the
−4,300,800 B `g_proj` overstatement nearly cancels an unrelated +5,732,384 B
omission of activation operands — is precisely why routing around it was the
right call rather than patching one side of the cancellation.

**Does this census give a third independent estimate of `B`? No, and the reason
is the instrument, not the effort.** Summing the DAG's own byte fields gives
19,199,493,156 B/step — 11.5× the accepted `B` — because `note_in_buf` records
the *binding extent* of each bound array, not the bytes the kernel traverses.
A routed-MoE dispatch binds all 256 experts and reads 8. Nothing in the trace
distinguishes those two without the gather indices, so the DAG **cannot**
produce an independent magnitude for `B`. What it can produce independently,
and what this report actually rests on, is the *structure*: which dispatch
writes a range, which dispatches later read it, and in what order. I therefore
took reader/writer structure from the DAG and per-family magnitudes from the
accepted r105-D census, and every byte claim below is labelled TRAVERSAL to
keep it separate from the BINDING numbers. Producing a genuine third estimate
of `B` would need the dropped `offset` argument plus gather-index capture —
scoped in §7 as a follow-up, not done here.

---

## 1. Stage 1 — the multi-read map

### 1.1 Headline

| granularity | total read | distinct touched | **ratio** |
|---|---|---|---|
| BINDING (what the tracer sees) | 19,199,493,156 | 18,779,421,828 | 1.0224 |
| **TRAVERSAL, upper bound** | **1,674,361,184** | **1,671,402,432** | **1.00177** |
| TRAVERSAL, above-SLC bytes only | 1,671,402,944 | 1,671,402,432 | **1.0000003** |

**The ratio is ≈ 1.00.** Stating it as the assignment asks: *one decode step
reads essentially every byte it touches exactly once.*

The traversal bound is constructed so it cannot understate. A byte is read twice
only if it is **bound** by two dispatches, so any buffer with one reading
dispatch has traversal multiplicity exactly 1 — no assumption required. For a
buffer with reader set `R`, the redundant traversal is at most the sum over `R`
minus its largest member, and each member's contribution is capped both by the
buffer extent and by that dispatch's entire per-call traversal budget from the
accepted `fern-r105d` census. Summed over all 240 multiply-bound ranges:

> **redundant traversal ≤ 2,958,752 B/step = 0.1770 % of `B` = 4.91 µs/step =
> 0.0747 % of `cs`.** That is **6.8× below the gate.**

The bound is *conservative* in a second way: MLX's allocator recycles scratch
buffers, so 12 of the `sliding_fused_attn_ring` "multi-read buffers" are one
pointer holding different logical tensors at different layers. Recycling inflates
apparent redundancy, so the true figure is lower still.

### 1.2 Breakdown by kernel family — the weight-payload cell

Weight payload is 95.90 % of `B`, so this is the cell that decides the question.
`excl` is the fraction of the family's traversal landing on buffers no other
dispatch binds — i.e. provably read once.

| traversal B | % of `B` | **excl** | shared bind B | family |
|---|---|---|---|---|
| 347,602,944 | 20.797 | **100.00 %** | 199,680 | `routed_nvfp4_swiglu_qmv_packed_top8keys` |
| 324,710,400 | 19.427 | **99.97 %** | 122,880 | `nvfp4_qkv_h64` |
| 259,584,000 | 15.531 | **100.00 %** | 3,840 | `oproj_act_h64` |
| 195,526,656 | 11.698 | **99.99 %** | 521,664 | `routed_shared_nvfp4_down_residual` |
| 109,182,976 | 6.532 | 94.11 % | 6,426,624 | `lmhead_int5_base_coarse_delta` |
| 86,589,440 | 5.181 | **99.96 %** | 40,960 | `nvfp4_qkv_h48` |
| 67,108,864 | 4.015 | **99.99 %** | 4,096 | `dense_gate_up_swiglu` |
| 64,901,120 | 3.883 | **100.00 %** | 672 | `oproj_act_h48` |
| 62,914,560 | 3.764 | 99.01 % | 629,880 | `sliding_fused_attn_ring` |
| 43,450,368 | 2.600 | 99.63 % | 159,744 | `shared_nvfp4_swiglu_qmv_rows1_halved` |
| 40,894,464 | 2.447 | 99.13 % | 359,424 | `residual_rms_router` |
| 33,554,432 | 2.008 | **99.99 %** | 4,096 | `dense_down_residual` |
| 23,592,960 | 1.412 | **99.99 %** | 2,680 | `full_fused_attn_grow` |
| 7,864,320 | 0.471 | 97.30 % | 122,880 | `gate_sp_h64` |
| 1,966,080 | 0.118 | 96.43 % | 40,960 | `gate_sp_h48` |
| ≤ 526,848 each | 0.1172 total (1,958,848 B) | mixed | — | 10 tail families (lmhead exact/argmax, `rmsbfloat16`, `gather_front`, `vn_copy`, `prefill_router_tournament`, `residual_rms_bf16`, `embedding_rope_atlas`, `argmax`) |

**Every family carrying ≥ 1 % of `B` is ≥ 94 % exclusive, and the eight largest
weight families are ≥ 99.96 %.** Total traversal provably read exactly once:
**1,661,717,366 B = 99.4205 % of `B`**. The pro-rata remainder, 9,685,066 B =
0.5795 % = 16.07 µs/step, is a *loose* upper bound dominated by an artefact
described next; the tight bound is the 0.177 % above.

### 1.3 The one above-SLC multi-read buffer is a false positive

Exactly one buffer larger than the ~24 MiB SLC is bound by two readers: the
392 MiB BF16 `lm_head` table (411,041,792 B = 100,352 × 2048 × 2). Its readers
are dispatch 402 `lmhead_exact_winner` (grid 32×1×1, group 32×1×1 — *one*
threadgroup) and dispatch 403 `lmhead_exact_fused_int5_sparse_refine`
(grid 802,816×1×1, group 256×1×1).

Neither traverses it. The solver already runs a two-tier lm_head: the bulk read
is dispatch 400 on the **INT5-compressed** table (109,182,976 B traversed,
6.53 % of `B`, one call), and the BF16 table is touched only where the coarse
pass leaves a tie. The accepted census prices `lmhead_exact_winner` at **512 B**
and `lmhead_exact_fused_int5_sparse_refine` at **526,848 B** of traversal —
together 0.032 % of `B` against a 411 MB binding extent. The apparent 392 MiB
redundancy is a pure binding artefact, which is exactly why §0's caveat had to
be resolved before any headline was quoted.

The second-largest shared buffer, 6,422,528 B of INT5 per-row deltas shared by
dispatches 400 and 403, is bounded the same way: dispatch 403's *entire*
traversal budget is 526,848 B, so it cannot re-read 6.4 MB.

### 1.4 Cache-residency assumption, stated and priced

The per-range reader map has one hole: **a range read twice inside a single
dispatch has one reader and is invisible to it.** Every decode GEMV broadcasts
its small operands to all threadgroups, so this is where the real multiplicity
lives. Measuring it directly (`roundtrip_census.py:stage1b`):

- Issue-level reads of operands ≤ 64 KiB: **4,348,001,680 B/step = 2.60 × `B`.**
- Distinct broadcast working set: **4,174,340 B = 0.2498 % of `B`.**
- **Largest broadcast operand: 32,896 B.** All of them are sub-SLC by three
  orders of magnitude.

**Assumption:** an operand ≤ 32,896 B stays resident across the ≤ 6,272
threadgroups of one dispatch, so its 2.60 × `B` of issue-level re-reads cost no
DRAM traffic.

**Pricing above and below the ~24 MiB SLC threshold, as required:**

- *Above SLC.* Rule 105-E (k): every buffer above the ~24 MiB SLC has
  amplification **exactly 1.00**
  (`research/maple-fern-r105e-decode-bandwidth-efficiency.md:267`). Nothing above
  the threshold is re-read; the above-SLC ratio is 1.0000003, and the 0.0000003
  is `lmhead_exact_winner`'s 512 B.
- *Below SLC.* Priced at the **measured** cost, not assumed to be zero: 105-E
  §3.3 drove a 4 KB buffer to 2.88× issued amplification and measured
  **0.45 µs out of 4371 µs = 0.010 % of the step**
  (`…r105e…md:112-116`). That is the error bar on the headline ratio:
  **1.00177 ± 0.010 % of step time.**
- *Falsification.* If the assumption were wrong and residency were zero, the
  broadcast traffic alone would cost 4,348,001,680 / 602.7e9 = **7,214 µs/step**
  against a measured M5 step of **4,141.5 µs** — a 1.74× physical impossibility.
  The assumption is therefore confirmed by contradiction, not merely asserted.

---

## 2. Stage 2 — intermediate round-trip census

227 buffers are written and read inside the step; their total binding extent is
2,416,776 B and **not one of them is above the SLC**. Grouping the 527
write→read pairs by family pair, and pricing a fusion generously as removing
*both* the store and the reload (`saved = 2 × round-trip bytes`):

| saved B | % `B` | µs | % `cs` | n | gap | same enc | writer → reader | writer grid / group (tgs) | reader grid / group (tgs) | geom match |
|---|---|---|---|---|---|---|---|---|---|---|
| 983,040 | 0.0588 | 1.63 | 0.0248 | 30 | 2 | 30/30 | `sliding_fused_attn_ring` → `oproj_act_h64` | 32768×1×1 / 1024×1×1 (32) | 16384×1×1 / 64×1×1 (256) | no |
| 802,816 | 0.0480 | 1.33 | 0.0203 | 1 | 1 | 1/1 | `lmhead_int5_base_coarse_delta` → `lmhead_coarse_argmax_stage1` | 3211264×1×1 / 512×1×1 (6272) | 224×128×1 / 224×1×1 (128) | no |
| 638,976 | 0.0382 | 1.06 | 0.0161 | 39 | 1 | 39/39 | `routed_nvfp4_swiglu_qmv_packed_top8keys` → `routed_shared_nvfp4_down_residual` | 131072×1×1 / 64×1×1 (2048) | 147456×1×1 / 288×1×1 (512) | no |
| 401,408 | 0.0240 | 0.67 | 0.0101 | 1 | 3 | 0/1 | `lmhead_int5_base_coarse_delta` → `lmhead_exact_fused_int5_sparse_refine` | 3211264×1×1 / 512×1×1 (6272) | 802816×1×1 / 256×1×1 (3136) | no |
| 401,408 | 0.0240 | 0.67 | 0.0101 | 1 | 1 | 0/1 | `gather_front` → `vn_copy` | 50176×1×1 / 1024×1×1 (49) | 50176×1×1 / 1024×1×1 (49) | **yes** |
| 401,408 | 0.0240 | 0.67 | 0.0101 | 1 | 1 | 0/1 | `lmhead_exact_fused_int5_sparse_refine` → `gather_front` | 802816×1×1 / 256×1×1 (3136) | 50176×1×1 / 1024×1×1 (49) | no |
| 401,408 | 0.0240 | 0.67 | 0.0101 | 1 | 1 | 1/1 | `gather_front` → `argmax` | 50176×1×1 / 1024×1×1 (49) | 1024×1×1 / 1024×1×1 (1) | no |
| 319,488 | 0.0191 | 0.53 | 0.0081 | 39 | 4 | 39/39 | `residual_rms_router` → `routed_shared_nvfp4_down_residual` | 16384×1×1 / 512×1×1 (32) | 147456×1×1 / 288×1×1 (512) | no |
| 319,488 | 0.0191 | 0.53 | 0.0081 | 39 | 1 | 31/39 | `routed_shared_nvfp4_down_residual` → `rmsbfloat16` | 147456×1×1 / 288×1×1 (512) | 512×1×1 / 512×1×1 (1) | no |
| 319,488 | 0.0191 | 0.53 | 0.0081 | 39 | 1 | 39/39 | `residual_rms_router` → `shared_nvfp4_swiglu_qmv_rows1_halved` | 16384×1×1 / 512×1×1 (32) | 16384×1×1 / 64×1×1 (256) | no |
| 245,760 | 0.0147 | 0.41 | 0.0062 | 30 | 1 | 18/30 | `oproj_act_h64` → `residual_rms_router` | 16384×1×1 / 64×1×1 (256) | 16384×1×1 / 512×1×1 (32) | no |
| 245,760 | 0.0147 | 0.41 | 0.0062 | 30 | 1 | 30/30 | `rmsbfloat16` → `nvfp4_qkv_h64` | 512×1×1 / 512×1×1 (1) | 327680×1×1 / 64×1×1 (5120) | no |
| 245,760 | 0.0147 | 0.41 | 0.0062 | 10 | 1–2 | 6/10 | `full_fused_attn_grow` → `oproj_act_h48` | — | — | no |
| 79,872 | 0.0048 | 0.13 | 0.0020 | 39 | 3 | 39/39 | `residual_rms_router` → `routed_nvfp4_swiglu_qmv_packed_top8keys` | — | — | no |
| 79,872 | 0.0048 | 0.13 | 0.0020 | 39 | 3 | 39/39 | `shared_nvfp4_swiglu_qmv_rows1_halved` → `routed_shared_nvfp4_down_residual` | — | — | no |
| 73,728 | 0.0044 | 0.12 | 0.0019 | 9 | 1 | 9/9 | `oproj_act_h48` → `residual_rms_router` | — | — | no |
| 73,728 | 0.0044 | 0.12 | 0.0019 | 9 | 1 | 9/9 | `rmsbfloat16` → `nvfp4_qkv_h48` | — | — | no |
| 39,936 | 0.0024 | 0.07 | 0.0010 | 39 | 2 | 39/39 | `residual_rms_router` → `prefill_router_tournament` | — | — | no |
| 32,768 | 0.0020 | 0.05 | 0.0008 | 1 | 1 | 1/1 | `dense_gate_up_swiglu` → `dense_down_residual` | — | — | no |
| ≤ 8,192 each | 0.0045 total (75,528 B) | 0.13 | 0.0019 | — | — | — | 14 further pairs (embedding→rms, rms→gate, residual_rms_bf16→dense, gate_sp→oproj, prefill_router→down_residual, lmhead argmax→winner, …) | — | — | — |

**Total if every one of the 33 family pairs were fused: 6,181,640 B = 0.3698 %
of `B` = 10.26 µs/step = 0.1562 % of `cs`.** The gate is 1.2 % of `B`; the sum of
*all* fusions is **3.24× short**, and the best single pair is **20.4× short**.

Rule 77 note: **only one nominated pair has matching grid and threadgroup
geometry** (`gather_front` → `vn_copy`, both 50176×1×1 / 1024×1×1, 49
threadgroups). Every other pair changes both grid and threadgroup shape across
the boundary, which is precisely why they are separate dispatches: the writer
and reader parallelise over different axes. Fusing them is not a matter of
deleting a barrier — it requires re-deriving one side's decomposition, and the
2.60 × `B` broadcast traffic in §1.4 shows the reader's operands are already
cache-resident, so the fused kernel would save no DRAM traffic it does not
already save.

---

## 3. Stage 3 — legality and editability triage

Nothing reaches the gate, so this section records *why* each candidate is
also hard, in gate-descending order, and whether it is even submittable.

| rank | candidate | % `B` (gate 1.2) | short by | legality — blocking DAG edges | Rule 90 editability |
|---|---|---|---|---|---|
| 1 | `sliding_fused_attn_ring` → `oproj_act_h64` | 0.0588 | 20.4× | **blocked**: `gate_sp_h64` is dispatched between the write and the read in all 30 instances; the o-projection consumes the gate scalar, so fusion must also absorb `gate_sp_h64` | ✅ editable (`Sources/MLXFastModel/`) |
| 2 | `lmhead_int5_base_coarse_delta` → `lmhead_coarse_argmax_stage1` | 0.0480 | 25.0× | legal (gap 1, same encoder, no intervening dispatch) but geometry 6272 tgs → 128 tgs is a full reduction-shape change | ✅ editable |
| 3 | `routed_nvfp4_swiglu_qmv_packed_top8keys` → `routed_shared_nvfp4_down_residual` | 0.0382 | 31.4× | legal (gap 1, same encoder ×39) but 2048 tgs → 512 tgs and the reader gathers a different expert-major layout | ✅ editable |
| 4 | `lmhead_int5_base_coarse_delta` → `lmhead_exact_fused_int5_sparse_refine` | 0.0240 | 50.0× | **blocked**: `lmhead_coarse_argmax_stage1` and `lmhead_exact_winner` both sit between, and the refine pass is *defined* by the threshold the winner computes — a true serial data dependence | ✅ editable |
| 5 | `gather_front` → `vn_copy` | 0.0240 | 50.0× | legal, **and the only geometry-identical pair in the step** | ✅ editable (`Vendor/mlx-swift/.../kernels/copy.metal`, `indexing/gather_front.h`) |
| 6 | `lmhead_exact_fused_int5_sparse_refine` → `gather_front` | 0.0240 | 50.0× | legal, crosses an encoder boundary | ✅ editable |
| 7 | `gather_front` → `argmax` | 0.0240 | 50.0× | legal; reader is a 1-threadgroup reduction | ✅ editable (`arg_reduce.metal`, AOT — needs metallib rebuild) |
| 8 | `residual_rms_router` → `routed_shared_nvfp4_down_residual` | 0.0191 | 62.9× | **blocked**: three families intervene ×39 (`shared_nvfp4_swiglu…`, `prefill_router_tournament`, `routed_nvfp4_swiglu…`) | ✅ editable |
| 9–33 | all remaining pairs | ≤ 0.0191 each, 0.1096 combined (1,831,688 B) | ≥ 62.9× | mixed | — |

Editability is not the binding constraint here — unlike #617, where the
mechanism lived in non-editable `device.cpp`, **every candidate in this table is
inside `editablePaths`** (97 entries, no wildcards). The binding constraint is
arithmetic: the whole family is worth 0.37 % of `B`.

---

## 4. Preregistered outcome

**N-ONCE** (Rule 72 outcome 1). The ratio is ≈ 1.00 and I said so in the first
line. Consequences the advisor can rely on:

1. **The "fuse dispatches to cut bytes" family is closed for decode.** Ceiling
   0.547 % of `B` = 0.231 % of `cs` (Stage 1 redundancy 0.177 % + Stage 2 round
   trips 0.370 %), against a 1.2 % gate — 2.19× short even if every single
   candidate were free and legal, which §3 shows they are not.
2. **`B` is not inflated.** Prior work priced the decode DRAM floor as
   `B / BW` = 2773.1 µs = 66.96 % of the M5 step. This census confirms `B` is
   very nearly the *distinct* footprint, so that floor is real and cannot be
   attacked by removing duplicate reads. Combined with #617 (70.6 % of the step
   is genuine serial data dependence, headroom 1 group = 0.0198 % of `cs`),
   two independent "remove overhead" families are now both closed with numbers.
3. **The remaining lever is bytes-per-weight, not bytes-per-read.** Every one of
   the eight largest families is ≥ 99.96 % exclusive. To move `B` you must make
   each weight byte smaller or read fewer weights — not read them fewer times.
4. **The solver's two-tier lm_head is already the byte-optimal shape** for its
   6.53 % of `B`: bulk INT5 (109.2 MB) plus 527 KB of sparse BF16 refine, i.e.
   0.13 % of the 392 MiB exact table.

**N-INSTRUMENT did not fire**, but honesty requires naming what it would have
covered. The dropped `offset` argument (§0) means the tracer cannot resolve
*sub-buffer* aliasing: two dispatches binding disjoint slices of one allocation
are recorded as binding the same range. That failure mode makes redundancy look
**larger**, never smaller, so it cannot overturn N-ONCE — it only means the true
ratio is somewhere in [1.0000003, 1.00177] rather than pinned. Fixing it is a
one-line change to `trace_dag.patch:101` if a future question needs slice
resolution.

---

## 5. Null cells (Rule 79)

- No buffer above the ~24 MiB SLC is genuinely read twice. The one candidate was
  a binding artefact (§1.3). **Null.**
- No intermediate tensor is above the SLC; the largest is 401,408 B. Every
  intermediate round trip is an SLC-resident store/reload. **Null at DRAM
  granularity.**
- 32 of 33 nominated fusion pairs have mismatched grid *and* threadgroup
  geometry. **Null on the "just merge the kernels" hypothesis.**
- No candidate, and no combination of candidates, clears the 1.2 %-of-`B` gate.
  **Null — no receipt spent.**
- Zero official receipts consumed, as instructed.

## 6. Reproduction

```bash
python3 research/r106g/scripts/read_census.py       # Stage 1 + per-range reader map
python3 research/r106g/scripts/roundtrip_census.py  # Stage 1b broadcast + Stage 2
python3 research/r106g/scripts/family_breakdown.py  # Stage 1 family table
python3 research/r106g/scripts/stage3_triage.py     # Stage 3 geometry + legality
```

All four read only the committed trace at
`research/artifacts/fern-r106g/dispatch_raw.tsv` and the accepted census at
`research/artifacts/fern-r105d/decode-byte-census.json`; none runs the model.
Outputs: `read_census.json`, `roundtrip_census.json`, `family_breakdown.json`,
`stage3_triage.json` under `research/artifacts/fern-r106g/`.

```bash
python3 research/r106g/scripts/log_wandb.py         # publishes the census to W&B
```

W&B run: <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/omdt3epj>
(`r106g-redundant-read-census`, id `omdt3epj`, state `finished`). It carries
every headline number in this report as summary keys, plus an `analysis`
artifact holding the four JSON censuses, the trace report, this document, and
the four analysis scripts.

## 7. Suggested follow-ups (not implemented)

- The `dense_gate_up_swiglu` + `dense_down_residual` pair is 6.02 % of `B` in two
  dispatches with only 32,768 B of round trip — i.e. an already byte-optimal
  dense block. Worth checking whether the *routed* path could adopt the same
  single-pair shape, but that is an arithmetic-intensity question, not a
  redundant-read one.
- `nvfp4_qkv_h64` is 19.43 % of `B` at 100 % exclusivity. Any further decode win
  almost certainly has to come from that cell, via bytes-per-weight.
- Rule 92 (mine, #617) said the dispatch-scheduling family reopens only with a
  mechanism that *removes a data dependence*. This census is the search for such
  a mechanism on the byte axis, and it found none worth a receipt. I suggest
  extending Rule 92 to cover fusion-for-bytes explicitly so a third student does
  not re-run this search.
- **A genuinely independent third estimate of `B` is buildable but was out of
  scope here** (§0.1). It needs two instrument changes: (a) a one-line fix at
  `research/r106c/scripts/trace_dag.patch:101` to add the dropped `offset`
  argument, which turns binding extents into real sub-buffer ranges; and
  (b) capture of the MoE gather indices, without which a routed dispatch is
  indistinguishable from one reading all 256 experts. With both, summing the
  trace directly would yield a third `B` independent of both r105-D and
  tanjiro's ledger. Given that (a) alone would only *tighten* the redundancy
  bound already below the gate — it can only shrink apparent redundancy, never
  grow it — I would not spend a round on this for its own sake, but it is the
  right foundation if any future round needs per-dispatch traversal truth.
