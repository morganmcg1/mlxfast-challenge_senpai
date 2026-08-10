import Foundation

enum LagunaConstants {
    static let hiddenSize = 2_048
    static let headDim = 128
    static let fullAttentionHeads = 48
    static let slidingAttentionHeads = 64
}

// Every gate below defaults ON in the runtime (`env != "0"`), so the resolved
// emission this ledger compiles is the one the scored decode path dispatches.
let lagunaNvfp4QmvSignCarryEnabled = true
let lagunaNvfp4QmvSeedElisionEnabled = true
let lagunaNvfp4ScaleFoldEnabled = true
let lagunaE4M3SignDomainCertified = true

func lagunaGatedAffineOProjNVFP4Source(
    heads: Int,
    signCarry: Bool = lagunaNvfp4QmvSignCarryEnabled,
    seedElide: Bool = lagunaNvfp4QmvSeedElisionEnabled,
    preActivatedGate: Bool = false,
    laneMajor: Bool = false,
    pairwise: Bool = false,
    numSimdgroups: Int = 2,
    resultsPerSimdgroup: Int = 4
) -> String {
    let scaleFold = lagunaNvfp4ScaleFoldEnabled
    let weightScale = scaleFold ? "" : " * 16384.0f"



    let scaleDecode = signCarry
        ? (lagunaE4M3SignDomainCertified
            ? "ushort sraw = ushort(sbits) << 7;\n"
                + "        float scale = float(as_type<half>(sraw));"
            : "ushort sraw = ushort(sbits + (sbits & 128)) << 7;\n"
                + "        float scale = float(as_type<half>(sraw));")
        : "ushort sraw = ushort(sbits & 127) << 7;\n"
            + "        half sconverted = as_type<half>(sraw);\n"
            + "        float scale = float((sbits & 128) ? -sconverted : sconverted);"



    let accumDecl = seedElide ? "float accum;" : "float accum = 0.0f;"
    let firstAccum = seedElide
        ? "if (j == 0) {\n"
            + "                accum =\n"
            + "                    (x_thread[8 * j] * v04.x +\n"
            + "                     x_thread[8 * j + 1] * v15.x +\n"
            + "                     x_thread[8 * j + 2] * v26.x +\n"
            + "                     x_thread[8 * j + 3] * v37.x);\n"
            + "            } else {\n"
            + "                accum +=\n"
            + "                    (x_thread[8 * j] * v04.x +\n"
            + "                     x_thread[8 * j + 1] * v15.x +\n"
            + "                     x_thread[8 * j + 2] * v26.x +\n"
            + "                     x_thread[8 * j + 3] * v37.x);\n"
            + "            }"
        : "accum +=\n"
            + "                (x_thread[8 * j] * v04.x +\n"
            + "                 x_thread[8 * j + 1] * v15.x +\n"
            + "                 x_thread[8 * j + 2] * v26.x +\n"
            + "                 x_thread[8 * j + 3] * v37.x);"
    let extract = """
                const uint xe = c & 0x0F0F0F0Fu;
                const uint ge = xe | (xe << 3);
                const uint yo = c & 0xF0F0F0F0u;
                const uint go = yo | (yo >> 3);
                const uint p0 = (ge << 9) & 0x8E008E00u;
                const uint p1 = (go << 8) & 0x8E008E00u;
                const uint p2 = (ge << 1) & 0x8E008E00u;
                const uint p3 = go & 0x8E008E00u;
"""
    let gateSetup = preActivatedGate ? "" : """
threadgroup float gt[gate_heads];
if(lid<gate_heads){
    float l=float(gate_logits[lid]);
    float g;
    if(metal::isnan(l)) g=NAN;
    else {
        float hi=metal::max(l,0.0f);
        float lo=metal::min(l,0.0f);
        g=(metal::isinf(lo)||metal::isinf(hi))?hi:hi+log1p(metal::exp(lo-hi));
    }
    gt[lid]=float(bfloat(g));
}
threadgroup_barrier(mem_flags::mem_threadgroup);
"""
    let loadInput = preActivatedGate
        ? """
float g=float(gate_values[column>>head_shift]);
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(bfloat(float(xp[i])*g));
"""
        : """
float g=gt[column>>head_shift];
for(uint i=0;i<values_per_thread;++i)
    x_thread[i]=float(bfloat(float(xp[i])*g));
"""







    let nibDiv = pairwise ? 4 : 2
    let laneIdx = pairwise ? "(simd_lid >> 1)" : "simd_lid"
    let scaleSetup =
        laneMajor
        ? """
const device uint8_t* nq = scale_nibbles +
    out_row * (in_vec_size_g / \(nibDiv)) +
    \(laneIdx) * (in_vec_size_g / 64);
const device uint8_t* bs = scale_bases + out_row;
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;
uint nsh = 0;
"""
        : """
const device uint8_t* sc = weight_scales +
    out_row * in_vec_size_g + simd_lid;
"""
    let scaleRead =
        laneMajor
        ? """
const uint8_t rb = bs[row];
    const bool esc = rb == 0xFFu;
    const device uint8_t* sp = esc
        ? (sc + row * in_vec_size_g)
        : (nq + row * (in_vec_size_g / \(nibDiv)));
    const uint8_t raw = sp[0];
    uint8_t sbits = esc ? raw : uint8_t(rb + ((raw >> nsh) & 0x0Fu));
"""
        : "uint8_t sbits = sc[row * in_vec_size_g];"
    let scaleAdvance =
        laneMajor
        ? """
sc += block_size / group_size;
nq += nsh >> 2;
nsh ^= 4;
"""
        : "sc += block_size / group_size;"
    let resultZeros = Array(repeating: "0.0f", count: resultsPerSimdgroup)
        .joined(separator: ", ")
    return """
constexpr uint in_vec_size = \(heads * LagunaConstants.headDim);
constexpr uint out_vec_size = \(LagunaConstants.hiddenSize);
constexpr uint gate_heads = \(heads);
constexpr uint head_shift = 7;
constexpr uint group_size = 16;
constexpr uint values_per_thread = 16;
constexpr uint codes_per_thread = values_per_thread / 8;
constexpr uint block_size = values_per_thread * 32;
constexpr uint results_per_simdgroup = \(resultsPerSimdgroup);
constexpr uint num_simdgroups = \(numSimdgroups);
constexpr uint in_vec_size_g = in_vec_size / group_size;

uint tile = threadgroup_position_in_grid.x;
uint lid = thread_position_in_threadgroup.x;
uint simd_gid = simdgroup_index_in_threadgroup;
uint simd_lid = thread_index_in_simdgroup;

\(gateSetup)

uint out_row = tile * (num_simdgroups * results_per_simdgroup) +
    simd_gid * results_per_simdgroup;
const device uint32_t* ws =
    (const device uint32_t*)weight_codes +
    out_row * (in_vec_size / 8) + simd_lid * codes_per_thread;
\(scaleSetup)
const device bfloat* xp = attention_output + simd_lid * values_per_thread;

thread float x_thread[values_per_thread];
thread float result[results_per_simdgroup] = {\(resultZeros)};

uint column = simd_lid * values_per_thread;
for (uint k = 0; k < in_vec_size; k += block_size) {
    \(loadInput)

    for (uint row = 0; row < results_per_simdgroup; ++row) {
        const device uint32_t* wl = ws + row * (in_vec_size / 8);
        \(scaleRead)
        \(scaleDecode)
        \(accumDecl)
        #pragma unroll
        for (uint j = 0; j < codes_per_thread; ++j) {
            const uint c = wl[j];
            \(extract)
            const float2 v04 = float2(as_type<half2>(p0))\(weightScale);
            const float2 v15 = float2(as_type<half2>(p1))\(weightScale);
            const float2 v26 = float2(as_type<half2>(p2))\(weightScale);
            const float2 v37 = float2(as_type<half2>(p3))\(weightScale);
            \(firstAccum)
            accum +=
                (x_thread[8 * j + 4] * v04.y +
                 x_thread[8 * j + 5] * v15.y +
                 x_thread[8 * j + 6] * v26.y +
                 x_thread[8 * j + 7] * v37.y);
        }
        result[row] += scale * accum;
    }

    ws += block_size / 8;
    \(scaleAdvance)
    xp += block_size;
    column += block_size;
}

for (uint row = 0; row < results_per_simdgroup; ++row) {
    result[row] = simd_sum(result[row] * 4194304.0f);
    if (simd_lid == 0) {
        projected[out_row + row] = bfloat(result[row]);
    }
}
"""
}

let a = CommandLine.arguments
print(lagunaGatedAffineOProjNVFP4Source(
    heads: Int(a[1])!, preActivatedGate: true, laneMajor: true, pairwise: true,
    numSimdgroups: Int(a[2])!, resultsPerSimdgroup: Int(a[3])!), terminator: "")
