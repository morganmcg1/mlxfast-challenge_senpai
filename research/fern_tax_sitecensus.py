#!/usr/bin/env python3
"""Barrier-site census for one default decode step.

Consumes the sitemap.tsv produced by research/fern_tax_sitetrace.py and emits
the per-site / per-layer barrier tables used by
research/maple-fern-decode-barrier-site-census.md.

    python3 research/fern_tax_sitecensus.py research/artifacts/fern_sites.sitemap.tsv
"""
import argparse
import collections
import sys

BAR_US = 1.3003
DISP_US = 0.1231
PCT_PER_US = 0.015280

ROLE = [
    ("decode_embedding_rope_atlas", "embed+rope"),
    ("rmsbfloat16", "inputNorm"),
    ("decode_nvfp4_qkv_h64", "qkv(h64)"),
    ("decode_nvfp4_qkv_h48", "qkv(h48)"),
    ("gate_sp_h64", "gate_softplus"),
    ("gate_sp_h48", "gate_softplus"),
    ("sliding_fused_attn", "attn(sliding)"),
    ("full_fused_attn", "attn(full)"),
    ("oproj_act_h64", "o_proj"),
    ("oproj_act_h48", "o_proj"),
    ("residual_rms_router", "postNorm+router"),
    ("residual_rms_bf16", "postNorm"),
    ("shared_nvfp4_swiglu_qmv", "shared_swiglu"),
    ("decode_router_top8", "router_top8"),
    ("routed_nvfp4_swiglu_qmv", "routed_swiglu"),
    ("routed_shared_nvfp4_down_residual", "down+residual"),
    ("dense_gate_up_swiglu", "dense_gate_up"),
    ("dense_down_residual", "dense_down"),
    ("lmhead_int5_base_coarse_delta", "lm:5a coarse"),
    ("lmhead_coarse_argmax_stage1", "lm:5b argmax1"),
    ("lmhead_exact_winner", "lm:5c winner"),
    ("lmhead_exact_fused_int5_sparse_refine", "lm:5d refine"),
    ("gather_front", "lm:gather"),
    ("argmax_", "lm:argmax"),
]


def role(kernel):
    for pat, name in ROLE:
        if pat in kernel:
            return name
    return kernel[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitemap")
    ap.add_argument("--step-len", type=int, default=406)
    args = ap.parse_args()

    rows = []
    with open(args.sitemap) as fh:
        header = fh.readline()
        for line in fh:
            f = line.rstrip("\n").split("\t")
            rows.append(
                dict(
                    idx=int(f[0]),
                    cb=int(f[1]),
                    ordn=int(f[2]),
                    bar=int(f[3]),
                    gap=int(f[4]),
                    kernel=f[5],
                    grid=f[6],
                    raw=[] if f[7] == "-" else f[7].split("|"),
                    war=[] if f[8] == "-" else f[8].split("|"),
                )
            )

    bounds = [r["idx"] for r in rows if "decode_embedding_rope_atlas" in r["kernel"]]
    steps = []
    for b in bounds:
        seg = [r for r in rows if b <= r["idx"] < b + args.step_len]
        if len(seg) == args.step_len and seg[-1]["idx"] == b + args.step_len - 1:
            nxt = [x for x in bounds if x == b + args.step_len]
            if nxt or b == bounds[-1]:
                steps.append(seg)
    if not steps:
        sys.exit("no full %d-dispatch step found" % args.step_len)
    step = steps[-1]
    print("## step windows found: %s (using idx %d)" % ([s[0]["idx"] for s in steps], step[0]["idx"]))
    nb = sum(r["bar"] for r in step)
    ncb = len({r["cb"] for r in step})
    print("## dispatches=%d barriers=%d command_buffers=%d" % (len(step), nb, ncb))
    print()

    # ---- layer segmentation: a layer starts at its inputNorm (rmsbfloat16) ----
    starts = [i for i, r in enumerate(step) if r["kernel"] == "rmsbfloat16"]
    layers = []
    for j, s in enumerate(starts):
        e = starts[j + 1] if j + 1 < len(starts) else len(step)
        layers.append(step[s:e])
    # last rmsbfloat16 begins the lm-head tail, not a transformer layer
    tail = layers.pop()
    print("## transformer layers detected: %d ; tail dispatches=%d" % (len(layers), len(tail)))
    print()

    # ---- 2.1 barrier site map ----
    print("### 2.1 barrier sites (one default decode step)")
    print()
    print("| # | cb | ord | consumer | RAW producers | WAR producers | gap |")
    print("|---|----|-----|----------|---------------|---------------|-----|")
    n = 0
    for r in step:
        if not r["bar"]:
            continue
        n += 1
        if n > 40:
            continue
        print(
            "| %d | %d | %d | %s | %s | %s | %d |"
            % (
                n,
                r["cb"],
                r["ordn"],
                role(r["kernel"]),
                ", ".join(role(p) for p in r["raw"]) or "-",
                ", ".join(role(p) for p in r["war"]) or "-",
                r["gap"],
            )
        )
    print()
    print("(first 40 of %d shown; full list in the tsv)" % n)
    print()

    # ---- per-layer templates ----
    sig = collections.Counter()
    for L in layers:
        s = tuple((role(r["kernel"]), r["bar"]) for r in L)
        sig[s] += 1
    print("### 2.2 per-layer barrier templates")
    print()
    for s, c in sig.most_common():
        print("**template x%d** (%d dispatches, %d barriers)" % (c, len(s), sum(b for _, b in s)))
        print()
        print("| ord | kernel | barrier? |")
        print("|-----|--------|----------|")
        for k, b in s:
            print("| | %s | %s |" % (k, "BAR" if b else "." ))
        print()
    print("**tail** (%d dispatches, %d barriers)" % (len(tail), sum(r["bar"] for r in tail)))
    print()
    print("| cb | kernel | barrier? | RAW |")
    print("|----|--------|----------|-----|")
    for r in tail:
        print("| %d | %s | %s | %s |" % (r["cb"], role(r["kernel"]), "BAR" if r["bar"] else ".", ", ".join(role(p) for p in r["raw"]) or "-"))
    print()
    lay_b = sum(sum(r["bar"] for r in L) for L in layers)
    print("layer barriers=%d tail barriers=%d pre-layer=%d total=%d"
          % (lay_b, sum(r["bar"] for r in tail),
             sum(r["bar"] for r in step[: starts[0]]), nb))
    print()

    # ---- barrier-charged edge census by (producer-role -> consumer-role) ----
    print("### barrier-charged edges, aggregated over the step")
    print()
    print("| producer role(s) | consumer role | count |")
    print("|------------------|---------------|-------|")
    edges = collections.Counter()
    for r in step:
        if not r["bar"]:
            continue
        key = ("+".join(sorted(role(p) for p in r["raw"])) or "(WAR/none)", role(r["kernel"]))
        edges[key] += 1
    for (p, c), n2 in edges.most_common():
        print("| %s | %s | %d |" % (p, c, n2))
    print()

    # ---- how often each *candidate* edge is actually charged ----
    print("### candidate-edge charge rate (per step)")
    print()
    cands = {
        "C1 inputNorm->qkv": ("inputNorm", ("qkv(h64)", "qkv(h48)")),
        "C2 attn->o_proj": (("attn(sliding)", "attn(full)"), ("o_proj",)),
        "C3 postNorm+router->top8": ("postNorm+router", ("router_top8",)),
        "C4 shared->down / routed->down": (("shared_swiglu", "routed_swiglu"), ("down+residual",)),
        "C5 postNorm+router first consumer": ("postNorm+router", ("shared_swiglu", "routed_swiglu", "router_top8")),
        "layer boundary down->inputNorm": ("down+residual", ("inputNorm",)),
    }
    print("| candidate edge | edge present | barrier charged | free (cb split / collapsed) |")
    print("|----------------|--------------|-----------------|------------------------------|")
    for name, (prod, cons) in cands.items():
        prods = (prod,) if isinstance(prod, str) else prod
        present = charged = 0
        for i, r in enumerate(step):
            if role(r["kernel"]) not in cons:
                continue
            has = any(role(p) in prods for p in r["raw"])
            # edge exists structurally if an earlier dispatch in the same layer had that role
            if has:
                present += 1
                if r["bar"]:
                    charged += 1
        print("| %s | %d | %d | %d |" % (name, present, charged, present - charged))
    print()

    # ---- refund pricing helper ----
    print("### refund pricing (M4-measured coefficients)")
    print()
    print("barrier = %.4f us, dispatch = %.4f us, score = %.6f %%/us" % (BAR_US, DISP_US, PCT_PER_US))


if __name__ == "__main__":
    main()
