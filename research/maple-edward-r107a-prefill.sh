#!/usr/bin/env bash
# R107-A stage 2: prefill control for the routed gate/up packing curve.
#
# The packed routed kernel is dispatched only from the decode branch of
# LagunaRuntimeSparseMoEBlock.forward, so prefill should be untouched by
# construction. This measures that rather than asserting it, and turns the
# result into an exclusion bound on any accidental coupling.
#
# decode_probe.py emits exactly one "prefill 512 tokens:" line per process
# launch, so precision comes from slot count, not from steps. Slot cost is
# dominated by the ~42.5 s model load, so steps are kept modest but non-zero to
# retain a per-slot greedy parity check.
#
# usage: bash research/maple-edward-r107a-prefill.sh [SG ...]     (default: 0 8)
#   SG=0 selects the untouched default path; SG>0 selects the _sgN pipeline.
set -uo pipefail

SNAP="${SNAP:-/tmp/maple-r107a-snap}"
OUT="${OUT:-/tmp/maple-r107a/prefill}"
REPS="${REPS:-8}"
STEPS="${STEPS:-64}"
SGS=("$@")
[ ${#SGS[@]} -eq 0 ] && SGS=(0 8)

WORKER="${SNAP}/new/mlxfast-runtime-worker"
[ -x "${WORKER}" ] || { echo "refusing: missing ${WORKER}" >&2; exit 3; }
if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor tree is dirty" >&2; exit 2
fi

mkdir -p "${OUT}"
PROV="${OUT}/provenance.txt"
: >"${PROV}"
log() { printf '%s\n' "$*" | tee -a "${PROV}"; }

tree_digest() {
  find Sources Vendor -type f -print0 | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
}
DIGEST_BEFORE="$(tree_digest)"
log "head=$(git rev-parse HEAD)"
log "digest_before=${DIGEST_BEFORE}"
log "reps=${REPS} steps=${STEPS} sgs=${SGS[*]}"
log "host=$(sysctl -n machdep.cpu.brand_string)"
shasum -a 256 "${WORKER}" | tee -a "${PROV}"

finish() {
  local after; after="$(tree_digest)"
  log "digest_after=${after}"
  [ "${after}" = "${DIGEST_BEFORE}" ] \
    && log "PASS(rule 75): Sources+Vendor unchanged across the timed run" \
    || log "FAIL(rule 75): Sources+Vendor changed during the timed run"
}
trap finish EXIT

NARMS=${#SGS[@]}
: >"${OUT}/index.tsv"
printf 'rep\tposition\tarm\tprefill_ms\n' >>"${OUT}/index.tsv"

for rep in $(seq 1 "${REPS}"); do
  # Per-rep palindrome: forward then reverse, so linear drift cancels within
  # the repetition and every arm sees one interior and one exterior slot.
  order=()
  for ((i = 0; i < NARMS; i++)); do order+=("${i}"); done
  for ((i = NARMS - 1; i >= 0; i--)); do order+=("${i}"); done

  pos=0
  for idx in "${order[@]}"; do
    pos=$((pos + 1))
    sg="${SGS[$idx]}"
    arm="sg${sg}"; [ "${sg}" = "0" ] && arm="base"
    tag=$(printf "rep%02d-pos%d-%s" "${rep}" "${pos}" "${arm}")
    echo "=== ${tag} ==="
    env DARKBLOOM_ROUTED_GATEUP_SG="${sg}" \
        DECODE_PROBE_WORKER="${WORKER}" \
      python3 research/decode_probe.py --steps "${STEPS}" --prefill \
        --dump-tokens "${OUT}/${tag}.tokens" \
        >"${OUT}/${tag}.log" 2>&1
    ms=$(awk '/^prefill 512 tokens:/ {print $4}' "${OUT}/${tag}.log")
    div=$(awk '/divergences/ {print $4}' "${OUT}/${tag}.log")
    [ -n "${ms}" ] || ms="NA"
    printf '%d\t%d\t%s\t%s\n' "${rep}" "${pos}" "${arm}" "${ms}" \
      >>"${OUT}/index.tsv"
    echo "  prefill=${ms} ms divergences=${div:-?}"
  done
done

echo "########## token parity across every slot ##########"
cksum "${OUT}"/rep*.tokens | awk '{print $1, $3}' | tee "${OUT}/tokens.cksum"
awk '{print $1}' "${OUT}/tokens.cksum" | sort -u | wc -l \
  | xargs -I{} echo "distinct token-stream checksums: {} (must be 1)"

python3 - "${OUT}" <<'PY' | tee "${OUT}/analysis.txt"
import statistics, sys
from collections import defaultdict
from pathlib import Path

out = Path(sys.argv[1])
rows = [l.split("\t") for l in
        (out / "index.tsv").read_text().splitlines()[1:]]
byrep = defaultdict(lambda: defaultdict(list))
for rep, pos, arm, ms in rows:
    if ms != "NA":
        byrep[int(rep)][arm].append(float(ms))

arms = sorted({a for r in byrep.values() for a in r})
print(f"# R107-A prefill control ({out})")
print(f"arms: {arms}  repetitions: {len(byrep)}")

# One estimate per arm per repetition, averaging its palindrome positions.
est = {r: {a: statistics.mean(v) for a, v in d.items()}
       for r, d in byrep.items()}
for a in arms:
    v = [e[a] for e in est.values() if a in e]
    print(f"  {a:6s} n={len(v):2d} mean={statistics.mean(v):8.3f} ms "
          f"median={statistics.median(v):8.3f} ms")

base = "base"
if base in arms:
    for a in arms:
        if a == base:
            continue
        d = [e[a] - e[base] for e in est.values() if a in e and base in e]
        if len(d) < 2:
            continue
        m = statistics.mean(d)
        se = statistics.stdev(d) / len(d) ** 0.5
        lo, hi = m - 2.16 * se, m + 2.16 * se   # t_.975 ~ n=14 df, conservative
        pct = 100 * m / statistics.mean([e[base] for e in est.values()])
        print(f"  {base}->{a}: {m:+.3f} ms [{lo:+.3f}, {hi:+.3f}] "
              f"({pct:+.3f}%)  excl>{max(abs(lo), abs(hi)):.3f} ms")
PY
echo "########## done ##########"
