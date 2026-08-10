# Decode C-vector container lifetime audit: NO-GO

## Verdict

**Status: vector-lifetime NO-GO. No implementation or successor is nominated.**

Reusing a populated `mlx_vector_array` measured far below the required conservative `18 us/token` in both ABBA and BAAB orders. The most conservative lower bounds across measured scored arities are only `0.936 us/token` (ABBA) and `0.684 us/token` (BAAB) after crediting all 334 populated containers/token. In addition, the C-vector implementation is outside the submission surface and a shared mutable caller-side container would lack proven lock-free/request-local ownership. The stop rule therefore applies independently on timing, editability, and concurrency safety.

## Identity, scope, and history

- PR `#662`; branch `cedar-askeladd/decode-vector-container-lifetime-audit`
- Required base `3b5e22b9fd8d1860ff1a33de5b200fe017ac96cf`
- Assignment start `0371c5d73536dcc54e42aec84bfcc34a9adf4341`
- Exact benchmark implementation `530c23c` (full SHA is available in branch history)
- Final result SHA: the commit containing this report, recorded non-recursively by the typed Senpai result
- Host/OS: Apple Silicon `arm64`, macOS `26.5.2`; CPU-only MLX device forced
- W&B: N/A; no model, GPU evaluation, training, or official operation ran

All refs/reflog and PRs `#344/#354/#633/#650` were audited. The exact same-size reusable C-vector ownership mechanism was novel. `#344` covered a static null wrapper; `#354` immutable Swift descriptor arrays; `#633` packed weight/GPU bindings; and `#650` instrumentation/census only. The all-ref match `2ebae10` was only the vendor import. This experiment did not revisit descriptor, guard, cache, LM-head, router/MoE, Q/K, or GPU work.

## Frozen census and lifecycle table

PR `#650` is frozen input: 323 `MLXFastKernel`, 8 `asyncEval`, and 3 blocking `eval` entries/token. Each kernel call creates one populated input container and one empty output container; eval creates one populated container. Thus there are 657 container lifetimes/token, but only the 334 populated containers have a meaningful `set_data` comparison. The scored call-site arities observed by static inspection are `{2,3,4,5,6,9,10}` for kernel inputs and include `1` for eval; the benchmark covers all eight.

| Family | calls/token | elements/container | immediate free | retained/copied handles | thread/common/editable |
|---|---:|---|---|---|---|
| attention/cache kernels | 120 | subset of 2..10 | after synchronous custom apply | copied into graph node | serial decode; M4/M5; scored caller editable |
| sparse MoE kernels | 195 | subset of 2..10 | after synchronous custom apply | copied into graph node | serial decode; M4/M5; scored caller editable |
| dense/shared expert | 3 | subset of 2..10 | after synchronous custom apply | copied into graph node | serial decode; M4/M5; scored caller editable |
| LM-head kernels | 4 | subset of 2..10 | after synchronous custom apply | copied into graph node | serial decode; M4/M5; scored caller editable |
| embedding kernel | 1 | subset of 2..10 | after synchronous custom apply | copied into graph node | serial decode; M4/M5; scored caller editable |
| `asyncEval` | 8 | 1 or more | immediately after C call | C++ moves shallow handles into event/graph state | eval lock; common; bridge implementation uneditable |
| blocking `eval` | 3 | 1 or more | after `mlx_eval` returns | consumed before return | recursive eval lock; common; bridge implementation uneditable |

The table deliberately does not infer per-arity dynamic counts from source syntax. The bound instead applies the worst lower interval over every observed arity to all 334 populated calls, which is more conservative than an arity-weighted estimate.

## Ownership proof and safety limit

1. `Vendor/mlx-swift/Source/MLX/Cmlx+Util.swift:6-10` creates a fresh C vector with `mlx_vector_array_new_data` and holds the Swift input buffer through the call.
2. `Sources/MLXFastModel/MLXFastKernel.swift:139-157` creates populated input and empty output vectors, invokes the custom kernel synchronously, frees both C containers, then wraps returned array handles.
3. `Vendor/mlx-swift/Source/MLX/Transforms+Eval.swift:6-9,15-25,32-40,48-53` serializes eval with a recursive lock. Blocking eval frees after return; async eval frees immediately after its C call.
4. `Vendor/mlx-swift/Source/Cmlx/mlx-c/mlx/c/vector.cpp:41-49` makes a heap `std::vector` and shallow-copies array handles. Lines 65-79 show `set_data` builds a fresh temporary vector and assigns it; destination capacity may be reused, but the temporary still allocates/copies. `private/vector.h:16-24,26-45,48-59` owns/frees only that vector wrapper.
5. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/array.h:82-91` defines shallow array copies. The transform bridge passes vectors by value and C++ graph/event code moves/copies those handles before returning; therefore the existing immediate frees are valid. Custom-kernel application likewise constructs graph state synchronously before return.
6. MLX arrays are not generally thread-safe (`docs/src/dev/MLXArray.md:26-43`). Eval has a lock, but ordinary kernel calls do not share it. The ranked worker is serial (`LagunaRuntimeModel.swift:1815-1827`), yet a reusable field/global would create mutable cross-call ownership not guaranteed by the public API. A request-local reuse owner could avoid this, but no single proven <=4 KiB submitted owner spans all 334 calls, and vector.cpp/private vector ownership files are not editable.

Conclusion: repopulating an unaliased container *after* a synchronous API return is locally valid, but a production shared container is not proven safe. Existing immediate-free semantics must remain.

## CPU-only microbenchmark

The exact release harness was committed before launch. It used metadata-only lazy MLX arrays (shallow handles, no model arrays, eval, GPU command, or Metal library), forced CPU, and compared:

- current: `mlx_vector_array_new_data` then `mlx_vector_array_free` every iteration;
- reuse: one pre-created exact-size container, `mlx_vector_array_set_data` every iteration, final free;
- empty control: matched loop/checksum with no vector API.

For each arity/order: 65,536 warmup iterations/arm; 16 cycles; 32,768 iterations/block; two blocks/arm/cycle = 1,048,576 timed iterations/arm; 524,288 empty iterations; ABBA and BAAB; deterministic 20,000-replicate paired bootstrap. JSON retains every cycle, median, p95, interval, and controls.

Successful supervised job `1809a574-ba18-4626-a793-302024255504` exited 0 at `2026-08-10T16:22:22Z`: 5.65 s real, 3.18 s user, 0.15 s system, maximum RSS 8,044,544 bytes, peak footprint 3,031,472 bytes. Earlier bounded failures were method repairs: missing nested resolution (`eec97267`), unrelated XCTest compilation (`a3c8d23`), executable visibility (`b6a7ce3`), and two accidental default-metallib initializations (`74a8b082`, `cd24d049`). The final metadata-only fixture avoided all GPU/default-library initialization.

Reproduce benchmark commit `530c23c`:

```bash
cd Vendor/mlx-swift
/usr/bin/time -l swift run -c release --force-resolved-versions \
  VectorContainerLifetimeMicrobench ../../../research/decode-vector-container-microbench.json
```

Artifact: `research/decode-vector-container-microbench.json`, 10,975 bytes, SHA-256 `f9f2174049727c0a5ee6cd9c7208f1e9b3c7c0d7d0d1451835771a4e4e0c69cf`. Harness SHA-256: main `d555e31451c50132126fc922277a592baf0ca941b9fc1a72a96d984303d53fe8`; fixture `73e860ff34b6554c0c9e583cb4ddb662e684f3f88d2a8de76a5559fb1bdb1370`.

Numbers are ns/container after the empty median (0 ns; p95 <=0.001 ns). `cur` and `reuse` are median/p95; CI is paired saving bootstrap 95%; final column is `334 * CI lower / 1000` us/token.

| n | order | cur med/p95 | reuse med/p95 | save med | CI ns | lower us/token |
|---:|---|---:|---:|---:|---:|---:|
|1|ABBA|29.600/44.303|26.263/37.525|3.427|2.801..5.281|0.936|
|1|BAAB|24.857/26.285|17.492/21.138|7.824|6.229..9.225|2.080|
|2|ABBA|45.710/47.264|32.084/43.590|13.107|4.688..14.600|1.566|
|2|BAAB|46.299/46.694|39.223/40.988|7.014|5.494..8.421|1.835|
|3|ABBA|61.508/63.412|51.784/54.536|9.456|6.971..11.528|2.328|
|3|BAAB|60.162/61.462|53.136/54.187|6.930|6.536..10.109|2.183|
|4|ABBA|61.473/63.071|51.374/52.600|10.071|9.943..10.267|3.321|
|4|BAAB|62.026/63.341|57.344/59.144|4.862|4.358..6.316|1.456|
|5|ABBA|85.371/85.884|75.300/76.552|8.995|8.467..10.434|2.828|
|5|BAAB|85.918/88.802|74.874/76.186|11.287|10.564..11.932|3.528|
|6|ABBA|88.772/90.923|78.616/79.894|10.001|8.769..11.870|2.929|
|6|BAAB|88.294/89.488|75.225/76.763|12.754|10.655..13.107|3.559|
|9|ABBA|122.574/123.713|110.957/114.267|10.565|9.446..11.396|3.155|
|9|BAAB|122.401/123.362|113.304/121.245|8.214|2.048..9.066|0.684|
|10|ABBA|125.369/127.014|115.505/118.152|8.184|7.310..10.065|2.442|
|10|BAAB|122.597/123.538|111.413/113.852|10.820|9.413..11.184|3.144|

## Controls, Amdahl bound, and restoration

The in-memory census validator accepted exactly `(323,8,3)` with checksum `80222704`. A positive control changed the kernel count to 324 and was rejected. No source-level count is converted into savings except the frozen `323+8+3=334` populated calls/token.

Predeclared gate, conservatively across all scored arities:

- ABBA: `334 * 2.801 ns = 0.936 us/token < 18 us/token` — fail.
- BAAB: `334 * 2.048 ns = 0.684 us/token < 18 us/token` — fail.

Even selecting each order's best lower interval yields only 3.321 and 3.559 us/token, still far below threshold. These are CPU bridge lower bounds, not end-to-end or M5 claims.

All temporary benchmark/package/test fixtures and nested `Package.resolved` are removed in the result commit. The final diff from assignment start retains only this report and its JSON; submitted production/vendor/generated/contract/default files are byte-identical. No correctness/model run was needed because no production code remains.

---

_This report was prepared by the OpenHands AI agent on behalf of the assigned student role._
