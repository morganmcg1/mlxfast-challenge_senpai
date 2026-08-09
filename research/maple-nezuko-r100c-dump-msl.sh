#!/bin/bash
# R100-C Step 1: dump the router GEMV MSL for arms pf0 / pf1 / pf1c and prove
# that arm 0 is character-identical to the generator on BASE_SHA. If arm 0's
# text drifted, A0 is not a control and every later number is meaningless.
#
# Uses the generator verbatim from the working tree (no hand-copied duplicate),
# following the pattern in research/tanjiro-r87a-verify-msl.sh.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_SHA="${1:-2e490fa36ee58820dff636b63513d667fd019049}"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
RPG="${RPG:-8}"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
mkdir -p research/msl

# Shared dependencies of the generator, verbatim.
extract_deps() {
    awk '
        /^private let lagunaRouterPrecomputedKeysEnabled =/{f=1}
        f&&/DARKBLOOM_ROUTER_PRECOMPUTED_KEYS/{print; f=0; next}
        f{print; next}
        /^private let lagunaNormInvMeanScratch =/{print; next}
        /^private func lagunaNormReductionTail\(/{g=1}
        g{print; if ($0=="}") g=0; next}
        /^private let lagunaNormReductionTail2048 =/{h=1}
        h{print; if (/epsilon: "1.0e-6f"\)/) h=0; next}
        /^private func lagunaRouterPrefetchGroups\(/{k=1}
        k{print; if ($0=="}") k=0; next}
    ' "$1" | sed 's/^private //'
}

# The generator itself, verbatim, from `private func ...Source(` up to the
# doc comment that introduces the kernel dictionary.
extract_gen() {
    awk '/^private func lagunaResidualRMSNormRouterSource\(/{f=1}
         /^\/\/\/ One kernel per supported/{f=0}
         f' "$1" | sed 's/^private //'
}

git show "$BASE_SHA:$SRC" > "$OUT"/base.swift

build_one() {  # $1=swift-source $2=binary $3=call-expression
    {
        echo 'import Foundation'
        extract_deps "$1"
        extract_gen "$1"
        echo "let src = $3"
        echo 'try! src.write(toFile: CommandLine.arguments[1], atomically: true, encoding: .utf8)'
    } > "$OUT/main_$2.swift"
    swiftc -O -o "$OUT/$2" "$OUT/main_$2.swift" || {
        echo "FATAL: could not compile generator harness for $2" >&2
        sed -n '1,40p' "$OUT/main_$2.swift" >&2
        return 1
    }
}

build_one "$SRC" cand "lagunaResidualRMSNormRouterSource(rowsPerGroup: $RPG, prefetch: Int(CommandLine.arguments[2])!)" || exit 1
build_one "$OUT"/base.swift base "lagunaResidualRMSNormRouterSource(rowsPerGroup: $RPG)" || exit 1

"$OUT"/base "research/msl/r100c_rpg${RPG}_BASE.body.metal"
for pf in 0 1 5; do
    tag=$([ "$pf" = 5 ] && echo pf1c || echo "pf$pf")
    "$OUT"/cand "research/msl/r100c_rpg${RPG}_${tag}.body.metal" "$pf"
done

status=0
if cmp -s "research/msl/r100c_rpg${RPG}_BASE.body.metal" \
          "research/msl/r100c_rpg${RPG}_pf0.body.metal"; then
    echo "CONTROL OK: arm pf0 is character-identical to BASE_SHA's generator"
else
    echo "FATAL: arm pf0 drifted from BASE_SHA -- A0 is not a control" >&2
    diff -u "research/msl/r100c_rpg${RPG}_BASE.body.metal" \
            "research/msl/r100c_rpg${RPG}_pf0.body.metal" | head -60 >&2
    status=1
fi

for pf in pf0 pf1 pf1c; do
    f="research/msl/r100c_rpg${RPG}_${pf}.body.metal"
    printf '%-6s %6s bytes  %4s lines  barriers=%s\n' "$pf" \
        "$(wc -c < "$f" | tr -d ' ')" "$(wc -l < "$f" | tr -d ' ')" \
        "$(grep -c threadgroup_barrier "$f")"
done
exit $status
