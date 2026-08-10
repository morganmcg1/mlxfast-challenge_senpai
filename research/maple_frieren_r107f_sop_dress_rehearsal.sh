#!/bin/bash
# R107-F / margin-certificate SOP dress rehearsal.
#
# Purpose: re-validate the certificate instrument on the CURRENT tree and
# measure an honest turnaround (SLA) for the service advertised in
# research/maple-frieren-margin-certificate-service.md.
#
# Protocol: two captures of the SAME arm (no env, no patch) -> certify.
# The only admissible verdict is PASS-BIT-EXACT; anything else means the
# instrument or the host is not reproducible and the service is DOWN.
set -u
cd /Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target

SCRIPT=research/maple-frieren-r106j-margin-certificate.py
OUT=research/artifacts/maple-frieren-r107f/sop
TMP=/tmp/r107f-sop
mkdir -p "$OUT" "$TMP"

echo "=== host/tree provenance ==="
git rev-parse HEAD
sha256sum .build-worker/release/mlxfast-runtime-worker 2>/dev/null || \
  shasum -a 256 .build-worker/release/mlxfast-runtime-worker
date -u +%Y-%m-%dT%H:%M:%SZ

T0=$(date +%s)
echo "=== phase 1/3: capture arm A (teacher, 64 steps) ==="
python3 "$SCRIPT" capture --label sop_rehearsal_a --mode teacher --steps 64 \
  --out "$TMP/a.npz"
echo "capture_a exit=$?"
T1=$(date +%s)

echo "=== phase 2/3: capture arm B (identical arm, teacher, 64 steps) ==="
python3 "$SCRIPT" capture --label sop_rehearsal_b --mode teacher --steps 64 \
  --out "$TMP/b.npz"
echo "capture_b exit=$?"
T2=$(date +%s)

echo "=== phase 3/3: certify A vs B ==="
# --expect-identical-build is MANDATORY here and only here: this is a null cell,
# both arms are the same binary on purpose. Cert v2 VOIDs an identical-build
# pair that does not declare itself (see SOP §9 trap 7); without the flag this
# rehearsal exits 3 even when the host is perfectly reproducible.
python3 "$SCRIPT" certify --baseline "$TMP/a.npz" --candidate "$TMP/b.npz" \
  --expect-identical-build \
  --out "$OUT/cert_rehearsal_null.json"
echo "certify exit=$?"
T3=$(date +%s)

echo "=== timings (seconds) ==="
echo "capture_a=$((T1-T0)) capture_b=$((T2-T1)) certify=$((T3-T2)) total=$((T3-T0))"
python3 - <<'PY'
import json
d = json.load(open('research/artifacts/maple-frieren-r107f/sop/cert_rehearsal_null.json'))
print('verdict:', d['verdict'])
print('reasons:', d.get('verdict_reasons'))
p = d['1_perturbation']
print('bitwise_identical:', p['bitwise_identical'],
      'elements_differing:', p['elements_differing'],
      '/', p['elements_compared'])
print('git_head baseline:', d['baseline_arm']['git_head'],
      'candidate:', d['candidate_arm']['git_head'])
PY
echo "=== done ==="
