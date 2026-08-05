# PR #34 research artefacts (student `maple-tanjiro`)

## `instrument.patch` — the r1 real-kernel injection instrument

`instrument.patch` is the complete r1 measurement instrument for
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, kept out of the scored tree so
that the merged head leaves that file byte-identical to the assignment base
(`279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`) and returns its 13,351 bytes of
per-file budget to the campaign. Reapply it from the repository root with
`git apply research/tanjiro-pr34/instrument.patch` (add `--check` first to
verify, `-R` to remove it again); it touches only that one file and applies
cleanly to the base revision. It adds five injection knobs on top of the
empty-dispatch and memory-sweep knobs the base already carries, each read once
at process start through `lagunaInjectEnvInt(key, default)` and each defaulting
to `0`, i.e. fully inert, so an unset environment reproduces base behaviour
exactly: `DARKBLOOM_INJECT_DECODE_ATTN` and `DARKBLOOM_INJECT_PREFILL_ATTN` are
counts of extra attention q/k/v/o projection copies (units: copies per forward
pass, at most one per transformer layer, capped at 40);
`DARKBLOOM_INJECT_DECODE_ROUTED` and `DARKBLOOM_INJECT_PREFILL_ROUTED` are counts
of extra routed-expert top-8 gate/up + down-reduce copies (units: copies per
forward pass, capped at 39 routed layers); `DARKBLOOM_INJECT_ARCH_PROBE` is a
boolean (0/1) that prints the resolved GPU architecture generation once; and
`DARKBLOOM_INJECT_VERBOSE` is a boolean (0/1) that logs the realised injection
counts so a local run can confirm the intended dispatches were actually issued.
Because the official runner sets **no** environment variables, an official
receipt is produced by editing the *default literal* of the wanted knob, never
by exporting a variable.

## What the base already provides (no patch needed)

The base revision already carries the merged #27 hardware-constant instrument in
the block delimited by `// BEGIN M5 HARDWARE-CONSTANT INSTRUMENT` …
`// END M5 HARDWARE-CONSTANT INSTRUMENT`. Its knobs, also all
`lagunaInjectEnvInt` defaults, are:

| knob | default | units / meaning |
| --- | --- | --- |
| `DARKBLOOM_INJECT_DECODE_EMPTY` | 0 | minimal-GPU-work dispatches added per single-token decode step |
| `DARKBLOOM_INJECT_PREFILL_EMPTY` | 0 | same, per multi-token forward pass |
| `DARKBLOOM_INJECT_EMPTY_SPREAD` | 1 | 1 = spread the count over all 40 layer boundaries, 0 = all at layer 0 |
| `DARKBLOOM_INJECT_EMPTY_TG` | 160 | threadgroups per injected dispatch (× 256 threads) |
| `DARKBLOOM_INJECT_DECODE_SWEEPS` | 0 | 256 MiB memory-sweep dispatches per decode step |
| `DARKBLOOM_INJECT_SWEEP_PASSES` | 1 | passes over the pool per sweep dispatch |
| `DARKBLOOM_INJECT_PREFILL_MATMULS` | 0 | 512×8192×2048 BF16 GEMMs per prefill forward |

The r2 dispatch-saturation ladder uses only `DARKBLOOM_INJECT_DECODE_EMPTY` and
`DARKBLOOM_INJECT_EMPTY_TG`, so it needs **no** code beyond the base.

## Other files

`note-common.md` and `note-r1.md` … `note-r4.md` are the public submission notes
for the four r1 receipts; `cfg-r1.md` … `cfg-r4.md` are the per-receipt
configuration paragraphs spliced into them. `m4-L*.json` are the matched local
M4 `--local-iterate` ladder results backing the r1 method validation.
