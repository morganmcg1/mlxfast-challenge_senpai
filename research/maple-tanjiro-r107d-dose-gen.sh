#!/bin/bash
# R107-D stage 1(b): emit an instruction-dosed copy of LagunaRuntimeModel.swift.
#
# Adds DOSE rounds of 8 independent fp32 fma per main-loop iteration of
# laguna_sliding_fused_attn_ring_v1.  The chain is seeded from live K registers
# and folded back into pair_score0 with a 1e-30 weight, so the compiler cannot
# eliminate it and the numeric effect is nil.  Eight accumulators give enough
# ILP that the dose measures issue slots, not fma latency.
#
# usage: maple-tanjiro-r107d-dose-gen.sh SRC DOSE OUT [ANCHOR_LO ANCHOR_HI ITERS GUARD]
# The default anchor window selects the sliding kernel's 4-deep main loop; pass
# 2100 2200 8 for the full kernel's 2-deep loop.
#
# GUARD is an optional Metal predicate ("lane < 16", "lane == 0") that wraps the
# dose.  Comparing a guarded dose with the unguarded dose of the same size
# prices instructions issued under a partial-lane mask, which is what the
# narrow prologue/epilogue sections of the shipped kernels are made of.
set -u
src="$1"; dose="$2"; out="$3"; lo="${4:-1600}"; hi="${5:-1720}"; iters="${6:-4}"; guard="${7:-}"
anchor=$(awk -v lo="$lo" -v hi="$hi" 'NR>=lo && NR<=hi && /^ *U pair_score1 = 0;$/ {print NR; exit}' "$src")
if [ -z "${anchor}" ]; then echo "anchor not found in $src" >&2; exit 1; fi
if [ "${dose}" -eq 0 ]; then cp "$src" "$out"; echo "anchor=${anchor} dose=0 (verbatim copy)"; exit 0; fi
awk -v n="${anchor}" -v d="${dose}" -v g="${guard}" '
NR == n {
  print
  if (g != "") print "    if (" g ") {"
  print "    U dz0 = pipe_ka[0]; U dz1 = pipe_ka[1];"
  print "    U dz2 = pipe_ka[2]; U dz3 = pipe_ka[3];"
  print "    U dz4 = pipe_kb[0]; U dz5 = pipe_kb[1];"
  print "    U dz6 = pipe_kb[2]; U dz7 = pipe_kb[3];"
  print "    for (int dd = 0; dd < " d "; ++dd) {"
  print "        dz0 = metal::fma(dz0, U(1.0000001), U(1e-6));"
  print "        dz1 = metal::fma(dz1, U(1.0000001), U(1e-6));"
  print "        dz2 = metal::fma(dz2, U(1.0000001), U(1e-6));"
  print "        dz3 = metal::fma(dz3, U(1.0000001), U(1e-6));"
  print "        dz4 = metal::fma(dz4, U(1.0000001), U(1e-6));"
  print "        dz5 = metal::fma(dz5, U(1.0000001), U(1e-6));"
  print "        dz6 = metal::fma(dz6, U(1.0000001), U(1e-6));"
  print "        dz7 = metal::fma(dz7, U(1.0000001), U(1e-6));"
  print "    }"
  print "    pair_score0 += U(1e-30) * ((dz0 + dz1) + (dz2 + dz3) + (dz4 + dz5) + (dz6 + dz7));"
  if (g != "") print "    }"
  next
}
{ print }
' "$src" > "$out"
echo "anchor=${anchor} dose=${dose} guard=${guard:-none} extra_fma_per_thread=$((dose * 8 * iters)) out=${out}"
