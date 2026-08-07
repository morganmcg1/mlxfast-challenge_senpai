# Decode marginal-cost ledger by duplicate injection

PR #218 - `maple-2026-08-07e-decode-marginal-cost-ledger`, revision `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `0c86fc3b5b637a15eee8f95a82d30e67e3e481b3`.

Host: Apple M4 Pro, 20 GPU cores, 48 GiB (low-memory startup profile),
`applegpu_g16s` generation 16, Swift 6.3.3. Steady one-token decode step on
this host is **8.20 ms** (M5 promoted receipt: 4.1436 ms).

**This experiment ships a zero-byte submitted diff.** The instrument is
research-only and is published as
`research/maple-fern-decode-dup-injection.patch`.

---

## 0. Headline

The steady one-token decode step **absorbs 2.85 ms of extra independent GPU
kernel work at zero wall-time cost** - 35 % of the 8.20 ms step. Below that
threshold the marginal cost of GPU work is statistically zero; above it, work
passes through at 56 % of its census GPU microseconds.

Every kernel family on the decode path has a census cost of 0.12-0.43 ms/step,
i.e. **5-24x below the absorption threshold**. Therefore:

> Making any single decode kernel family cheaper - or deleting it outright -
> buys approximately nothing. The decode step is not throughput-bound.

This is a quantitative explanation for the programme's long run of
"census says 200 us, deletion measures 0 +/- 12 us" results (#204 among them),
and it re-prices the remaining optimization space: the lever is **dispatch
count and dependency-chain depth**, not arithmetic.

---

## 1. What was built

A duplicate-injection instrument (`enum LagunaDecodeDup`) inside
`LagunaRuntimeModel.swift`. At a wired site it re-issues the same dispatch
`K-1` extra times into scratch that nothing reads, appends the scratch roots to
the layer's `asyncEval` so they cannot be dead-code eliminated, and then
discards them. `K = 1` is bit-identical to the unmodified runtime.

Controls (all env, all default-off):

| Env | Meaning |
| --- | --- |
| `DARKBLOOM_DECODE_DUP_TARGET` | wired site name |
| `DARKBLOOM_DECODE_DUP_SCHEDULE` | per-segment K schedule |
| `DARKBLOOM_DECODE_DUP_CHAIN` | thread copy *i* into copy *i+1* (serial) |
| `DARKBLOOM_DECODE_DUP_VERBOSE` | per-forward census of every wired site |
| `DARKBLOOM_DECODE_DUP_FAULT` | perturb the **real** input by +1 bf16 ULP |

`research/fern_dup_probe.py` drives one worker process through a palindromic
schedule of K-arms, aligning to the worker's own segment announcements;
`research/fern_dup_stats.py` reduces it with the segment median as the unit of
replication.

