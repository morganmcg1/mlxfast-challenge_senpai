# Step 0 offline census - fp_gather_qmm_rhs_expert_nax probe arms

Generated on M4 Pro (applegpu_g16s). The nax kernel family is NOT selected on
gen-16 hardware, so these are static/compile-time counts from the shipped
metallib AIR (post-optimisation), not runtime measurements.

Tool: xcrun -sdk macosx metal-objdump --disassemble <lib>.metallib
Source: research/nax_msl_compile_check.sh with PROBE={0,1,2,3}

Legend: `pb` = `DARKBLOOM_NAX_GATHER_PROBE` arm (0 = default/off, 1 = M2
double-MMA, 2 = S2 double weight load+dequant, 3 = B2 two extra barriers per
k-iteration). `mma` counts `__tensorops_impl_matmul2d_op_run_cooperative`
call sites, `barr` counts `air.wg.barrier`, `dev_ld` / `tg_ld` / `tg_st` count
`addrspace(1)` loads and `addrspace(3)` loads/stores.

## Per-kernel static counts (post-optimisation AIR)

```
pb  kernel                      mma  barr  dev_ld  tg_ld  tg_st  ir_lines
0   2048x1024_bk64_pb0            1     7       6      4      5       537
0   512x2048_bk64_pb0             1     5       6      2      4       583
1   2048x1024_bk64_pb1            2     7       6      4      5       697
1   512x2048_bk64_pb1             2     5       6      2      4       743
2   2048x1024_bk64_pb2            1     8       8      4      6       583
2   512x2048_bk64_pb2             1     6       8      2      5       629
3   2048x1024_bk64_pb3            1     9       6      4      5       539
3   512x2048_bk64_pb3             1     7       6      2      4       585
```

## Confound verdict per arm

| arm | intended delta | observed static delta vs pb0 | verdict |
|-----|----------------|------------------------------|---------|
| M2 (pb1) | 2x MMA, no extra memory traffic | mma 1 -> 2; barr / dev_ld / tg_ld / tg_st all unchanged | CLEAN. CSE defeated: the shadow `tile_matmad_nax` survived to shipped AIR and pulled in zero extra loads, stores or barriers. |
| S2 (pb2) | 2x weight load + dequant | dev_ld 6 -> 8 (weight + scales); barr +1 (the extra WAR barrier); tg_st +1 (second stage into the same `Ws`); mma unchanged | CLEAN, but carries one extra barrier by construction. Pure staging cost is recovered as `dS2 - dB2/2`. |
| B2 (pb3) | +2 `threadgroup_barrier` per k-iteration | barr +2; every other counter unchanged | CLEAN. The compiler did not merge or hoist the added barriers. |

All added call sites live inside the same loop nests as the originals, so the
static ratio equals the dynamic ratio.

Barrier accounting for the decomposition: the stock k-loop body executes
2 barriers per iteration. B2 raises that to 4 (exactly doubled), S2 to 3.
Therefore

    pure double-MMA cost       = dM2
    pure double-staging cost   = dS2 - dB2/2
    pure barrier/schedule cost = dB2

## Pipeline reflection (M4 Pro, maxThreadgroupMemoryLength = 32768 B)

`swift research/tanjiro_metallib_stats.swift` - every arm, both shapes:

    threadgroupMemoryLength       = 9232 B
    maxTotalThreadsPerThreadgroup = 1024
    threadExecutionWidth          = 32

`floor(32768 / 9232) = 3` resident threadgroups per core = 12 simdgroups per
core. The hardware simdgroup limit (96 per core, i.e. 24 threadgroups) is not
binding. Threadgroup memory is the binding occupancy term and it is identical
across all four arms.

Honest caveat: `maxTotalThreadsPerThreadgroup = 1024` is saturated and
therefore uninformative about register pressure for this kernel (`Dtile` alone
is `[4 x <8 x float>]` = 32 floats per thread, so a 32-register-per-thread
budget is implausible). The M4 reflection cannot rule out an M5
register-pressure or occupancy change for M2, which carries +5 allocas versus
pb0 (`Dshadow` plus the extra cooperative-tensor operand buffers).

Mitigating asymmetry: falsification is confound-free. If `dM2 ~ 0` then H1 is
dead regardless of register pressure. Only a LARGE `dM2` admits the occupancy
alternative explanation, and that case is flagged rather than claimed.

## Inertness of the default arm (pb0)

Adding `int probe = 0` as a defaulted trailing template parameter must not
perturb the shipped default kernel. Verified by generating front-end IR from
the assignment base revision and from the worktree, both at PROBE=0 with
neither the trailing template argument nor the `_pb<n>` name suffix emitted
(this mirrors what `quantized.cpp` does when the probe is off):

    diff /tmp/inert_base.ll /tmp/inert_head.ll   ->   70 lines

All 70 lines are Itanium mangling of threadgroup globals gaining `Li0E`, the
new trailing template argument:

    ...Lb1ELb1EE...Ws_storage   ->   ...Lb1ELb1ELi0EE...Ws_storage

affecting `Ws_storage`, `bounds.0`, `bounds.1` and their uses. Normalising
`ELi0EE` -> `EE` makes every diff line pair up exactly (zero unmatched lines),
so no instruction, operand, type or ordering differs.

`research/nax_safety_rig.sh` reports this as a FAIL because it uses a byte
comparison (`cmp -s`) that cannot see through symbol mangling. The check is
deliberately left strict; the mangling-only nature of the difference is
recorded here rather than papered over by weakening the rig.

Safety rig summary (`BASE_REV=0a90df98d0982dbbcbfe774e49d6fe99b24e1c18`, BK=64):

    1. compile + link + emit-IR for all arms .................. PASS
    2. pb0 inertness (byte-identical IR) ...................... FAIL (mangling only, see above)
    3. non-empty MMA body (3 cooperative matmul calls) ........ PASS
    4. widened device load reachable (kSrcBytes=16 widened) ... PASS
    5. wide-load guard negative control ....................... PASS
    6. mlx-generated twin matches header ...................... PASS

