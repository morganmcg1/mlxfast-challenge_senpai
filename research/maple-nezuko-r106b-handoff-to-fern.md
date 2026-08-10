# R106-B Stage C handoff — `maple-nezuko` → `maple-fern` (#625 integration tree)

**Status: DRAFT / placeholder. Do not integrate anything from this file until the
`VERDICT` line below says `SEND`.** The paired A/B in
`research/maple-nezuko-r106b-revert-residual.md` §C is the only admissible
source for the numbers; this file exists so the handoff is reviewable in-tree.

```
VERDICT: PENDING
```

## Why this file exists rather than a comment on #625

My role has no GitHub write credential (`gh` is unauthenticated in this
workspace and no `GH_TOKEN`/PAT is provisioned), so I cannot post a comment on
#625 directly. The advisor's Stage C instruction asks for a comment id; §G of my
report records that constraint explicitly and points here instead. Everything a
comment would have carried is in this file, in the order fern's queue rule needs
it (measured % of `cs` first, reproduction command second).

## Candidate

`laguna_sliding_fused_attn_ring_packred_v1` — the sliding decode-attention
kernel with its cross-lane reductions packed into `float2`/`float4` butterflies,
cutting shuffle instructions from **229 to 109 per lane per call** with **zero**
change to grid, threadgroup size, threadgroup memory, dispatch count, or bytes
requested.

- Single file touched: `Sources/MLXFastModel/LagunaRuntimeModel.swift`.
- Selection: `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1`, default **off**.
- Scope: does not touch `residual_rms_router` or router prefetch (frieren), the
  NVFP4 qmv inner loop or weight encoding (tanjiro), decode dispatch/encode
  ordering (fern), the QKV projection kernel (edward, #629), or the routed
  K-loop (alphonse, #630). It is the sliding attention kernel only.

## To be filled from §C/§E/§F before this becomes a real handoff

| field | value |
|---|---|
| paired Δ decode (µs/step) | *pending* |
| 95 % CI | *pending* |
| % of `cs` at 0.015228 %/µs/step | *pending* |
| n pairs / dof | *pending* |
| bit-exact? | *pending* |
| sha256 + bytes of changed file | *pending* |
| reproduce with | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 ./benchmark.sh --local-submit` |

## Standing caveats fern should carry forward regardless of the number

1. **Standalone this lever cannot clear frieren's 0.4 % of `cs` bar** (≈ 26
   µs/step). The whole named residual it targets is 0.3204 %. It is only worth
   integrating *composed* with other levers, which is exactly why it is being
   handed over early rather than withheld.
2. **Rule 98.9**: no kernel-local or cache-resident number appears anywhere in
   the handoff. The Δ quoted is a whole-model paired `--local-submit` figure.
3. If the candidate is **not** bit-exact, it must not be integrated on my
   evidence alone — it needs frieren's margin certificate from #597 (zero
   argmax flips across the full golden set). I will say plainly in §F which case
   applies.
