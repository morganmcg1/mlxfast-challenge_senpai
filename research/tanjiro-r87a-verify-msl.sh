#!/bin/bash
# R87-A: prove the refactored routed gate/up R1 source generator emits, at
# DARKBLOOM_ROUTED_GATEUP_INPUT_PF=0 with both probes off, MSL that is
# byte-identical to the inline string literal on BASE_SHA. Rule 33 keys the
# pipeline cache on the kernel name, and mode 0 keeps the stock name, so mode 0
# must also keep the stock source or A0 is not a control.
#
# Also dumps the MSL for every variant to research/msl/ for inspection.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_SHA="${1:-3217f111142346e004f41fae611a8bede172a659}"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
mkdir -p research/msl

# The generator, verbatim from the working tree (no hand-copied duplicate).
awk '/^let lagunaRoutedGateUpInputPF = min/{f=1}
     /^private let lagunaRoutedSwiGLUQMVPackedTop8R1Kernel/{f=0}
     f' "$SRC" | sed 's/^private //' > "$OUT"/gen.swift

# The router prelude, verbatim.
awk '/^private let lagunaRouterTop8PrecomputedPrelude = """/{f=1}
     f{print}
     f&&/^"""$/&&!/= """/{exit}' "$SRC" | sed 's/^private //' > "$OUT"/prelude.swift

# The stock literal body, verbatim from BASE_SHA.
git show "$BASE_SHA:$SRC" | awk '
    /name: "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"/{k=1}
    k&&/^    source: """$/{f=1; next}
    f&&/^""",$/{exit}
    f' > "$OUT"/stock.msl

{
  echo 'import Foundation'
  echo 'let lagunaScalePatchHeaderBytes = 128'
  echo 'let lagunaNvfp4RowScaleSuffix = " * 4194304.0f"'
  cat "$OUT"/prelude.swift
  cat "$OUT"/gen.swift
  # Embedded as a real Swift literal so its \(...) interpolations resolve the
  # same way the base binary resolves them.
  echo 'let stock = """'
  cat "$OUT"/stock.msl
  echo '"""'
  echo 'let gen = lagunaRoutedGateUpR1Source()'
  echo 'try! gen.write(toFile: CommandLine.arguments[1], atomically: true, encoding: .utf8)'
  echo 'print(lagunaRoutedGateUpR1KernelName)'
  echo 'print(gen == stock ? "MATCH" : "DIFF")'
} > "$OUT"/main.swift

swiftc -O -o "$OUT"/verify "$OUT"/main.swift || exit 1

status=0
for spec in "0 0 " "1 0 " "2 0 " "3 0 " "0 2 " "0 4 " "0 0 1"; do
    read -r pf b e0 <<<"$spec"
    tag="pf${pf}_b${b}_e${e0:-0}"
    res=$(DARKBLOOM_ROUTED_GATEUP_INPUT_PF="$pf" \
          DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS="$b" \
          DARKBLOOM_PROBE_ROUTED_EXPERT0_PF="${e0:-0}" \
          "$OUT"/verify "research/msl/$tag.metal")
    name=$(echo "$res" | head -1)
    verdict=$(echo "$res" | tail -1)
    printf '%-12s %-70s %s\n' "$tag" "$name" "$verdict"
    if [ "$tag" = "pf0_b0_e0" ] && [ "$verdict" != "MATCH" ]; then
        echo "FATAL: mode 0 is not byte-identical to the stock literal" >&2
        diff -u <(sed -e "s/\\\\(lagunaNvfp4RowScaleSuffix)/ * 4194304.0f/g" "$OUT"/stock.msl) research/msl/pf0_b0_e0.metal | head -60 >&2
        status=1
    fi
done
exit $status
