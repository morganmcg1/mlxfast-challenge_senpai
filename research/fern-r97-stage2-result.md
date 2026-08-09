# R97-A Stage 2 result — layer-0 dense-MLP block-exponent compaction

Assignment `maple-r97-a-dense-mlp-stage2`, revision `r97-a-rev1`, PR #525.
Base `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.
Preregistration: `research/fern-r97-stage2-preregistration.md`, committed as
`1e683e5` before any timing datum was collected.

Host: M4 Pro, 48 GiB, low-memory startup profile. **Directional only.** The M4
Pro reports Apple GPU generation 16 and does not select the `_nax` prefill
kernels the ranked M5 uses; every number below is a decode-side measurement on
the shipped dense-MLP path, which is the same kernel family on both machines,
but the official M5 remains authoritative.

## 1. What shipped

Three submitted files:

| path | role |
|---|---|
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | `LagunaDenseBlockExponentBank`, packer, bit-exactness certificate |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | two block-exponent kernels, their wrappers, the two selection flags |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` | bank construction at load time and the dispatch preference |

Both banks are built once outside the scored hot path and are installed only
after a certificate rebuilds every BF16 pattern of the plane bit-for-bit; a
plane that fails the certificate is declined and the stock path runs.

## 2. Timed states

| state | gate/up plane | down plane |
|---|---|---|
| base | stock BF16 | stock BF16 |
| S2a | block-exponent `B=128, d=4`, escapes allowed | stock BF16 |
| S2b | block-exponent `B=128, d=4`, escapes allowed | block-exponent `B=row(8192), d=6`, no escapes |

<!-- RESULTS -->

## 3. Escape census, confirmed at load time

The packer prints one census line per plane. Observed with
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`:

```
block-exponent B128 d4 escaped 1735/262144: dense gate/up
block-exponent B8192 d6 escaped 0/2048: dense down
```

Both match the preregistration exactly. The preregistration predicted 1735
escaped gate/up blocks (858 gate + 877 up) out of 262,144 and zero escaped
down rows out of 2,048; the bytes/step arithmetic in §5 of the preregistration
was computed from those counts, so the byte predictions carry no census risk.
Both certificates passed, so neither plane was declined.

## 3b. Rung-control verification

Before any timed comparison the instrument itself was checked. The ladder
patch replaces the two `*Active()` predicates with a read of a shared mmap
control word, so a silent mmap failure would fall back to the static default
(rung 2) and dispatch both kernels in every process — an instrument that
reports "no effect" for the wrong reason. Three single-rung processes were run
with `SCHEDULE="const:0;const:1;const:2"` and dispatch logging on:

| process | rung | `block-exponent kernel:` notes | token-stream hash | teacher-forced mismatches |
|---|---|---|---|---|
| p00 | 0 (base) | none | `004d82089b71b300` | 0 |
| p01 | 1 (S2a) | `dense gate/up` | `004d82089b71b300` | 0 |
| p02 | 2 (S2b) | `dense gate/up`, `dense down` | `004d82089b71b300` | 0 |

The control word is therefore read live, each rung selects exactly the intended
kernel set, and all three rungs produce the identical token stream.

## 4. Equivalence and correctness

<!-- CORRECTNESS -->

## 5. Byte budget

<!-- BUDGET -->

## 6. W&B evidence

<!-- WANDB -->

## 7. Reproduction

<!-- REPRO -->

## 8. Deviations from the preregistration

<!-- DEVIATIONS -->

## 9. Verdict against the go/no-go bar

<!-- VERDICT -->
