# R122-A — is nezuko's o_proj win throughput, absorption, or redistribution?

Assignment: PR #718, `maple-r122-a-oproj-absorption-decomposition`, revision
`r122-a-rev1`. Base `fa2a81b7624f6afa807830eb9ad7eb6d38c3d11d` (advisor HEAD
after the R117-C merge). Host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU
generation 16 — no `_nax` kernels, so this is M4-directional evidence for a
mechanism question, not a ranked number.

## §0 Verdict

*Pending — this file is committed before any data is taken, so that the
pre-registration in §1 provably precedes the measurement.*

## §1 Pre-registration (committed 2026-08-11T08:47Z, before any data)

Definitions, all in µs/step, all arms from one binary at base `fa2a81b7`,
selected only by `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP`:

- `C4` = `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=4` (pre-merge geometry, 256 TGs,
  512 simdgroups).
- `R2` = `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=2` (shipped default, 512 TGs,
  1024 simdgroups).
- `ΔB` = (R2 − C4) o_proj family GPU busy, h64 + h48, SPLIT=1, raw (undeflated).
- `ΔT` = (R2 − C4) total GPU busy summed over all kernels, SPLIT=1, raw.
- `ΔW` ≈ −80 µs/token is nezuko's already-measured SPLIT=0 wall delta; it is an
  input to this experiment, not an output of it.

Decision table, fixed in advance:

| finding | verdict |
|---|---|
| `ΔB ≤ −60` and `ΔT ≤ −60`, named neighbours flat | **(A) THROUGHPUT** — K3 was not at the DRAM roof; the byte model double-counts cached activation re-reads and every "% of peak" figure in the corpus needs an audit. |
| `ΔB ∈ [−25, +25]` and `ΔT ∈ [−25, +25]`, and the SPLIT=0 leg shows inter-command-buffer gap falling by ≥ 50 | **(B) ABSORPTION** — byte-level peak claims survive; the purchasable pool is latency absorption, whose M5 transfer must be priced separately and pessimistically. |
| `ΔB ≤ −60` but `ΔT ≈ 0`, or a named neighbour rises by ≥ 40 | **(C) REDISTRIBUTION** — name the neighbour; the residency model becomes a contention model. |
| any arm's dispatch count differs, or the golden hash differs | **VOID** — instrument failure, stop and report. |

If the point estimate lands between bands, the report says so plainly and
publishes the interval and the n that would separate them, rather than forcing
a call.

Negative controls whose busy must be reported per arm: `decode_nvfp4_qkv_h64…`
(K2), `routed_…_swiglu_qmv_packed_top8keys_r1_bf16_v2` (K1),
`routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` (K4),
`sliding_fused_attn_ring_v1`, `full_fused_attn_grow_v1`.

Instrument commitments:

- One binary, env-switched, paired and interleaved, mirrored orders reported
  separately (`C4 R2 R2 C4` then `R2 C4 C4 R2`).
- SPLIT=1 numbers are read **raw**. The additive per-dispatch SPLIT=1 overhead
  (~1.554 µs × calls/step) is identical in both arms because `rps` changes
  threadgroup count and not dispatch count, so it cancels exactly in the paired
  difference. `L-DEFLATE-ONCE`: no deflation inside Leg 1.
- The o_proj rows are matched **by role** (substring on the kernel family), not
  by exact string equality, because nezuko name-suffixes pipelines per geometry
  (`_rps2ns2`). The matched pipeline names are printed per arm and are
  themselves the proof the knob took effect.
- Bimodality screen on every per-run sample set: elevated Sarle's coefficient
  **and** ≥ 2 modes from a smoothed-histogram peak count ⇒ instrument failure.
- Raw per-run samples are dumped under `research/r122a-runs/`.
