#!/usr/bin/env bash
# Dry-run the Part B manifest for Sources/MLXFastModel/LagunaRuntimeModel.swift.
#
# The scored file must stay byte-identical in this checkout, so the applier runs
# against a scratch tree under $TMPDIR and the repository copy is only ever read.
# The scratch tree's own SHA-256 is printed before and after to prove that.
#
# Two proofs, matching research/frieren_comment_strip_check.sh:
#   phase 1  every comment-looking line inside a `"""` literal is enumerated and
#            shown byte-identical between the pristine and relocated copies. The
#            scored file has 5 such lines (embedded Metal kernel source), so the
#            file-wide `comment_lines_inside_literal=0` assertion the checker
#            applies to the vendor files cannot hold here; this is the stronger
#            replacement, not a relaxation.
#   phase 2  code residue equality with comments normalised away, computed with a
#            literal-aware normaliser so kernel source is compared, not stripped.
#   phase 3  rule-29 containment and arithmetic agreement: every relocated line is
#            extracted; a line carrying a bit-exactness idiom is a hard failure
#            unless its block emits a pointer; moved bytes must equal the note's
#            relocated-line bytes; and the planner's projected final size must equal
#            the applier's actual final size to the byte.
#   phase 4  DocC abstract detachment, run on the relocated scratch copy.
#
# Usage: research/fern_partB_dry_run.sh [SPEC_JSON]
#        MLXFAST_DRY_RUN_INJECT=rule|bytes|size  inject one fault to prove phase 3
#        actually fails. Any injected run that reports PASS is itself a failure.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root" || exit 1

SPEC="${1:-research/fern_partB_lagunaruntimemodel_spec.json}"
REL="Sources/MLXFastModel/LagunaRuntimeModel.swift"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

printf '=== fern_partB_dry_run.sh ===\n'
printf 'spec      = %s\n' "$SPEC"
printf 'scratch   = %s\n' "$work"

before_sha="$(shasum -a 256 "$REL" | awk '{print $1}')"
before_len="$(wc -c <"$REL" | tr -d ' ')"
printf 'repo copy  before  %s  %s B\n' "$before_sha" "$before_len"

mkdir -p "$work/Sources/MLXFastModel" "$work/notes"
cp "$REL" "$work/$REL"
cp "$SPEC" "$work/spec.json"

pristine="$work/pristine.swift"
cp "$REL" "$pristine"

( cd "$work" && python3 "$repo_root/research/frieren_relocate_comments.py" spec.json )
apply_rc=$?
if [ "$apply_rc" -ne 0 ]; then
  printf 'FAIL applier exited %d\n' "$apply_rc"
  exit 1
fi

after_sha="$(shasum -a 256 "$REL" | awk '{print $1}')"
printf 'repo copy  after   %s\n' "$after_sha"
if [ "$before_sha" != "$after_sha" ]; then
  printf 'FAIL the dry run modified the repository copy of %s\n' "$REL"
  exit 1
fi
printf 'ok    repository copy of %s is byte-identical\n\n' "$REL"

relocated="$work/$REL"

# ---- phase 1: literal-interior comment lines are enumerated and untouched ----
printf -- '--- phase 1: comment-looking lines inside """ literals ---\n'
lit_lines() {
  awk '
    {
      n = gsub(/"""/, "\"\"\"")
      if (inlit) {
        line = $0; sub(/^[ \t]+/, "", line)
        if (line ~ /^\/\//) { printf "%d\t%s\n", NR, $0 }
      }
      if (n % 2 == 1) inlit = !inlit
    }' "$1"
}
lit_lines "$pristine"  >"$work/lit.base"
lit_lines "$relocated" >"$work/lit.head"
nb=$(wc -l <"$work/lit.base" | tr -d ' ')
nh=$(wc -l <"$work/lit.head" | tr -d ' ')
bb=$(awk -F'\t' '{s += length($2) + 1} END {printf "%d", s}' "$work/lit.base")
printf 'base literal-interior comment lines = %s (%s B)\n' "$nb" "$bb"
printf 'head literal-interior comment lines = %s\n' "$nh"
cat "$work/lit.base"
# Relocating blocks above this region shifts its line numbers, so the proof is
# text equality plus a single uniform offset -- not identical line numbers.
cut -f2- "$work/lit.base" >"$work/lit.base.txt"
cut -f2- "$work/lit.head" >"$work/lit.head.txt"
if ! cmp -s "$work/lit.base.txt" "$work/lit.head.txt"; then
  printf 'FAIL literal-interior comment TEXT differs\n'
  diff -u "$work/lit.base.txt" "$work/lit.head.txt" | head -40
  exit 1
fi
shifts=$(paste "$work/lit.base" "$work/lit.head" \
  | awk -F'\t' '{print $3 - $1}' | sort -u | tr '\n' ' ')
printf 'ok    literal-interior comment TEXT byte-identical\n'
printf 'ok    line-number shift is uniform: %s(one value = no insertion inside the literal)\n' "$shifts"
if [ "$(printf '%s' "$shifts" | wc -w | tr -d ' ')" -ne 1 ]; then
  printf 'FAIL non-uniform shift implies an edit inside the literal\n'
  exit 1
fi

# Every planned block must be disjoint from those lines.
python3 - "$SPEC" "$work/lit.base" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1]))
lit = {int(l.split("\t")[0]) for l in open(sys.argv[2]) if l.strip()}
bad = [(b["start"], b["end"], i)
       for f in spec["files"] for b in f["blocks"] for i in lit
       if b["start"] <= i <= b["end"]]
print("ok    no planned block covers a literal-interior line" if not bad
      else f"FAIL planned blocks cover literal lines: {bad}")
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] || exit 1

# ---- phase 2: literal-aware code residue equality ----
printf -- '\n--- phase 2: code residue equality (literal-aware) ---\n'
normalise() {
  # Strip comment-only lines, but only outside `"""` literals, so embedded
  # kernel source is compared rather than deleted.
  awk '
    {
      keep = 1
      line = $0; sub(/^[ \t]+/, "", line)
      n = gsub(/"""/, "\"\"\"")
      if (!inlit && line ~ /^\/\//) keep = 0
      if (n % 2 == 1) inlit = !inlit
      if (keep) { sub(/[ \t]+$/, ""); print }
    }' "$1" | cat -s
}
normalise "$pristine"  >"$work/nb"
normalise "$relocated" >"$work/nh"
pb=$(wc -c <"$pristine" | tr -d ' ')
hb=$(wc -c <"$relocated" | tr -d ' ')
rb=$(wc -c <"$work/nb" | tr -d ' ')
if cmp -s "$work/nb" "$work/nh"; then
  printf 'ok    %-46s base=%-7s head=%-7s saved=%-7s residue=%s IDENTICAL\n' \
    "$REL" "$pb" "$hb" "$((pb - hb))" "$rb"
else
  printf 'FAIL residues differ\n'
  diff -u "$work/nb" "$work/nh" | head -60
  exit 1
fi

# ---- phase 3: rule-29 containment and arithmetic agreement ----
printf -- '\n--- phase 3: rule-29 containment and arithmetic agreement ---\n'
note="$work/notes/LagunaRuntimeModel.notes.md"
python3 "$repo_root/research/fern_partB_phase3_check.py" \
  "$SPEC" "$pristine" "$relocated" "$note"
phase3_rc=$?

printf -- '\n--- phase 4: DocC abstract detachment on the relocated copy ---\n'
python3 "$repo_root/research/fern_vendor_docc_detach_check.py" "$relocated"
docc_head=$?
python3 "$repo_root/research/fern_vendor_docc_detach_check.py" "$pristine" \
  >"$work/docc.base" 2>&1
docc_base=$?
printf 'pristine copy exit=%d  %s\n' "$docc_base" "$(tail -1 "$work/docc.base")"
printf 'relocated copy exit=%d\n' "$docc_head"
if [ "$docc_head" -ne "$docc_base" ]; then
  printf 'FAIL relocation changed the DocC detachment verdict\n'
  phase3_rc=1
fi

printf -- '\n--- projection ---\n'
cap=524288
printf 'projected size      %s B\n' "$hb"
printf 'per-file cap        %s B\n' "$cap"
printf 'headroom before     %s B\n' "$((cap - pb))"
printf 'headroom after      %s B\n' "$((cap - hb))"
printf 'note file written   notes/%s (%s B, scratch only)\n' \
  "LagunaRuntimeModel.notes.md" "$(wc -c <"$note" | tr -d ' ')"

if [ "$phase3_rc" -ne 0 ]; then
  printf '\nRESULT: FAIL (phase 3/4 assertion fired%s)\n' \
    "${MLXFAST_DRY_RUN_INJECT:+ under injected fault $MLXFAST_DRY_RUN_INJECT}"
  exit 1
fi
printf '\nRESULT: PASS (dry run only; %s untouched in this checkout)\n' "$REL"
