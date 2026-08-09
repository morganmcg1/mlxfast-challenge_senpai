#!/usr/bin/env bash
# R104-C gate G2: close the one open non-device threat left by PR #572
# (research/maple-tanjiro-r103b-kernel-text-differential.md:925-936, :1251-1259).
#
# The r103-B rungs bounded the GPU difference and showed dispatch counts are
# identical, but they did not bound HOST-side CPU and encode work: the OLD->NEW
# fold narrowed six symbols from `internal` to `private` and merged
# LagunaRuntimeLayers.swift into LagunaRuntimeModel.swift.  Either can change
# Swift specialisation, which is host-side work the GPU differential cannot see.
#
# Oracle: the Swift compiler.  Six forced-clean builds, two per revision,
# interleaved OLD MID NEW OLD MID NEW.  Objects of the scored module are wiped
# before every build so no hash can be a replayed object.  Extends
# research/nezuko_r103c_object_identity.sh from 2 arms to 3 revisions and from
# a single-file oracle to the whole module (the fold changed the file set, so a
# single-file hash under-covers the surface).
#
# Per build we record, for the WHOLE MLXFastModel module:
#   - sha256 and size of every emitted object
#   - the aggregate __TEXT byte count
#   - the multiset of defined (demangled) symbols
#   - sha256 of the linked worker binary
#
# Verdicts:
#   V1 determinism  each revision's two builds must be byte-identical.  This
#                   validates the oracle; without it no cross-revision claim
#                   means anything.
#   V2 host channel OLD vs MID vs NEW aggregate __TEXT and defined-symbol
#                   multiset.  Equal => the host-side CPU/encode channel is
#                   bounded to nothing and the threat is closed.  Unequal =>
#                   the threat is not closed, and the diff localises it.
#
# Zero benchmark receipts, no GPU, no timing.
set -uo pipefail
cd "$(dirname "$0")/../../.."
ROOT=$PWD
OUT=$ROOT/research/artifacts/tanjiro-r104c/hostgate
mkdir -p "$OUT"

REVS=(old mid new)
OBJREL=.build-worker/arm64-apple-macosx/release/MLXFastModel.build
BINREL=.build-worker/release/mlxfast-runtime-worker

snapshot() { # $1=rev  $2=pass
  local rev=$1 pass=$2 d=$ROOT/.mlxfast-private/r103b-$rev
  local tag="${rev}.p${pass}"
  ( cd "$d/$OBJREL" && shasum -a 256 ./*.o ) | sort -k2 > "$OUT/obj.$tag.sha256"
  ( cd "$d/$OBJREL" && for f in ./*.o; do
      printf '%s %s\n' "$(size -m "$f" | awk '/Segment __TEXT/{print $4}')" "$f"
    done ) | sort -k2 > "$OUT/text.$tag.txt"
  awk '{s+=$1} END{print s}' "$OUT/text.$tag.txt" > "$OUT/textsum.$tag.txt"
  ( cd "$d/$OBJREL" && nm -Ug ./*.o 2>/dev/null; nm -U ./*.o 2>/dev/null ) \
    | awk '{ $1=""; $2=""; sub(/^  /,""); print }' | sort > "$OUT/syms.$tag.txt"
  shasum -a 256 "$d/$BINREL" | cut -d' ' -f1 > "$OUT/bin.$tag.sha256"
}

build() { # $1=rev  $2=pass
  local rev=$1 pass=$2 d=$ROOT/.mlxfast-private/r103b-$rev
  echo "-- build $rev pass $pass --"
  rm -f "$d/$OBJREL"/*.o
  ( cd "$d" && CLANG_MODULE_CACHE_PATH="$d/.build-worker/clang-module-cache" \
      swift build -c release --force-resolved-versions \
        --scratch-path .build-worker --product mlxfast-runtime-worker ) \
    >"$OUT/build.$rev.p$pass.log" 2>&1 || {
      echo "BUILD FAILED rev=$rev pass=$pass"; tail -25 "$OUT/build.$rev.p$pass.log"; return 3; }
  # staleness guard: every object must postdate the wipe
  local newest_src
  newest_src=$(cd "$d" && ls -t Sources/MLXFastModel/*.swift | head -1)
  for o in "$d/$OBJREL"/*.o; do
    [ "$o" -nt "$d/$newest_src" ] || { echo "STALE OBJECT $o"; return 4; }
  done
  snapshot "$rev" "$pass"
  ( cd "$d" && git checkout -- Package.resolved 2>/dev/null )
  echo "   objects=$(wc -l <"$OUT/obj.$rev.p$pass.sha256" | tr -d ' ')" \
       "textsum=$(cat "$OUT/textsum.$rev.p$pass.txt")" \
       "syms=$(wc -l <"$OUT/syms.$rev.p$pass.txt" | tr -d ' ')"
}

echo "== R104-C G2: six forced-clean builds, interleaved =="
for pass in 1 2; do
  for rev in "${REVS[@]}"; do
    build "$rev" "$pass" || exit $?
  done
done

echo
echo "== V1 determinism (two forced-clean builds per revision) =="
det_ok=1
for rev in "${REVS[@]}"; do
  if cmp -s "$OUT/obj.$rev.p1.sha256" "$OUT/obj.$rev.p2.sha256"; then
    echo "  $rev: object set byte-identical across passes -> PASS"
  else
    echo "  $rev: object set DIFFERS across passes -> FAIL"; det_ok=0
    diff "$OUT/obj.$rev.p1.sha256" "$OUT/obj.$rev.p2.sha256" | head -20
  fi
done

echo
echo "== V2 host-side channel: OLD vs MID vs NEW =="
for rev in "${REVS[@]}"; do
  printf '  %-4s objects=%-3s __TEXT=%-9s defined_symbols=%s worker_sha=%s\n' \
    "$rev" "$(wc -l <"$OUT/obj.$rev.p1.sha256" | tr -d ' ')" \
    "$(cat "$OUT/textsum.$rev.p1.txt")" \
    "$(wc -l <"$OUT/syms.$rev.p1.txt" | tr -d ' ')" \
    "$(cut -c1-12 "$OUT/bin.$rev.p1.sha256")"
done
for pair in "old mid" "mid new" "old new"; do
  set -- $pair
  only_a=$(comm -23 "$OUT/syms.$1.p1.txt" "$OUT/syms.$2.p1.txt" | wc -l | tr -d ' ')
  only_b=$(comm -13 "$OUT/syms.$1.p1.txt" "$OUT/syms.$2.p1.txt" | wc -l | tr -d ' ')
  echo "  $1 -> $2 : symbols only in $1 = $only_a ; only in $2 = $only_b"
  comm -23 "$OUT/syms.$1.p1.txt" "$OUT/syms.$2.p1.txt" > "$OUT/symdiff.$1-only.vs-$2.txt"
  comm -13 "$OUT/syms.$1.p1.txt" "$OUT/syms.$2.p1.txt" > "$OUT/symdiff.$2-only.vs-$1.txt"
done

echo
[ "$det_ok" = 1 ] && echo "V1: PASS (oracle is deterministic)" || echo "V1: FAIL"
echo "done"
