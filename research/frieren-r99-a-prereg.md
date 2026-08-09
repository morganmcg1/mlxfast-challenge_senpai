# r99-A preregistration

Written 2026-08-09T14:18:49Z, before any r99-A timing number was produced or
read. Committed on top of `9462c68a4c6271f23b5966d813be056b05654c8e`.

- assignment `maple-r98-a-decode-attn-qmv-mlp`, revision `r99-a-rev1`, PR #539
- base `c6c66344d9848d95158edc31f31943aabe4de079` on
  `codex/mlxfast-maple-20260804-advisor`
- host: Apple M4 Pro, 20 GPU cores, 48 GB, `applegpu_g16s` (gen 16).
  Ranked hardware is M5 Max, 40 GPU cores, `applegpu_g17s` (gen 17).

## 1. Static audit, established before measurement

These are byte facts from `git show`, not timing claims, so recording them here
does not contaminate the preregistration.

The current base differs from `e510bb3d` in exactly two textually disjoint
mechanisms, and in nothing else. Two independently written generators compose
to reproduce the historical text byte for byte:

| variant | generator invocation | sliding literal | vs base | full literal | vs base |
| --- | --- | --- | --- | --- | --- |
| `base` | (none) | 10242 | +0 | 12422 | +0 |
| `d4` | `gen4deep.py 4` | 14328 | +4086 | 12422 | +0 |
| `d8` | `gen4deep.py 8` | 22492 | +12250 | 12422 | +0 |
| `epi` | `frieren_r99_epilogue.py float4` | 10015 | -227 | 12422 | +0 |
| `d4epi` | both | **14101 == `e510bb3d`** | +3859 | 12422 | +0 |
| `epiboth` | `epi` + same on full kernel | 10015 | -227 | **12195 == `e510bb3d`** | -227 |

Three independent confirmations:

1. `gen4deep.py 2` reproduces the shipped base file byte for byte (`cmp` clean).
   The frontier's 2-deep loop *is* this generator at depth 2, so depth 4 differs
   from the base by templated slot count alone.
2. `d4epi` reproduces the `e510bb3d` sliding kernel byte for byte, and its
   +3859 B is exactly the delta the assignment quotes.
3. `epiboth` reproduces the `e510bb3d` full kernel byte for byte. The +227 B
   the assignment records as unexplained on `laguna_full_fused_attn_grow_v1`
   is exactly, and only, the lost `float4` epilogue.

So the rebase dropped **three** mechanisms, not two: loop depth on the sliding
kernel, and the r85-c `float4` merge epilogue on *both* attention kernels. The
epilogue regression was not in the assignment's audit.

## 2. Was 2-deep a deliberate M5-measured improvement or a reconciliation casualty?

**Casualty.** The base's sliding loop is byte-identical to `gen4deep.py 2`,
which is our own pre-r96 text. The organizer lineage never contained r96, so
nothing in it ever measured 4-deep and chose against it. Same for the epilogue:
`epiboth` reconstructs `e510bb3d` exactly, so the frontier holds the pre-r85-c
form, not a measured revision of it.

## 3. Rungs

Deviation from the brief, declared in advance: the brief's rung 1 says to port
the old loop body back. I port **only the loop**, keeping the frontier epilogue,
and measure the epilogue as its own rung. Comment 4 of the assignment requires
mechanism and codegen separation, the two edits are textually disjoint, and
`d4epi` proves the pair still composes to the old text exactly.

| rung | arm | mechanism |
| --- | --- | --- |
| 0 | `base` vs `base` | harness null on this host today |
| 1 | `base` vs `d4` | sliding loop 2-deep -> 4-deep |
| 1b | `base` vs `epi` | sliding `float4` merge epilogue (r85-c restoration) |
| 1c | `base` vs `d4epi` | both, additivity test |
| 1d | `d4` vs `base` | flipped revert control, sign must invert |
| 1e | `base` vs `d8` | depth dose-response, research only |
| 1f | `base` vs `epiboth`, kernel `laguna_full_fused_attn_grow_v1` | full-kernel epilogue, evidence only, not shipped |
| 2 | router weight prefetch | only after rung 1 and 1b report |
| 3 | combination | only if rung 1 or 2 is non-negative in isolation |

The candidate will not ship a change to `laguna_full_fused_attn_grow_v1`; rung
1f is measured only so the advisor can decide whether to open a follow-up.

Rung 1e uses a fix to `gen4deep.py`, which silently truncated `SUFFIX` to four
slots for any depth above 4 and would have emitted a stride-8 loop body that
only advances four slots. That is a wrong-answer generator bug, not a
performance question; the guard now rejects depths that do not divide the 16
rows per simdgroup.

## 4. Predictions, recorded before measurement

Probe resolution on this host is +/-0.5 % of kernel time, which is +/-3.2
us/step against the 636.0 us/step sliding decode pool quoted by the advisor.

| rung | predicted probe delta at K=16 and K=20 | predicted us/step | predicted score |
| --- | --- | --- | --- |
| 1 `d4` | -2.9 %, interval [-4.0 %, -2.0 %] | -18.4 | +0.28 % |
| 1b `epi` | -3.3 %, interval [-4.5 %, -2.0 %] | -21.0 | +0.32 % |
| 1c `d4epi` | -6.1 % if additive | -39.4 | +0.60 % |
| 1e `d8` | see falsifier below | | |

Rung 1's prediction is r96's own kernel-level measurement of this exact change
(-3.0 % at <= 1 threadgroup per core, about 12 sigma against a +/-0.25 % null),
rescaled to the advisor's actual 636.0 us/step pool rather than r96's estimated
290 us/step pool. Rung 1b's is r85-c's end-to-end -20.98 us/step [-22.76,
-19.19] on this kernel, converted to a percentage of the same pool.

K=16 is 0.8 threadgroups per core on this host and matches the ranked M5
sliding occupancy of 32 threadgroups over 40 cores. r96 argues K=20 is the
faithful M4 proxy. Both are headline; K=24 and above are 1.2 threadgroups per
core or more and are structurally blind to this effect on a 20-core part.

## 5. Falsifiers and bars

At least as strict as the brief.

- **Codegen-tax falsifier.** Merged PR #540 showed that on this exact kernel
  every prefetch-expressing rewrite regressed the base by +5 to +7 % with a
  flat dose-response, because the restructuring stopped the compiler forming
  the fused predicated `T_LOAD` diamond. If rung 1e's depth-8 delta is not
  monotonically better than depth 4, or if any rung lands at +2 % or worse,
  I treat that as an implementation defect or codegen tax and say so, not as a
  refutation of pipelining.
- **Occupancy confound.** Every arm must report
  `staticThreadgroupMemoryLength`, `maxTotalThreadsPerThreadgroup` and
  `threadExecutionWidth`. Both epilogue forms occupy the same `4 * BN * BDP`
  floats by construction, so threadgroup memory must be invariant. Any drop in
  `maxTotalThreadsPerThreadgroup` is a register-pressure confound; per the AGX
  residency table the first cliff is 1024 -> 896 threads per core, a 12.5 %
  thread-level parallelism loss that would swamp the effect being measured.
- **Sign control.** Rung 1d must invert rung 1's sign to within the null. If it
  does not, the probe is not measuring what I think and no rung is reported.

Bars:

- **GO to an official receipt** only if the shipped candidate's probe evidence
  predicts at least +40 us/step, with the whole 95 % interval on the improving
  side, and the occupancy and sign controls clean. On the recorded predictions
  rungs 1 and 1b together sit at about 39.4 us/step, that is, right at the bar
  and about 1.3 sigma on a single official receipt. I record now that the
  honest expected outcome is therefore **a kernel-level result with receipts
  declined**, and that I will only spend a receipt if the measured deltas beat
  the predictions above.
- **REVERT** a rung if its delta at both K=16 and K=20 is non-improving and the
  95 % interval excludes the predicted improvement.
- **STOP** as soon as two rungs are clean negatives at the probe resolution, or
  after rung 3.

Six official receipts are available. Declining them when the probe shows
sub-resolution effects is explicitly endorsed by the programme, and a clean
negative on the 636.0 us/step pool is a real deliverable.

## 6. Reporting commitment

Whatever the numbers say, the result document will carry: this preregistration
verbatim, the static audit table above, per-rung probe output with the full K
ladder and the pipeline-property table, the sign control, the byte report
against the full base SHA, upstream equivalence and `swift test` status for any
rung that ships, and an explicit statement of which predictions were wrong.

All inherited figures (636.0 us/step pool, 0.015280 % score per us/step,
r96's -3.0 %, r85-c's -20.98 us/step) are PROVISIONAL and are labelled as such.
