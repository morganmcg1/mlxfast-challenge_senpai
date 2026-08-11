// Decide, on this host, whether MLX's NAX kernel families are reachable.
//
// Run with:  swift research/fern_r109f_nax_probe.swift
//
// This replicates `mlx::core::metal::is_nax_available()`
// (Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:913) and the
// `arch_gen_` parsing at device.cpp:560-572 exactly, so the answer here is the
// answer the runtime will give.  It matters because every `_nax` kernel family
// is invisible to a local A/B on a host that fails this check: the local build
// silently takes the non-NAX fallback, so an arm that only edits `_nax` code
// measures as exactly 0.00 % locally no matter what it does on the ranked host.
//
// NAX-gated (invisible locally when this prints false):
//   matmul.cpp:957            steel_matmul_regular_axpby_nax   (dense GEMM, prefill)
//   matmul.cpp:925            steel_gemm_splitk_axpby_nax
//   matmul.cpp:2290           gather_mm_rhs_nax
//   matmul.cpp:2373           steel_gemm_segmented_nax
//   quantized.cpp:728         qmm            -> nax
//   quantized.cpp:951         gather_qmm     -> nax
//   quantized.cpp:1669        gather_qmm_rhs -> nax
//   quantized.cpp:1906        GatherQMM      -> gather_qmm_rhs_nax
//   sdpa.cpp:177              sdpa_full_self_attention_nax     (attention, prefill)
//
// NOT NAX-gated (identical kernel family locally and on the ranked host):
//   quantized.cpp:238  qmv          quantized.cpp:420   qvm
//   quantized.cpp:1025 gather_qmv   quantized.cpp:1091  gather_qvm
//   sdpa.cpp:329 sdpa_vector        sdpa.cpp:418 sdpa_vector_2pass
//     (dispatched when query_sequence_length <= 8, i.e. decode)
//
// So on a host that prints false: decode is measurable, prefill is not.

import Metal

let d = MTLCreateSystemDefaultDevice()!
print("device.name      = \(d.name)")

// device.cpp:560 — MLX_METAL_GPU_ARCH overrides the probed architecture string.
let override = ProcessInfo.processInfo.environment["MLX_METAL_GPU_ARCH"] ?? ""
let archName = override.isEmpty ? d.architecture.name : override
print("architecture     = \(archName)\(override.isEmpty ? "" : "  (MLX_METAL_GPU_ARCH override)")")

// device.cpp:564-572 — arch_gen_ is the two digits before the trailing letter.
let chars = Array(archName.utf8)
var agTens = 0
var agOnes = 0
if chars.count >= 3 {
    agTens = Int(chars[chars.count - 3]) - 48
    agOnes = Int(chars[chars.count - 2]) - 48
    if !(agTens < 10 && agTens >= 0) { agTens = 0 }
    if !(agOnes < 10 && agOnes >= 0) { agOnes = 0 }
}
let archGen = agTens * 10 + agOnes
let archLast = Character(UnicodeScalar(chars[chars.count - 1]))
print("arch_gen_        = \(archGen)")
print("arch.back()      = \(archLast)")

// device.cpp:917-927 — macOS 26.2 availability AND gen >= (arch == 'p' ? 18 : 17).
var osOK = false
if #available(macOS 26.2, *) { osOK = true }
let need = (archLast == "p") ? 18 : 17
let naxOK = osOK && (archGen >= need)
print("macOS >= 26.2    = \(osOK)")
print("gen requirement  = >= \(need)")
print("is_nax_available = \(naxOK)")
print("")
if naxOK {
    print("VERDICT: NAX kernels run here; _nax arms are locally measurable.")
} else {
    let why = osOK ? "GPU generation \(archGen) < \(need)" : "macOS older than 26.2"
    print("VERDICT: NAX kernels DO NOT run here (\(why)).")
    print("  Any arm that edits only _nax code will measure 0.00 % locally.")
    print("  Locally measurable: decode (qmv/qvm/gather_qmv/gather_qvm, sdpa_vector).")
    print("  NOT locally measurable: prefill (steel_gemm_fused_nax, qmm/gather_qmm nax,")
    print("                          sdpa_full_self_attention_nax).")
}
