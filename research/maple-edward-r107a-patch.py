#!/usr/bin/env python3
"""Research-only (PR #629, R107-A) stage-0 source instrumentation.

`geom`  adds a one-shot stderr receipt of the reached dispatch geometry and a
        dump of the exact Metal source handed to the selected pipeline.
`fault` is the store-row negative control: the `_sgN` pipeline is compiled from
        the 2-simdgroup source while still dispatched at 32*S threads, which is
        precisely the cache-poisoning failure mode the distinct names exist to
        prevent. Rows S..511 are then never written and the golden must fail.

Both are applied, built, and reverted by research/maple-edward-r107a-stage0.sh;
neither ships.
"""
import sys

SRC = "Sources/MLXFastModel/LagunaRuntimeModel.swift"

RECEIPT = '''
private let lagunaR107GeometryReceipt: Bool = {
    let selector = lagunaRoutedGateUpPackingSimdgroups
    let sg = selector > 0 ? selector : 2
    let gridThreads = LagunaConstants.numExpertsPerTok * 256 * 64
    let threadsPerGroup = 32 * sg
    let name = selector > 0
        ? "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2_sg\\(sg)"
        : "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"
    var out = "R107GEOM selector=\\(selector) simdgroups_per_tg=\\(sg)"
    out += " grid_threads=\\(gridThreads) threads_per_tg=\\(threadsPerGroup)"
    out += " threadgroups=\\(gridThreads / threadsPerGroup)"
    out += " total_simdgroups=\\(gridThreads / 32)"
    out += " rows_per_simdgroup=1"
    out += " logical_rows=\\(gridThreads / 32 / LagunaConstants.numExpertsPerTok)"
    out += " pipeline=\\(name)\\n"
    out += "R107SRC_BEGIN\\n"
    out += lagunaRoutedSwiGLUQMVPackedTop8R1Source(sg)
    out += "\\nR107SRC_END\\n"
    FileHandle.standardError.write(out.data(using: .utf8)!)
    return true
}()

'''

ANCHOR_FUNC = "func lagunaRoutedSwiGLUQMVPackedTop8(\n"
ANCHOR_BODY = (
    "    precondition(routerKeys.size == LagunaConstants.numExperts)\n")
FAULT_FROM = "        source: lagunaRoutedSwiGLUQMVPackedTop8R1Source(sg),\n"
FAULT_TO = "        source: lagunaRoutedSwiGLUQMVPackedTop8R1Source(2),\n"


def main() -> int:
    mode = sys.argv[1]
    text = open(SRC).read()
    if mode == "geom":
        assert text.count(ANCHOR_FUNC) == 1 and text.count(ANCHOR_BODY) == 1
        text = text.replace(ANCHOR_FUNC, RECEIPT.lstrip("\n") + ANCHOR_FUNC)
        text = text.replace(
            ANCHOR_BODY, ANCHOR_BODY + "    _ = lagunaR107GeometryReceipt\n")
    elif mode == "fault":
        assert text.count(FAULT_FROM) == 1
        text = text.replace(FAULT_FROM, FAULT_TO)
    else:
        raise SystemExit("mode must be geom|fault")
    open(SRC, "w").write(text)
    print(f"applied {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
