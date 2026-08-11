#!/usr/bin/env python3
"""R114-E Stage 3.5: busy-vs-gap attribution for the gate_sp/QKV fusion.

Inputs are the per-step figures printed by decode_probe under the PR-91 GPUPROF
hook (MLXFAST_GPUPROF_SPLIT=1) for the three captures C1, F1, C2 taken from one
instrumented build.  Numbers are us/step unless stated otherwise.

The control is captured twice, before and after the fused arm, so that the
control repeat price bounds drift for every quantity we difference.
"""

# Per-dispatch instrumentation overhead charged by MLXFAST_GPUPROF_SPLIT=1.
# Same constant the R109-E bandwidth atlas uses (research/maple-alphonse-r109e-bwatlas.py:34).
SPLIT1_INFLATION_US = 1.554

C1 = dict(wall=9775, busy=8554, gap=1222, disp=406,
          g64=237.5, g48=80.1, q64=1343.0, q48=363.1, ring=648.0)
C2 = dict(wall=9772, busy=8558, gap=1215, disp=406,
          g64=236.7, g48=80.3, q64=1343.2, q48=363.1, ring=647.2)
F1 = dict(wall=9232, busy=8242, gap=990, disp=366,
          f64=1357.3, f48=368.5, ring=634.3)

SPLIT0_SCORED_DELTA_US = -76.8   # 36-run ABBA on ./benchmark.sh --local-iterate
ATLAS_GATE_SP_US = 261.6         # R109-E atlas entry, already SPLIT-corrected


def main() -> None:
    C = {k: (C1[k] + C2[k]) / 2 for k in C1}

    print("== control repeat price (C2 - C1) ==")
    for k in ("wall", "busy", "gap", "ring"):
        print("  %-5s %+6.1f" % (k, C2[k] - C1[k]))
    print("  gate  %+6.1f" % ((C2["g64"] + C2["g48"]) - (C1["g64"] + C1["g48"])))
    print("  qkv   %+6.1f" % ((C2["q64"] + C2["q48"]) - (C1["q64"] + C1["q48"])))

    gate = C["g64"] + C["g48"]
    qkv = C["q64"] + C["q48"]
    fused = F1["f64"] + F1["f48"]

    print("\n== targeted busy ==")
    print("  control gate_sp        %8.1f" % gate)
    print("  control qkv            %8.1f" % qkv)
    print("  control targeted total %8.1f" % (gate + qkv))
    print("  fused qkv_gate         %8.1f" % fused)
    print("  delta targeted busy    %+8.1f" % (fused - (gate + qkv)))
    added = fused - qkv
    print("  busy added by gate tiles inside fused kernel %+.1f" % added)
    print("  absorbed fraction of gate busy               %.1f%%"
          % (100 * (1 - added / gate)))

    print("\n== per-call (us) ==")
    for tag, n, g, q, f in (("h64", 30, C["g64"], C["q64"], F1["f64"]),
                            ("h48", 10, C["g48"], C["q48"], F1["f48"])):
        print("  %s  gate %.2f + qkv %.2f = %.2f  ->  fused %.2f  (qkv grew %+.2f)"
              % (tag, g / n, q / n, (g + q) / n, f / n, (f - q) / n))

    dw = F1["wall"] - C["wall"]
    db = F1["busy"] - C["busy"]
    dg = F1["gap"] - C["gap"]
    print("\n== SPLIT=1 wall decomposition ==")
    print("  d_wall %+.1f = d_busy %+.1f + d_gap %+.1f   (residual %+.1f)"
          % (dw, db, dg, dw - db - dg))
    print("  non-targeted busy delta %+.1f  (of which ring %+.1f, ring drift %+.1f)"
          % (db - (fused - (gate + qkv)), F1["ring"] - C["ring"], C2["ring"] - C1["ring"]))
    print("  dispatches %d -> %d (%+d)" % (C["disp"], F1["disp"], F1["disp"] - C["disp"]))
    print("  gap per dispatch  C %.2f   F %.2f" % (C["gap"] / C["disp"], F1["gap"] / F1["disp"]))

    inflation = 40 * SPLIT1_INFLATION_US
    serialized = dw + inflation
    print("\n== transfer to the scored SPLIT=0 world ==")
    print("  instrumentation on the 40 removed dispatches   %+.1f" % -inflation)
    print("  serialized-world saving (SPLIT=1, deflated)    %+.1f" % serialized)
    print("  measured scored saving (SPLIT=0 ABBA)          %+.1f" % SPLIT0_SCORED_DELTA_US)
    print("  realized fraction of the serialized saving     %.1f%%"
          % (100 * SPLIT0_SCORED_DELTA_US / serialized))
    print("  realized fraction of the R109-E atlas entry    %.1f%%"
          % (100 * -SPLIT0_SCORED_DELTA_US / ATLAS_GATE_SP_US))


if __name__ == "__main__":
    main()
