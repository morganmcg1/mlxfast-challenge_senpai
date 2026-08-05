# Dead Code Removal — Budget Recovery Plan

**Date:** 2026-08-05T19:50Z
**Purpose:** Free editable-surface byte budget for the merge gate/up QMV experiment.
**Current budget:** 3,000,000 byte cap, ~3,495 bytes headroom. Need ~5,300 bytes for merge gate/up QMV.
**Analysis source:** Explore agent (dead-code-analysis task), read-only measurement pass.

## Tier 1 — SAFEST, fully dead by default (~12,096 bytes total)

### 1. DARKBLOOM_PREFILL_ROUTER_TOP8 (~7,457 bytes)

- **Location:** `LagunaRuntimeModel.swift` lines 9008–9147 (flag+doc+kernel+func) + 9624–9641 (dispatch)
- **Status:** Default-OFF. Superseded by `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT` (default-ON).
- **Safety:** Tournament code references no Top8 symbols — cleanly separable.
- **Removal:** Delete the flag declaration, kernel, function, and dispatch block. No other code depends on it.

### 2. DARKBLOOM_PREFILL_FUSED_SHARED (~1,430 bytes)

- **Location:** `LagunaRuntimeModel.swift` lines 3950–3959 (flag+doc) + 8537–8558 (call block)
- **Status:** Default-OFF. Doc explicitly states "RANKED GATE-FAILED... Left in-tree as the receipt."
- **Safety:** Standalone `if` block, no dependencies.
- **Removal:** Delete the flag and the standalone if-block.

### 3. DARKBLOOM_FUSED_QKV safe parts (~2,061 bytes)

- **Location:** `LagunaRuntimeModel.swift` lines 94–100, 5434, 5560–5586, 11280–11286
- **Status:** Default-OFF. Superseded by `DARKBLOOM_FUSED_QKV_PROJECTION` (default-ON).
- **Safety:** Safe parts are the flag, doc, and unused dispatch. Note: the interleaved serving branch (5857–5872, ~972 B) is riskier to remove — leave it.
- **Removal:** Delete only the listed line ranges. Preserve the interleaved serving branch at 5857–5872.

### 4. DARKBLOOM_FUSED_FULL_ATTN_WHOLE_MODEL_WARMUP (~1,148 bytes)

- **Location:** `LagunaRuntimeModel.swift` 1831–1836 + `LagunaRuntimeWeights.swift` 482–494
- **Status:** Default-OFF. Doc calls it "retired bundled arm."
- **Safety:** Requires `var warmDecodeLogits` → `let` at weights line 480.
- **Removal:** Delete the flag in LagunaRuntimeModel.swift and the warmup function body in LagunaRuntimeWeights.swift. Change `var warmDecodeLogits` to `let warmDecodeLogits`.

## Tier 2 — Medium risk, ~11,800 bytes more (optional)

These are lower priority and riskier. Only remove if additional budget is needed:

1. V1 ablation kernels in LmHeadPrune (~4,305 B) — kept for A/B tooling protocol
2. PREFILL_TAIL_WIDELD dead arm (~2,056 B) — collapsible ternary
3. SHARED_FIRST_DOWN dead arm (~1,344 B) — collapsible ternary
4. Measured-null warmup function bodies (~3,125 B) — need 2-file edits

## Procedure

1. Remove all four Tier-1 candidates from `LagunaRuntimeModel.swift` and `LagunaRuntimeWeights.swift`.
2. Build with `swift build -c release --force-resolved-versions` to verify compilation.
3. Run `./benchmark.sh --local-iterate` to verify correctness and no timing regression.
4. Run `senpai/check-editable-budget.sh "$BASE_SHA"` to verify the freed budget.
5. Expected freed bytes: ~12,096 (3.5× the 3,495 B currently needed; comfortably exceeds the ~5,300 B needed for merge gate/up QMV).

## Risk Assessment

- **Correctness:** All four flags are default-OFF, so removing them changes no runtime behavior. The ranked path never executes any of this code.
- **Compilation:** The `warmDecodeLogits` var→let change is the only structural modification. Verify with a release build.
- **A/B testing:** These flags were used for past experiments. Removing them eliminates the ability to A/B test those specific mechanisms, but they are all superseded by newer mechanisms (Tournament, FUSED_QKV_PROJECTION, etc.).
- **Upstream equivalence:** Not required since no numerical path is changed. All removed code is dead by default.
