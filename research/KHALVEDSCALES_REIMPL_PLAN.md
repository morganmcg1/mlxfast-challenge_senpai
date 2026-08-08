# kHalvedScales Re-implementation Plan (Without _nax Template Instantiations)

## Root Cause of Original Failure
PR #342 added `bool kHalvedScales = false` as a template parameter to QuantizedBlockLoader
and fp_qmm_t_impl, plus a `_hs_1` kernel name suffix. Each _nax kernel got a
kHalvedScales=true variant → new kernel library entries → new JIT compilations →
~900s M5 compile budget exceeded → 40+ consecutive M5 build failures.

## Recommended Approach: Runtime Constant Parameter (Approach c)

Convert `kHalvedScales` from a template parameter to a runtime `set_bytes` argument,
following the existing `run_skip_pct` pattern at `quantized.cpp:1938` / `fp_quantized_nax.h:1223`.

### Why this works
- kHalvedScales is dispatch-uniform (same for all threads in a kernel invocation)
- A runtime `if (kHalvedScales)` branch has zero divergence cost
- Metal compiler generates ONE kernel binary with both branches present
- No new kernel name, no new template instantiation, no new JIT compile
- This is exactly the pattern the codebase already uses for `run_skip_pct`
- The comment at fp_quantized_nax.h:1219-1222 states run_skip_pct is "deliberately NOT
  a function constant: it must never participate in the pipeline specialization key"

### Implementation (6 files)

1. **fp_quantized_nax.h:210** — Remove kHalvedScales from template params, add as
   constructor param + member; change `if constexpr(kHalvedScales)` → `if(kHalvedScales)`
   in read_scale(), next(), constructor initializer

2. **fp_quantized_nax.h:528** — Remove kHalvedScales/kGatherEscape from fp_qmm_t_impl
   template params, add as function params

3. **fp_quantized_nax.h:895,957,1077** — Add `const constant bool& kHalvedScales` to
   kernel signatures; pass kGatherEscape as literal (false for qmm, true for gather)

4. **quantized.cpp:541,663** — Remove `_hs_1` kernel suffix; remove `halved_scales`
   template arg from get_qmm_nax_kernel_wrapped; add `set_bytes(halved_scales, c++)`
   after M

5. **mlx-generated/fp_quantized_nax.cpp** — Sync embedded source string with .h

6. **LagunaRuntimeModel.swift:229** — Re-enable `lagunaPrefillSharedHalvedEnabled`
   with NAX check

### Critical details
- kGatherEscape can remain a per-kernel-function literal (false for qmm_t_nax/static,
  true for gather_qmm_t_nax) — it's fixed per kernel function, not per dispatch
- Adding set_bytes(halved_scales) shifts subsequent constant buffer indices — kernel
  signature and dispatch must match exactly
- This is M5-only (uses _nax kernels). M4 can verify build but not timing.
- Verify bit-exactness via upstream equivalence: research/run_upstream_equivalence.sh

### Expected gain
- ~0.9% total score (same as original PR #342)
- ~4KB code budget
- Zero new JIT compilations
- M5 build safe (no new template instantiations)

### Approach comparison
| Approach | Bit-exact | M5 build | Budget | Gain | Verdict |
|---|---|---|---|---|---|
| (a) Host precompute | N/A | Safe | Low | None | No savings |
| (b) Custom JIT kernel | Risky | Safe | High | Negative | Impractical |
| (c) Runtime constant | Same arithmetic | Zero new JIT | ~4KB | ~0.9% | BEST |
| (d) Scale reshaping | N/A | New JIT | Low | Requires kernel changes | No |
