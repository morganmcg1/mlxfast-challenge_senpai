#!/usr/bin/env bash
# R106-B Stage B — bit-exactness instrument for the PACKRED packed-reduction sliding
# decode-attention kernel.
#
# research/run_upstream_equivalence.sh runs the vendored-Laguna upstream oracle
# with ZERO tolerance (MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR defaults to "0")
# and prints EQUIVALENCE_EXACT_STEPS = the number of steps whose
# "maximumAbsoluteLogitError" is exactly 0. Running it once with the PACKRED gate off
# and once with it on therefore answers the bit-exactness question directly:
# if both arms report the same EQUIVALENCE_EXACT_STEPS and exit 0, the packed
# kernel reproduces the shipped path bit-for-bit against the same oracle.
#
# Logs are kept outside the worktree so a run never dirties the checkout.
set -uo pipefail
cd "$(dirname "$0")/.."

# Amendment 2 promotes H4 back into the evidence campaign, so H4 needs the same
# certificate as PACKRED: arm "h4" is checked here too. Arm "off" is the control
# and doubles as the check that the header-macro refactor itself is
# behaviour-preserving.
for arm in off on h4; do
  log="/tmp/r106b_packred_exact_${arm}.log"
  echo "=== exactness arm=${arm} start $(date -u +%H:%M:%S)"
  case "$arm" in
    on) DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 research/run_upstream_equivalence.sh > "$log" 2>&1 ;;
    h4) DARKBLOOM_FUSED_SLIDING_ATTN_H4=1 research/run_upstream_equivalence.sh > "$log" 2>&1 ;;
    *)  research/run_upstream_equivalence.sh > "$log" 2>&1 ;;
  esac
  st=$?
  echo "arm=${arm} exit=${st}"
  # Gate provenance. Without this, a mistyped gate would quietly compare the
  # control kernel against itself and report a bit-exactness certificate for a
  # kernel that never ran. Each sliding-attention kernel announces its MLX name
  # once, from its own one-shot initialiser, so the name below is the kernel the
  # oracle actually exercised.
  case "$arm" in
    on) want=laguna_sliding_fused_attn_ring_packred_v1 ;;
    h4) want=laguna_sliding_fused_attn_ring_h4_v1 ;;
    *)  want=laguna_sliding_fused_attn_ring_v1 ;;
  esac
  # Read only the announce line, never any other mention of a kernel name: the
  # source string and the comments in the log also contain kernel names, and a
  # comma-joined union of those would spuriously fail the comparison below.
  got="$(grep -o 'sliding fused attn kernel: [a-z0-9_]*' "$log" 2>/dev/null \
    | sed 's/.*: //' | sort -u | paste -sd, -)"
  echo "arm=${arm} kernel=${got:-<none>} expected=${want}"
  if [ "$got" != "$want" ]; then
    echo "arm=${arm} FATAL: gate provenance mismatch -- this arm's certificate is void" >&2
    exit 1
  fi
  grep -E 'EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT' "$log" | sed "s/^/arm=${arm} /"
  grep -c '"maximumAbsoluteLogitError"' "$log" | sed "s/^/arm=${arm} report_steps=/"
  grep -oE '"maximumAbsoluteLogitError" : [0-9.e-]+' "$log" | sort -u \
    | sed "s/^/arm=${arm} distinct: /"
  echo "=== exactness arm=${arm} done $(date -u +%H:%M:%S)"
done

git checkout -- Package.resolved 2>/dev/null || true
echo "logs: /tmp/r106b_packred_exact_off.log /tmp/r106b_packred_exact_on.log"
