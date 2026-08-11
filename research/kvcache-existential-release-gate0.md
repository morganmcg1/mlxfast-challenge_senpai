# KVCache existential release Gate 0

## Verdict

**NO-GO.** The optimized release worker still performs one checked concrete-cache
cast per decoder layer, so the suspected operation is real and reachable.
However, the controlled CPU proxy measured only **19.272 ns/token** mean paired
savings, or **0.482 ns/token/layer**, with a paired bootstrap 95% confidence
interval of **[17.967, 20.806] ns/token**. The decision rule requires the lower
bound to reach **6,530.349 ns/token** (163.259 ns/layer). The observed lower
bound is about 363 times smaller than required.

Do not implement concrete cache specialization on this evidence. Direct the
next optimization effort toward a materially larger decode cost center.

## Assignment and scope

- PR: `#756`
- Branch: `cedar-thorfinn/kvcache-existential-release-gate0`
- Assignment base: `7580143d4adbb266886b0f4fdf5903e42fd47657`
- Analysis starting commit: `6fa58f724bd614cc88c4de0624bd125f73b0e6c6`
- Submitted-path changes: none
- Research-only committed artifact: this report
- Production code changes: none

This was a static release-artifact inspection followed by the one permitted
CPU-only proxy microbenchmark. No model was loaded or executed. No GPU work,
`--local-iterate`, `--local-submit`, upstream-equivalence run, quality run, W&B
run, dependency installation, or official submission was performed.

## Scored-path trace

The checked release operation is on the scored decode path:

1. `Sources/MLXFastHarness/LagunaRuntimeWorker.swift:419-442` handles
   `decode_step`, takes `state.decodeCache`, and requests one-token logits.
2. `Sources/MLXFastHarness/LagunaRuntimeWorker.swift:201-208` accepts `[KVCache]`
   in `lagunaLogits` and calls the runtime model.
3. `Sources/MLXFastModel/LagunaRuntimeModel.swift:11652-11687` is the public
   model boundary.
4. `Sources/MLXFastModel/LagunaRuntimeModel.swift:11562-11599` is the 40-layer
   loop; it extracts `cache?[i]` and forwards a `KVCache?` to each layer.
5. `Sources/MLXFastModel/LagunaRuntimeModel.swift:11030-11044` forwards that
   existential cache into attention.
6. `Sources/MLXFastModel/LagunaRuntimeModel.swift:6020` checks
   `RotatingKVCache`, while line 6046 checks `SimpleKVCache`.

The exact cache-shape and offset validation at lines 11409-11446, and mask
selection at lines 11541-11552, occur outside the 40-layer loop. They are not
the repeated operation evaluated here.

## Stage 1: optimized production artifact

### Build

Exact command:

```sh
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker \
  --product mlxfast-runtime-worker
```

Result:

- Exit status: 0
- Wall time: 30.435 s
- Artifact: `.build-worker/release/mlxfast-runtime-worker`
- Format: Mach-O 64-bit arm64 executable
- Size: 49,210,744 bytes
- SHA-256: `3aaea7ca78f7917dcc5489a6409e71b79709fa1fc467b4eafcc061de5c1a8d1d`
- `Package.resolved` SHA-1 before and after:
  `b1fcc577135271fc1cf1bdb9ef31c69167e6898b`

### Inspection commands

```sh
xcrun nm -nm .build-worker/release/mlxfast-runtime-worker
xcrun swift-demangle < /tmp/cedar-thorfinn-gate0.nm
xcrun llvm-objdump --macho --disassemble \
  .build-worker/release/mlxfast-runtime-worker
xcrun llvm-objdump --macho --indirect-symbols \
  .build-worker/release/mlxfast-runtime-worker
xcrun nm -u \
  .build-worker/arm64-apple-macosx/release/MLXFastModel.build/LagunaRuntimeModel.swift.o
```

### Release evidence

Both source-level checked casts remain in the release attention function:

- Rotating-cache sequence: `0x100d68674-0x100d686d0`
- Simple-cache sequence: `0x100d68b24-0x100d68b80`

Each sequence materializes the corresponding concrete class metadata, calls
address `0x10122fc24`, and tests `w0` to select its branch. The Mach-O indirect
symbol table maps `0x10122fc24` to `_swift_dynamicCast`. Depending on the layer's
cache family, one of these checks succeeds and is taken, yielding one checked
cast per layer and 40 casts per decode token.

The compiled `LagunaRuntimeModel.swift.o` also has undefined references to
`_swift_dynamicCast`, `_swift_dynamicCastClass`, `_swift_retain`,
`_swift_release`, `_swift_retain_n`, and `_swift_release_n`. Those object-level
references are supporting context only; the address-resolved final-executable
inspection above is the attributable proof for the two checked cache casts.

Because a production checked cast survived release optimization and was
reachable in the repeated layer loop, Stage 2 was allowed.

## Stage 2: CPU proxy microbenchmark

### Design

The temporary Swift benchmark defined a minimal class-bound `CacheLike`
protocol, final `FullCache` and `RotatingCache` classes, and exactly 40 strictly
alternating concrete cache instances.

- **A, existential:** the instances were stored as `[any CacheLike]`; each layer
  cast its element to the concrete final class expected for that layer.
- **B, pretyped:** the same instances were exposed through parallel typed
  `[FullCache?]` and `[RotatingCache?]` references, with no casts.
- Both arms called the same `@inline(never)` useful-work functions, used the same
  population and seed, and produced the same checksum.
- Warmup was 2,500 tokens.
- Measurement used 40 ABBA blocks, each with 25,000 tokens per arm execution.
  Within each block, A was the mean of A1/A2 and B was the mean of B1/B2.
- The estimator was paired `A - B` savings per token and per 40 layers.
- The 95% interval used 100,000 deterministic paired bootstrap resamples of the
  40 block differences.
- The aggregate checksum was consumed observably after measurement.

### Host and toolchain

- Host: Mac mini `Mac16,11`
- SoC: Apple M4 Pro
- CPU: 14 cores (10 performance, 4 efficiency)
- Unified memory: 48 GB
- OS target reported by Swift: arm64-apple-macosx26.0
- Swift: Apple Swift 6.3.3
- Swift compiler: `swiftlang-6.3.3.1.3 clang-2100.1.1.101`
- `llvm-objdump`: Apple LLVM 21.0.0

### Commands and artifacts

Exact compile command:

```sh
swiftc -O -whole-module-optimization \
  /tmp/cedar-thorfinn-kvcache-gate0.swift \
  -o /tmp/cedar-thorfinn-kvcache-gate0
```

Exact run command:

```sh
/tmp/cedar-thorfinn-kvcache-gate0 40 25000
```

Artifact identities before cleanup:

- Source SHA-256:
  `4482bf4b7d87fbd3f5b0dfcfb364ca94bb36776b4ce62e7a3cbb3f0d8a7c02b1`
- Executable SHA-256:
  `6e2f547deefc2a9a1e3f92e333e6ad540b3dcee690553bcc17b125bdca96b207`
- Successful compile wall time: 0.669 s
- Benchmark wall time: 0.506 s
- Final checksum: `1513781170765395334`

The first compile attempt failed before execution because file-private top-level
declarations could not expose the benchmark's top-level values under Swift 6.3.
Removing only those access modifiers fixed the temporary benchmark; its design,
work, populations, and measurement protocol were unchanged.

### Benchmark artifact inspection

Targeted disassembly used:

```sh
xcrun nm -nm /tmp/cedar-thorfinn-kvcache-gate0
xcrun swift-demangle < /tmp/cedar-thorfinn-kvcache-gate0.nm
xcrun llvm-objdump -d --disassemble-symbols='<runExistential symbol>' \
  /tmp/cedar-thorfinn-kvcache-gate0
xcrun llvm-objdump -d --disassemble-symbols='<runPretyped symbol>' \
  /tmp/cedar-thorfinn-kvcache-gate0
```

The optimizer lowered the benchmark's final-class casts to inline metadata
checks rather than importing `_swift_dynamicCast`:

- A (`runExistential`, address `0x1000023cc`) retains each existential class
  reference at `0x100002460-0x100002468`, then compares class metadata for
  `FullCache` at `0x100002470` or `RotatingCache` at `0x100002438`, with failure
  branches.
- B (`runPretyped`, address `0x100002508`) has neither those retains nor class
  metadata comparisons. It directly loads typed optional references at
  `0x100002560` or `0x100002590`, checks nil, and calls the same useful-work
  functions as A.

Thus the timed A arm retains the relevant existential class check and ownership
work, while B removes it without removing useful work.

## Raw ABBA results

All time columns are nanoseconds except the normalized columns stated in their
headers.

```csv
config,blocks,iterations_per_arm,layers,warmup_iterations,bootstrap_samples
config,40,25000,40,2500,100000
block,a1_ns,b1_ns,b2_ns,a2_ns,a_ns_per_token,b_ns_per_token,savings_ns_per_token,savings_ns_per_layer
0,4810209,3624542,3261458,3913834,174.481,137.720,36.761,0.919
1,3554500,2630084,2443375,3126500,133.620,101.469,32.151,0.804
2,2831083,2096667,2094792,2710750,110.837,83.829,27.007,0.675
3,2580333,1813584,1770000,2327958,98.166,71.672,26.494,0.662
4,2242542,1638500,1582125,2133917,87.529,64.412,23.117,0.578
5,2052500,1512208,1497167,1972333,80.497,60.188,20.309,0.508
6,1970291,1399667,1396583,1875375,76.913,55.925,20.988,0.525
7,1803208,1337375,1318875,1675834,69.581,53.125,16.456,0.411
8,1675833,1230792,1214542,1640208,66.321,48.907,17.414,0.435
9,1642250,1214666,1214625,1640167,65.648,48.586,17.063,0.427
10,1640167,1214541,1214625,1642166,65.647,48.583,17.063,0.427
11,1640125,1214541,1214709,1640166,65.606,48.585,17.021,0.426
12,1640125,1214500,1216625,1640167,65.606,48.623,16.983,0.425
13,1640208,1214625,1214667,1640250,65.609,48.586,17.023,0.426
14,1640209,1217292,1214667,1640209,65.608,48.639,16.969,0.424
15,1640167,1214750,1214666,1640250,65.608,48.588,17.020,0.426
16,1643500,1214541,1214709,1640208,65.674,48.585,17.089,0.427
17,1640208,1214375,1214583,1643208,65.668,48.579,17.089,0.427
18,1645042,1214666,1214750,1640250,65.706,48.588,17.118,0.428
19,1640208,1214459,1217458,1640208,65.608,48.638,16.970,0.424
20,1640250,1214584,1214667,1640208,65.609,48.585,17.024,0.426
21,1640209,1217334,1214667,1640208,65.608,48.640,16.968,0.424
22,1640250,1214500,1214667,1640208,65.609,48.583,17.026,0.426
23,1643250,1214708,1214625,1640250,65.670,48.587,17.083,0.427
24,1640250,1214625,1214667,1643500,65.675,48.586,17.089,0.427
25,1640250,1214750,1214667,1640208,65.609,48.588,17.021,0.426
26,1640250,1214625,1217500,1640208,65.609,48.642,16.967,0.424
27,1640250,1214583,1214750,1652833,65.862,48.587,17.275,0.432
28,1640209,1217666,1219292,1640208,65.608,48.739,16.869,0.422
29,1640208,1214667,1214667,1640208,65.608,48.587,17.022,0.426
30,1643041,1214584,1214625,1640208,65.665,48.584,17.081,0.427
31,1640250,1214667,1214708,1643125,65.668,48.587,17.080,0.427
32,1640250,1214500,1214667,1640083,65.607,48.583,17.023,0.426
33,1640167,1214625,1218458,1640250,65.608,48.662,16.947,0.424
34,1640250,1214458,1214667,1640208,65.609,48.583,17.027,0.426
35,1640250,1217875,1214625,1640250,65.610,48.650,16.960,0.424
36,1640208,1224292,1214667,1640250,65.609,48.779,16.830,0.421
37,1657584,1215875,1215875,1856250,70.277,48.635,21.642,0.541
38,1872833,1216000,1216709,1870917,74.875,48.654,26.221,0.656
39,1856291,1216042,1215833,1856292,74.252,48.638,25.614,0.640
summary,mean_a_ns_per_token=73.880,mean_b_ns_per_token=54.608,mean_savings_ns_per_token=19.272,mean_savings_ns_per_layer=0.482,bootstrap95_lower_ns_per_token=17.967,bootstrap95_upper_ns_per_token=20.806,threshold_ns_per_token=6530.349,verdict=NO-GO,checksum=1513781170765395334
```

## Decision calculation

| Quantity | Result |
| --- | ---: |
| Mean A | 73.880 ns/token |
| Mean B | 54.608 ns/token |
| Mean paired savings | 19.272 ns/token |
| Mean paired savings per layer | 0.482 ns/token/layer |
| Bootstrap 95% lower bound | 17.967 ns/token |
| Bootstrap 95% upper bound | 20.806 ns/token |
| GO lower-bound threshold | 6,530.349 ns/token |
| Equivalent threshold per layer | 163.259 ns/token/layer |
| Lower bound / threshold | 0.002751 |
| Decision | **NO-GO** |

The CPU proxy is not an end-to-end decode estimate and cannot establish an M5
speedup. It is deliberately favorable to the proposed specialization because
it isolates the removable operation. Even under that isolated design, the
lower confidence bound is only about 0.275% of the required savings. This is
not close enough to justify production implementation or a model benchmark.

## Cleanup and recommendation

The temporary benchmark source, executable, symbol listings, and disassembly
files were removed after capturing this report. The ignored release scratch
build is not part of the submitted diff. The working submitted surface remains
unchanged.

**Recommendation:** close this mechanism as a measured negative. Preserve the
release-disassembly finding as useful attribution evidence, but do not spend a
production-change or model-timing allocation on concrete KV-cache
specialization.
