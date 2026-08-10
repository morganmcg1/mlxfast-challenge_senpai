# Metal JIT resource-attribution probe

**Outcome: Gate 0 NO-GO.** On this M4 Pro/Xcode 26.6 host, the accessible Metal paths do not expose a usable candidate-sensitive register, occupancy, spill-volume, or memory-transaction metric for non-spilling kernels. The experiment therefore stopped before control reruns, per the assignment gate.

## Scope and provenance

- Assignment: PR #647, branch `cedar-tanjiro/metal-jit-resource-attribution`.
- Required production base: `fa463e5a0600e9248ace9668773e11e09061914d`.
- Measurement started from `2981a14ef6b00b238f6edea7c26294ae6bfec496`; it was tree-identical to the required base before this report.
- No production, vendored, harness, package, or benchmark file was changed. Only this report and its JSON table are retained.
- Host: Apple M4 Pro, 48 GB; macOS 26.5.2 (25F84); Xcode 26.6 (17F113); macOS 26.5 SDK; Swift 6.3.3; Apple clang 21; Metal compiler MobileAsset 17.6.109.0 / Apple metal 32023.883.
- W&B: N/A. This is local toolchain measurement, not training and not an official submission.

## Predeclared decision rule

Before calibration, a filter could pass only if it exposed a direct resource metric (registers, spilled bytes, occupancy, or load/store transactions), reproduced with no more than 1% spread over five builds/runs, added no more than 1% timed-workload perturbation, and classified both known timing-negative controls in the same direction. AIR syntax, metallib size, native-text size, pipeline width, and maximum thread count were excluded as resource-pressure proxies.

## Gate 0 capability matrix

| Path | Invocation/result | Exposed data | Verdict |
|---|---|---|---|
| AIR/metallib | `xcrun metal -std=metal3.2 -O3 -c probe.metal -o probe.air`; `xcrun metallib probe.air -o probe.metallib`; both rc 0 | AIR LLVM IR; deterministic container | Compiler realization only |
| `metal-objdump` | `--disassemble` rc 0; `--build-table=all` rc 0 with unsupported-file diagnostic | AIR IR, metadata; no native ISA or resource report | Unusable |
| `g16g` | `xcrun g16g`, rc 72 | Tool unavailable | Unusable |
| `strings` | probe AIR/metallib | No register, spill, occupancy, or transaction fields | Unusable |
| Pipeline reflection | local Swift/Metal probe, job `f11b3089-8d06-4ece-b9d7-97f6c4e950e0`, rc 0 | Both kernels: width 32, max threads 1024, static TG memory 0, two bindings | Not candidate-sensitive |
| Counter API | same probe | One counter set, `timestamp`; four samples; only `GPUTimestamp`; stage sampling supported, dispatch sampling unsupported | Timestamp only |
| Metal GPU Counters template | `xctrace record --template 'Metal GPU Counters' --launch -- probe`, job `bf354009-90b4-48c0-a892-959580e65576`, rc 0 | Warning: selected counter profile unsupported; zero counter-info/value rows | Unusable |
| Metal System Trace | `xctrace record --template 'Metal System Trace' --launch -- probe`, job `a51b1547-a7e5-4cde-a101-6b05e0519ddf`, rc 0 | Spill-event schema available, but zero spill/activity rows; counter set contained only unrelated `RT Unit Active` | No separator |
| Shader profiler list | System Trace export | Scalar/vector PC spans 110/100 bytes | Native-text size; explicitly excluded |
| Command-buffer timestamps | public API/header inventory | GPU start/end timestamps available | Timing, not attribution |

Public pipeline-state/reflection headers expose thread execution width, maximum threads, static threadgroup memory, and bindings, but no register count, spill allocation, occupancy, or memory-transaction count. The System Trace spill table is the sole resource-adjacent path: it reports discrete compiler spill events and `spilled-bytes`, but both representative scalar and vector kernels generated zero rows. It cannot rank ordinary non-spilling candidates.

## Determinism and artifact integrity

A representative OProj scalar-versus-`uint2` load probe was compiled five times. Every compile and link returned 0 and produced identical artifacts:

| Repeats | AIR bytes / SHA-256 | metallib bytes / SHA-256 | spread |
|---:|---|---|---:|
| 5 | 4240 / `01e9ce458f447b9c100711252c151e406418d6b95e9fb4e7658d67bd63b99ab3` | 7788 / `4364bab9e1bd6994bcaffc2d615be0ebbf0229c5f75356771d93a98ed51f2c22` | 0% |

The optimized AIR preserved the intended distinction (scalar `i32`, alignment 4; vector `<2 x i32>`, alignment 8). That proves compiler realization, not register or memory-resource improvement.

Selected trace-export hashes (raw traces were not retained because they contain host identifiers):

| Export | rows | SHA-256 |
|---|---:|---|
| System Trace spill events | 0 | `d990503e165c1c840466f945f3aef7884ad8ed171f9fd97dbd069b0ac7d827bc` |
| System Trace compiler activity | 0 | `680d6f3f164d5577a12f9ae620a515b99826c272c6dae282223c5295cfa32c4b` |
| System Trace shader list | 2 | `94b3bcb8eff5691a70bc984c881c25cef7bc7bdc559e0d69fa0d09463872a898` |
| GPU Counters counter info | 0 | `21d4602564c9f6c99b44441795e2aa4a67e7adf603378ab2d1b5f44a6768cc6c` |
| GPU Counters values | 0 | `68b62a3c4315f71a6179a8852a1d3a9aa40672cf3066fc98875e700e9e2f689a` |

## Controls and perturbation

No new ABBA/BAAB timing was run after Gate 0 failed. Historical control evidence was used only to verify the required classification target:

| Control | Compiler realization | Prior matched timing | Available direct metric | Classification |
|---|---|---|---|---|
| #637 prefill RoPE `float4`, head `77b0c8cada8fd05519d006a7a91569076e4a9d97` | aligned `<4 x float>` AIR; unchanged width/max threads/static TG memory | ABBA 121 cycles: 0.999451845x, 95% CI savings [-3812.5, -1062] ns; timing-negative | None | Cannot classify |
| #643 decode OProj `uint2`, head `c79fe498b2ddf8a3321927a317bf2888bda5d741` | `<2 x i32>` alignment 8 versus scalar alignment 4; unchanged pipeline proxies | ABBA +19.820 us CI [-5.884,+45.524]; BAAB -4.931 us, 0.996736x, CI [-10.807,+0.945]; order reversal | None | Cannot classify |

| Perturbation check | Result |
|---|---|
| Required resource instrumentation overhead <=1% | Not assessable: no usable resource metric survived Gate 0 |
| Bare probe wall time | 0.374 s; pipeline/counter capability probe only |
| Metal System Trace launch wall time | 6.771 s; not comparable to a timed kernel sample |
| Metal GPU Counters launch wall time | 10.935 s; unsupported profile |

## Conclusion

The hypothesis was not validated. The local public/release toolchain can confirm that vector source constructs survive into AIR, but it cannot attribute their timing behavior to register pressure, occupancy, spills, or memory transactions. The one spill-event schema is candidate-sensitive only when a compiler spill occurs; it was empty for both kernels and cannot separate the known negative OProj control. Proceeding to #637/#643 reruns or optional #638 would violate the predeclared gate and risk replacing timing with nondiagnostic size proxies.

**Recommendation:** do not use this toolchain as a prefilter. Revisit only with a supported Apple GPU counter profile or an authorized native compiler-resource report that exposes numeric registers/occupancy/transactions and can first pass the two negative controls.

_Generated by OpenHands, an AI agent, on behalf of the assigned research student._
