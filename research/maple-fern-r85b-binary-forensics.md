# R85-B binary forensics: what the split changes, and what a re-rolled build changes

Artifacts: `/tmp/maple-r85b-snap/{base,cand,cand2}/mlxfast-runtime-worker`,
`/tmp/maple-r85b-split/{emit,objects}-*.{json,txt}`, `binaries.sha256`, `binary-sizes.txt`.
Base = `3217f111142346e004f41fae611a8bede172a659`. Arms built in order cand -> base -> cand2,
each from a pruned object directory, `cand2` from source **byte-identical** to `cand`.

## 0. Arm identity

| arm | source | worker SHA256 | size (B) | objects |
|---|---|---|---:|---:|
| base | `3217f111` `LagunaRuntimeModel.swift`, no `LagunaRuntimeLayers.swift` | `074dc162…` | 49,091,816 | 9 |
| cand | HEAD (split) | `9c8a12d9…` | 49,092,440 | 10 |
| cand2 | HEAD (split), independent rebuild | `2c5294fa…` | 49,092,440 | 10 |

`prune_stale_objects()` is load-bearing: without it SwiftPM keeps `LagunaRuntimeLayers.swift.o`
from the previous arm and links it into `base`. The base arm here is confirmed at 9 objects, and
the object-name sets differ between base and cand by exactly `LagunaRuntimeLayers.swift.o`.

## 1. The build is deterministic for identical source (headline)

`cand` vs `cand2` — byte-identical Swift source, two independent `swift build` invocations with a
full `base` build in between to force a genuine re-roll:

* **Emitted object code is bit-identical.** `fern_emit_compare.py diff emit-cand.json emit-cand2.json`
  → `VERDICT: code-identical`. Every one of the 31 non-DWARF sections has delta `+0`, including
  `__TEXT,__text` at 443,488 B in both. Defined symbols 9,151 vs 9,151, `only-in-cand=0`,
  `only-in-base=0`, both raw and with private discriminators normalised.
* **Every symbol lands at the same address.** `nm -n -U` over the linked worker: 143,140 symbols in
  each, `common=143,140`, `only-in-A=0`, `only-in-B=0`, and **143,140 / 143,140 at an identical
  address (shift bucket `+0`, count 143,140; no other bucket exists)**. Restricted to the 2,314
  `12MLXFastModel` symbols: all `+0`.
* The linked executables nonetheless differ, but only in **455 of 49,092,440 bytes (0.00093 %)**:

  | region | bytes | what it is |
  |---|---:|---|
  | load commands, offsets 4328–4343 | 16 | `LC_UUID` (`07F724A6-…` vs `E2A4F0B4-…`) |
  | `LINKEDIT` symtab / strtab / code signature | 300 | symbol-table ordering + the signature hash, which must change if any byte does |
  | `__TEXT,__objc_stubs` | 138 | one byte in each of 138 ObjC msgSend stubs |
  | `__TEXT,__stubs` | 1 | one byte in one stub |

* The stub difference decodes to a **single GOT slot**. In each 32-byte stub the 4th word changes
  `f9429210` → `f9429610`, i.e. `ldr x16, [x16, #0x520]` → `ldr x16, [x16, #0x528]`: imm12 165 vs 164,
  scaled ×8. `_objc_msgSend`'s GOT entry moved by exactly one pointer. **The stub addresses are
  unchanged** (`0x101220ac0` in both dumps), the instruction count is unchanged, and the referenced
  target is unchanged.

**Interpretation.** For this toolchain and this source, a rebuild is *not* a code lottery. There is no
codegen re-roll, no function reordering, no alignment or page displacement — only build-identity
metadata and a one-slot GOT permutation in ObjC interop stubs that the scored Swift decode path does
not go through. This has two consequences:

1. The `cand2` arm is **not** measuring a layout lottery. It is a clean **null control built through the
   full independent-build pipeline**, so its paired band is an empirical noise floor for the
   instrument, the session and the build process combined. That is a stronger control than planned.
2. It is direct evidence *against* "a different build rolls different code" as the mechanism behind the
   PR #457 give-back (11.1 µs/step, 42 %, on untouched kernels with byte-identical executables). At the
   Swift/Mach-O level there is nothing to re-roll. The remaining live hypotheses in fb5 — Metal **JIT
   pipeline compilation ordering** and **GPU power/clock redistribution** — are not touched by this
   result, and the identical-executable premise of the #457 observation is here reproduced from the
   opposite direction: identical source really does give an identical image.

## 2. The split is a deterministic relayout, not a lottery

`base` vs `cand`:

* Object-level: `VERDICT: code CHANGED`. `__TEXT,__text` 443,132 → 443,488 B, **+356 B (+0.080 ‰)**.
  Per object: `LagunaRuntimeModel.swift.o` 261,652 → 202,720 (−58,932) and the new
  `LagunaRuntimeLayers.swift.o` 0 → 59,288 (+59,288). Net +356.
* Symbol-name delta, private discriminators normalised: `only-in-cand=83`, `only-in-base=13`.
  The 13 removals are exactly the widened declarations losing their file-private discriminator —
  `lagunaDecodeEmbeddingRoPEAtlas` (+4 `Tv*` thunks), `lagunaRouterPrecomputedKeysEnabled`
  (+`_WZ`/`_Wz` once-tokens), `lagunaTerminalPrefillFusionEnabled` (same), plus one specialised
  `makeLagunaAttentionGateProjection` thunk and one `_ArrayBuffer` specialisation. Their internal
  twins reappear on the `+` side under the undiscriminated mangling. This is precisely the
  five-widening set, and nothing else.
  The remaining `+` entries are type-metadata accessors and witness-table symbols
  (`…GMd`, `…GMR`, `…sWL`) that WMO must now emit in a second object file.
* Link-level: 143,137 vs 143,140 symbols, `common=142,993`. **99,189 common symbols move**;
  43,804 stay put. The shift histogram is dominated by small constants — `+92` (47,153),
  `+160` (22,157), `−16` (9,713), `+96` (7,521), `+16` (4,967), `+144` (2,866), `+32` (2,624),
  `+176` (995) — consistent with +356 B of text plus per-section realignment rippling downstream.
  Within `12MLXFastModel` (2,171 common symbols) 407 are unmoved and there are two large buckets,
  `+90,888` (114 symbols) and `+93,856` (59), which are the carve itself being relocated because
  `LagunaRuntimeLayers.swift.o` sorts before `LagunaRuntimeModel.swift.o` in the WMO object list.

**Interpretation.** The split does displace code, and that displacement is real — but §1 shows the
toolchain is deterministic, so the displacement is a **fixed, reproducible function of the source**,
not a coin flip that the official M5 build might re-roll differently. That converts the layout question
from "unbounded and unclosable" into "one specific, repeatable relayout whose cost is what the paired
campaign measures". It does not make the layout concern vanish — Mytkowicz 2009 and STABILIZER 2013
are about exactly this kind of constant displacement — but it does mean the measured band applies to
the same relayout that would ship.

## 3. What this evidence does and does not close

Mechanism partition (frontier framing), updated with the measurements above:

| mechanism | status |
|---|---|
| M1 semantic change in moved code | Closed by construction (verbatim move) and by the symbol-delta audit: the only mangling changes are the five widenings. Pending: binary-level body-identity via `fern_emit_compare.py asm`, deferred so as not to perturb the in-flight campaign. |
| M2 changed behaviour / dispatch | Closed by the gates: 64-step tripwire `passed=True`, upstream equivalence 1 test executed, `--local-submit` `passed_correctness=True max_abs_diff=0`, plus `0 divergences` on every campaign run's teacher-forced token stream. |
| M3 build/layout lottery | **Newly bounded.** Identical source ⇒ identical addresses (§1), so there is no per-build lottery to average over. The split's relayout (§2) is deterministic and is the thing under test. |
| M4 measurement/session drift | Bounded by the counterbalanced ABBA pairing and, empirically, by the `cand2` null arm. |

Honest holes: this is an M4 Pro (Apple GPU gen 16) toolchain and linker; the official M5 build uses the
same source but its own link. §1 makes it likely, not certain, that the M5 link is equally
deterministic. And determinism is not neutrality — a fixed relayout can still cost time, which is what
the paired band is for.
