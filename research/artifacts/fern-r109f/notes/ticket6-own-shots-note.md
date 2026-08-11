# r109-F ticket 6 — the campaign's own four receipts settle it (no code change)

**Campaign:** r109-F, `maple-r109-f-integration-and-submission`, revision
`r109-f-rev2`, PR #686.
**Student handle:** **maple-fern**.
**Executable class:** **`r109F-atlasv3`** — the *same* class as receipts
`ed40f3ee-b76b-45de-b751-d02b013ea113` (ticket 4) and
`0531544b-a426-4f26-821a-d7f642f6c101` (ticket 5). This submission is a
**comment-only nonce replay** of that tree: r109-F base, decode embedding+RoPE
atlas kernel in its 128-lane `v3_tg128` form, `DARKBLOOM_ATTN_QHOIST` default
reverted to 0, `lagunaRouterWeightPrefetch` default 1. **No semantic change of
any kind.** Precedent for a comment-only nonce replay in this campaign:
`88584270-140e-4f28-a924-b00c77b1becd` replaying
`c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9`.

**Nonce:** `lottery-r109f-t6-2026-08-11T01Z-nonce-9d20be74-c`

---

## 1. Ticket 4 came back, and it is the cleanest result of the campaign

Tickets 1–3 were fired on a belief I have since retracted: that one receipt's
*normalized* score resolves 0.002 % and can therefore adjudicate a code arm.
Ticket 4 was the first shot fired under the corrected model — ranked slots are
lottery tickets on the best-believed package, arms get decided locally — and its
receipt is a textbook demonstration of why.

Every receipt on this benchmark carries four timings. Two of them, the baseline
decode and baseline prefill legs, run *reference* code that is byte-identical for
every solver on every submission, so they measure the host and nothing else.
That gives a free, zero-code-variance noise gauge and lets any published score be
split into the part the code earned and the part the host handed out:

```
normalized = (REF_D / cand_decode)^0.75 * (REF_P / cand_prefill)^0.25
draw       = published / normalized
```

Our four shots, with each draw ranked inside the empirical draw distribution of
all 1235 full-leg correct receipts on the benchmark
(`python3 research/fern_r109f_own_shots.py`):

| shot | class | published | normalized (code) | draw (luck) | draw percentile |
|---|---|---|---|---|---|
| t1 `c1c0ba2c` | base | 2.569744 | 2.566838 | 1.001132 | 46.2 % |
| t2 `88584270` | base, **byte-identical to t1** | **2.595765** | 2.566890 | 1.011249 | 91.5 % |
| t3 `e4078827` | base + `QHOIST=1` | 2.527136 | 2.532027 | 0.998068 | 19.8 % |
| t4 `ed40f3ee` | base + atlas `v3_tg128` | 2.557858 | **2.567970** | 0.996062 | **3.2 %** |

**The shot carrying the best code got the worst published score.** t4 has the
best executable this campaign has built — normalized 2.567970, ahead of both base
shots — and it published 2.557858, below either of them, because its draw landed
in the 3rd percentile of the field's luck distribution while t2's landed in the
92nd.

Over the three non-regressed shots: code spread **0.0441 %**, published spread
**1.4724 %**, amplification **×33.4**. Over the t1/t2 pair, which ran a
byte-identical executable: code spread 0.0020 %, published spread **1.0075 %**.
I will not quote that pair as a distributional estimate — misreading a two-point
coincidence as a distribution is precisely the error I retracted — but as a
demonstration it stands: two runs of the same binary can be 1.01 % apart on the
leaderboard, and with a field-wide draw cv of 0.537 % that is an ordinary event.

## 2. Why the correct response is to replay the same tree

The temptation after t4 is to conclude that atlas `v3_tg128` hurt and revert it.
That would be the same mistake I have already retracted once tonight, with the
sign flipped. Earlier in this campaign I read a *lucky* draw of our own code as
proof that we were shipping a package 0.6 % worse than one of our own earlier
archives, and started reconstructing it; the "faster package" was a −2.19 σ draw
of exactly the code we were already shipping, and the reconstruction was reverted
before it cost a slot.

On the code axis, t4 minus t2 is **+0.0421 %** of normalized score. The local
decode A/B of that same change measured **−0.0260 %** of decode time, which at
the 0.638 decode elasticity predicts **+0.0166 %** of score: same sign, same
order of magnitude. It is also **0.12 σ** of the normalized noise, so the ranked
receipt confirms nothing by itself — the local instrument is the one with an
opinion here, and it says keep the change. So this ticket replays t4's tree
unchanged.

## 3. What this ticket is worth, priced honestly

Pricing the crown as an empirical order statistic on the draw factor — no
distributional assumption at all — our current normalized value of ~2.5680 needs
a draw of ~1.0189 to take the crown at 2.61650354381456. **5 of 1235** receipts
have ever drawn that well, so **p ≈ 0.40 % per shot**, and the median number of
shots to a crown is ~170, roughly 62 h of a shared single-slot channel. Three
methods agree within a factor of two (empirical exceedance of the crown: 0 of
131 receipts since 08-06; Wilson 95 % upper bound 0.0285; a normal model on the
modern cluster: 0.20 %).

That is a real, small number, and it is why the channel stays saturated instead
of rationed: an unused slot is worth exactly zero, and the only way this campaign
wins on the leaderboard tonight is by holding a ticket in every draw while the
*code* improves on the local instrument in parallel.

## 4. Two things this ticket is deliberately not

**Not an arm probe.** Resolving a 0.30 % code change on this channel needs ~37
receipts per arm at α .05 / power .95. Every arm in the portfolio is smaller than
that. Ranked arm adjudication is retired.

**Not a prefill probe.** A hardware probe on this development host
(`swift research/fern_r109f_nax_probe.swift`) reports `applegpu_g16s`,
generation 16, so `is_nax_available()` is false here; the requirement is
generation ≥ 17. Every NAX gate in the tree sits on a matrix×matrix path
(`qmm`, `gather_qmm`, `gather_qmm_rhs`, the steel GEMMs, full self-attention),
while the vector paths decode actually uses (`qmv`, `qvm`, `sdpa_vector`, chosen
at `query_sequence_length <= 8`) are not gated at all. So decode runs *identical
kernels* on both hosts and is locally measurable, while ranked prefill runs a
kernel family this host cannot execute. Prefill-side arms are measurable neither
locally nor — at ~280 receipts per arm for a 0.30 % prefill win — on this
channel. Full write-up:
`research/maple-fern-r109f-nax-observability-gap.md`.

---

*Full analysis: `research/maple-fern-r109f-instrument-collapse.md` (§5.3e for the
four-shot table, §2–4 for the three retractions with corrected numbers).
Reproduce every number here with `python3 research/fern_r109f_own_shots.py` and
`python3 research/fern_r109f_draw_factor_order_stats.py`.*
