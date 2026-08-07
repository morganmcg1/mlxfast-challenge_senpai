# Relocated commentary — `LagunaConfig.swift`

Measurement narrative and design history moved verbatim out of `Sources/MLXFastModel/LagunaConfig.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `e1d070f2`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `Laguna architecture summary`

_relocated from lines 8-13 at base e1d070f2_


Laguna is a 256-expert MoE decoder: 40 layers, hidden 2048, GQA with 8 KV
heads and head dim 128, mixed full-attention (48 query heads, YaRN partial
RoPE) and sliding-window layers (64 query heads, plain RoPE, window 512),
a dense MLP only at layer 0, and sigmoid top-8 routing with a shared
expert on layers 1-39. The vocabulary head is untied.
