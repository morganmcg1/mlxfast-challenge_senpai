#!/usr/bin/env bash
# R85-B Part 2c: inventory the submitted editable surface.
#
# Research-only helper (outside editablePaths). Reproduces the accounting used
# by senpai/check-editable-budget.sh -- directory entries expand to every
# regular file beneath them, duplicates are counted once -- and additionally
# reports the per-file byte table sorted descending plus each entry's rollup.
set -euo pipefail

MAX_TOTAL_BYTES=3000000
MAX_FILE_BYTES=524288

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

contract="${1:-benchmark.json}"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-inventory.XXXXXX")"
trap 'rm -rf "${work_dir}"' EXIT

entries="${work_dir}/entries"
pairs="${work_dir}/pairs"
missing="${work_dir}/missing"
jq -r '.editablePaths[]' "${contract}" > "${entries}"
: > "${pairs}"
: > "${missing}"

entry_count=0
while IFS= read -r entry; do
  [[ -n "${entry}" ]] || continue
  entry_count=$((entry_count + 1))
  if [[ -L "${entry}" ]]; then
    printf 'SYMLINK\t%s\n' "${entry}" >> "${missing}"
  elif [[ -f "${entry}" ]]; then
    printf '%s\t%s\n' "${entry}" "${entry}" >> "${pairs}"
  elif [[ -d "${entry}" ]]; then
    while IFS= read -r file; do
      printf '%s\t%s\n' "${entry}" "${file}" >> "${pairs}"
    done < <(find "${entry}" -type f | LC_ALL=C sort)
  else
    printf 'ABSENT\t%s\n' "${entry}" >> "${missing}"
  fi
done < "${entries}"

# Deduplicate by file, keeping the first entry that claimed it.
sized="${work_dir}/sized"
: > "${sized}"
seen="${work_dir}/seen"
: > "${seen}"
while IFS=$'\t' read -r entry file; do
  if grep -Fqx -- "${file}" "${seen}"; then
    continue
  fi
  printf '%s\n' "${file}" >> "${seen}"
  printf '%s\t%s\t%s\n' "$(wc -c < "${file}" | tr -d ' ')" "${file}" "${entry}" >> "${sized}"
done < "${pairs}"

total="$(awk -F'\t' '{s+=$1} END {print s+0}' "${sized}")"
file_count="$(wc -l < "${sized}" | tr -d ' ')"
over_cap="$(awk -F'\t' -v cap="${MAX_FILE_BYTES}" '$1 > cap' "${sized}" | wc -l | tr -d ' ')"

echo "=== editable surface inventory ==="
echo "contract              : ${contract}"
echo "editablePaths entries : ${entry_count}"
echo "distinct files        : ${file_count}"
echo "total bytes           : ${total}/${MAX_TOTAL_BYTES} (headroom $((MAX_TOTAL_BYTES - total)))"
echo "per-file cap          : ${MAX_FILE_BYTES} (files over cap: ${over_cap})"
if [[ -s "${missing}" ]]; then
  echo
  echo "!! entries that are not a regular file or directory:"
  cat "${missing}"
fi

echo
echo "=== per-entry rollup (bytes, files, entry) ==="
awk -F'\t' '{b[$3]+=$1; n[$3]++} END {for (e in b) printf "%10d  %4d  %s\n", b[e], n[e], e}' "${sized}" \
  | LC_ALL=C sort -rn

echo
echo "=== per-file bytes, descending ==="
awk -F'\t' -v cap="${MAX_FILE_BYTES}" \
  '{printf "%10d  %8d  %s\n", $1, cap - $1, $2}' "${sized}" | LC_ALL=C sort -rn
echo
echo "(second column is remaining headroom under the ${MAX_FILE_BYTES}-byte per-file cap)"
