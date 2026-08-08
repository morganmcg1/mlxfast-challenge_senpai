#!/usr/bin/env bash
# frieren_comment_strip_check.sh --- prove a comment-relocation PR is a compiler no-op.
#
# For each in-scope file this script extracts the BASE and HEAD versions, applies
# one identical normalisation to both (drop comment-only lines, drop the
# `// See notes/...` pointers this PR adds, strip trailing whitespace, collapse
# blank runs), and asserts the two residues are byte-identical. A green run means
# the only textual difference between BASE and HEAD is comment prose.
#
# VALIDITY PRECONDITION -- READ THIS.
#   The normalisation deletes every line whose first non-space characters are
#   `//`. In this codebase Metal kernel source is embedded inside Swift `"""`
#   multi-line string literals, and a `//` line inside such a literal is *Metal
#   source code*, not a Swift comment. Deleting it would silently change the
#   compiled kernel, and the residues would still compare equal, so the check
#   would report a false pass.
#
#   Therefore the equivalence proven below is only valid for files that contain
#   ZERO comment-looking lines inside `"""` regions. This script asserts that
#   precondition on BOTH the base and head version of every file and FAILS LOUDLY
#   if it ever stops holding. Do not relax that assertion; re-scope the PR instead.
#
#   This check is necessary but NOT sufficient: it cannot see a comment edit that
#   split a token. The build and upstream-equivalence gates remain mandatory.
#
#   LagunaRuntimeModel.swift is listed and CANNOT satisfy the precondition: it
#   embeds 212 """ kernel-source literals, 5 of whose lines start with `//` and are
#   Metal code, not comments. That is a property of the file, not of any candidate,
#   so this script can never validate it and reports FAIL for it unconditionally.
#   research/fern_partB_dry_run.sh phases 1-2 are the literal-aware equivalent:
#   phase 1 asserts the literal-interior comment text is byte-identical and that no
#   planned block covers it, phase 2 compares code residue with the literals held
#   out. Whether this script should distinguish "not covered" from "failed" is a
#   design question left to the advisor; suppressing the file here would overstate
#   coverage, so the loud failure stands.
#
# Usage: research/frieren_comment_strip_check.sh [BASE_SHA]

set -uo pipefail

BASE_SHA="${1:-e1d070f256a1f5cef5a62a1d001dfbfe8b81bd0c}"

FILES=(
  "Sources/MLXFastModel/LagunaRuntimeModel.swift"
  "Sources/MLXFastModel/LagunaRuntimeWeights.swift"
  "Sources/MLXFastModel/LagunaConfig.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BatchKVCache.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableRotatingKVCache.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompilableKVCache.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BaseConfiguration.swift"
)

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root" || exit 1

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail=0

# Assert: no comment-looking line sits inside a Swift `"""` multi-line literal.
# Toggles literal state on every odd count of `"""` on a line.
assert_no_comment_in_literal() {
  awk '
    {
      n = gsub(/"""/, "\"\"\"")
      if (inlit) {
        line = $0
        sub(/^[ \t]+/, "", line)
        if (line ~ /^\/\//) { bad++; badbytes += length($0) + 1 }
      }
      if (n % 2 == 1) { inlit = !inlit; delims += n } else { delims += n }
    }
    END { printf "%d %d %d\n", delims, bad, badbytes }
  ' "$1"
}

normalise() {
  # 1. drop the pointer lines this PR adds
  # 2. drop comment-only lines
  # 3. strip trailing whitespace
  # 4. collapse runs of blank lines to one
  sed -e 's/[[:space:]]*$//' "$1" \
    | grep -v -e '^[[:space:]]*//[[:space:]]*See notes/' \
    | grep -v -e '^[[:space:]]*//' \
    | cat -s
}

printf '=== frieren_comment_strip_check.sh ===\n'
printf 'BASE_SHA = %s\n' "$BASE_SHA"
printf 'HEAD     = %s\n' "$(git rev-parse HEAD)"
printf '\n--- precondition: zero comment bytes inside """ regions ---\n'

for f in "${FILES[@]}"; do
  tag="$(printf '%s' "$f" | tr '/' '_')"
  base="$work/base.$tag"
  head="$work/head.$tag"
  if ! git show "$BASE_SHA:$f" >"$base" 2>/dev/null; then
    printf 'FAIL  %s: cannot read base version at %s\n' "$f" "$BASE_SHA"
    fail=1
    continue
  fi
  cp "$f" "$head" || { fail=1; continue; }

  for v in base head; do
    src="$work/$v.$tag"
    read -r delims bad badbytes <<<"$(assert_no_comment_in_literal "$src")"
    if [ "$bad" -ne 0 ]; then
      printf 'FAIL  %-58s %-4s tripleQuotes=%s comment_lines_inside_literal=%s bytes=%s\n' \
        "$f" "$v" "$delims" "$bad" "$badbytes"
      printf '      PRECONDITION VIOLATED: this file embeds commented kernel source.\n'
      printf '      The strip-equivalence result below is NOT VALID for this file.\n'
      fail=1
    else
      printf 'ok    %-58s %-4s tripleQuotes=%-4s comment_lines_inside_literal=0\n' \
        "$f" "$v" "$delims"
    fi
  done
done

printf '\n--- code residue equality (base vs head, comments normalised away) ---\n'

tot_base=0
tot_head=0
for f in "${FILES[@]}"; do
  tag="$(printf '%s' "$f" | tr '/' '_')"
  base="$work/base.$tag"
  head="$work/head.$tag"
  [ -f "$base" ] && [ -f "$head" ] || continue

  normalise "$base" >"$work/nb.$tag"
  normalise "$head" >"$work/nh.$tag"

  bb=$(wc -c <"$base" | tr -d ' ')
  hb=$(wc -c <"$head" | tr -d ' ')
  rb=$(wc -c <"$work/nb.$tag" | tr -d ' ')
  tot_base=$((tot_base + bb))
  tot_head=$((tot_head + hb))

  if cmp -s "$work/nb.$tag" "$work/nh.$tag"; then
    printf 'ok    %-58s base=%-7s head=%-7s saved=%-7s residue=%s IDENTICAL\n' \
      "$f" "$bb" "$hb" "$((bb - hb))" "$rb"
  else
    printf 'FAIL  %-58s residues differ\n' "$f"
    diff -u "$work/nb.$tag" "$work/nh.$tag" | head -60
    fail=1
  fi
done

printf '\n--- totals ---\n'
printf 'base bytes = %s\nhead bytes = %s\nrecovered  = %s\n' \
  "$tot_base" "$tot_head" "$((tot_base - tot_head))"

if [ "$fail" -ne 0 ]; then
  printf '\nRESULT: FAIL\n'
  exit 1
fi
printf '\nRESULT: PASS (comment-only change on all %s files)\n' "${#FILES[@]}"
