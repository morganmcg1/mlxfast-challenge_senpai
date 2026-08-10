#!/usr/bin/env bash
# Research-only (PR #629, R107-A) stage 0: prove the reached dispatch geometry
# for S in {2,4,8,16}, prove greedy token parity at every S, and show the
# store-row negative control fails.
#
# `bash research/maple-edward-r107a-stage0.sh geom-only` reuses the snapshots an
# earlier full run built and re-probes geometry alone, which is how the SG=1
# receipt for the stage-1 `null1` null arm was topped up without paying for
# three rebuilds and the parity and fault probes again.
set -uo pipefail

MODE="${1:-full}"
SNAP="${SNAP:-/tmp/maple-r107a-snap}"
OUT="${OUT:-/tmp/maple-r107a/stage0}"
PARITY_STEPS="${PARITY_STEPS:-96}"
# 1 is not an accepted selector value, so it must resolve to the untouched
# shipped path; the receipt is what proves the `null1` arm is that path.
GEOM_SG_LIST="${GEOM_SG_LIST:-1 2 4 8 16}"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor tree is dirty" >&2; exit 2
fi
if [ ! -f weights/config.json ]; then
  echo "refusing: weights/ is not a transformed checkpoint" >&2; exit 2
fi
DIGEST_BEFORE="$(find Sources Vendor -type f -print0 | sort -z \
  | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"

build_variant() {
  local mode="$1" name="$2"
  python3 research/maple-edward-r107a-patch.py "${mode}" || return 1
  NAME="${name}" SNAP="${SNAP}" bash research/maple-edward-r107a-build.sh
  local rc=$?
  git checkout -- Sources Vendor
  return ${rc}
}

if [ "${MODE}" != geom-only ]; then
  NAME=new SNAP="${SNAP}" bash research/maple-edward-r107a-build.sh \
    || { echo "candidate build failed" >&2; exit 3; }
  build_variant geom geom || { echo "geom build failed" >&2; exit 3; }
  build_variant fault fault || { echo "fault build failed" >&2; exit 4; }
fi

DIGEST_AFTER="$(find Sources Vendor -type f -print0 | sort -z \
  | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"
echo "digest_before=${DIGEST_BEFORE}"
echo "digest_after=${DIGEST_AFTER}"
[ "${DIGEST_BEFORE}" = "${DIGEST_AFTER}" ] \
  && echo "PASS(rule 75): Sources+Vendor restored after instrumented builds" \
  || { echo "FAIL(rule 75): tree not restored" >&2; exit 5; }

probe() {  # tag snapshot steps [SG]
  local tag="$1" snap="$2" steps="$3" sg="${4:-}"
  local ev=()
  [ -n "${sg}" ] && ev=(DARKBLOOM_ROUTED_GATEUP_SG="${sg}")
  echo "=== ${tag} (snapshot=${snap} steps=${steps} sg=${sg:-unset}) ==="
  env ${ev[@]+"${ev[@]}"} \
    DECODE_PROBE_WORKER="${SNAP}/${snap}/mlxfast-runtime-worker" \
    python3 research/decode_probe.py --steps "${steps}" \
      --stderr "${OUT}/${tag}.err" \
      --dump-tokens "${OUT}/${tag}.tokens" >"${OUT}/${tag}.log" 2>&1
  PROBE_RC=$?
  echo "  probe_rc=${PROBE_RC}"
  grep -E "^teacher-forced|^decode steps=" "${OUT}/${tag}.log" \
    || { echo "  (no summary)"; tail -3 "${OUT}/${tag}.err"; }
  grep -o '^R107GEOM .*' "${OUT}/${tag}.err" | head -1
  awk '/^R107SRC_BEGIN$/{f=1;next} /^R107SRC_END$/{f=0} f' "${OUT}/${tag}.err" \
    | head -400 >"${OUT}/${tag}.metal"
  if [ -s "${OUT}/${tag}.metal" ]; then
    printf 'metal_src_sha=%s rows_stride_line=%s\n' \
      "$(shasum -a 256 "${OUT}/${tag}.metal" | awk '{print $1}')" \
      "$(grep -n 'logical_row = tile' "${OUT}/${tag}.metal" | head -1)"
  fi
}

echo "########## A. geometry receipts (instrumented build) ##########"
probe geom-base geom 8
[ "${PROBE_RC}" = 0 ] || { echo "FAIL: probe harness is dead; aborting" >&2
  tail -20 "${OUT}/geom-base.log" >&2; exit 6; }
for s in ${GEOM_SG_LIST}; do probe "geom-sg${s}" geom 8 "${s}"; done

if [ "${MODE}" = geom-only ]; then echo "########## done (geom-only) ##########"; exit 0; fi

echo "########## B. greedy token parity on the shipped candidate ##########"
probe parity-base new "${PARITY_STEPS}"
for s in 2 4 8 16; do probe "parity-sg${s}" new "${PARITY_STEPS}" "${s}"; done
echo "--- token stream checksums (must all be equal) ---"
cksum "${OUT}"/parity-*.tokens | awk '{print $1, $3}'
awk '{print $1}' <(cksum "${OUT}"/parity-*.tokens) | sort -u | wc -l \
  | xargs -I{} echo "distinct parity token checksums: {} (must be 1)"

echo "########## C. store-row negative control (MUST fail) ##########"
probe fault-sg8 fault "${PARITY_STEPS}" 8
probe fault-sg16 fault "${PARITY_STEPS}" 16
echo "########## done ##########"
