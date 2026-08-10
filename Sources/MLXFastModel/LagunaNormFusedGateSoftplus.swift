import Foundation
import MLX
import MLXFast

/// The standalone `rmsbfloat16` attention pre-norm dispatch moves 8 KB and
/// still costs ~3.5 us of GPU busy time plus ~3 us of command-buffer gap, so it
/// is launch-bound, not work-bound. Folding it into the NVFP4 QKV matvec is a
/// measured 1.62x regression on that kernel because each of its 5120
/// threadgroups then recomputes the whole 2048-element normalize. `gate_sp` is
/// the other consumer of `normalized` and launches only `heads / (NS * R)`
/// threadgroups, so hosting the reduction there replicates the elementwise cost
/// a handful of times instead of 5120 while still publishing `normalized`.
///
/// Threadgroup width, not replication, decides whether the fusion pays. The
/// same reduction costs +23.0 us per dispatch over the shipped 64-thread
/// geometry and +7.3 us over 256 threads, and the removed dispatch is worth
/// ~8.7 us. `(NS, R)` moves gate rows between threadgroups at constant
/// arithmetic, so NS=8 simdgroups with one row each keeps the tile count at
/// `heads / 8` while quadrupling the threads available to the reduction.
private let lagunaNormFusedGateSoftplusMode = ProcessInfo.processInfo.environment[
    "DARKBLOOM_NORM_FUSED_GATE_SP"] ?? "1"
private let lagunaNormFusedGateSoftplusEnabled = lagunaNormFusedGateSoftplusMode != "0"

/// Only mode `1` lets the fused kernel be the sole producer of `normalized`.
/// Modes `2`, `3`, and `4` keep the standalone pre-norm dispatch feeding the QKV
/// matvec, so `gate_sp` never joins the QKV critical path; they exist to
/// attribute the paired delta of mode 1 to its parts.
///
///   2  reduction restated in `gate_sp`, `normalized` still stored (unread)
///   3  reduction restated in `gate_sp`, no `normalized` output at all
///   4  no reduction: the shipped gate math at the fused kernel's geometry,
///      still consuming `normalized` from `rmsbfloat16`
///
/// 4-vs-shipped is therefore the pure threadgroup-geometry contrast, 2-vs-4 the
/// pure decoupling contrast, and 3-vs-2 the cost of the unread store.
let lagunaNormFusedGateSoftplusPublishesNormalized = lagunaNormFusedGateSoftplusMode == "1"

/// True when the caller must materialise `rmsbfloat16`'s output and hand it to
/// the fused kernel instead of the residual.
let lagunaNormFusedGateSoftplusConsumesNormalized = lagunaNormFusedGateSoftplusMode == "4"

private let lagunaNormFusedGateSoftplusEmitsNormalized = lagunaNormFusedGateSoftplusMode == "1"
    || lagunaNormFusedGateSoftplusMode == "2"

/// Simdgroups per threadgroup and gate rows per simdgroup. The reduction, the
/// matvec, and the dispatch geometry are all written against these.
private let lagunaNormFusedGateSoftplusSimdgroups = 8
private let lagunaNormFusedGateSoftplusRowsPerSimdgroup = 1

/// The AOT `rms_single_row` laguna fast path restated over `NS` simdgroups.
/// Simdgroup `sg` owns AOT chunks `CPS*sg ..< CPS*sg+CPS`; lane `l` of chunk `g`
/// accumulates the same four contiguous squares in the same order into the same
/// `laguna_norm_sums[g]` slot, so the final 32-lane `simd_sum` sees an operand
/// vector identical to the AOT kernel's `local_sums[0..<32]`. The normalized
/// activation is staged in threadgroup memory because the matvec rereads the
/// whole row once per simdgroup.
private let lagunaNormFusedGateSoftplusPrologue = """
threadgroup float laguna_norm_sums[32];
threadgroup float laguna_norm_inv[1];
threadgroup bfloat laguna_norm_x[K];
constexpr uint CPS = 16 / NS;
if (sg == 0 && lane >= 16) { laguna_norm_sums[lane] = 0; }
for (uint chunk = 0; chunk < CPS; ++chunk) {
    const uint g = sg * CPS + chunk;
    const device bfloat* row_x = residual + g * 128 + lane * 4;
    float acc = 0;
    for (uint i = 0; i < 4; ++i) { float xi = float(row_x[i]); acc += xi * xi; }
    acc = simd_sum(acc);
    if (lane == 0) { laguna_norm_sums[g] = acc; }
}
threadgroup_barrier(mem_flags::mem_threadgroup);
if (sg == 0) {
    float acc = simd_sum(laguna_norm_sums[lane]);
    if (lane == 0) {
        laguna_norm_inv[0] = metal::precise::rsqrt(acc / float(K) + 1.0e-6f);
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);
const float laguna_inv_mean = laguna_norm_inv[0];
{
    LAGUNA_EMIT_SETUP
    for (uint chunk = 0; chunk < CPS; ++chunk) {
        const uint base = (sg * CPS + chunk) * 128 + lane * 4;
        for (uint i = 0; i < 4; ++i) {
            const bfloat v = bfloat(
                norm_weight[base + i] * bfloat(float(residual[base + i]) * laguna_inv_mean));
            laguna_norm_x[base + i] = v;
            LAGUNA_EMIT_STORE
        }
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);
"""

private func lagunaNormFusedGateSoftplusSource(heads: Int) -> String {
    let prologue: String
    let load: String
    if lagunaNormFusedGateSoftplusConsumesNormalized {
        prologue = ""
        load = "normalized_in[col+i]"
    } else {
        let emits = lagunaNormFusedGateSoftplusEmitsNormalized
        prologue =
            lagunaNormFusedGateSoftplusPrologue
            .replacingOccurrences(
                of: "LAGUNA_EMIT_SETUP",
                with: emits ? "const bool laguna_emit = (tile == 0);" : "")
            .replacingOccurrences(
                of: "LAGUNA_EMIT_STORE",
                with: emits ? "if (laguna_emit) { normalized[base + i] = v; }" : "")
        load = "laguna_norm_x[col+i]"
    }
    return """
constexpr uint K=\(LagunaConstants.hiddenSize),GS=32,V=8;
constexpr uint BK=V*32,R=\(lagunaNormFusedGateSoftplusRowsPerSimdgroup);
constexpr uint NS=\(lagunaNormFusedGateSoftplusSimdgroups),KG=K/GS,SS=GS/V;
uint tile=threadgroup_position_in_grid.x;
uint sg=simdgroup_index_in_threadgroup;
uint lane=thread_index_in_simdgroup;
\(prologue)
uint orow=tile*(NS*R)+sg*R;
const device uint8_t* ws=(const device uint8_t*)packed_codes+orow*K+lane*V;
const device bfloat* sc=scales+orow*KG+lane/SS;
const device bfloat* bs=biases+orow*KG+lane/SS;
thread float x[V];
thread float r[R];
for(uint row=0;row<R;++row) r[row]=0.0f;
uint col=lane*V;
for(uint k=0;k<K;k+=BK){
    float sum=0.0f;
    for(uint i=0;i<V;++i){
        x[i]=float(\(load));
        sum+=x[i];
    }
    for(uint row=0;row<R;++row){
        const device uint8_t* wl=ws+row*K;
        float s=float(sc[row*KG]),b=float(bs[row*KG]),a=0.0f;
        for(uint i=0;i<V;++i) a+=x[i]*wl[i];
        r[row]+=s*a+sum*b;
    }
    ws+=BK; sc+=BK/GS; bs+=BK/GS; col+=BK;
}
for(uint row=0;row<R;++row){
    r[row]=simd_sum(r[row]);
    if(lane==0){
        float l=float(bfloat(r[row]));
        float g;
        if(metal::isnan(l)) g=NAN;
        else {
            float hi=metal::max(l,0.0f);
            float lo=metal::min(l,0.0f);
            g=(metal::isinf(lo)||metal::isinf(hi))?hi:hi+log1p(metal::exp(lo-hi));
        }
        gate_values[orow+row]=bfloat(g);
    }
}
"""
}

private let lagunaNormFusedGateSoftplusKernels: [Int: MLXFast.MLXFastKernel] = {
    let inputNames =
        lagunaNormFusedGateSoftplusConsumesNormalized
        ? ["normalized_in", "packed_codes", "scales", "biases"]
        : ["residual", "norm_weight", "packed_codes", "scales", "biases"]
    let outputNames =
        lagunaNormFusedGateSoftplusEmitsNormalized
        ? ["gate_values", "normalized"] : ["gate_values"]
    let suffix =
        lagunaNormFusedGateSoftplusConsumesNormalized
        ? "geom" : (lagunaNormFusedGateSoftplusEmitsNormalized ? "emit" : "noemit")
    var result: [Int: MLXFast.MLXFastKernel] = [:]
    for heads in [LagunaConstants.slidingAttentionHeads, LagunaConstants.fullAttentionHeads] {
        result[heads] = MLXFast.metalKernel(
            name: "laguna_gate_sp_rms_\(suffix)_h\(heads)_v1",
            inputNames: inputNames,
            outputNames: outputNames,
            source: lagunaNormFusedGateSoftplusSource(heads: heads),
            ensureRowContiguous: true)
    }
    return result
}()

/// Emits the attention pre-norm activation and the per-head softplus gate from
/// one dispatch, replacing a separate `rms_norm` launch. Returns `nil` when the
/// fused path does not apply, in which case the caller must keep the two-kernel
/// form.
func lagunaNormFusedGateSoftplus(
    residual: MLXArray, normWeight: MLXArray, normalizedInput: MLXArray?,
    bank: LagunaNativeAffineWeight, heads: Int
) -> (normalized: MLXArray?, gate: MLXArray)? {
    let rowsPerTile =
        lagunaNormFusedGateSoftplusSimdgroups * lagunaNormFusedGateSoftplusRowsPerSimdgroup
    guard lagunaNormFusedGateSoftplusEnabled,
        LagunaConstants.hiddenSize == 2048,
        LagunaConstants.rmsNormEpsilon == 1e-6,
        heads % rowsPerTile == 0,
        bank.mode == .affine, bank.bits == 8, bank.groupSize == 32,
        let biases = bank.biases,
        let kernel = lagunaNormFusedGateSoftplusKernels[heads],
        residual.dtype == .bfloat16,
        residual.dims(1, 1, LagunaConstants.hiddenSize),
        normWeight.dtype == .bfloat16,
        normWeight.dims(LagunaConstants.hiddenSize),
        bank.packedCodes.dims(heads, LagunaConstants.hiddenSize / 4),
        bank.scales.dtype == .bfloat16,
        bank.scales.dims(heads, LagunaConstants.hiddenSize / 32),
        biases.dtype == .bfloat16,
        biases.dims(heads, LagunaConstants.hiddenSize / 32)
    else { return nil }

    var inputs: [MLXArray] = [bank.packedCodes, bank.scales, biases]
    if lagunaNormFusedGateSoftplusConsumesNormalized {
        guard let normalizedInput,
            normalizedInput.dtype == .bfloat16,
            normalizedInput.dims(1, 1, LagunaConstants.hiddenSize)
        else { return nil }
        inputs.insert(normalizedInput, at: 0)
    } else {
        inputs.insert(contentsOf: [residual, normWeight], at: 0)
    }

    let emits = lagunaNormFusedGateSoftplusEmitsNormalized
    let threadsPerTile = 32 * lagunaNormFusedGateSoftplusSimdgroups
    let outputs = kernel(
        inputs,
        grid: ((heads / rowsPerTile) * threadsPerTile, 1, 1),
        threadGroup: (threadsPerTile, 1, 1),
        outputShapes: emits
            ? [[1, 1, heads], [1, 1, LagunaConstants.hiddenSize]] : [[1, 1, heads]],
        outputDTypes: emits ? [.bfloat16, .bfloat16] : [.bfloat16])
    return (normalized: emits ? outputs[1] : nil, gate: outputs[0])
}
