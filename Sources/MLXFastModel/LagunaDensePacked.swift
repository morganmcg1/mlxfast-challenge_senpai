import Foundation
import MLX
import MLXFastCore
import MLXNN

// Lossless 12-bit re-encoding of layer 0's dense BF16 MLP planes.
//
// Decode reads the whole dense MLP once per step and both fused kernels sit
// at 96-97% of the memory ceiling, so the only lever left is bytes moved. A
// census of the three planes shows the mantissas are incompressible (the
// trailing-zero histogram is exactly geometric) but every plane carries a
// per-intermediate-channel exponent scale: with one best-placed 15-wide
// exponent window per channel, 99.985% of weights fit a 4-bit delta.
//
// So a weight becomes `sign << 7 | mantissa7` in a byte plane plus a 4-bit
// exponent delta in a nibble plane, over a uint8 base per channel: 12 bits
// against 16, exactly. Delta code 15 escapes to the stock BF16 element, which
// stays resident because prefill still runs stock `Linear` on it.
//
// The channel axis differs per plane. `gate_proj`/`up_proj` are
// `[intermediate, hidden]`, so the channel is the OUTPUT row and one base
// covers a whole 2048-long reduction; `down_proj` is `[hidden, intermediate]`,
// so the channel is the REDUCTION index and the base is an 8192-byte vector
// every row re-reads out of cache. Basing either plane on the wrong axis
// escapes ~95% of weights.
// Opt-in, not opt-out. The encoding is lossless and certified, but the unpack
// ALU measured ~2.2x the bandwidth it buys, so enabling it costs ~0.7% of score
// (see research/maple-nezuko-pr85-dense-mlp-lossless-repack.md). Default OFF so
// that merging this branch for its write-up cannot regress the frontier.
let lagunaDensePackedEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_DENSE_PACKED"] == "1"

/// Init-time full-tensor certificate. Off by default: the packer only ever
/// publishes a bank that reproduces its source, and the check costs a second
/// pass over 50M weights.
let lagunaDensePackedVerifyEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_DENSE_PACKED_VERIFY"] == "1"

/// One re-encoded BF16 plane. `bases` is indexed by row when
/// `baseAxis == 0` and by reduction index when `baseAxis == 1`.
struct LagunaDensePackedBank {
    let mantissas: MLXArray
    let nibbles: MLXArray
    let bases: MLXArray
    let escapes: Int

    var arrays: [MLXArray] { [mantissas, nibbles, bases] }
    var byteCount: Int { mantissas.size + nibbles.size + bases.size }
}

final class LagunaDenseMLPBanks {
    let gateUp: LagunaDensePackedBank
    let down: LagunaDensePackedBank
    let gateWeight: MLXArray
    let upWeight: MLXArray
    let downWeight: MLXArray

    init(
        gateUp: LagunaDensePackedBank, down: LagunaDensePackedBank,
        gateWeight: MLXArray, upWeight: MLXArray, downWeight: MLXArray
    ) {
        self.gateUp = gateUp
        self.down = down
        self.gateWeight = gateWeight
        self.upWeight = upWeight
        self.downWeight = downWeight
    }

    var arrays: [MLXArray] { gateUp.arrays + down.arrays }
}

extension LagunaRuntimeMLP {
    /// Re-encodes layer 0's three dense planes and retains them on this
    /// instance. Returns the new arrays so the caller can batch one `eval`.
    /// Declines -- leaving `_densePackedBanks` nil and the stock BF16 path
    /// untouched -- unless every plane packs losslessly. Guards the same
    /// exact dense configuration `prepareFusedDenseGateUp()` does, so it
    /// never fires on the NVFP4 shared-expert instance of this class.
    func prepareDensePacked() -> [MLXArray] {
        let hidden = LagunaConstants.hiddenSize
        let intermediate = LagunaConstants.denseIntermediateSize
        guard lagunaDensePackedEnabled, _densePackedBanks == nil,
            type(of: gateProj) == Linear.self,
            type(of: upProj) == Linear.self,
            type(of: downProj) == Linear.self,
            gateProj.bias == nil, upProj.bias == nil, downProj.bias == nil,
            gateProj.weight.dtype == .bfloat16,
            upProj.weight.dtype == .bfloat16,
            downProj.weight.dtype == .bfloat16,
            gateProj.weight.dims(intermediate, hidden),
            upProj.weight.dims(intermediate, hidden),
            downProj.weight.dims(hidden, intermediate)
        else {
            return []
        }
        let gate = gateProj.weight
        let up = upProj.weight
        let down = downProj.weight
        guard let packedGate = lagunaDensePackPlane(gate, baseAxis: 0),
            let packedUp = lagunaDensePackPlane(up, baseAxis: 0),
            let packedDown = lagunaDensePackPlane(down, baseAxis: 1)
        else {
            return []
        }
        if lagunaDensePackedVerifyEnabled {
            guard lagunaDensePackedReproduces(packedGate, gate, baseAxis: 0),
                lagunaDensePackedReproduces(packedUp, up, baseAxis: 0),
                lagunaDensePackedReproduces(packedDown, down, baseAxis: 1)
            else {
                lagunaTrace("dense packed declined (reconstruction mismatch)")
                return []
            }
        }
        // The gate/up kernel indexes one fused bank exactly as the stock fused
        // BF16 bank did -- gate rows first -- so row arithmetic is unchanged.
        let gateUp = LagunaDensePackedBank(
            mantissas: contiguous(
                concatenated([packedGate.mantissas, packedUp.mantissas], axis: 0)),
            nibbles: contiguous(concatenated([packedGate.nibbles, packedUp.nibbles], axis: 0)),
            bases: contiguous(concatenated([packedGate.bases, packedUp.bases], axis: 0)),
            escapes: packedGate.escapes + packedUp.escapes)
        let banks = LagunaDenseMLPBanks(
            gateUp: gateUp, down: packedDown,
            gateWeight: gate, upWeight: up, downWeight: down)
        _densePackedBanks = banks
        lagunaTrace(
            "dense packed gate/up \(gateUp.byteCount)B esc \(gateUp.escapes)"
                + " down \(packedDown.byteCount)B esc \(packedDown.escapes)")
        return banks.arrays
    }
}

/// Chooses, per channel, the 15-wide exponent window covering the most
/// weights, then emits the mantissa byte plane, the delta nibble plane and
/// the uint8 base vector. `baseAxis` names the axis the base is indexed by:
/// 0 for a base per row, 1 for a base per reduction index.
private func lagunaDensePackPlane(_ w: MLXArray, baseAxis: Int) -> LagunaDensePackedBank? {
    let rows = w.dim(0)
    let cols = w.dim(1)
    guard cols.isMultiple(of: 2) else { return nil }
    let reduceAxis = 1 - baseAxis
    let bits = contiguous(w).view(dtype: .uint16).asType(.int32)
    let exponent = (bits >> 7) & 0x00FF

    // A window start below the channel minimum is dominated by the minimum
    // itself, and one above `max - 14` cannot beat `max - 14`, so searching
    // `min ..< min + 13` is exhaustive for every channel whose exponent span
    // is at most 26 -- the measured maximum is 26. A wider channel still
    // encodes correctly, just with more escapes.
    let low = exponent.min(axis: reduceAxis, keepDims: true).asType(.int32)
    var best = low
    var bestCoverage = lagunaDenseWindowCoverage(exponent, low, reduceAxis)
    for offset in 1...12 {
        let start = low + MLXArray(Int32(offset))
        let coverage = lagunaDenseWindowCoverage(exponent, start, reduceAxis)
        let better = coverage .> bestCoverage
        best = which(better, start, best)
        bestCoverage = which(better, coverage, bestCoverage)
    }
    guard best.min().item(Int32.self) >= 0, (best.max().item(Int32.self) + 14) <= 255
    else {
        return nil
    }

    let delta = exponent - best
    let escaped = (delta | (14 - delta)) .< 0
    let code = which(escaped, MLXArray(Int32(15)), delta).asType(.uint8)
    // `sign << 7 | mantissa7`: the BF16 low byte carries the exponent LSB in
    // bit 7, not the sign, so this is a rebuilt byte and not a raw slice.
    let mantissas = contiguous((((bits >> 8) & 0x80) | (bits & 0x7F)).asType(.uint8))
    // Byte b holds element 2b in bits 0-3 and 2b+1 in bits 4-7, so the ushort
    // a lane loads for its four columns yields code `i` at `(dq >> 4i) & 15`.
    let u16 = contiguous(code).view(dtype: .uint16)
    let nibbles = contiguous(
        ((u16 & MLXArray(UInt16(0x000F)))
            | ((u16 >> 4) & MLXArray(UInt16(0x00F0)))).asType(.uint8))
    let bases = contiguous(best.asType(.uint8).reshaped([baseAxis == 0 ? rows : cols]))
    return LagunaDensePackedBank(
        mantissas: mantissas, nibbles: nibbles, bases: bases,
        escapes: Int(escaped.asType(.int32).sum().item(Int32.self)))
}

/// Count of weights whose exponent lands in `[start, start + 14]`, per channel.
private func lagunaDenseWindowCoverage(
    _ exponent: MLXArray, _ start: MLXArray, _ reduceAxis: Int
) -> MLXArray {
    let shifted = exponent - start
    return ((shifted | (14 - shifted)) .>= 0).asType(.int32)
        .sum(axis: reduceAxis, keepDims: true)
}

/// Init-time certificate: decode all three planes with MLX and require every
/// BF16 bit pattern to match the plane the stock kernels read.
func lagunaDensePackedReproduces(
    _ bank: LagunaDensePackedBank, _ plane: MLXArray, baseAxis: Int
) -> Bool {
    let rows = plane.dim(0)
    let cols = plane.dim(1)
    guard bank.mantissas.dims(rows, cols), bank.nibbles.dims(rows, cols / 2),
        bank.bases.dim(0) == (baseAxis == 0 ? rows : cols)
    else {
        return false
    }
    let packedNibbles = bank.nibbles.asType(.int32).reshaped([rows, cols / 2, 1])
    let code = concatenated([packedNibbles & 0x0F, (packedNibbles >> 4) & 0x0F], axis: 2)
        .reshaped([rows, cols])
    let bases = bank.bases.asType(.int32).reshaped(baseAxis == 0 ? [rows, 1] : [1, cols])
    let mantissas = bank.mantissas.asType(.int32)
    let rebuilt = ((mantissas & 0x80) << 8) | ((bases + code) << 7) | (mantissas & 0x7F)
    let stock = contiguous(plane).view(dtype: .uint16).asType(.int32)
    let decoded = which(code .== 15, stock, rebuilt)
    return (decoded .!= stock).asType(.int32).sum().item(Int32.self) == 0
}

// The two kernels below are the stock `laguna_dense_gate_up_swiglu_bf16_v1`
// and `laguna_dense_down_residual_bf16_v1` with the weight FETCH replaced and
// nothing else: same tiling, same activation loads, same accumulation order,
// same epilogue. A decoded weight is `bfloat_bits << 16`, which is exactly
// what `float(bfloat)` produces, so every product and partial sum is
// bit-identical to the stock kernel's.
//
// `LAGUNA_ANY_ESCAPE` tests four packed codes at once: ANDing a nibble word
// with its own 1/2/3-bit right shifts leaves bit 4i set exactly when code i
// is 0b1111, and `0x1111` selects those four bits.
//
// The escape source pointer is null on the fast path so the compiler cannot
// prove the stock element dereferenceable and hoist the load out of the
// branch -- hoisting it would restore the traffic this kernel exists to
// remove.
private let lagunaDensePackedDecodePrelude = """
#define LAGUNA_ANY_ESCAPE(dq) \\
    ((((dq) & ((dq) >> 1)) & (((dq) >> 2) & ((dq) >> 3)) & 0x1111u) != 0u)
#define LAGUNA_DECODE(mv, dq, base, i) \\
    as_type<float>( \\
        ((uint(mv[i]) & 0x80u) << 24) \\
        | (((base) + ((uint(dq) >> (4u * (i))) & 15u)) << 23) \\
        | ((uint(mv[i]) & 0x7Fu) << 16))
"""

private let lagunaDensePackedGateUpKernel = MLXFast.metalKernel(
    name: "laguna_dense_packed_gate_up_swiglu_v1",
    inputNames: ["input", "wm", "wd", "wb", "gate_stock", "up_stock"],
    outputNames: ["activated"],
    source: lagunaDensePackedDecodePrelude + """

constexpr uint in_vec_size = 2048;
constexpr uint nibble_stride = in_vec_size / 2;
constexpr uint output_width = 8192;
constexpr uint rows_per_thread = 4;
constexpr uint values_per_thread = 4;
constexpr uint block_width = 128;
constexpr uint blocks = in_vec_size / block_width;
constexpr uint rows_per_group = 64;

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;

uint row_base = tile * rows_per_group + simd_group * rows_per_thread;

thread float gate_result[rows_per_thread] = {0.0f, 0.0f, 0.0f, 0.0f};
thread float up_result[rows_per_thread] = {0.0f, 0.0f, 0.0f, 0.0f};
thread float coefficients[values_per_thread];
thread uint gate_base[rows_per_thread];
thread uint up_base[rows_per_thread];
for (uint row = 0; row < rows_per_thread; ++row) {
    gate_base[row] = uint(wb[row_base + row]);
    up_base[row] = uint(wb[output_width + row_base + row]);
}

uint column = lane * values_per_thread;
for (uint block = 0; block < blocks; ++block) {
    const vec<bfloat, 4> c4 =
        *((const device vec<bfloat, 4>*)(input + column));
    for (uint i = 0; i < values_per_thread; ++i) {
        coefficients[i] = float(c4[i]);
    }
    for (uint row = 0; row < rows_per_thread; ++row) {
        uint r = row_base + row;
        uint elt = r * in_vec_size + column;
        uint nib = r * nibble_stride + (column >> 1);

        const uchar4 gm = *((const device uchar4*)(wm + elt));
        const ushort gd = *((const device ushort*)(wd + nib));
        const device bfloat* gs =
            LAGUNA_ANY_ESCAPE(gd) ? (gate_stock + elt) : (const device bfloat*)0;
        if (gs) {
            const vec<bfloat, 4> gw = *((const device vec<bfloat, 4>*)gs);
            for (uint i = 0; i < values_per_thread; ++i) {
                gate_result[row] += float(gw[i]) * coefficients[i];
            }
        } else {
            for (uint i = 0; i < values_per_thread; ++i) {
                gate_result[row] +=
                    LAGUNA_DECODE(gm, gd, gate_base[row], i) * coefficients[i];
            }
        }

        const uchar4 um =
            *((const device uchar4*)(wm + (output_width + r) * in_vec_size + column));
        const ushort ud =
            *((const device ushort*)(
                wd + (output_width + r) * nibble_stride + (column >> 1)));
        const device bfloat* us =
            LAGUNA_ANY_ESCAPE(ud) ? (up_stock + elt) : (const device bfloat*)0;
        if (us) {
            const vec<bfloat, 4> uw = *((const device vec<bfloat, 4>*)us);
            for (uint i = 0; i < values_per_thread; ++i) {
                up_result[row] += float(uw[i]) * coefficients[i];
            }
        } else {
            for (uint i = 0; i < values_per_thread; ++i) {
                up_result[row] +=
                    LAGUNA_DECODE(um, ud, up_base[row], i) * coefficients[i];
            }
        }
    }
    column += block_width;
}

for (uint row = 0; row < rows_per_thread; ++row) {
    for (ushort delta = 16; delta >= 1; delta >>= 1) {
        gate_result[row] += metal::simd_shuffle_down(gate_result[row], delta);
        up_result[row] += metal::simd_shuffle_down(up_result[row], delta);
    }
}
if (lane == 0) {
    for (uint row = 0; row < rows_per_thread; ++row) {
        bfloat gate = bfloat(gate_result[row]);
        bfloat up = bfloat(up_result[row]);
        bfloat exp_abs = metal::exp(metal::abs(gate));
        bfloat denominator = bfloat(1) + exp_abs;
        bfloat y = bfloat(1) / denominator;
        bfloat sigmoid = gate < bfloat(0) ? y : bfloat(1) - y;
        bfloat silu = bfloat(gate * sigmoid);
        activated[row_base + row] = bfloat(silu * up);
    }
}
""",
    ensureRowContiguous: true
)

func lagunaDensePackedGateUpSwiGLU(
    _ input: MLXArray, banks: LagunaDenseMLPBanks
) -> MLXArray {
    lagunaDensePackedGateUpKernel(
        [
            input, banks.gateUp.mantissas, banks.gateUp.nibbles, banks.gateUp.bases,
            banks.gateWeight, banks.upWeight,
        ],
        grid: ((LagunaConstants.denseIntermediateSize / 64) * 512, 1, 1),
        threadGroup: (512, 1, 1),
        outputShapes: [[1, 1, LagunaConstants.denseIntermediateSize]],
        outputDTypes: [.bfloat16]
    )[0]
}

private let lagunaDensePackedDownKernel = MLXFast.metalKernel(
    name: "laguna_dense_packed_down_residual_v1",
    inputNames: ["activated", "wm", "wd", "wb", "down_stock", "residual"],
    outputNames: ["output"],
    source: lagunaDensePackedDecodePrelude + """

constexpr uint in_vec_size = 8192;
constexpr uint nibble_stride = in_vec_size / 2;
constexpr uint rows_per_thread = 4;
constexpr uint values_per_thread = 4;
constexpr uint block_width = 128;
constexpr uint blocks = in_vec_size / block_width;
constexpr uint rows_per_group = 16;

uint tile = threadgroup_position_in_grid.x;
uint simd_group = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;

uint row_base = tile * rows_per_group + simd_group * rows_per_thread;

thread float result[rows_per_thread] = {0.0f, 0.0f, 0.0f, 0.0f};
thread float coefficients[values_per_thread];

uint column = lane * values_per_thread;
for (uint block = 0; block < blocks; ++block) {
    const vec<bfloat, 4> c4 =
        *((const device vec<bfloat, 4>*)(activated + column));
    for (uint i = 0; i < values_per_thread; ++i) {
        coefficients[i] = float(c4[i]);
    }
    const uchar4 bq = *((const device uchar4*)(wb + column));
    for (uint row = 0; row < rows_per_thread; ++row) {
        uint elt = (row_base + row) * in_vec_size + column;
        const uchar4 mv = *((const device uchar4*)(wm + elt));
        const ushort dq = *((const device ushort*)(
            wd + (row_base + row) * nibble_stride + (column >> 1)));
        const device bfloat* stock =
            LAGUNA_ANY_ESCAPE(dq) ? (down_stock + elt) : (const device bfloat*)0;
        if (stock) {
            const vec<bfloat, 4> w = *((const device vec<bfloat, 4>*)stock);
            for (uint i = 0; i < values_per_thread; ++i) {
                result[row] += float(w[i]) * coefficients[i];
            }
        } else {
            for (uint i = 0; i < values_per_thread; ++i) {
                result[row] += LAGUNA_DECODE(mv, dq, uint(bq[i]), i) * coefficients[i];
            }
        }
    }
    column += block_width;
}

for (uint row = 0; row < rows_per_thread; ++row) {
    for (ushort delta = 16; delta >= 1; delta >>= 1) {
        result[row] += metal::simd_shuffle_down(result[row], delta);
    }
}
if (lane == 0) {
    for (uint row = 0; row < rows_per_thread; ++row) {
        bfloat down = bfloat(result[row]);
        output[row_base + row] = bfloat(residual[row_base + row] + down);
    }
}
""",
    ensureRowContiguous: true
)

func lagunaDensePackedDownResidual(
    _ activated: MLXArray, residual: MLXArray, banks: LagunaDenseMLPBanks
) -> MLXArray {
    lagunaDensePackedDownKernel(
        [
            activated, banks.down.mantissas, banks.down.nibbles, banks.down.bases,
            banks.downWeight, residual,
        ],
        grid: ((LagunaConstants.hiddenSize / 16) * 128, 1, 1),
        threadGroup: (128, 1, 1),
        outputShapes: [[1, 1, LagunaConstants.hiddenSize]],
        outputDTypes: [.bfloat16]
    )[0]
}
