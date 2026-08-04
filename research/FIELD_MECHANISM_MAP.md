# Field mechanism map and promotion arithmetic

Advisor-owned analysis of the public `mlxfast` submission corpus for benchmark
`1854efdf-feba-4773-bae9-b80520881a74` (`laguna-xs-2.1-serial-v2`).

Snapshot: 2026-08-04T09:35Z. 1372 submission records; 909 carry complete
timing metrics.

Every submission's note is public and every submission's editable-path tree is
readable with `mlxfast reset <submission> --force`, **including rejected and
failed ones**. This is the largest information asset available to the campaign
and it is free.

## How to read any two official runs against each other

Published speedups use a same-session paired baseline, so raw `officialScore`
is not comparable across sessions. Normalise to the canonical reference first:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns              = norm_decode_su**0.75 * norm_prefill_su**0.25
```

The reference values are the tight cluster of session baselines: 10 of the last
12 promoted runs had `baseline_decode_seconds_per_token` inside
0.013875-0.013911 (+/-0.13%). Validated: `baseline_x / candidate_x` reproduces
each reported speedup to 1e-5, and `decode_speedup**0.75 * prefill_speedup**0.25`
reproduces `officialScore` to 1e-4.

Decompose each run into the two physical quantities before comparing
mechanisms (derivation and official validation in
`research/maple-fern-prefill-roofline.md`):

```
S = 512 * prefill_seconds_per_token                  # 512-token seed forward
T = decode_seconds_per_token - S/128                 # steady one-token step
sigma = (S/128) / decode_seconds_per_token
```

`S` and `T` say *where* a tree is fast. The two published ratios do not, because
`decode_speedup` blends both.

## The true frontier is a rejected submission

Ranking by `ns` irrespective of status. Rejection here means "did not beat the
promoted best", not a correctness failure.

> **Correction (nezuko #12).** The per-axis records below were read off this
> `ns`-sorted table and were wrong. The true field records are
> **nd 2.739127 (`ae9ac90b`)** and **npf 2.0220 (`e2822dc1`)**, neither of which
> is the `ns` leader. Their naive union is `ns = 2.5390`; de-biased for the
> winner's curse the true field ceiling is **2.5281–2.5318**. See
> "The field cannot promote us" below.

| id | user | status | created | ns | norm decode | norm prefill | S (ms) | T (ms) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `4bf4f794` | a-github-name | rejected | 08-04 06:39 | **2.5331** | 2.7338 | 2.0153 | | |
| `c00737b7` | metaspartan | rejected | 08-03 15:55 | 2.5284 | 2.7288 | 2.0112 | | |
| `0929b324` | a-github-name | rejected | 08-04 09:12 | 2.5277 | 2.7257 | 2.0160 | | |
| `eab0722b` | a-github-name | rejected | 08-04 05:32 | 2.5270 | 2.7264 | 2.0123 | | |
| `d643f13b` | a-github-name | rejected | 08-04 04:50 | 2.5270 | 2.7262 | 2.0126 | | |
| `86b31f1d` | a-github-name | rejected | 08-03 23:35 | 2.5269 | 2.7242 | 2.0165 | | |
| `2df3a1d6` | lBroth | rejected | 08-03 20:02 | 2.5264 | 2.7273 | 2.0083 | | |
| `56cfb68d` | rinaldofesta | rejected | 08-03 14:36 | 2.5264 | 2.7245 | 2.0143 | | |
| `913e588f` | davidtai | rejected | 08-04 02:57 | 2.5262 | 2.7216 | **2.0203** | | |
| `21f1d1a3` | metaspartan | accepted | 08-03 19:20 | 2.5260 | 2.7247 | 2.0127 | | |
| `0a9d439b` | davidtai | accepted | 08-03 12:28 | 2.5256 | 2.7232 | 2.0148 | | |
| `8415f63c` | promoted best / our base | accepted | 08-03 19:32 | 2.5165 | 2.7113 | 2.0120 | 97.820 | 4.3587 |
| `27b9c7c6` | **ours** | rejected | 08-04 07:53 | 2.5152 | 2.7123 | 2.0057 | 98.153 | 4.3530 |

Nine trees beat the one the whole field is sitting on. `4bf4f794` is **0.71%
ahead of us**. `S`/`T` for the harvested trees is nezuko's deliverable in #12.

Best prefill alone: `e2822dc1` (noskillcoding, 2.0220), `913e588f` (2.0203),
`2debe38b` (lBroth, 2.0196).

Note we are already marginally **ahead** of the promoted best on the steady step
(4.3530 vs 4.3587 ms) and **behind** on the seed forward (98.153 vs 97.820 ms).

## Session draw is not a strategy

Draw factor `= officialScore / ns`, i.e. how favourable a session's paired
baseline was. Over 909 records:

| min | p10 | p25 | median | p75 | p90 | p95 | p99 | max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.98066 | 0.98409 | 0.98540 | 0.98857 | 0.99411 | 0.99734 | 0.99904 | 1.00155 | **1.00896** |

`8415f63c` drew **1.0090** — essentially the maximum ever observed. It holds the
board on a session-lottery win, which is why nine better trees sit in the
rejected pile.

Promotion requires `officialScore > 2.53921`:

| our ns | required draw | P(draw) | expected submissions |
| ---: | ---: | ---: | ---: |
| 2.5152 (today) | 1.00954 | ~0 | never observed |
| 2.5260 | 1.00523 | 0.0033 | ~303 |
| 2.5331 (field best ever) | 1.00241 | 0.0077 | ~130 |
| 2.5400 | 0.99969 | 0.0363 | ~28 |
| 2.5450 | 0.99772 | 0.0847 | ~12 |

**Matching the best tree anyone has ever built still costs ~130 expected
submissions.** Resubmission is not a lottery ticket worth buying.
**Programme target: ns >= 2.545.**

There is no submission rate limit (only generic HTTP 429 handling,
`mlxfast.js:23629-23632, 23646-23651`). Round trip ~35 minutes.

## The board is frozen

2026-08-04: **41 submissions, 0 accepted.** Accepted per day — 07-24:11,
07-25:18, 07-26:12, 07-27:0, 07-28:13, 07-29:22, 07-30:6, 07-31:15, 08-01:28,
08-02:7, 08-03:7, 08-04:**0**. Corpus: 139 accepted (138 promoted), 769
rejected, 463 failed.

One outlier draw has stalled the entire field for ~14 hours. We are not racing
an hourly-moving target; spend the time to get the tree right.

## Mechanism coverage

Keyword index over all 1372 public notes. `hits` = submissions whose note
mentions the theme; `best_ns` = best normalised score among them. Median is
reported for completeness but is dominated by *when* a submission was made
rather than by the mechanism, so treat only `hits` and `best_ns` as signal.

| mechanism | hits | scored | best_ns | med_ns |
| --- | ---: | ---: | ---: | ---: |
| M5 specific | 1146 | 729 | 2.5331 | 2.0129 |
| graph capture / fusion | 997 | 655 | 2.5331 | 2.0182 |
| NVFP4 / fp4 | 953 | 627 | 2.5284 | 2.0854 |
| bit-exact claim | 942 | 633 | 2.5331 | 2.0615 |
| threadgroup geometry | 874 | 594 | 2.5331 | 2.0123 |
| LM head / logits | 847 | 553 | 2.5331 | 2.1123 |
| routing / topk | 752 | 499 | 2.5284 | 2.0866 |
| eval / synchronization | 704 | 464 | 2.5331 | 2.0445 |
| simdgroup / simd | 663 | 455 | 2.5284 | 1.9798 |
| int8 attention envelope | 533 | 333 | 2.5269 | 2.1339 |
| metal kernel | 525 | 346 | 2.5284 | 2.0229 |
| speculative / draft (banned) | 500 | 348 | 2.5331 | 2.2090 |
| RoPE | 496 | 324 | 2.5331 | 1.9198 |
| nax variants | 422 | 285 | 2.5284 | 2.0761 |
| quantized matmul qmm | 404 | 272 | 2.5284 | 1.9845 |
| prefill chunking | 391 | 220 | 2.5284 | 1.9741 |
| RMSNorm | 363 | 259 | 2.5284 | 1.9842 |
| SDPA / attention kernel | 349 | 252 | 2.5331 | 1.9700 |
| mask construction | 325 | 189 | 2.5234 | 1.9228 |
| float precision bf16/fp16 | 319 | 207 | 2.5284 | 1.9066 |
| thread mapping / vectorization | 312 | 233 | 2.5284 | 1.9217 |
| occupancy | 297 | 192 | 2.5284 | 1.9755 |
| allocation / buffer reuse | 275 | 208 | 2.5331 | 2.1024 |
| M4 specific | 254 | 165 | 2.5331 | 2.4457 |
| shared expert | 218 | 158 | 2.5269 | 2.1764 |
| KV cache | 202 | 120 | 2.5253 | 1.8692 |
| dequant | 182 | 115 | 2.5218 | 1.9066 |
| reduction / softmax | 175 | 125 | 2.5284 | 2.4903 |
| MoE gather-GEMM | 172 | 108 | 2.5205 | 1.9033 |
| concat / copy elimination | 172 | 86 | 2.5081 | 1.8699 |
| GQA | 146 | 87 | 2.5151 | 1.4872 |
| **latency vs bandwidth bound** | **137** | 64 | **2.5264** | 1.9413 |
| expert weight layout | 126 | 76 | 2.5231 | 2.1570 |
| autotune / sweep | 126 | 70 | 2.5203 | 1.9425 |
| command buffer / encoder | 125 | 90 | 2.5202 | 1.9920 |
| **host-side / CPU overhead** | **106** | 69 | **2.5264** | 2.1234 |
| steel gemm | 95 | 67 | 2.5179 | 1.9796 |
| **offline weight transform** | **58** | 30 | **2.5261** | 1.6151 |
| batching rows / multi-row | 56 | 28 | 2.5139 | 2.4906 |
| **residency / wired memory** | **53** | 44 | 2.4944 | 1.8349 |
| **core count / GPU cores** | **35** | 22 | 2.4611 | 1.7126 |
| lut / lookup table | 28 | 19 | 2.5213 | 2.1234 |
| **sliding window** | **18** | 12 | 2.5234 | 1.6555 |
| **wave quantization** | **1** | 0 | — | — |

### Reading the map — RETRACTED as an assignment signal (nezuko #12)

**The interpretation that used to sit here was wrong and is withdrawn.** It read
per-mechanism `best_ns` / `med_ns` off a keyword index over submission *notes*
and treated low-hit / high-best cells as headroom. nezuko showed the cells are
dominated by **note-length artifacts**: long notes mention many keywords, so hit
counts measure prose, not work. Splitting the corpus by axis and comparing
against the overall distribution gives a median
`|axis-mean nd − overall mean nd|` of **0.220%**, which is inside the measurement
noise. There is no per-axis signal in this table.

Two things survive:

1. **`Sources/MLXFastTransform/` has 0 attempts in 147 swept diffs.** This is a
   direct count over actual code diffs, not a keyword hit, so it is real. It is
   the only genuinely zero-attempt axis in the public record, and it is fern's
   #22. (The `offline weight transform` row's 58 keyword hits are notes that
   *discuss* transformation while changing runtime code.)
2. Keyword counts remain a fine way to answer "has anyone written about X",
   which is useful for avoiding a re-derivation. They are not a way to answer
   "is X under-explored".

Assignment selection now comes from the **decode byte budget and the M5
roofline** (`research/CURRENT_RESEARCH_STATE.md`), not from this table.

Saturation is still worth noting: anything above ~500 hits has certainly been
swept by someone on real M5 hardware, so our advantage there can only come from a
*model* that predicts the optimum rather than from sweeping.

Mechanisms in this table that the campaign has since closed on its own evidence,
so that nobody reopens them from a low hit count: `host-side / CPU overhead`
(frieren #14 — in-loop host CPU is fully absorbed by the GPU), `occupancy` and
`wave quantization` (tanjiro #13 — the risers are work imbalance, not occupancy),
`residency / wired memory` (fern #19 — the first forward is the *fastest*, and the
M5 constructor already wires ~31.4 GiB before hello), and `KV cache`
(frieren #14 — re-request amplification refuted at ≥6.9σ).

## The field cannot promote us

Normalising all 909 scored records: ours is nd 2.7130 (91st pct), npf 2.0057
(88th pct), ns 2.5157. Field records are nd **2.739127** (`ae9ac90b`) and npf
**2.0220** (`e2822dc1`).

```
naive union of both maxima:  ns = 2.739127^0.75 * 2.0220^0.25 = 2.5390
promotion needs                   officialScore > 2.53921 = ns * draw
```

The naive union lands one part in ten thousand short of promotion at a
draw of exactly 1.000. De-biasing both maxima for the winner's curse — measured
directly on family A (n = 18 byte-identical runs): nd +0.494%, ns +0.413% — gives
a **true field ceiling of 2.5281–2.5318**, which is 0.5–0.7% short of even the
1-in-12 shot at ns 2.545.

**The union of everything the entire public field has ever achieved cannot
promote us.** Every arm must therefore target a mechanism the field does not
have. `npf 2.0220` in particular has stood unbeaten for 102 subsequent
submissions; prefill, not decode, is the harder public wall.

## API access

```
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  https://api.mlx.fast/api/submissions/<uuid>
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions
```

The CLI truncates the `metrics` column; always use the API for numbers. Token
resolution order is `MLXFAST_API_TOKEN` -> `YUKON_API_TOKEN` ->
`SUPABASE_ACCESS_TOKEN` -> `~/.config/mlxfast/config.json`
(`/usr/local/libexec/mlxfast.js:20960`).

`mlxfast submission-note <id>` prints a note. `mlxfast reset <submission>
--force` restores editable paths from any submission. `mlxfast submit
--note-file <path> --model "Claude Opus 5"`; the note is public and mandatory,
5-100 KiB.

## Cached artifacts

Regenerable from the API; kept out of git.

- `/tmp/subs.json` — all 1372 raw records (14.9 MB)
- `/tmp/rows.json` — 909 records with id, user, status, created, officialScore,
  ns, norm decode, norm prefill, promoted, rejection reason
- `/tmp/allnotes_meta.json` — 1373 note metadata entries
- `/tmp/scan_hits.json` — 44 mechanism categories to submission-id lists
- `/tmp/mkmap.py` — regenerates the coverage table above

Note *bodies* were not persisted, only the keyword index. Harvesting the top
trees' actual notes and diffs is nezuko's assignment (#12).
