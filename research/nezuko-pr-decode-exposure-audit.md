# Decode exposure audit: what 0.456 ms/step of "concurrency" actually is,
# and what the §2.b census is worth once it is priced correctly

*Assignment `maple-2026-08-06p-decode-exposure-audit`, revision `r1`, PR #174.
Host: Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, GPU generation 16, macOS
26.5.2, GPU idle 38-39 C. Decode-only; no `_nax` kernels are reachable here and
none are touched. Zero submitted-surface bytes: the diff is `research/` only.*

---

## 0. The contradiction, and the one number that resolves it

PR #101 forced the MLX Metal encoder from `DispatchTypeConcurrent` to
`DispatchTypeSerial` and measured **+0.456 ms/step** of decode wall time
(p = 0.029). My own PR #158 measured `gpu_busy_sum` flat at **7.99 +- 0.06 ms**
while command buffers per step went 45 -> 204, and concluded "hidden concurrent
work <= 0.06 ms/step". The two results differ by **7.6x** and cannot both
describe the same machine.

They do not. The resolution is a single arithmetic error in PR #158, and it is
the *same* 7.6x seen from the other side.

TBD-0: headline table.

---

## 1. Pre-registered prediction and verdict

The predictions in `research/nezuko-a0-split-prereg.md` were committed in
`625d451` **before any SPLIT=1 / SPLIT=2 dispatch-type data existed**.

TBD-1.

---

## 2. A0: the discriminator

TBD-2.

---

## 3. Exposure factors

TBD-3.

---

## 4. The re-priced census

TBD-4.

---

## 5. Top surviving decode targets, priced

TBD-5.

---

## 6. What to stop targeting

TBD-6.

---

## 7. Does `gpu_busy_sum` survive as an instrument?

TBD-7.

---

## 8. Reproduction

TBD-8.
