#!/usr/bin/env python3
"""R127-A §13 — executable form of the §12 applier's work order (edits A1–A25).

Why this exists: #741 is read-only by assignment, so the 25 corrections in §12 of
`research/r127a_provenance_audit.md` were shipped as prose. Prose does not survive a
2-hour handover with five students. This script carries the same 25 edits as *data*
(exact spans / exact substrings, each guarded by an md5 of the text it expects to find
at the audited advisor head) and can either emit a `git apply`-able patch or write the
files in a checkout that the operator owns.

It edits three files this branch does **not** own — the manifest, the state file and
`slot_holder_arithmetic.py` — which is why the default mode is `--check` and why
`--apply` refuses to run without an explicit `--root`.

No GPU, no build, no benchmark, no network. Pure text.

Usage
-----
  # 1. is the audited text still there, unchanged, at the ref?
  python3 research/tools/r127a_s13_apply_work_order.py --check

  # 2. the minimum useful patch (A2+A3+A4: stops screening against a bar ~30 % low)
  python3 research/tools/r127a_s13_apply_work_order.py --emit-patch --only A2,A3,A4

  # 3. everything, or one tier
  python3 research/tools/r127a_s13_apply_work_order.py --emit-patch
  python3 research/tools/r127a_s13_apply_work_order.py --emit-patch --tiers D

  # 4. write into a checkout you own
  python3 research/tools/r127a_s13_apply_work_order.py --apply --root /path/to/worktree

Exit codes: 0 all selected edits are present-and-unapplied (or already applied),
2 drift (a guard did not match), 3 usage error.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import subprocess
import sys

REF = "6778867dc8579eff3302d49d064c2bc0cf60ead2"  # codex/mlxfast-maple-20260804-advisor @ 12:59Z
MAN = "research/maple_endgame_handoff_manifest.md"
CRS = "research/CURRENT_RESEARCH_STATE.md"
TOOL = "research/tools/slot_holder_arithmetic.py"

# ---------------------------------------------------------------------------
# The work order. Two edit kinds:
#   span: replace lines [start, end] (1-based, inclusive) with `new`
#   subs: on line `line`, apply each (old, new) substring replacement in order
# `guard` is the md5 of the exact text expected at the ref (span text joined by "\n",
# or the single line). Regenerate with --print-guards after any deliberate re-target.
# ---------------------------------------------------------------------------

A1_NEW = [
    "There are not four currencies. There are **two hosts** × **two quantities**, and only one of the",
    "four combinations is the scored denominator. Score divides by `decode_seconds_per_token`, and",
    "`LagunaRuntimeLocalIterate.swift:767-769` charges the 512-token seed forward into it",
    "(`includes_seed_prefill=true`, `:776`), so the denominator is `D = S/decodeSteps + T`, **not** the",
    "step-only time `T`. `Constants.swift:113` fixes the scored config at 128 steps; `:117` runs",
    "`--local-submit` at 1023, which shrinks the seed's share ~8× and produces a *different* `D` on the",
    "*same* host. A µs/step delta in `T` moves `D` one-for-one, so the only correct rate is `0.75 / D`",
    "at 128 steps. Every row below is labelled by (host, harness, step count).",
    "",
    "| currency | decode step | 1 µs/step is | provenance |",
    "|---|---|---|---|",
    "| **ranked host `D₁₂₈`** (what the receipt scores) | **4910.9 µs** | **0.01527 % of score** | measured: `mean_D` of replicate group `dc437b0e`, n=5, r103 artifact |",
    "| **our M4 `D₁₂₈`** — the scored local denominator | **≈12 798 µs** | **0.00586 % of score** | measured by `./benchmark.sh --local-iterate`, the 128-step harness: `research/maple-alphonse-r114-gatesp.md:432-434,:444-446` (36 runs, arm means 0.0129820 / 0.0129052 s/tok); `research/maple-edward-r110/REPORT.md:294-297` (12 775–12 972 µs) |",
    "| ~~our M4 `--local-submit`~~ **`D₁₀₂₃`, not a scored denominator** | 8882 µs | — | measured by maple-nezuko, #730 (N2/N4/N8 levels 8880.9–8888.4). 1023 steps (`Constants.swift:117`) ⇒ the seed is amortised ~8× thinner than the scored config. Do not price against it. |",
    "| ~~frieren's bench control host~~ **step-only `T`, not a `D`** | 8213 µs | — | measured, #733 (control median 8.213–8.217 ms; a fast mode at 8.148–8.152 also exists — see §5b). `LagunaRuntimeLocalIterate.swift:631` reports `totalStepOnlySeconds` as a *separate* field from the scored `secondsPerToken` (`:864`). Add `S/128` before pricing. |",
    "",
    "Cross-check, from the trusted brief: `senpai/program.md:216-221` states `--local-iterate` carries",
    "`sigma = 33.6 %` of prefill share against `--local-submit`'s \"about 5.9 %\". With `T ≈ 8470 µs` that",
    "puts `D₁₂₈` at 12 369–13 376 µs (12 798 sits mid-band) and predicts `D₁₀₂₃ ≈ 9024 µs` at",
    "σ = 6.1 % — closing on nezuko's 8882 and program.md's 5.9 %. (#741 §6.1, F1.)",
]

A2_NEW = [
    "**(a) The 0.00586 %/µs constant is correct, and the reason it looked unsourceable is the same trap",
    "as (b).** It implies a 12.8 ms decode step, which is exactly what the *scored* 128-step harness",
    "measures on our M4; the 8.2–8.9 ms figures are a step-only time and a 1023-step denominator. The",
    "constant did **not** manufacture the delta-1 headline: §4c already establishes that the headline came",
    "from a column misread (sign) and from pricing a `+66.88` counterfactual instead of the `+4.67`",
    "measurement (14×). `66.88 × 0.00586 = 0.392 %` is the *correct* price of a +66.88 µs/step local",
    "delta; the input was wrong, not the exchange rate. Frieren's #733 prices therefore stand as banked:",
    "FUSED is **−0.323 %**, not −0.504 %. (#741 §6.2, F1.)",
]

A3_NEW = [
    "Requirement table in the two *scored* denominators (from §6.5) — each host's own `D₁₂₈`:",
    "",
    "| target | % of score | ranked µs/step (`D` = 4910.9) | local µs/step (`D₁₂₈` ≈ 12 798) |",
    "|---|---|---|---|",
    "| +0.26 % (**3.2 %** chance at the bar, §6.5c; the \"≈10–15 %\" printed here earlier was error 5) | 0.26 | **17** | **44** |",
    "| +0.50 % (**8.0 %** chance at the bar, §6.5c; the \"≈50 %\" printed here earlier was error 5) | 0.50 | **32** | **85** |",
    "| +1.26 % (**50 %** chance at the bar — the real even-money delta, §6.5c) | 1.26 | **82** | **215** |",
]

A4_NEW = [
    "The old table's \"44 / 84\" local column was **right to within rounding** (`0.26/0.005860 = 44.4`,",
    "`0.50/0.005860 = 85.3`), and the \"31 / 59\" that replaced it sets the bar **≈30 % too low — the",
    "flattering direction**, because it divides by a `D₁₀₂₃` the score never sees. There is no separate",
    "bench-host column: convert a step-only `T` delta into the measuring host's `D₁₂₈` first, then divide.",
    "(#741 §6.3/§8.1, F1.)",
]

A5_NEW = [
    "— was the instrument (§5b). The +0.50 % target needs **85 local µs/step** and the phantom band tops",
    "out at ≈64, so every candidate that looked big enough to matter was, at its own screen's face value,",
    "*still not big enough* — and then turned out to be the instrument as well. That is the deepest reason",
    "this campaign could not have succeeded by local screening alone. (#741 §6.4, F1.)",
]

A6_NEW = [
    "One figure this correction rescues: §7 item 2's \"≈8919 µs wall vs ≈8567 µs busy\" is a **local M4 wall",
    "step** measured under the 1023-step harness (consistent with nezuko's 8882), so its ~350 µs of",
    "non-busy time is worth `0.75 × 350/12798 =` **2.05 %** of score locally against the scored `D₁₂₈`,",
    "not the `0.75 × 350/8919 = 2.94 %` a `D₁₀₂₃` denominator would suggest. It remains the largest single",
    "decode opportunity in the document, still local, still subject to the ~42 % end-to-end evaporation of",
    "#473, still unattacked. (#741 §6.5, F1.)",
]

A7_NEW = [
    "**Rule for reuse: never write a µs/step number without naming the host, the harness, and the decode",
    "step count.** One host has two step lengths (`T` and `D`) and two denominators (128 and 1023 steps).",
    "Prices in percent-of-score are safe to move between sections; prices in µs/step are not.",
]

A8_NEW = [
    "(the local equivalents in this sentence are ≈44 and ≈85 µs/step: they come from the 0.00586 %/µs",
    "currency, which §6.6 as corrected shows is **sourced and right** for our M4's scored 128-step",
    "`D₁₂₈` ≈ 12 798 µs — the \"31 and 59 µs/step\" that briefly replaced them divide by a `D₁₀₂₃` the",
    "score never sees and set the bar ≈30 % low; #741 §8.1, F1),",
]

A13_NEW = [
    "> W&B `cccr6f2q`), i.e. **≈ −0.03 % of score** on the isolated-kernel delta. #729's own wall arm is",
    "> null ([−19.33, +17.86] µs/step ⇒ |Δscore| ≤ 0.11 %); the \"as much as −0.14 %\" that stood here came",
    "> from edward's **routed-expert** measurement (#731), a different kernel and a disjoint dispatch site",
    "> (#741 §6.9, F7). Every \"+0.38 %\" in §4a/§4b is my misreading of",
]

A17_NEW = [
    "Operating point (ranked host): `mean_D = 4910.9 µs` (replicate group `dc437b0e`, n = 5, r103",
    "artifact) — **this is the number all ranked prices divide by**. The `S = 97.863 ms` /",
    "`T = 4.3224 ms` pair implies `D = 5087 µs` and `research/RESEARCH_IDEAS_2026-08-06_09:00.md:3` gives",
    "4908.372; the three span 3.6 % and only the measured `mean_D` is traceable to a run. σ from the",
    "stated `S`/`T` is **15.03 %**, not 14.98 %; elasticities decode 0.638, seed 0.362 either way.",
    "Pooled `ns` cv 0.149 %. (#741 §6.12, F10.)",
]

A18_NEW = [
    "| ~~within-program σ 0.1860–0.2276 %~~ — **not a rail at all** | — | `need = BAR/cs` is a *draw factor*; a replicate sd of `cs` cannot be its σ (#741 F19) |",
    "| **measured `sd(ln official) = 0.3728 %`, n = 5** — the predictive σ | program mean **2.586989** (correct) | **0.037 %** (z = 3.38); honest n=5 interval **[≈0 %, 12 %]** |",
]

A19_NEW = [
    "Hers is **confirmed, not shrunk**: the draw factor `L = official/cs` was measured on 12 distinct",
    "programs in the 2026-08-04 ledger (`RESEARCH_STATE_ARCHIVE_through-round-21.md:5684-5695`) at",
    "`sd(ln L) = 0.5568 %`, 11 dof, 95 % CI [0.394 %, 0.945 %]; `cs` spans 8.8 % across those programs and",
    "`corr(ln cs, ln L)` is not distinguishable from zero, so there is no between-program leakage to",
    "discount. The 0.1860–0.2276 % replicate sd of `cs` is not a rail on the draw factor at all. The",
    "predictive σ for one more official run of a program we hold is measured directly:",
    "`sd(ln official) = 0.3728 %` (n=5, group `dc437b0e`) ⇒ **≈0.04 % per draw, 95 % interval",
    "[≈0 %, 12 %]** (#741 §10.3/§11.2, F19/F21).",
]

A19B_NEW = [
    "The empirical 1.48 % is an **upper** bound because it is a tail count, not because of leakage:",
    "fern's 0.538 % is measured *across* programs, and the draw factor's own sd is 0.5568 % when measured",
    "on 12 distinct programs whose `cs` spans 8.8 % (#741 F21), so there is nothing to discount away. The",
    "rail that governs *\"re-fire the tree we hold\"* is the directly measured `sd(ln official) = 0.3728 %`",
    "(n = 5, group `dc437b0e`), which prices one draw at **≈0.04 %** with an honest 95 % interval of",
    "**[≈0 %, 12 %]** (#741 F19). Plan against that, not against `[≈0 %, 1.5 %]`: that bracket's lower",
    "rail was a replicate sd of `cs` — not a draw factor at all — and its upper rail was an empirical tail",
    "wrongly assumed inflated. Nothing about the endgame conclusion changes except its strength: at",
    "≈0.04 % per draw, re-firing is worth less again than the previous revision said.",
]

A19C_NEW = [
    "consistently from the program mean, my within-program σ gives z = 6.3–7.8 ⇒ P ≈ 0 — but that σ is a",
    "replicate sd of `cs` and `need = BAR/cs` is a *draw factor*, so it was never a rail on this question",
    "(#741 F19). The predictive σ is measurable directly: `sd(ln official) = 0.3728 %` (n = 5, group",
    "`dc437b0e`) prices one draw at **≈0.04 %**, honest 95 % interval **[≈0 %, 12 %]**. Plan against that,",
    "not against the `[≈0 %, 1.5 %]` bracket printed here earlier. Her arithmetic reproduces to six",
    "digits; mine did not survive, and the reason it did not is now named.**",
]

A21_NEW = [
    "  variance is the `bl_pre` baseline draw.",
    "  🚨 **RE-ANCHOR REQUIRED (#741 F20).** The P(record) table that stood here was computed against the",
    "  **retired** crown 2.61650354381456 over the median draw (`2.616504/0.998597 = 2.620180`). The crown",
    "  moved to **2.6195531094824** (`cdcd091` / `4ea72c3b`) at ≈02:14Z on 2026-08-11, so every per-draw",
    "  figure below is optimistic by **≈1.7–1.9×**: at our best-ever `cs` it prints 3.239 %/draw where the",
    "  same method re-anchored gives ≈1.8–1.9 %, which this file's own elasticity — \"+0.1 % of `cs`",
    "  multiplies p/draw by 1.56×\", the sentence immediately after the retired table — predicts.",
    "  Re-anchored break-even `cs` is `2.6195531094824/0.998597 = 2.623234`, not 2.620180. Retired values,",
    "  kept only so the discount is auditable: `cs` 2.575633 → 0.415 %; **2.582286 → 0.748 %** (1-in-134);",
    "  2.585060 → 1.163 %; 2.588362 → 1.744 %; **2.590559 → 3.239 %**; 2.591868 → 4.153 %;",
    "  2.600 → 14.286 %; 2.610 → 34.551 %; **2.6202 → 50 %**. At our operating",
]

A23_NEW = [
    "# `need` is a DRAW FACTOR, not a score ratio: OUR_PROGRAM is a program-normalized `cs` and BAR is an",
    "# *official* score (= cs x L), so `need` asks \"what draw multiplier must one more official run of our",
    "# own program deliver?\". That is why WITHIN_SD -- a replicate sd of `cs` -- is not its sigma (741 F19).",
    "need = BAR / OUR_PROGRAM",
    "print(\"    multiplier needed      \", f\"{need:.6f}\", \"(6.5b: 1.014441)\")",
]

A24_NEW = [
    "# 741 F19: the predictive sigma of a draw factor is measurable directly -- sd(ln official) over our",
    "# own program's replicate group -- and every row below is centred on that program's mean draw",
    "# (DRAW_MEDIAN), never on 1.0. WITHIN_SD is deliberately no longer used in this comparison: it is a",
    "# replicate sd of `cs`, and `need` is a draw factor (see the comment above), so it is not a rail here.",
    "OFFICIAL_SD = 0.003728         # 741 10.3, measured sd(ln official), n=5, group dc437b0e",
    "DRAW_SD_12PROG = 0.005568      # 741 11.2, sd(ln L) over 12 programs, 11 dof, CI [0.394 %, 0.945 %]",
    "",
    "",
    "def p_draw(sd, centre=DRAW_MEDIAN):",
    "    zz = (need - centre) / sd",
    "    return zz, 1.0 - 0.5 * (1.0 + math.erf(zz / math.sqrt(2.0)))",
    "",
    "",
    "z_off, p_off = p_draw(OFFICIAL_SD)",
    "print(\"    z (measured official sd) \", f\"{z_off:.3f}\", \"-> normal p =\", f\"{p_off*100:.3f} %\",",
    "      \"(741 F19: 0.037 % taken in logs, 0.036 % in this ratio form; honest n=5 CI [~0 %, 12 %])\")",
    "z, p_norm = p_draw(DRAW_SD)    # fern's draw component; p_norm feeds sections E and F below",
    "print(\"    z (fern draw component)  \", f\"{z:.3f}\", \"-> normal p =\", f\"{p_norm*100:.2f} %\",",
    "      \"(6.5b: z=2.344, 0.95 % normal / 1.48 % empirical)\")",
    "z_12, p_12 = p_draw(DRAW_SD_12PROG)",
    "print(\"    z (draw factor, 12 progs)\", f\"{z_12:.3f}\", \"-> normal p =\", f\"{p_12*100:.2f} %\",",
    "      \"(741 F21: measured on 12 distinct programs, so it is not between-program leakage)\")",
]

A25_NEW = [
    "### 6.5b Independent confirmation from the opposite direction — the winner's curse (maple-fern, #686)",
    "",
    "> ⚠️ **Provenance (#741 F17): the primary source is not in the tree.** PR #686 closed unmerged and",
    "> `research/fern-r109f-interim-1200Z.md` is absent at head — no file matching `r109f` exists — so this",
    "> section's numeric core (`2.576540`, `2.582263`, `1.016694`, `1.009444`, `1.001830`) occurs in the",
    "> repository a successor receives **only** here, in `MAPLE_TO_SLOT_HOLDER_BRIEF.md`, and in",
    "> `research/tools/slot_holder_arithmetic.py:10-14` — all of which cite this section. §9.5 reaches the",
    "> same conclusion entirely in-tree. **The conclusion survives; the citation does not.**",
]

EDITS = [
    # id, tier, finding, path, kind, payload, guard
    dict(id="A1", tier="D", finding="F1", path=MAN, kind="span", start=999, end=1004,
         new=A1_NEW, guard="4c10feab69de08f5c3e2dea76b3859d2", note="§6.6 currency table — two hosts × two quantities"),
    dict(id="A2", tier="D", finding="F1", path=MAN, kind="span", start=1008, end=1014,
         new=A2_NEW, guard="a5f5d02843133fc2189f2f7cadf93071", note="§6.6 consequence (a) — constant is sourced, drop UNSOURCED"),
    dict(id="A3", tier="D", finding="F1", path=MAN, kind="span", start=1027, end=1033,
         new=A3_NEW, guard="16a7eb4bb81129b94b6f30dc55b8d44a", note="§6.6 requirement table — local column is 44 / 85 / 215"),
    dict(id="A4", tier="D", finding="F1", path=MAN, kind="span", start=1035, end=1036,
         new=A4_NEW, guard="cd8f6780e644287cae2a604b5cb0e2a6", note="the '~40 % too high' sentence is backwards (≈30 % too low)"),
    dict(id="A5", tier="C", finding="F1", path=MAN, kind="span", start=1044, end=1046,
         new=A5_NEW, guard="af06b16d90f4097f324a3ba3e45e6d3a", note="§6.6 closing — 85 local µs/step vs a band topping out at ≈64"),
    dict(id="A6", tier="C", finding="F1", path=MAN, kind="span", start=1048, end=1052,
         new=A6_NEW, guard="a58c5b72d27d51f1bdde7dfd1f9856dd", note="§7-item-2 reprice — 2.05 %, not 2.94 %"),
    dict(id="A7", tier="P", finding="F1", path=MAN, kind="span", start=1054, end=1055,
         new=A7_NEW, guard="a41517ed30e030d34492f000a14b9c1e", note="Rule for reuse — name harness and step count, not just host"),
    dict(id="A8", tier="D", finding="F1", path=MAN, kind="span", start=819, end=820,
         new=A8_NEW, guard="0ca1b032c2bc043c4e37a7a4009ccaf6", note="§6.5 second copy of the 44/84 → 31/59 inversion"),
    dict(id="A9", tier="C", finding="F5", path=MAN, kind="subs", line=468,
         subs=[("gave up −82 µs/step.",
                "gave up **−35 µs/step** (#718's corrected figure; the −82/−80/−79.4 renderings are superseded, #741 §6.7).")],
         guard="f7feb06d0f3734197138a2689d24cc01", note="§5 o_proj — −35, not −82"),
    dict(id="A10", tier="C", finding="F6", path=MAN, kind="subs", line=241,
         subs=[("**REFUTED. −0.282 % of score**",
                "**REFUTED. −0.282 % of the decode step = −0.135 % of score**")],
         guard="ead8c85b699e9c6ac74cd5d769a68b44", note="§4 row 4 — #731 units (apply with A11)"),
    dict(id="A11", tier="C", finding="F6", path=MAN, kind="subs", line=481,
         subs=[("**−0.282 % score**",
                "**−0.282 % of the decode step = −0.135 % of score**")],
         guard="a6d1cc63411b4c30b19dcb4dd7fe45ce", note="§5 — #731 units, second copy (apply with A10)"),
    dict(id="A12", tier="P", finding="F7", path=MAN, kind="subs", line=416,
         subs=[("edward's routed-wall replication (#731)",
                "edward's routed-**expert** measurement (#731 — a different kernel and a disjoint dispatch site from delta 1's shared-expert SwiGLU QMV)")],
         guard="114134a4d00a0657c3dfa259bff6b143", note="§4c — routed/shared conflation"),
    dict(id="A13", tier="P", finding="F7", path=MAN, kind="span", start=257, end=258,
         new=A13_NEW, guard="55da3fb8cb010a6429008d0618ffe597", note="§4a banner — the −0.14 % bound belongs to another kernel"),
    dict(id="A14", tier="C", finding="F8", path=MAN, kind="subs", line=321,
         subs=[("**≈ −0.03 % of score or worse**",
                "**≈ −0.03 % of score** (isolated leg +4.73 ± 0.52 µs/step; #729's wall arm is null, [−19.33, +17.86] µs/step ⇒ |Δscore| ≤ 0.11 %)")],
         guard="c0a40e1c0336e4955a920fdfed248ae3", note="§4b DO-NOT-LAND cell — restore §4c's hedge"),
    dict(id="A15", tier="C", finding="F9", path=MAN, kind="subs", line=239,
         subs=[("**≈ +0.04 % of score** — not worth a draw",
                "**≈ +0.062 % of score** — not worth a draw"),
               ("≈ +0.17 % prefill ≈ **+0.04 % score**",
                "≈ +0.17 % of the seed/prefill forward ⇒ **+0.062 % of score** (§1's seed elasticity 0.362, not the bare 0.25 prefill weight; #741 §6.11)")],
         guard="3891b65849260b5b936176e2aaf45df4", note="§4 row 2 — delta 2's axis weight (apply with A16)"),
    dict(id="A16", tier="C", finding="F9", path=MAN, kind="subs", line=503,
         subs=[("≈+0.17 % prefill ⇒ **≈+0.04 % score**",
                "≈+0.17 % of the seed/prefill forward ⇒ **+0.062 % of score** (§1's seed elasticity 0.362, not the bare 0.25 prefill weight; #741 §6.11)")],
         guard="a9e95017dbe6d035834b0083474f5053", note="§5 — delta 2, second copy (apply with A15)"),
    dict(id="A17", tier="C", finding="F10", path=MAN, kind="span", start=157, end=158,
         new=A17_NEW, guard="ee90701cd07a08f31a29ee1a409a9d52", note="§1 operating point — lead with mean_D, σ = 15.03 %"),
    dict(id="A18", tier="D", finding="F19", path=MAN, kind="span", start=954, end=954,
         new=A18_NEW, guard="aef9726d5a2e52d6f254dfe7dc7c8f6b", note="§6.5c bracket — the lower rail is not a rail"),
    dict(id="A19", tier="D", finding="F21", path=MAN, kind="span", start=908, end=909,
         new=A19_NEW, guard="b580f520e96df7ef089663445fdb8fd2", note="§6.5c — fern's 0.538 % is confirmed, not leakage"),
    dict(id="A19b", tier="D", finding="F19+F21", path=MAN, kind="span", start=958, end=962,
         new=A19B_NEW, guard="fdaf6f8bf6051492e8d1682ee2ed0941", note="§6.5c — second copy of the leakage discount + the [≈0 %, 1.5 %] bracket"),
    dict(id="A19c", tier="D", finding="F19", path=MAN, kind="span", start=896, end=898,
         new=A19C_NEW, guard="d04e5ac79fd889ee42ff7a42ec3c624d", note="§6.5b retraction — the bracket's lower rail was never a rail"),
    dict(id="A19d", tier="C", finding="F19", path=MAN, kind="subs", line=62,
         subs=[("brackets it lower still at **[≈0 %, 1.5 %]**",
                "brackets it lower still — and #741 F19 re-prices that bracket on the directly measured `sd(ln official) = 0.3728 %` (n=5) as **≈0.04 % per draw, 95 % interval [≈0 %, 12 %]**")],
         guard="438c9bfa3e945c49e132bf755eca6043", note="§0 executive summary — third copy of the bracket"),
    dict(id="A20", tier="D", finding="F20", path=CRS, kind="subs", line=3412,
         subs=[("Record still **2.61650354381456**",
                "Record **2.61650354381456** is the *retired* crown — superseded at ≈02:14Z on 2026-08-11 by `cdcd091` / `4ea72c3b` at **2.6195531094824** (+0.1165 %; #741 F20)")],
         guard="631c34605a169d13838dd5b74233fb49", note="CRS — the crown moved (apply with A21)"),
    dict(id="A21", tier="D", finding="F20", path=CRS, kind="span", start=3511, end=3514,
         new=A21_NEW, guard="9a6149a14ac6e76657394273530776e1", note="CRS P(record) table — optimistic ≈1.7–1.9× (apply with A20)"),
    dict(id="A22", tier="C", finding="F21", path=CRS, kind="subs", line=3509,
         subs=[("median 0.998597, sd(ln L) 0.5359 %,",
                "median 0.998597 (undated here; the 2026-08-04 ledger `RESEARCH_STATE_ARCHIVE_through-round-21.md:5684-5695` gives 0.992644 — +0.60 % apart, 1.6× the predictive σ), sd(ln L) 0.5359 %,")],
         guard="42292f2b36ea79b5cd50ee4ab88db252", note="CRS — date-stamp the median draw factor"),
    dict(id="A23", tier="D", finding="F19", path=TOOL, kind="span", start=35, end=36,
         new=A23_NEW, guard="efa2a00cb4b10b0152af3d042ac45b1c", note="tool — name the random variable (a draw factor)"),
    dict(id="A24", tier="D", finding="F19", path=TOOL, kind="span", start=37, end=44,
         new=A24_NEW, guard="dff58e43c0a60e8296b92b825ea416c7", note="tool — right σ, right centre (four lines become a block)"),
    dict(id="A25", tier="P", finding="F17", path=MAN, kind="span", start=872, end=872,
         new=A25_NEW, guard="7740d122c7d0f8d9f1a3d5c4d467f77b", note="§6.5b — primary source not in tree; conclusion survives"),
]

APPLY_ORDER_NOTES = """
Couplings (from §12.2): A3 with A4; A10 with A11; A15 with A16; A20 with A21.
A1-A8 are one edit in seven places (all F1). Minimum useful set: --only A2,A3,A4.
A18, A19, A19b, A19c, A19d, A23, A24 are one edit in seven places (F19 + F21); A19b/c/d
are the second, third and fourth copies of the [~0 %, 1.5 %] bracket and of the
'between-program leakage' discount, found while checking that the patched document did not
contradict itself four lines below A18's table. Apply the whole F19/F21 group or none of it.
This tool applies per file in descending line order, so ordering is handled for you.
"""


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def read_ref(path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{REF}:{path}"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"cannot read {REF}:{path} -- {out.stderr.strip()}")
    return out.stdout.split("\n")


def read_root(root: str, path: str) -> list[str]:
    with open(f"{root.rstrip('/')}/{path}", encoding="utf-8") as fh:
        return fh.read().split("\n")


def old_text(lines: list[str], e: dict) -> str:
    if e["kind"] == "span":
        return "\n".join(lines[e["start"] - 1:e["end"]])
    return lines[e["line"] - 1]


def new_text(e: dict, current: str) -> str:
    if e["kind"] == "span":
        return "\n".join(e["new"])
    out = current
    for old, new in e["subs"]:
        out = out.replace(old, new)
    return out


def status_of(lines: list[str], e: dict) -> tuple[str, str]:
    """Return (state, detail). state in {ok, applied, drift}."""
    if e["kind"] == "span":
        span = lines[e["start"] - 1:e["end"]]
        if len(span) != e["end"] - e["start"] + 1:
            return "drift", "span runs off the end of the file"
        got = "\n".join(span)
        if e["guard"] and md5(got) == e["guard"]:
            return "ok", ""
        if lines[e["start"] - 1:e["start"] - 1 + len(e["new"])] == e["new"]:
            return "applied", "already applied"
        return "drift", f"md5 {md5(got)} != guard {e['guard']}; first line: {span[0][:70]!r}"
    if e["line"] > len(lines):
        return "drift", "line past end of file"
    line = lines[e["line"] - 1]
    if e["guard"] and md5(line) == e["guard"]:
        missing = [old for old, _ in e["subs"] if old not in line]
        if missing:
            return "drift", f"guard matched but substring absent: {missing[0][:60]!r}"
        return "ok", ""
    if all(old not in line for old, _ in e["subs"]) and all(new in line for _, new in e["subs"]):
        return "applied", "already applied"
    return "drift", f"md5 {md5(line)} != guard {e['guard']}; line: {line[:70]!r}"


def apply_to(lines: list[str], edits: list[dict]) -> tuple[list[str], list[str]]:
    """Apply edits (same file) to `lines`, descending by position so numbering holds."""
    out = list(lines)
    log = []
    for e in sorted(edits, key=lambda x: x.get("start", x.get("line", 0)), reverse=True):
        state, detail = status_of(out, e)
        if state == "drift":
            log.append(f"  {e['id']}: DRIFT — {detail}")
            continue
        if state == "applied":
            log.append(f"  {e['id']}: already applied, skipped")
            continue
        if e["kind"] == "span":
            out[e["start"] - 1:e["end"]] = e["new"]
        else:
            out[e["line"] - 1] = new_text(e, out[e["line"] - 1])
        log.append(f"  {e['id']}: applied ({e['tier']}, {e['finding']}) — {e['note']}")
    return out, log


def select(args) -> list[dict]:
    edits = EDITS
    if args.only:
        want = {x.strip().upper() for x in args.only.split(",")}
        edits = [e for e in edits if e["id"].upper() in want]
        missing = want - {e["id"].upper() for e in edits}
        if missing:
            sys.exit(f"unknown edit id(s): {sorted(missing)}")
    if args.tiers:
        tiers = {t.strip().upper() for t in args.tiers.split(",")}
        edits = [e for e in edits if e["tier"] in tiers]
    if not edits:
        sys.exit("selection is empty")
    return edits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify guards at the ref (default)")
    ap.add_argument("--emit-patch", action="store_true", help="print a unified diff against the ref")
    ap.add_argument("--apply", action="store_true", help="write files under --root")
    ap.add_argument("--print-guards", action="store_true", help="recompute the md5 guard table")
    ap.add_argument("--root", default=None, help="checkout to read/write (default: read from ref)")
    ap.add_argument("--only", default=None, help="comma-separated edit ids, e.g. A2,A3,A4")
    ap.add_argument("--tiers", default=None, help="comma-separated tiers, e.g. D or D,C")
    args = ap.parse_args()

    if args.apply and not args.root:
        sys.exit("--apply needs an explicit --root: these three files are owned by others (usage error)")
    edits = select(args)
    paths = sorted({e["path"] for e in edits})
    source = (lambda p: read_root(args.root, p)) if args.root else read_ref

    if args.print_guards:
        for e in EDITS:
            lines = source(e["path"])
            print(f'    {e["id"]}: "{md5(old_text(lines, e))}",')
        return 0

    if args.emit_patch:
        chunks = []
        for p in paths:
            lines = source(p)
            new, log = apply_to(lines, [e for e in edits if e["path"] == p])
            for line in log:
                print(line, file=sys.stderr)
            if new == lines:
                continue
            diff = difflib.unified_diff(lines, new, fromfile=f"a/{p}", tofile=f"b/{p}", lineterm="")
            chunks.append("\n".join(diff))
        if not chunks:
            print("nothing to emit", file=sys.stderr)
            return 2
        print("\n".join(chunks))
        return 0

    if args.apply:
        rc = 0
        for p in paths:
            lines = read_root(args.root, p)
            new, log = apply_to(lines, [e for e in edits if e["path"] == p])
            print(f"{p}")
            for line in log:
                print(line)
                if "DRIFT" in line:
                    rc = 2
            if new != lines:
                with open(f"{args.root.rstrip('/')}/{p}", "w", encoding="utf-8") as fh:
                    fh.write("\n".join(new))
        return rc

    # default: --check
    print(f"ref {REF}" if not args.root else f"root {args.root}")
    bad = 0
    for e in edits:
        lines = source(e["path"])
        state, detail = status_of(lines, e)
        flag = {"ok": "OK   ", "applied": "DONE ", "drift": "DRIFT"}[state]
        loc = f'{e["path"]}:{e.get("start", e.get("line"))}'
        print(f'{flag} {e["id"]:<4} {e["tier"]}  {loc:<48} {e["note"]}')
        if state == "drift":
            print(f"        {detail}")
            bad += 1
    print(f"\n{len(edits) - bad}/{len(edits)} targets verified" + (f"; {bad} DRIFT" if bad else ""))
    print(APPLY_ORDER_NOTES.strip())
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
