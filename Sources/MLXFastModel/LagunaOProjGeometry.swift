import Foundation

/// Rows per simdgroup for the decode o_proj NVFP4 QMV.
///
/// The shipped o_proj kernel is the geometric outlier of the decode GEMV pool:
/// `results_per_simdgroup = 4`, `num_simdgroups = 2`, so a 2048-row projection
/// dispatches only **256 threadgroups** at 512 B/thread, against the QKV
/// projection's 5120 threadgroups at 32 B/thread. The o_proj kernels also run
/// 9.1 % (h64) and 16.6 % (h48) further from the machine's 256.7 GB/s
/// asymptotic DRAM peak than their QKV siblings, on a byte total that is
/// 96.9 % irreducible NVFP4 payload (see
/// `research/nezuko-r117-stage0-attn-byte-floor.md`). Geometry is the only
/// unpinned term left in the family.
///
/// Changing this value only decides **which** simdgroup owns **which** output
/// row. For a fixed output row the accumulation is still 32 lanes x
/// `values_per_thread = 16` serial FP32 adds over the same K-block order,
/// closed by the same `simd_sum`. The summation tree is untouched, so every
/// setting is bit-identical to the default -- unlike a load-width widening,
/// which repartitions the per-lane chain and is not bit-exact.
///
/// `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP` accepts 1, 2, 4 (default, shipped),
/// 8 or 16. Anything else falls back to 4. 16 is included so the ladder can
/// show an interior optimum rather than only an edge: at 16 rows the o_proj
/// dispatch is 4096 threads in 64 threadgroups, which is certainly too few
/// threads to fill a 20-core GPU even though its in-flight load count is
/// unchanged. The value is baked into the Metal
/// function name (`_rps1ns2`, `_rps2ns2`, `_rps8ns2`, ...) because MLX caches
/// compiled pipelines by name and a sweep whose arms share one name silently
/// measures the first-built geometry every time.
///
/// The default is 2, not the historical 4: on a 20-core M4 Pro a blocked,
/// interleaved 8-block ladder measured 2 at -79.4 us/token, CI95 [-87.8,
/// -71.1], against a byte-identical control whose interval covered zero. The
/// kernel is occupancy-limited here, not bandwidth-limited -- halving the rows
/// per simdgroup doubles the threadgroup count from 256 to 512 and adds activation
/// re-reads, and it still wins, which is why the byte model predicted the
/// wrong sign. See research/nezuko-r117-c-final-report.md F7.
let lagunaOProjRowsPerSimdgroup: Int = {
    guard
        let raw = ProcessInfo.processInfo.environment[
            "DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP"],
        let value = Int(raw),
        [1, 2, 4, 8, 16].contains(value)
    else {
        return 2
    }
    return value
}()

/// Simdgroups per threadgroup for the decode o_proj NVFP4 QMV.
///
/// This is the *other* half of the geometry. `rowsPerSimdgroup` sets how many
/// output rows one simdgroup accumulates from a single resident copy of the
/// input activation vector -- it is an **activation-reuse** factor, and it
/// moves the total activation bytes re-read per step. `simdgroupsPerThreadgroup`
/// moves only how those simdgroups are *packaged* into dispatchable tiles: at a
/// fixed `rowsPerSimdgroup` the number of simdgroups, and therefore the
/// activation traffic, is identical, but the threadgroup count halves when this
/// doubles.
///
/// The pair is what makes the ladder attributable. `rps=8, ns=2` and
/// `rps=4, ns=4` both dispatch **128 threadgroups** on a 2048-row projection,
/// but only the first cuts activation traffic (157.3 MB/step vs 314.6). If
/// `rps=8` wins and `ns=4` does not, the win is reuse. If both move together,
/// the effect is tail quantization across the 20-core GPU and has nothing to do
/// with bytes. Without this control the ladder confounds the two perfectly.
///
/// `DARKBLOOM_OPROJ_SIMDGROUPS` accepts 2 (default, shipped) or 4. 1 is
/// deliberately rejected: the gated-affine prologue fills a threadgroup array
/// with `if (lid < gate_heads)`, so a 32-thread threadgroup would leave the
/// upper gate entries uninitialised and silently corrupt the output rather than
/// fail a bit-exactness check.
let lagunaOProjSimdgroups: Int = {
    guard
        let raw = ProcessInfo.processInfo.environment[
            "DARKBLOOM_OPROJ_SIMDGROUPS"],
        let value = Int(raw),
        [2, 4].contains(value)
    else {
        return 2
    }
    return value
}()

/// Threads per o_proj threadgroup: 32 lanes per simdgroup.
let lagunaOProjThreads: Int = 32 * lagunaOProjSimdgroups

/// Metal function-name suffix for the selected geometry.
///
/// The empty-suffix case is pinned to `rps=4, ns=2` -- the *historical* shipped
/// geometry -- and deliberately not moved to the new `rps=2` default. Keeping
/// it here means the shipped configuration emits `_rps2ns2`, which is the exact
/// function the certified R2 arm measured, so the landed default and the
/// evidence for it are the same compiled pipeline rather than merely the same
/// source.
let lagunaOProjRowsPerSimdgroupSuffix: String =
    (lagunaOProjRowsPerSimdgroup == 4 && lagunaOProjSimdgroups == 2)
    ? ""
    : "_rps\(lagunaOProjRowsPerSimdgroup)ns\(lagunaOProjSimdgroups)"

/// Zero-initialiser list for the kernel's `thread float result[...]` array.
let lagunaOProjResultInit: String =
    Array(repeating: "0.0f", count: lagunaOProjRowsPerSimdgroup)
    .joined(separator: ", ")

/// Threadgroups for an `outVec`-row o_proj dispatch:
/// `lagunaOProjSimdgroups` simdgroups per threadgroup,
/// `lagunaOProjRowsPerSimdgroup` rows each. Returns nil when the row count does
/// not divide, so the caller keeps the shipped geometry rather than dropping or
/// duplicating rows.
func lagunaOProjTiles(outVec: Int) -> Int? {
    let rowsPerTile = lagunaOProjSimdgroups * lagunaOProjRowsPerSimdgroup
    guard outVec % rowsPerTile == 0 else { return nil }
    return outVec / rowsPerTile
}
