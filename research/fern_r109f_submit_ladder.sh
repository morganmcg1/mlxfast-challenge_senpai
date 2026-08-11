#!/usr/bin/env bash
# fern r109-f: repeated ./benchmark.sh --local-submit draws with per-draw
# archival, for the n>=3 baseline / candidate ladders owed to Cedar.
#
# Usage: research/fern_r109f_submit_ladder.sh <label> <n>
#
# Archives, per draw i:
#   research/fern-r109f-submit-ladder/<label>-<i>.json        score.local-submit.json
#   research/fern-r109f-submit-ladder/<label>-<i>.integrity   benchmark-integrity.local-submit.json
#   research/fern-r109f-submit-ladder/<label>-<i>.log         full stdout/stderr
# and appends one CSV row per draw to
#   research/fern-r109f-submit-ladder/<label>.csv
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

label="${1:?label}"
n="${2:?n}"
out="research/fern-r109f-submit-ladder"
mkdir -p "${out}"
csv="${out}/${label}.csv"
if [ ! -f "${csv}" ]; then
  echo "label,draw,started_utc,exit,git_head,commit,score_local,ns_official,decode_s_per_tok,prefill_s_per_tok,max_abs_diff,golden_hash,passed,passed_correctness,wall_s" > "${csv}"
fi

head_sha="$(git rev-parse HEAD)"

for i in $(seq 1 "${n}"); do
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  t0="$(date +%s)"
  # Unattended: never prompt for a fan boost; the thermal gate still waits.
  MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit \
    > "${out}/${label}-${i}.log" 2>&1
  rc=$?
  t1="$(date +%s)"
  wall=$(( t1 - t0 ))
  if [ -f score.local-submit.json ]; then
    cp score.local-submit.json "${out}/${label}-${i}.json"
  fi
  if [ -f benchmark-integrity.local-submit.json ]; then
    cp benchmark-integrity.local-submit.json "${out}/${label}-${i}.integrity"
  fi
  python3 - "${label}" "${i}" "${started}" "${rc}" "${head_sha}" "${wall}" \
      "${out}/${label}-${i}.json" "${csv}" <<'PY'
import json, sys
label, i, started, rc, head, wall, path, csv = sys.argv[1:9]
# Official normalisation constants (organizer scoring), not the per-run local
# baseline fields, so draws stay comparable to receipts.
DEC0, PRE0 = 0.013890, 0.0003845
try:
    with open(path) as f:
        d = json.load(f)
    m = d["metrics"]
    dec = m["decode_seconds_per_token"]; pre = m["prefill_seconds_per_token"]
    ns = (DEC0 / dec) ** 0.75 * (PRE0 / pre) ** 0.25 if dec and pre else ""
    row = [label, i, started, rc, head, m.get("commit", ""), d.get("score", ""),
           f"{ns:.6f}" if ns != "" else "", f"{dec:.12f}", f"{pre:.12f}",
           m.get("max_abs_diff", ""), m.get("golden_hash", ""),
           d.get("passed", ""), m.get("passed_correctness", ""), wall]
except Exception as e:
    row = [label, i, started, rc, head, "", "", "", "", "", "", "", "", f"ERR:{e}", wall]
with open(csv, "a") as f:
    f.write(",".join(str(x) for x in row) + "\n")
print("DRAW", label, i, "rc=", rc, "ns=", row[7], "wall=", wall)
PY
done

echo "=== ${csv} ==="
cat "${csv}"
