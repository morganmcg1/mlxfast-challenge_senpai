#!/bin/bash
# R108-N stage 1: emit a class-dosed copy of LagunaRuntimeModel.swift for the
# sliding fused decode attention kernel.
#
# Generalises maple-tanjiro-r107d-dose-gen.sh from a single fp32-fma dose to a
# per-class dose, so the instruction census can price each class it proposes to
# remove instead of assuming every slot costs the same as an fma.
#
#   CLASS=fma  D rounds of 8 fp32 metal::fma        (reproduces R107-D)
#   CLASS=mul  D rounds of 8 fp32 multiply
#   CLASS=sum  D rounds of 8 simd_sum + 8 multiply  (subtract the mul arm)
#   CLASS=shf  D rounds of 8 simd_shuffle_xor       (one butterfly step each)
#
# All arms use eight independent accumulators seeded from live K registers and
# fold back into pair_score0 with a 1e-30 weight, so the dose cannot be
# eliminated, measures issue slots rather than latency, and is numerically nil.
#
# usage: maple-edward-r108n-class-dose-gen.sh SRC DOSE OUT CLASS \
#            [ANCHOR_LO ANCHOR_HI ITERS]
set -u
src="$1"; dose="$2"; out="$3"; class="${4:-fma}"
lo="${5:-1600}"; hi="${6:-1720}"; iters="${7:-4}"
anchor=$(awk -v lo="$lo" -v hi="$hi" \
    'NR>=lo && NR<=hi && /^ *U pair_score1 = 0;$/ {print NR; exit}' "$src")
if [ -z "${anchor}" ]; then echo "anchor not found in $src" >&2; exit 1; fi
if [ "${dose}" -eq 0 ]; then
    cp "$src" "$out"
    echo "anchor=${anchor} class=${class} dose=0 (verbatim copy)"
    exit 0
fi
case "$class" in
  fma) body='dzN = metal::fma(dzN, U(1.0000001), U(1e-6));' ;;
  mul) body='dzN = dzN * U(1.0000001);' ;;
  sum) body='dzN = metal::simd_sum(dzN) * U(0.03125);' ;;
  shf) body='dzN = metal::simd_shuffle_xor(dzN, 1u);' ;;
  *)   echo "unknown class $class" >&2; exit 1 ;;
esac
awk -v n="${anchor}" -v d="${dose}" -v body="${body}" '
NR == n {
  print
  print "    U dz0 = pipe_ka[0]; U dz1 = pipe_ka[1];"
  print "    U dz2 = pipe_ka[2]; U dz3 = pipe_ka[3];"
  print "    U dz4 = pipe_kb[0]; U dz5 = pipe_kb[1];"
  print "    U dz6 = pipe_kb[2]; U dz7 = pipe_kb[3];"
  print "    for (int dd = 0; dd < " d "; ++dd) {"
  for (i = 0; i < 8; ++i) {
    line = body
    gsub(/dzN/, "dz" i, line)
    print "        " line
  }
  print "    }"
  print "    pair_score0 += U(1e-30) * ((dz0 + dz1) + (dz2 + dz3) + (dz4 + dz5) + (dz6 + dz7));"
  next
}
{ print }
' "$src" > "$out"
echo "anchor=${anchor} class=${class} dose=${dose} extra_ops_per_thread=$((dose * 8 * iters)) out=${out}"
