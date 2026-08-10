# R107-A — routed MoE gate/up threadgroup-packing curve (PR #629)

Student: maple-edward. Branch `maple-edward/r107-routed-gateup-packing`.
Assigned head `526881c4f6e2b879c1dfef67212b852cf5c9b7ed`, PR base
`ca39d2163255a4fdda39609447328b76acd7f0a9`.

Host: Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, macOS 26.5.2, Apple GPU
generation 16 (`applegpu_g16s`), low-memory startup profile. Every timing number
below is M4-local and directional; only the tagged structural claims are argued
to transfer.

---

## 0. Blocking process defect (read first)

PR #629 contains **no `<!-- senpai-assignment:v1 ... -->` marker**. Verified at
2026-08-10T10:03Z (creation), 10:46Z and 10:59Z: zero markers, zero comments,
zero reviews, `updated_at` frozen at `2026-08-10T10:03:23Z`. The controller has
re-emitted `malformed_assignment` on every poll.

Repair is advisor-owned (`repair_assignment_routing`). My tool surface is
`get_prs`, `respond_to_human_issue` (needs a human-authored Issue; none exists)
and `submit_experiment_result`; the terminal `gh` is unauthenticated. I have no
way to comment on the PR, so this document is the notification channel.

Consequence: `submit_experiment_result` needs `assignment_id` and `revision_id`
that the missing marker was supposed to supply. The experiment was run to
completion anyway so that no advisor time is lost once routing is repaired.

## 0a. Correction to the PR body

The PR body names the site as `lagunaRoutedSwiGLUQMVPackedTop8Kernel`. That is
the **v1 fallback**
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_bf16_v1`, declared at
`LagunaRuntimeModel.swift:7892-7902`). The shipped default on the scored decode
path is the **R1** variant
`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, declared at
`:7915-8028`, selected at `:8044` unless `DARKBLOOM_ROUTED_GATEUP_R1=0`).
The experiment parameterizes R1, which is the code that actually runs.

---

## 1. Rule-83 history search

TODO

## 2. Mechanism and implementation

TODO

## 3. Stage 0 — reached geometry, parity, fault control

TODO

## 4. Stage 1 — rotated-palindrome full-decode timing

TODO

## 5. Prefill

TODO

## 6. Verdict against the graduation gate

TODO

## 7. Suggested follow-ups (not implemented)

TODO

## 8. Artefacts

TODO
