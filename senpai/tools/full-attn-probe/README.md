# Full (growing-KV) fused decode attention probe

A standalone Metal harness for the `full_fused_attn_grow_v1` family, adapted
from `senpai/tools/sliding-attn-probe`. It times and bit-diffs kernel variants
in about one second instead of the eight minutes a matched
`--local-iterate` pair costs.

It is not part of the submitted surface. Nothing here runs on the scored path.

## Geometry

Laguna's full-attention decode shape: 48 query heads, 8 KV heads, `head_dim`
128, GQA group 6, 10 full-attention layers per decode step, 1024-thread
threadgroups, contiguous bf16 cache of `capacity` 640 slots with live prefix
`N = 576` (the midpoint of the scored window's 513..640). `params` is
`[writeIdx, N, capacity]`, matching `lagunaFullFusedAttention`.

Unlike the sliding kernel this family is partial-rotary: `rotary_pairs = 32`,
so `angles` holds cos at `[0..31]` and sin at `[32..63]`.

## Two modes

### Variant mode

```bash
python3 render.py HEAD lagunaFullFusedAttentionKernel probe_w2.metal
xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation
./probe w2:probe_w2.metal:2
```

`render.py` takes any git ref, so a variant that is not on the scored path can
still be rendered from the commit that introduced it. The width-1 kernel this
harness was built to test lives in commit `9f88d94` and was deliberately not
kept in the runtime (it costs 15,021 bytes of a 345-byte budget and is predicted
to regress on the 40-core ranking host):

```bash
python3 render.py 9f88d94 lagunaFullFusedAttentionKernelW1 probe_w1.metal
./probe w2:probe_w2.metal:2 w1:probe_w1.metal:1
```

Each argument is `label:file.metal:headsPerThreadgroup`; the dispatched
threadgroup count is `48 / headsPerThreadgroup`. The first variant is the
reference for the bytewise output diff, so pass the shipped kernel first.

Trust `min`, not `median`: the median column is polluted by first-block effects.
Only within-process ordering is comparable, so repeat the whole process to get
independent orderings rather than trusting one run.

### Occupancy mode

```bash
./probe --occupancy w1:probe_w1.metal:1
```

Times one fixed kernel at `g = 1..48` dispatched threadgroups, scanning
alternate directions per round so monotone host drift cannot fake a step.
Outputs are meaningless for `g < 48`; the deliverable is the *shape* of time
versus `g`.

This is the measurement that pins concurrent occupancy. On this M4 Pro both
the shipped width-2 kernel and the width-1 kernel are flat from `g = 1` to
`g = 20`, jump sharply at `g = 21`, stay flat to `g = 40`, and jump again at
`g = 41`. Twenty concurrent 1024-thread threadgroups on a 20-core GPU is
**one threadgroup per core**, and it is identical for 9216 B and 17920 B of
threadgroup memory, so threadgroup memory is not the occupancy limiter in this
family — the 1024-thread threadgroup size is.

That staircase is why heads-per-threadgroup is not a free tuning knob: it moves
the dispatched threadgroup count across wave boundaries whose positions depend
on the host's core count, so an argmax measured on one Apple Silicon generation
does not transfer to another.
