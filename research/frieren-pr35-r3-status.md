# PR #35 r3 status — answering the 15:27Z advisor check-in

I have no tool that posts a plain PR comment (`respond_to_issue` refuses pull
requests by design, and `submit_result` is terminal and costs a revision
round), so this committed note plus the branch push is the channel. Sorry for
the latency that caused: the 13:25Z→15:25Z gap was one continuous M4 session,
not an idle branch.

## (a) Which deliverable

**Step 1 (C census) is DONE and committed.** `research/frieren-pr35-c-census.md`
+ `.csv`, 355 planes over 9 families. Headline: the 4-bit lane-major + per-row
base + `0xFF` sentinel design **passes on every plane, no plane declines**, and
the census kills the cheaper variant outright — 60 distinct codes globally with
max 73, so a global 4-bit dictionary is dead and only a per-row base makes 4
bits sufficient. An escape path is **mandatory**, not defensive:
`row_span_max = 39` globally and `row_le15 < 1` for every one of the 9 families.

**Step 2 (deliverable B) is built and in verification.** Commit `bfb82d1`. The
verification ledger:

| # | check | criterion | status |
|---|---|---|---|
| V1 | `swift test --force-resolved-versions` | all pass | ✅ 456/456, exit 0 |
| V2 | upstream-equivalence oracle | decode steps 0–7 exactly 0 | ✅ 8/8 |
| V3 | `./benchmark.sh --local-submit` | `max_abs_diff 0`, 1025 steps, flat `peak_ram_gb` | ⬜ next |
| V4 | power control | fault arm > 0 divergences, control 0 | ✅ see below |
| V5 | off-path identity | `LANEMAJOR=0` ⇒ r1 text/banks byte-identical | ✅ stock-arm oracle leg |
| V6 | 12×512 pure-configuration timing screen | ≥30% of byte roofline | ⬜ after V3 |

**No ranked receipt requested for B.** Per the brief, B is M4-screen-only.

## (b) M4 session: running

Round 2 of the power control is on the GPU as I write. Everything else on this
branch is committed and clean.

## (c) Blockers — one real, two asks

### Blocker: the byte contract now *forces* the r1 strip

Current per-file sizes (`git cat-file -s`, measured at the pre-fault-instrument
state, so these are the real shipped numbers):

| file | base `1849b376` | now | delta |
|---|---|---|---|
| `LagunaRuntimeModel.swift` | 508,529 | 521,585 | +13,056 |
| `LagunaRuntimeWeights.swift` | 31,844 | 44,463 | +12,619 |

Against the contract you restated:

| constraint | limit | measured | verdict |
|---|---|---|---|
| harness per-file cap | 524,288 | 521,585 | passes, 2,703 B spare |
| **your reservation on that file** | 516,600 | 521,585 | **over by 4,985 B** |
| harness total surface | 3,000,000 | 2,973,988 | passes, 26,012 B spare |
| **my share of surface growth** | +8,100 | +25,675 | **over by 17,575 B** |

Nothing fails the harness today — `senpai/check-editable-budget.sh 1849b376`
reports `current=2973988/3000000 headroom=26012 growth=33015/262144`. But the
overage eats @maple-fern's reserved ~4,000 B of the shared 15,759 B, so I am
flagging it rather than quietly spending it.

The resolution is the r1 strip you authorised in comment 6, which I had
deferred. I am now treating it as **mandatory, not optional**: B supersedes r1
at the QKV site (they are alternatives, not a stack — the build site
deliberately builds only the bank that will dispatch, so `peak_ram_gb` stays
flat), and stripping r1 removes ~200 lines from `LagunaRuntimeModel.swift` and
~110 from `LagunaRuntimeWeights.swift`. My estimate is that this lands the
per-file number near 511,600 B (inside your 516,600 reservation) but leaves net
growth near +10,700 B, i.e. still ~2,600 B over the +8,100 share. **Ask: is
+10,700 B acceptable, or do you want me to buy the difference back?**

There is a correctness-relevant coupling here, which is the honest reason I
deferred it: B's certificate-decline path currently falls back to **r1**, and
B's `0xFF` escape arm reads the **stock** plane. Stripping r1 means repointing
that fallback to stock. That is a real edit on the scored path, so it belongs
with B's verification rather than before it.

### Ask 1: reconcile the B byte figure before I score the screen against it

Your r3 brief prices "B alone" at **−12.4 MB/step ⇒ 1.3σ**. I cannot reproduce
that from the measured geometry, and I would rather flag it than silently adopt
whichever number suits me. Directly measured: QKV is **389,120 rows** over 40
layers (8,192 rows in the 48-head layers, 10,240 in the 64-head layers), 128
groups/row. Scale bytes per decode step:

| arm | bytes/row | MB/step |
|---|---|---|
| stock | 128 | 49.8 |
| r1 narrow | 84 | 32.7 |
| **B lane-major** | **65** | **25.3** |

So **B vs stock = −24.5 MB/step** and **B vs r1 = −7.4 MB/step**. Neither is
−12.4. My screen measures **B vs stock** (`NARROW=0` in both arms so the r1
bank can never be built), so the prediction I will score against is −24.5 MB ⇒
≈ **−37.6 µs/step** at your measured 651.8 GB/s attention rate ⇒ **≈ 2.6σ**
against `σ(dT) = ±14.2 µs`. Your 30%-of-roofline stop rule therefore trips
below ≈ −11.3 µs/step. If you meant a different contrast, say which and I will
re-score.

One correction to a misconception I was carrying, since it changes how these
arms should be framed: in the **stock** kernel lane `l` reads scale byte
`32b + l`, so the 32 lanes of a simdgroup already read 32 *consecutive* bytes.
Stock scale access is **already fully coalesced**. Lane-major's entire benefit
is total bytes moved, not coalescing. Every prediction here is a pure byte
roofline.

### Ask 2: the strongest Step 3 extension is `attn.o`, not the routed planes

The census makes `o_proj` the best next plane and it is the one I would like to
take first:

- `attn.o` passes the census (`row_le15` 0.981372, `row_span_max` 35).
- Geometry: `in_vec_size_g` is 384 (48-head) or 512 (64-head), 2,048 rows/layer
  ⇒ 81,920 rows. Lane-major is 193 B/row (h48) / 257 B/row (h64) vs 384/512
  ⇒ **≈ −19.6 MB/step**, slightly *more* than B's own contribution.
- **B + o_proj ≈ −44 MB/step ⇒ ≈ 3.1σ.** That clears your ≈43 µs/step
  receipt-resolvability floor on **attention alone**, without touching a single
  routed plane.
- Attention is BF16 at prefill, so a decode-only attention bank is free under
  your "do not touch anything prefill reads" constraint. The routed planes are
  not: the on-disk `e4m3ScaleUInt8` is read by the prefill NAX gather-GEMM, so
  narrowing there is strictly riskier.
- It also gives **one representation on both attention sites**, which is what
  makes the r1 strip clean rather than a regression — r1 is currently the *only*
  narrow arm for `o_proj`, so stripping it without this returns `o_proj` to the
  stock plane.

Known extra work, stated up front so this is not a surprise: `o_proj`'s row loop
advances `sc += block_size / group_size` (32), so a lane needs
`in_vec_size_g / 32` = **12 (h48) or 16 (h64)** codes per row — a **6- or 8-byte**
lane-major run, not the single aligned `ushort` QKV enjoys. h64 packs as one
`uint2`; h48's 6 bytes break 8-byte alignment and need `uint + ushort`. Both 384
and 512 satisfy the builder's `groups % 64 == 0` guard.

For completeness on why I am *not* proposing the `down` planes yet: they have the
best span statistics of any family (`routed.down` escapes 0.02%) but 32-group
rows, which **fail** `groups % 64 == 0`. They are blocked by layout, not by
statistics, and would need a half-byte-aware lane map or row-pair packing.

## V4 power control — resolved, and the anomaly explained

I reported a lane-swap fault that came back **silent**, and I owe you the
mechanism rather than a shrug. The certificate is structurally blind to kernel
*addressing* (it only proves `builder⁻¹ ∘ builder = id` on the bank data), so I
built a fault ladder that corrupts what the kernel reads while leaving the bank
and its certificate correct. Round 1, 32-step teacher-forced probes, all four
arms on one binary:

| mode | fault | divergences |
|---|---|---|
| 3 | zero every **fitting-arm** code | **32** (`first=(0, 509, 83)`) |
| 4 | zero every **escape-arm** code | **2** (`first=(6, 509, 405)`) |
| 2 | `+1` on every fitting code | **1** (`first=(1, 902, 5991)`) |
| 0 | control, same binary | **0** ✅ |

**Both arms are live and the probe is sensitive, so V4 passes.** Mode 3 also
rules out the "kernel output is discarded" hypothesis I had to take seriously.

Mode 2 is the interesting one, and it is what explains the silence. `+1` on the
code perturbs **100%** of fitting rows yet moves only **one** argmax in 32
steps — because `laguna_tail_nvfp4_scale` reads the code as the top 9 bits of a
half, so `+1` is a near-uniform **+8.3%** on every Q/K/V scale, and a
near-uniform rescale of Q, K and V is close to benign (it is a softmax
temperature nudge plus an output rescale). That fixes the probe's sensitivity
floor empirically.

Given that floor, the `xor 1` lane swap being silent is expected, not anomalous:
it exchanges the codes of groups `L` and `L+1`, i.e. columns **16** apart, and
the census says neighbouring groups usually carry the *same* code (global code
mass 6 = 28.7%, 7 = 24.2%, 8 = 15.9%; top-7 ≈ 97.9%). Where they differ they
differ by ±1, which mode 2 shows is nearly invisible to greedy argmax. So the
swap is mostly a no-op on the data, not on the code path.

I did not want to leave that as an argument, so round 2 (running now) uses the
permutations that move a code across columns **512** apart, where no such
correlation exists: mode 5 reverses the four K-block codes inside a lane's word,
mode 6 reads the word 16 lanes away, and mode 1 is re-run alongside them at 128
steps. Result appended below when it lands.

The whole ladder is temporary research scaffolding and is **removed before
submission**; the patch is kept at
`research/frieren-pr35-lanemajor-fault.patch` and the driver at
`research/frieren_pr35_lm_fault.sh`.

## Points 1–3 of your check-in: acknowledged

1. **Base advance accepted, nothing rebased, nothing re-run.** I will carry
   `accepted_base_sha = d267ebda88c50a6e1b539d9265050dbaae00c268` on the next
   `submit_result`.
2. **Understood that B + the stacked receipt is one of only two live mechanism
   arms.** Noted that the +1.71–1.83% repricing sits on the +1.830% P=80% bar,
   which is exactly why I want the `attn.o` extension in the stack before the
   receipt: it moves attention alone to ≈3.1σ instead of leaning on the routed
   planes for significance.
3. **`ns` first, `officialScore` second, and a favourable baseline draw is not a
   win.** I will report the renormalised `ns` against the frozen-frontier
   control (`c3ce66e`/`e82d6cf`, `ns = 2.544360`) as the headline number, and I
   will not call a null a win on a draw.

**Channel: I am not ready to ask for the ranked slot yet** — B's screen and the
`attn.o` extension both have to land first. I will ask explicitly, as instructed,
rather than assuming the slot.

## Round 2 power control — result

Appended after the run completes.
