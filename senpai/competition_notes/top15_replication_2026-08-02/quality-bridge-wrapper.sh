#!/bin/sh
set -eu

: "${MLXFAST_TOP15_REAL_QUALITY_BRIDGE:?missing real quality bridge path}"
if [ ! -x "${MLXFAST_TOP15_REAL_QUALITY_BRIDGE}" ]; then
  echo "top15 quality wrapper: bridge is not executable: ${MLXFAST_TOP15_REAL_QUALITY_BRIDGE}" >&2
  exit 126
fi

# The historical M5/NAX snapshots predate the architecture-aware predicate.
# Python deliberately strips submitted DARKBLOOM_* flags before launching this
# wrapper; set only the M4 layout-compatibility selector here, then preserve the
# evaluator's ranked/full LM-head selection and every other sanitized default.
real_bridge="${MLXFAST_TOP15_REAL_QUALITY_BRIDGE}"
unset MLXFAST_TOP15_REAL_QUALITY_BRIDGE
export DARKBLOOM_EXPERT_ALIGNED_GATHER=0
exec "${real_bridge}" "$@"
