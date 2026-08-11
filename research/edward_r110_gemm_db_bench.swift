// R110-B Stage 0/1: isolated timing rig for the NVFP4 gather-GEMM K loop.
//
// PR #693 (maple-r110-b-gemm-double-buffer-staging). Research-only: this file
// is NOT on benchmark.json's editablePaths and is never compiled by a scored
// build.
//
// Build & run:
//   xcrun swiftc -O research/edward_r110_gemm_db_bench.swift \
//       -o /tmp/edr110 && /tmp/edr110
//
// What it does
// ------------
// Reproduces get_gather_qmm_kernel()'s JIT source composition
// (jit_kernels.cpp:952-975) by extracting the four R"preamble(...)preamble"
// bodies straight out of Vendor/mlx-swift/Source/Cmlx/mlx-generated/*.cpp in
// the order utils, quantized_utils, gemm, fp_quantized, then appending the
// exact get_template_definition() instantiation that quantized.cpp emits for
// the Laguna prefill MoE call (bm16/bn32/bk32/wm1/wn2, gs16, b4, nt).
//
// Variants are produced by *string mutation of that extracted source*, so
// Stage 0 needs no vendored-file edit and no MLX rebuild:
//
//   base   shipped gemm_loop_aligned (2 threadgroup barriers per k-iteration)
//   nobar  the WAR barrier deleted. NUMERICALLY WRONG -- it is a pure timing
//          probe for the upper bound on what removing that barrier can buy.
//   db     real ping-pong double buffering: 2x staging, 1 barrier per
//          k-iteration, loads for tile k issued before the mma for tile k-1.
//   null   empty kernel on the same grid -- dispatch/encode floor control.
//
// Env knobs:
//   ED_REPS=<n>      dispatches per command buffer (default 4)
//   ED_CBS=<n>       timed command buffers per variant slot (default 9)
//   ED_PAIRS=<n>     ABBA pair count (default 4 -> 8 slots per variant)
//   ED_SHAPE=gate_up|down|both  (default both)
//   ED_IDX=multinomial|aligned  (default multinomial) routed-index distribution

import Foundation
import Metal

let stderrHandle = FileHandle.standardError

func log(_ s: String) {
    print(s)
    fflush(stdout)
}

func die(_ s: String) -> Never {
    stderrHandle.write(("FATAL: " + s + "\n").data(using: .utf8)!)
    exit(1)
}

func env(_ k: String) -> String? {
    guard let v = ProcessInfo.processInfo.environment[k], !v.isEmpty else { return nil }
    return v
}

func envInt(_ k: String, _ d: Int) -> Int { Int(env(k) ?? "") ?? d }

func fmt(_ v: Double, _ digits: Int = 3) -> String { String(format: "%.\(digits)f", v) }

func pad(_ s: String, _ w: Int) -> String {
    s.count >= w ? s : String(repeating: " ", count: w - s.count) + s
}

func median(_ xs: [Double]) -> Double {
    precondition(!xs.isEmpty)
    let s = xs.sorted()
    return s.count % 2 == 1 ? s[s.count / 2] : 0.5 * (s[s.count / 2 - 1] + s[s.count / 2])
}

// MARK: - JIT source composition

let repoRoot: String = {
    var d = FileManager.default.currentDirectoryPath
    while d != "/" {
        if FileManager.default.fileExists(atPath: d + "/benchmark.json") { return d }
        d = (d as NSString).deletingLastPathComponent
    }
    die("could not locate repo root (benchmark.json) from cwd")
}()

let genDir = repoRoot + "/Vendor/mlx-swift/Source/Cmlx/mlx-generated"

func extractPreamble(_ file: String) -> String {
    guard let text = try? String(contentsOfFile: genDir + "/" + file, encoding: .utf8) else {
        die("cannot read \(file)")
    }
    guard let open = text.range(of: "R\"preamble(") else { die("no preamble open in \(file)") }
    guard let close = text.range(of: ")preamble\"", range: open.upperBound..<text.endIndex) else {
        die("no preamble close in \(file)")
    }
    return String(text[open.upperBound..<close.lowerBound])
}

// jit_kernels.cpp:952-975 order.
let baseSource: String = {
    var s = ""
    for f in ["utils.cpp", "quantized_utils.cpp", "gemm.cpp", "fp_quantized.cpp"] {
        s += "\n// ---- \(f) ----\n"
        s += extractPreamble(f)
    }
    return s
}()

let kernelName = "nvfp4_gather_qmm_rhs_nt_bfloat16_gs_16_b_4_bm_16_bn_32_bk_32_wm_1_wn_2"
// get_template_definition(kernels.h:402-424) for the shipped Laguna prefill call.
let templateDef = """

template [[host_name("\(kernelName)")]] [[kernel]] decltype(
    fp_gather_qmm_rhs<bfloat16_t, 16, 4, 16, 32, 32, 1, 2, true>)
    fp_gather_qmm_rhs<bfloat16_t, 16, 4, 16, 32, 32, 1, 2, true>;

[[kernel]] void ed_null_kernel(
    device float* sink [[buffer(0)]],
    uint3 tid [[threadgroup_position_in_grid]]) {
  if (tid.x == 0xffffffu) {
    sink[0] = 1.0f;
  }
}

"""

// MARK: - source mutations

let loopAnchor = "METAL_FUNC void gemm_loop_aligned("

func replaceGemmLoopAligned(_ src: String, with body: String) -> String {
    guard let a = src.range(of: loopAnchor) else { die("gemm_loop_aligned not found") }
    guard src.range(of: loopAnchor, range: a.upperBound..<src.endIndex) == nil else {
        die("gemm_loop_aligned found more than once")
    }
    guard let end = src.range(of: "\n}\n", range: a.upperBound..<src.endIndex) else {
        die("gemm_loop_aligned close brace not found")
    }
    return src.replacingCharacters(in: a.lowerBound..<end.upperBound, with: body)
}

// Shipped body minus the WAR barrier. Numerically wrong (iteration k+1's
// staging store can race iteration k's mma read) -- timing probe only.
let nobarBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  for (int k = 0; k < k_iterations; k++) {
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
    loader_a.next();
    loader_b.next();
  }
}

"""

// Ping-pong. `a_tile`/`b_tile` are element counts of one staged tile; the
// caller must have allocated 2x. Both loaders expose a mutable `dst`, so the
// buffer flip needs no loader change.
let dbBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations,
    const int a_tile,
    const int b_tile) {
  if (k_iterations <= 0) {
    return;
  }

  loader_a.load_unsafe();
  loader_b.load_unsafe();
  loader_a.next();
  loader_b.next();
  loader_a.dst += a_tile;
  loader_b.dst += b_tile;
  threadgroup_barrier(mem_flags::mem_threadgroup);

  int cur = 0;
  for (int k = 1; k < k_iterations; k++) {
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    loader_a.next();
    loader_b.next();

    mma_op.mma(As + cur * a_tile, Bs + cur * b_tile);

    threadgroup_barrier(mem_flags::mem_threadgroup);

    cur ^= 1;
    loader_a.dst += cur ? a_tile : -a_tile;
    loader_b.dst += cur ? b_tile : -b_tile;
  }

  mma_op.mma(As + cur * a_tile, Bs + cur * b_tile);
  if (cur) {
    loader_a.dst -= a_tile;
    loader_b.dst -= b_tile;
  }
}

"""

// Same ping-pong, but fully unrolled over buffer parity so no `mma` operand
// address depends on a loop-carried runtime value. Discriminates a real
// mechanism cost from a dynamic-addressing artifact.
let db2Body = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations,
    const int a_tile,
    const int b_tile) {
  if (k_iterations <= 0) {
    return;
  }

  loader_a.load_unsafe();
  loader_b.load_unsafe();
  loader_a.next();
  loader_b.next();
  loader_a.dst += a_tile;
  loader_b.dst += b_tile;
  threadgroup_barrier(mem_flags::mem_threadgroup);

  int k = 1;
  for (; k + 1 < k_iterations; k += 2) {
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    loader_a.next();
    loader_b.next();
    mma_op.mma(As, Bs);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.dst -= a_tile;
    loader_b.dst -= b_tile;

    loader_a.load_unsafe();
    loader_b.load_unsafe();
    loader_a.next();
    loader_b.next();
    mma_op.mma(As + a_tile, Bs + b_tile);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.dst += a_tile;
    loader_b.dst += b_tile;
  }

  if (k < k_iterations) {
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    loader_a.next();
    loader_b.next();
    mma_op.mma(As, Bs);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As + a_tile, Bs + b_tile);
  } else {
    mma_op.mma(As, Bs);
  }
  loader_a.dst -= a_tile;
  loader_b.dst -= b_tile;
}

"""

// Occupancy control: 2x staging allocated, shipped single-buffer schedule.
// Isolates the residency tax of the doubled threadgroup footprint from the
// pipelining benefit. Numerically identical to base.
let dbmemBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations,
    const int a_tile,
    const int b_tile) {
  (void)a_tile;
  (void)b_tile;
  for (int k = 0; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
    loader_a.next();
    loader_b.next();
  }
}

"""

// Roofline split probes. Both are NUMERICALLY WRONG timing probes.
//   noload: staging removed -> mma + barrier cost only.
//   nomma:  mma removed     -> staging + barrier cost only.
let noloadBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  for (int k = 0; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
    loader_a.next();
    loader_b.next();
  }
}

"""

let nommaBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  for (int k = 0; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.load_unsafe();
    loader_b.load_unsafe();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.next();
    loader_b.next();
  }
}

"""

// MARK: - zero-tgmem register prefetch
//
// The db* arms buy overlap with a doubled threadgroup footprint and pay for it
// in residency. The register route buys the same overlap for ~7 registers per
// thread and leaves the staging arrays -- and therefore resident-threadgroup
// count -- exactly as shipped. Both loaders get a `RegTile` holding one
// thread's share of one k-tile, a `prefetch()` that performs only the device
// reads, and a `stage_regs()` that performs only the threadgroup stores.
//
// Bit-exactness: prefetch captures the same uint32 codes `fp4nv_pack4` would
// have produced and the same scale byte, and stage_regs feeds them to the same
// `fp4nv_decode8`; the steel loader holds the identical 16-byte ReadVector.

let steelLoaderAnchor = """
  /* Load from device memory into threadgroup memory - without bound checking */
  METAL_FUNC void load_unsafe() const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      *((threadgroup ReadVector*)(&dst[i * dst_ld])) =
          *((const device ReadVector*)(&src[i * src_ld]));
    }
  }
"""

let steelLoaderRegs = """

  struct RegTile {
    ReadVector v[(BROWS + TROWS - 1) / TROWS];
  };

  METAL_FUNC void prefetch(thread RegTile& r) const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      r.v[i / TROWS] = *((const device ReadVector*)(&src[i * src_ld]));
    }
  }

  METAL_FUNC void stage_regs(const thread RegTile& r) const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      *((threadgroup ReadVector*)(&dst[i * dst_ld])) = r.v[i / TROWS];
    }
  }
"""

let quantLoaderAnchor = """
  void load_unsafe() const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }

    stage();
  }
"""

let quantLoaderRegs = """

  struct RegTile {
    uint32_t c[fp4nv_fast ? (n_reads / 4) : 1];
    uint8_t b[fp4nv_fast ? 1 : (n_reads * bytes_per_pack)];
    uint8_t s;
  };

  void prefetch(thread RegTile& r) const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }
    if constexpr (fp4nv_fast) {
      for (int i = 0; i < n_reads / 4; i++) {
        r.c[i] = fp4nv_pack4(src + i * 4);
      }
    } else {
      for (int i = 0; i < n_reads * bytes_per_pack; i++) {
        r.b[i] = src[i * bytes_per_pack];
      }
    }
    r.s = *scales;
  }

  void stage_regs(const thread RegTile& r) const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }
    if constexpr (fp4nv_fast) {
      const float scale = fp4nv_scale_x16384(r.s);
      for (int i = 0; i < n_reads / 4; i++) {
        T vals[8];
        fp4nv_decode8<T>(r.c[i], scale, vals);
        for (int j = 0; j < 8; j++) {
          dst[i * 8 + j] = vals[j];
        }
      }
    } else {
      T scale = dequantize_scale<T, group_size>(r.s);
      for (int i = 0; i < n_reads; i++) {
        dequantize<T, bits>(r.b[i], scale, dst + i * pack_factor);
      }
    }
  }
"""

func injectRegisterPrefetchLoaders(_ src: String) -> String {
    var s = src
    for (anchor, addition) in [
        (steelLoaderAnchor, steelLoaderRegs),
        (quantLoaderAnchor, quantLoaderRegs),
    ] {
        guard s.components(separatedBy: anchor).count == 2 else {
            die("register-prefetch loader anchor not unique")
        }
        s = s.replacingOccurrences(of: anchor, with: anchor + addition)
    }
    return s
}

func makeRegisterPrefetchSource(_ body: String) -> String {
    replaceGemmLoopAligned(injectRegisterPrefetchLoaders(baseSource), with: body)
}

// One register set. The device reads for tile k are issued before the RAW
// barrier and the mma for tile k-1, so their latency overlaps that mma.
// Staging arrays and barrier count are exactly as shipped.
let pfBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  if (k_iterations <= 0) {
    return;
  }

  typename loader_a_t::RegTile ra;
  typename loader_b_t::RegTile rb;

  loader_a.prefetch(ra);
  loader_b.prefetch(rb);
  loader_a.next();
  loader_b.next();

  for (int k = 1; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra);
    loader_b.stage_regs(rb);
    loader_a.prefetch(ra);
    loader_b.prefetch(rb);
    loader_a.next();
    loader_b.next();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
  }

  threadgroup_barrier(mem_flags::mem_threadgroup);
  loader_a.stage_regs(ra);
  loader_b.stage_regs(rb);
  threadgroup_barrier(mem_flags::mem_threadgroup);
  mma_op.mma(As, Bs);
}

"""

// Two register sets unrolled over parity, so no prefetch has a WAR dependence
// on the stage it follows. Discriminates a real scheduling limit from a
// register-reuse artifact, exactly as db2 does for db.
let pf2Body = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  if (k_iterations <= 0) {
    return;
  }

  typename loader_a_t::RegTile ra0, ra1;
  typename loader_b_t::RegTile rb0, rb1;

  loader_a.prefetch(ra0);
  loader_b.prefetch(rb0);
  loader_a.next();
  loader_b.next();

  int k = 1;
  for (; k + 1 < k_iterations; k += 2) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra0);
    loader_b.stage_regs(rb0);
    loader_a.prefetch(ra1);
    loader_b.prefetch(rb1);
    loader_a.next();
    loader_b.next();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);

    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra1);
    loader_b.stage_regs(rb1);
    loader_a.prefetch(ra0);
    loader_b.prefetch(rb0);
    loader_a.next();
    loader_b.next();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
  }

  if (k < k_iterations) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra0);
    loader_b.stage_regs(rb0);
    loader_a.prefetch(ra1);
    loader_b.prefetch(rb1);
    loader_a.next();
    loader_b.next();
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);

    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra1);
    loader_b.stage_regs(rb1);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
  } else {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.stage_regs(ra0);
    loader_b.stage_regs(rb0);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
  }
}

"""

// Control: the same register routing with zero overlap -- prefetch and stage
// stay inside the same barrier pair the shipped loop uses. Numerically
// identical to base, so (pf - regstage) is the pure overlap term and
// (regstage - base) is the price of the register detour.
let regstageBody = """
METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  typename loader_a_t::RegTile ra;
  typename loader_b_t::RegTile rb;
  for (int k = 0; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);
    loader_a.prefetch(ra);
    loader_b.prefetch(rb);
    loader_a.stage_regs(ra);
    loader_b.stage_regs(rb);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    mma_op.mma(As, Bs);
    loader_a.next();
    loader_b.next();
  }
}

"""

func makeDoubleBufferedSource(_ body: String) -> String {
    var s = replaceGemmLoopAligned(baseSource, with: body)
    let stageOld = """
      threadgroup T Xs[BM * BK_padded];
      threadgroup T Ws[transpose ? BN * BK_padded : BK * BN_padded];
    """
    let stageNew = """
      constexpr int kATile = BM * BK_padded;
      constexpr int kBTile = transpose ? BN * BK_padded : BK * BN_padded;
      threadgroup T Xs[2 * kATile];
      threadgroup T Ws[2 * kBTile];
    """
    guard s.components(separatedBy: stageOld).count == 2 else {
        die("staging declaration anchor not unique")
    }
    s = s.replacingOccurrences(of: stageOld, with: stageNew)

    let callOld = "gemm_loop_aligned(Xs, Ws, mma_op, loader_x, loader_w, K_it);"
    let callNew = "gemm_loop_aligned(Xs, Ws, mma_op, loader_x, loader_w, K_it, kATile, kBTile);"
    let n = s.components(separatedBy: callOld).count - 1
    guard n == 2 else { die("expected 2 gemm_loop_aligned call sites, found \(n)") }
    return s.replacingOccurrences(of: callOld, with: callNew)
}

let variantSource: [String: String] = [
    "base": baseSource,
    "nobar": replaceGemmLoopAligned(baseSource, with: nobarBody),
    "db": makeDoubleBufferedSource(dbBody),
    "db2": makeDoubleBufferedSource(db2Body),
    "dbmem": makeDoubleBufferedSource(dbmemBody),
    "noload": replaceGemmLoopAligned(baseSource, with: noloadBody),
    "nomma": replaceGemmLoopAligned(baseSource, with: nommaBody),
    "pf": makeRegisterPrefetchSource(pfBody),
    "pf2": makeRegisterPrefetchSource(pf2Body),
    "regstage": makeRegisterPrefetchSource(regstageBody),
]

// MARK: - device setup

guard let device = MTLCreateSystemDefaultDevice() else { die("no Metal device") }
guard let queue = device.makeCommandQueue() else { die("no command queue") }

log("device: \(device.name)  maxTG=\(device.maxThreadgroupMemoryLength) B")

func buildLibrary(_ tag: String) -> MTLLibrary {
    let opts = MTLCompileOptions()
    opts.fastMathEnabled = false // device.cpp:630
    let src = variantSource[tag]! + templateDef
    do {
        return try device.makeLibrary(source: src, options: opts)
    } catch {
        let path = "/tmp/edr110_\(tag).metal"
        try? src.write(toFile: path, atomically: true, encoding: .utf8)
        die("compile failed for \(tag) (source at \(path)):\n\(error)")
    }
}

func makePipeline(_ lib: MTLLibrary, _ name: String, alignAll: Bool) -> MTLComputePipelineState {
    let fc = MTLFunctionConstantValues()
    var t = true
    for idx in [200, 201, 202] {
        fc.setConstantValue(&t, type: .bool, index: idx)
    }
    do {
        let fn = alignAll ? try lib.makeFunction(name: name, constantValues: fc)
                          : lib.makeFunction(name: name)!
        return try device.makeComputePipelineState(function: fn)
    } catch {
        die("pipeline failed for \(name): \(error)")
    }
}

// MARK: - problem setup

struct Shape {
    let tag: String
    let M: Int
    let K: Int
    let N: Int
}

let shapes: [Shape] = {
    // Prefill of 512 tokens, top-8 of 256 experts -> 4096 gathered rows.
    // gate_up: K=hidden 2048 -> N=2*moe_intermediate 1024
    // down:    K=moe_intermediate 512 -> N=hidden 2048
    let all = [Shape(tag: "gate_up", M: 4096, K: 2048, N: 1024),
               Shape(tag: "down", M: 4096, K: 512, N: 2048)]
    switch env("ED_SHAPE") ?? "both" {
    case "gate_up": return [all[0]]
    case "down": return [all[1]]
    default: return all
    }
}()

let numExperts = 256
let groupSize = 16

func makeBuffer(_ bytes: Int, label: String) -> MTLBuffer {
    guard let b = device.makeBuffer(length: bytes, options: .storageModePrivate) else {
        die("alloc \(bytes) failed for \(label)")
    }
    b.label = label
    return b
}

// Sorted routed indices.
//   multinomial: realistic top-8 routing -- expert runs of noisy length, so
//                most BM=16 row tiles straddle >1 expert and the kernel
//                re-runs its whole K loop per segment.
//   aligned:     exactly M/numExperts rows per expert. Same weight bytes and
//                same useful MAC count, but every 16-row tile holds exactly
//                one expert -> zero segment-restart waste. The difference
//                against multinomial IS the restart amplification.
func sortedIndices(_ M: Int, mode: String) -> [UInt32] {
    var counts = [Int](repeating: M / numExperts, count: numExperts)
    if mode != "aligned" {
        counts = [Int](repeating: 0, count: numExperts)
        var state: UInt64 = 0x9E3779B97F4A7C15
        for _ in 0..<M {
            state = state &* 6364136223846793005 &+ 1442695040888963407
            counts[Int((state >> 33) % UInt64(numExperts))] += 1
        }
    }
    var out = [UInt32]()
    out.reserveCapacity(M)
    for e in 0..<numExperts {
        for _ in 0..<counts[e] { out.append(UInt32(e)) }
    }
    return out
}

// Expected K-loop executions per BM=16 row tile, from the actual index vector.
func segmentsPerTile(_ idx: [UInt32]) -> Double {
    var segs = 0
    var t = 0
    while t < idx.count {
        let end = min(t + 16, idx.count)
        segs += 1
        for i in (t + 1)..<end where idx[i] != idx[i - 1] { segs += 1 }
        t = end
    }
    return Double(segs) / Double((idx.count + 15) / 16)
}

struct Problem {
    let shape: Shape
    let x: MTLBuffer
    let w: MTLBuffer
    let scales: MTLBuffer
    let indices: MTLBuffer
    let y: MTLBuffer
    let sink: MTLBuffer
    let gridX: Int
    let gridY: Int
    let segsPerTile: Double
}

let idxModes: [String] = {
    switch env("ED_IDX") ?? "multinomial" {
    case "both": return ["multinomial", "aligned"]
    case let m: return [m]
    }
}()
let idxMode = idxModes[0]

func makeProblem(_ s: Shape) -> Problem {
    let packFactor = 2 // get_pack_factor<8, 4>()
    let bytesPerPack = 1 // get_bytes_per_pack<8>()
    let wBytes = numExperts * s.N * (s.K * bytesPerPack / packFactor)
    let sBytes = numExperts * s.N * (s.K / groupSize)
    let idx = sortedIndices(s.M, mode: idxMode)
    let idxBuf = device.makeBuffer(bytes: idx, length: idx.count * 4, options: .storageModeShared)!
    return Problem(
        shape: s,
        x: makeBuffer(s.M * s.K * 2, label: "x"),
        w: makeBuffer(wBytes, label: "w"),
        scales: makeBuffer(sBytes, label: "scales"),
        indices: idxBuf,
        y: makeBuffer(s.M * s.N * 2, label: "y"),
        sink: makeBuffer(1024, label: "sink"),
        gridX: (s.N + 31) / 32,
        gridY: (s.M + 15) / 16,
        segsPerTile: segmentsPerTile(idx))
}

// MARK: - timing

let reps = envInt("ED_REPS", 4)
let cbs = envInt("ED_CBS", 9)
let pairs = envInt("ED_PAIRS", 4)

func timeOne(_ pso: MTLComputePipelineState, _ p: Problem, isNull: Bool) -> Double {
    var M32 = Int32(p.shape.M), N32 = Int32(p.shape.N), K32 = Int32(p.shape.K)
    var samples = [Double]()
    for i in 0..<(cbs + 3) {
        let cb = queue.makeCommandBuffer()!
        let enc = cb.makeComputeCommandEncoder()!
        enc.setComputePipelineState(pso)
        for _ in 0..<reps {
            if isNull {
                enc.setBuffer(p.sink, offset: 0, index: 0)
            } else {
                enc.setBuffer(p.x, offset: 0, index: 0)
                enc.setBuffer(p.w, offset: 0, index: 1)
                enc.setBuffer(p.scales, offset: 0, index: 2)
                enc.setBuffer(p.indices, offset: 0, index: 3)
                enc.setBuffer(p.y, offset: 0, index: 4)
                enc.setBytes(&M32, length: 4, index: 5)
                enc.setBytes(&N32, length: 4, index: 6)
                enc.setBytes(&K32, length: 4, index: 7)
            }
            enc.dispatchThreadgroups(
                MTLSize(width: p.gridX, height: p.gridY, depth: 1),
                threadsPerThreadgroup: MTLSize(width: 32, height: 2, depth: 1))
        }
        enc.endEncoding()
        cb.commit()
        cb.waitUntilCompleted()
        if let e = cb.error { die("command buffer error: \(e)") }
        if i >= 3 {
            samples.append((cb.gpuEndTime - cb.gpuStartTime) * 1e3 / Double(reps))
        }
    }
    return median(samples)
}

// MARK: - main

let tags = (env("ED_TAGS") ?? "base,nobar,db,db2,dbmem,noload,nomma")
    .split(separator: ",").map(String.init)
var libs = [String: MTLLibrary]()
for t in tags {
    libs[t] = buildLibrary(t)
    log("compiled variant \(t)")
}
let nullPso = makePipeline(libs["base"]!, "ed_null_kernel", alignAll: false)
var psos = [String: MTLComputePipelineState]()
for t in tags {
    let p = makePipeline(libs[t]!, kernelName, alignAll: true)
    psos[t] = p
    log("  \(pad(t, 6)): tgmem=\(p.staticThreadgroupMemoryLength) B  maxTGThreads=\(p.maxTotalThreadsPerThreadgroup)")
}

// Same weight/activation buffers, different routed-index vector.
func reroute(_ p: Problem, _ mode: String) -> Problem {
    let idx = sortedIndices(p.shape.M, mode: mode)
    return Problem(
        shape: p.shape, x: p.x, w: p.w, scales: p.scales,
        indices: device.makeBuffer(bytes: idx, length: idx.count * 4, options: .storageModeShared)!,
        y: p.y, sink: p.sink, gridX: p.gridX, gridY: p.gridY,
        segsPerTile: segmentsPerTile(idx))
}

for s in shapes {
    let p0 = makeProblem(s)
    let probs = idxModes.map { (mode: $0, p: reroute(p0, $0)) }
    log("")
    log("=== shape \(s.tag): M=\(s.M) K=\(s.K) N=\(s.N)  grid=\(p0.gridX)x\(p0.gridY) tgs ===")
    for e in probs {
        log("routing \(pad(e.mode, 12)): K-loop executions per BM=16 tile = \(fmt(e.p.segsPerTile, 3))")
    }

    // Key "<mode>|<tag>"; modes are interleaved inside the ABBA sweep so host
    // drift cannot masquerade as a routing effect.
    var acc = [String: [Double]]()
    let slots = probs.flatMap { e in tags.map { (key: "\(e.mode)|\($0)", pso: psos[$0]!, p: e.p) } }
    for sl in slots { acc[sl.key] = [] }
    var nullAcc = [Double]()

    nullAcc.append(timeOne(nullPso, p0, isNull: true))
    for _ in 0..<pairs {
        for sl in slots { acc[sl.key]!.append(timeOne(sl.pso, sl.p, isNull: false)) }
        for sl in slots.reversed() { acc[sl.key]!.append(timeOne(sl.pso, sl.p, isNull: false)) }
    }
    nullAcc.append(timeOne(nullPso, p0, isNull: true))

    log(String(format: "null control  : %8.4f ms/dispatch (n=%d)", median(nullAcc), nullAcc.count))
    for e in probs {
        let baseMs = median(acc["\(e.mode)|base"]!)
        for t in tags {
            let a = acc["\(e.mode)|\(t)"]!
            let m = median(a)
            log(String(format: "%-12s %-6s: %8.4f ms  vs base %+6.2f %%  (n=%d, spread %.1f %%)",
                       (e.mode as NSString).utf8String!, (t as NSString).utf8String!,
                       m, (baseMs - m) / baseMs * 100.0, a.count,
                       (a.max()! - a.min()!) / m * 100.0))
        }
        // Per-layer projection: 39 MoE layers, one dispatch of this shape each.
        let proj = tags.map { "\($0) \(fmt(median(acc["\(e.mode)|\($0)"]!) * 39, 1))" }.joined(separator: ", ")
        log("  \(e.mode) per-prefill projection (39 layers, ms): " + proj)
    }
    if idxModes.count > 1 {
        let mm = median(acc["multinomial|base"]!)
        let am = median(acc["aligned|base"]!)
        let segRatio = probs[0].p.segsPerTile / probs[1].p.segsPerTile
        log(String(format:
            "SEGMENT-RESTART TAX: base %.4f -> %.4f ms aligned = %.2f %% of kernel time; K-loop ratio %.3fx",
            mm, am, (mm - am) / mm * 100.0, segRatio))
    }
}
