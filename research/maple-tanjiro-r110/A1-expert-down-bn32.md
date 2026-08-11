# R110-A arm A1 — routed/shared down-projection NAX tile `BN` 64 -> 32

Branch: `maple-tanjiro/r110-prefill-nax-arm-factory`.

Status (rev3): **delivered as a patch, second in the firing order.** A1 was the
branch head at rev2; rev3 promoted A2 to the head and demoted A1 to
`research/maple-tanjiro-r110/A1-expert-down-bn32.patch`. Apply it to the
assignment base — see `READY.md` §6 for the exact commands. `git apply --check`
and `git apply --numstat` were both re-run against the current head after the
swap: the patch applies cleanly and produces exactly
`1 1 Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`.

Base: `32665a6b66ce0d2d72b84772863575a6fdc35fb7`.

> **That base is the *gate-time* base, not the live one.** The live assignment
> base is `30904ecbf180aa05d7ddf5cc957e83155fbfc6f4`, and the numstat commands
> below still reference the old one. All of `32665a6b`, `adfca1e5`, `9fe37190`
> and `30904ecb` are **surface-identical** (`git diff --numstat <a> <b> --
> Sources Vendor benchmark.json Package.swift` is empty for every pair), so the
> A1 diff and its gate evidence carry across unchanged. Verify against
> `30904ecb`.

## The diff

```
$ git diff --numstat 32665a6b66ce0d2d72b84772863575a6fdc35fb7 -- Sources Vendor benchmark.json Package.swift
1	1	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

`quantized.cpp:1242`, inside `darkbloom_expert_down_bn()`:

```c
-      return 64;
+      return 32;
```

That is the whole arm. The `DARKBLOOM_EXPERT_DOWN_BN` env override still
accepts `32|64`, so fern can A/B the same binary in place with
`DARKBLOOM_EXPERT_DOWN_BN=64` if a bisect is ever wanted; the *default* — which
is what the ranked runner sees — moves to 32.

## Where it lands on the scored path

Single call site: `quantized.cpp:1396`, inside the gate at `:1393-1397`:

```
expert_aligned_gather && mode != "affine" && transpose
  && group_size == 16 && bits == 4
  && K == 512 && N == 2048
  && M >= 64 && bm == 64 && wm == 4 && (wn == 2 || wn == 1)
```

* `K == 512, N == 2048` selects exactly the routed-expert **down** projection
  (and the shared expert's down projection), nothing else.
* `M >= 64` makes this **prefill-only**. Decode runs `M == 8`; the gate is
  false there, so the decode leg of the score cannot move. This arm is a pure
  prefill arm, which is the 25 % leg — see "what this is worth" below.
* The default tile at this site comes from `darkbloom_stage_bm128_variant()`
  default `5`, i.e. `bm=64, wm=4, wn=1`.

So the change is `BN: 64 -> 32` with `WN = 1`:

| | before | after |
|---|---|---|
| `BN` | 64 | 32 |
| `SN = BN/WN` | 64 | 32 |
| `TN = SN/16` | 4 | 2 |
| `grid.x = ceil(N/BN)` | 32 | 64 |
| `grid.y = egroups` | 256 | 256 |
| `group_dims = (32, wn, wm)` | (32,1,4) | (32,1,4) |

`TN = 2` is even, so `tile_matmad_nax` takes its `TN % 2 == 0` path — the same
path `TN = 4` takes. No new code path in the kernel body, only a smaller
register tile and twice as many threadgroups.

`darkbloom_stage_wide_load_ok` still returns true at `bn=32`
(`col_step = 32 * 256 = 8192`, `% 16 == 0`), so the `_wl_1` flag in the kernel
name is unchanged. The only kernel-name delta is `_bn_64_` -> `_bn_32_`.

## Bit-exactness argument

`BN` partitions the **output column** axis `N` only.

1. The K-reduction is `BN`-independent: each output element still accumulates
   over the full `K = 512` in the same order, in the same `BK` chunks, with the
   same accumulator type. Changing how many columns a threadgroup owns does not
   reassociate a single dot product.
2. Each output element is written by exactly one threadgroup before and after;
   there is no cross-threadgroup reduction over `N`, so no atomics and no new
   ordering.
3. Scale/bias addressing for the NVFP4 operand is keyed on the **absolute**
   row/column index, not on a tile-relative one, so a narrower tile reads the
   same scales for the same columns.
4. The upstream comment at `quantized.cpp:1234-1237` is explicit that this
   shape "stores plain BN-wide Dtile slices, so BN is free there", in contrast
   to the fused gate/up shape where `BN` pairs column `c` with `c + BN/2` and
   *is* a correctness lock. We are not touching the gate/up `BN`.

Conclusion: bit-identical output, different thread geometry. This is a
scheduling arm, not a numerics arm.

## Build / template risk

The template is generic in `bn` (`get_template_definition(..., bm, bn, bk, wm,
wn, ...)` at `quantized.cpp:1590-1600`) and this kernel family is **JIT-only**,
so there is no AOT metallib entry to add and `tools/build-mlx-metallib.sh` is
not needed. The realistic failure mode is a JIT pipeline error on the first
prefill dispatch on M5, which would produce a cheap, unambiguous `failed`
receipt rather than a wrong number.

## Predicted direction

Honestly: **unknown sign, plausible small win.** Two competing effects:

* `+` More parallelism. `grid.x` doubles 32 -> 64, so the down-projection
  dispatch goes from `32 * 256 = 8192` to `64 * 256 = 16384` threadgroups.
  Both are far above one-per-core on a 40-core M5, so this is not an
  occupancy-filling argument; it is a *tail/imbalance* argument — the routed
  gather-GEMM has ragged per-expert row counts, and finer column tiles give the
  scheduler smaller units to pack.
* `+` Smaller register tile (`TN 4 -> 2`) reduces register pressure per
  simdgroup, which can raise resident simdgroups per core.
* `-` Each threadgroup re-reads the same `A` rows for half as many output
  columns, so total `A` traffic from device memory doubles for this shape. The
  advisor's own R105 note says the routed gather-GEMM is memory-bound, so this
  is a real cost, not a rounding error.

Net: this is exactly the kind of arm that has to be *measured on M5*, which is
the point of the queue. I am not claiming a win; I am claiming a clean, cheap,
single-knob, correctness-safe probe of a lever nobody has priced.

## What this is worth

Prefill elasticity 0.362 and `S ~= 97.9 ms`, so 1 ms off `S` is ~0.37 % of
score. The down projection is one of the two routed gather-GEMM shapes and runs
once per layer for 40 layers, so a 3 % move on that shape alone is order
0.3-0.5 ms. Under the withdrawn 0.378 % landing bar, any non-negative arm that
removes >= 0.3 ms of `S` is worth landing.

## Discriminator on the M5 receipt

Read candidate `prefill_seconds_per_token` against the reference
`1.87812e-4 +/- 2.607e-7 s/token` (n=14, sd 0.103 % on identical code).

* A 0.5 % move is ~9.4e-7 s/token, i.e. **~3.6 sigma** — resolvable in one run.
* A 0.2 % move is ~1.4 sigma — needs a repeat before it is believed.
* `decode_seconds_per_token` must be **statistically flat**. The gate is
  `M >= 64`, so decode cannot legitimately move; a decode move is evidence of a
  session/thermal artefact, not of this arm, and should invalidate the pair.

Both floors (`0.95` decode, `0.95` prefill) must hold; nothing here can move
decode, so the decode floor is a session-health check for this arm.

## Local gates run on this branch

Host: `Mac16,11` M4 Pro, 48 GB.

* `senpai/validate-assignment-scope.sh 1bc1c895... Vendor/.../quantized.cpp`
  -> `assignment scope OK: 1 submitted path(s)`.
* `senpai/check-editable-budget.sh 1bc1c895...` ->
  `editable budget OK: current=2681206/3000000 headroom=318794
  growth=-302643/262144 files=142`.
* `./benchmark.sh --local-iterate` -> `"passed": true`,
  `"passed_correctness": true`, `"max_abs_diff": 0`,
  `golden_hash b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`
  (this run *is* the public correctness/drift tripwire; `--local-iterate`
  executes it before timing). Timing on this host:
  `prefill 0.001111 s/token`, `decode 0.012955 s/token`.
* `research/run_upstream_equivalence.sh` -> see `GATES.md` in this directory.

### Caveat you must not skip

**This M4 Pro reports Apple GPU generation 16, `is_nax_available()` is false,
and it never selects any `_nax` kernel.** Therefore the local green above
proves: the tree builds, the harness is healthy, the non-NAX path is
unperturbed, and the change is syntactically/semantically sound C++. It does
**not** validate the `_nax` numerics or geometry, because the changed line is
only read inside the NAX gather-GEMM selection. The M5 receipt is the first and
only real test of this arm. Do not report the local green as correctness
evidence for the kernel itself.

Local prefill timing here is likewise **not** evidence for or against A1: on
this host the affected dispatch does not exist.
