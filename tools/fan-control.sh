#!/usr/bin/env bash
# Manual Mac fan control helper for the local benchmark thermal gate.
#
# Usage:
#   tools/fan-control.sh boost    # force every fan to 70% of its maximum speed
#   MLXFAST_FAN_BOOST_PERCENT=80 tools/fan-control.sh boost
#                                 # operator-only fallback after 70% is insufficient
#   tools/fan-control.sh normal   # hand fan control back to macOS (automatic)
#   tools/fan-control.sh status   # print one of: manual | auto | none
#                                 # (manual = at least one fan's mode bit set)
#
# `boost` refuses to run while any fan is already in manual mode: that bit
# means another fan controller (or a prior boost that was never restored)
# holds the fans, and boosting would silently overwrite its targets. It also
# reads every write back from the SMC and refuses to report success for a fan
# whose write did not stick (some firmware silently drops fan writes unless a
# global force-gate like Ftst is set; this helper deliberately never writes
# that key).
#
# WHY THIS NEEDS SUDO: fan targets live in the System Management Controller
# (SMC), and macOS only accepts SMC key writes from root. `boost` and `normal`
# therefore run their `smc` writes under sudo. sudo prompts for your password
# itself, on your terminal, via its normal secure prompt: this script never
# reads, stores, echoes, or logs the password (no piping a password into
# sudo's stdin, no askpass plumbing), and it invalidates sudo's cached
# credential right after the writes with `sudo -k`, so no elevated session
# lingers.
#
# The boost target defaults to 70% of each fan's maximum RPM. An operator may
# explicitly request 80% after a verified 70% trial cannot satisfy the thermal
# gate; every other value is refused. 80% adds noise and wear, so use it only
# for a bounded campaign and restore automatic control afterward. `normal`
# pins nothing -- it clears the manual-mode bit so macOS's automatic fan curve
# takes over again, exactly as if this script had never run.
set -euo pipefail

readonly FAN_BOOST_PERCENT="${MLXFAST_FAN_BOOST_PERCENT:-70}"
# Read-back tolerance when verifying a written fan target. The SMC stores
# the target as a 4-byte float, so the value read back can differ from the
# one written by rounding -- fractions of an RPM, never more. Anything
# further off than this means the firmware did not accept the write.
readonly FAN_TARGET_VERIFY_TOLERANCE_RPM=10
SUDO_CREDENTIAL_ACTIVE=0
AUTO_RESTORE_ON_EXIT=0
AUTO_RESTORE_FAN_COUNT=0

drop_sudo_credential() {
  if (( SUDO_CREDENTIAL_ACTIVE == 1 )); then
    sudo -k >/dev/null 2>&1 || true
    SUDO_CREDENTIAL_ACTIVE=0
  fi
}

run_sudo() {
  SUDO_CREDENTIAL_ACTIVE=1
  sudo "$@"
}

cleanup_fan_control_exit() {
  local exit_status="$?"
  trap - EXIT
  # Do not let a second interactive/termination signal interrupt the bounded
  # best-effort restoration once teardown has started. SIGKILL remains
  # inherently unrecoverable.
  trap '' INT TERM HUP
  set +e
  if (( AUTO_RESTORE_ON_EXIT == 1 && AUTO_RESTORE_FAN_COUNT > 0 )); then
    if ! restore_fans_to_auto "${AUTO_RESTORE_FAN_COUNT}"; then
      echo "fan-control.sh: URGENT: interrupted boost cleanup could not verify automatic fan control" >&2
      (( exit_status != 0 )) || exit_status=1
    fi
  fi
  drop_sudo_credential
  exit "${exit_status}"
}

exit_for_signal() {
  local exit_status="$1"
  exit "${exit_status}"
}

# Unexpected failures must not leave a partial fan override or sudo's cached
# credential behind. Successful boost deliberately clears the restore flag so
# its verified manual target persists until the operator requests `normal`.
trap cleanup_fan_control_exit EXIT
trap 'exit_for_signal 130' INT
trap 'exit_for_signal 143' TERM
trap 'exit_for_signal 129' HUP

usage() {
  echo "usage: $0 {boost|normal|status}" >&2
  exit 64
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "fan-control.sh: only supported on macOS" >&2
  exit 1
fi

# smc CLI discovery: explicit override, PATH, then the copy bundled inside
# smcFanControl.app (a common way to have the tool without a PATH install).
find_smc() {
  local candidate
  if [[ -n "${MLXFAST_SMC_BIN:-}" ]]; then
    if [[ -x "${MLXFAST_SMC_BIN}" ]]; then
      printf '%s\n' "${MLXFAST_SMC_BIN}"
      return 0
    fi
    echo "fan-control.sh: MLXFAST_SMC_BIN is set but not executable: ${MLXFAST_SMC_BIN}" >&2
    return 1
  fi
  if candidate="$(command -v smc 2>/dev/null)"; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  for candidate in \
      "/Applications/smcFanControl.app/Contents/Resources/smc" \
      /opt/homebrew/bin/smc \
      /usr/local/bin/smc; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

# Prints the numeric value of an SMC key: "  F0Mx  [flt ]  5920.0 (bytes ...)"
# becomes "5920.0". Reads are unprivileged; only writes need root.
smc_read_number() {
  local key="$1"
  local output value bytes
  output="$("${SMC_BIN}" -k "${key}" -r 2>/dev/null)" || output=""
  value="$(
    printf '%s\n' "${output}" \
      | sed -E 's/.*\]//; s/\(bytes.*//' \
      | awk '{print $1; exit}'
  )"
  if [[ -n "${value}" ]]; then
    printf '%s\n' "${value}"
    return 0
  fi

  # The classic smcFanControl CLI can read Apple-Silicon float keys but may
  # print only their four raw bytes. Decode that native-endian float using the
  # inverse of float_to_hex below; other key types keep the normal text path.
  if [[ "${output}" == *"[flt "* ]]; then
    bytes="$(
      printf '%s\n' "${output}" \
        | sed -nE 's/.*\(bytes ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2})\).*/\1\2\3\4/p'
    )"
    if [[ "${bytes}" =~ ^[0-9A-Fa-f]{8}$ ]]; then
      perl -e 'printf "%.6f\n", unpack("f", pack("H*", $ARGV[0]))' -- "${bytes}"
    fi
  fi
}

smc_key_is_float() {
  local key="$1"
  "${SMC_BIN}" -k "${key}" -r 2>/dev/null | grep -q '\[flt'
}

# smc -w takes raw hex bytes; fan targets are 4-byte native-endian IEEE-754
# floats on Apple Silicon.
float_to_hex() {
  perl -e 'printf "%s", unpack("H*", pack("f", $ARGV[0]))' -- "$1"
}

read_fan_count() {
  local count
  count="$(smc_read_number FNum)"
  if ! [[ "${count}" =~ ^[0-9]+$ ]]; then
    printf '0\n'
    return 0
  fi
  printf '%s\n' "${count}"
}

# A fan is under manual (forced) control when bit zero of its F<i>Md value is
# set. Firmware may expose additional mode flags (for example value 3), so the
# whole byte must not be compared with the literal value 1.
read_fan_mode() {
  local fan_index="$1"
  local mode
  mode="$(smc_read_number "F${fan_index}Md")" || mode=""
  [[ "${mode}" =~ ^[0-9]+$ ]] || return 2
  printf '%s\n' "${mode}"
}

fan_mode_value_is_manual() {
  local mode="$1"
  [[ "${mode}" =~ ^[0-9]+$ ]] || return 2
  (( (10#${mode} & 1) != 0 ))
}

fan_mode_is_manual() {
  local fan_index="$1"
  local mode
  mode="$(read_fan_mode "${fan_index}")" || return 2
  fan_mode_value_is_manual "${mode}"
}

# Prints the index of every fan currently in manual mode, one per line.
# Inspecting EVERY fan (not just fan 0) matters: another fan controller, or a
# partially-restored boost, can hold any subset of the fans manual.
list_manual_fans() {
  local fan_count="$1"
  local i mode_status
  for (( i = 0; i < fan_count; i++ )); do
    if fan_mode_is_manual "${i}"; then
      printf '%s\n' "${i}"
    else
      mode_status="$?"
      if (( mode_status != 1 )); then
        echo "fan-control.sh: could not read fan ${i} mode (F${i}Md)" >&2
        return 2
      fi
    fi
  done
}

# Reads a just-written fan mode/target back from the SMC and confirms the
# write actually took: manual mode set, and the stored target within
# FAN_TARGET_VERIFY_TOLERANCE_RPM of the requested RPM (the target
# round-trips through a 4-byte float, so exact string equality is too
# strict). Reads are unprivileged. Some firmware silently drops fan writes
# unless a global force-gate key (Ftst) is set; this helper deliberately does
# not write that key, so a dropped write must surface as a loud failure
# instead of a silently-ineffective "boost".
verify_fan_boost_write() {
  local fan_index="$1"
  local requested_rpm="$2"
  local mode_after target_after
  mode_after="$(read_fan_mode "${fan_index}")" || mode_after=""
  if [[ -z "${mode_after}" ]] || ! fan_mode_value_is_manual "${mode_after}"; then
    echo "fan-control.sh: WARNING: fan ${fan_index} mode read-back is '${mode_after:-<unreadable>}' (expected the manual bit to be set); the F${fan_index}Md write did not stick" >&2
    return 1
  fi
  target_after="$(smc_read_number "F${fan_index}Tg")" || target_after=""
  if ! [[ "${target_after}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "fan-control.sh: WARNING: fan ${fan_index} target read-back is '${target_after:-<unreadable>}' (expected about ${requested_rpm} RPM); the F${fan_index}Tg write did not stick" >&2
    return 1
  fi
  if ! awk -v got="${target_after}" -v want="${requested_rpm}" \
      -v tolerance="${FAN_TARGET_VERIFY_TOLERANCE_RPM}" \
      'BEGIN { delta = got - want; if (delta < 0) delta = -delta; exit !(delta <= tolerance) }'; then
    echo "fan-control.sh: WARNING: fan ${fan_index} target read-back is ${target_after} RPM, not the requested ${requested_rpm} RPM; the F${fan_index}Tg write did not stick" >&2
    return 1
  fi
}

# Clear manual mode for every fan and verify the read-back. `smc -w` reports
# only that the request was sent, so neither normal teardown nor rollback may
# claim success from its exit status alone.
restore_fans_to_auto() {
  local fan_count="$1"
  local i mode write_failed=0 verify_failed=0
  for (( i = 0; i < fan_count; i++ )); do
    if ! run_sudo "${SMC_BIN}" -k "F${i}Md" -w 00; then
      echo "fan-control.sh: WARNING: failed to request automatic mode for fan ${i}" >&2
      write_failed=1
    fi
  done
  sleep 0.2
  for (( i = 0; i < fan_count; i++ )); do
    mode="$(read_fan_mode "${i}")" || mode=""
    if [[ -z "${mode}" ]]; then
      echo "fan-control.sh: WARNING: fan ${i} automatic-mode read-back is unreadable" >&2
      verify_failed=1
    elif fan_mode_value_is_manual "${mode}"; then
      echo "fan-control.sh: WARNING: fan ${i} remains in manual mode (F${i}Md=${mode})" >&2
      verify_failed=1
    fi
  done
  (( write_failed == 0 && verify_failed == 0 ))
}

# Printed once before the first sudo prompt so the password request never
# arrives unexplained. Skipped when sudo already holds a cached credential
# (no prompt will appear).
explain_sudo() {
  if sudo -n true 2>/dev/null; then
    return 0
  fi
  cat >&2 <<EOF
fan-control.sh: changing fan speed writes SMC keys, which macOS only allows
fan-control.sh: as root -- sudo will now prompt for your password. The prompt
fan-control.sh: is sudo's own secure prompt: this script never reads, stores,
fan-control.sh: or logs the password, and it drops the cached credential right
fan-control.sh: after the write (sudo -k).
EOF
}

require_fans() {
  local count="$1"
  if (( count == 0 )); then
    echo "fan-control.sh: no controllable fans detected (fanless machine, or an unsupported smc build)" >&2
    exit 1
  fi
}

do_boost() {
  local fan_count i max_rpm min_rpm target hex manual_fans failed_fans=""
  case "${FAN_BOOST_PERCENT}" in
    70|80) ;;
    *)
      echo "fan-control.sh: MLXFAST_FAN_BOOST_PERCENT must be 70 or 80 (got '${FAN_BOOST_PERCENT}')" >&2
      exit 64
      ;;
  esac
  fan_count="$(read_fan_count)"
  require_fans "${fan_count}"
  # Refuse to boost over another controller. A set manual-mode bit on ANY fan
  # means something else -- a third-party fan tool, or a previous boost that
  # was never restored -- already holds that fan, and writing our own targets
  # would silently overwrite its settings. Conservative behavior: skip the
  # boost and tell the user how to hand control back to macOS first.
  # (benchmark.sh's offer checks `status` before calling boost, so on the
  # benchmark path this is a backstop, not a second warning.)
  if ! manual_fans="$(list_manual_fans "${fan_count}" | tr '\n' ' ')"; then
    echo "fan-control.sh: refusing to boost because current fan ownership could not be read safely" >&2
    exit 1
  fi
  manual_fans="${manual_fans% }"
  if [[ -n "${manual_fans}" ]]; then
    echo "fan-control.sh: fan(s) ${manual_fans} are already in manual mode; another fan controller (or a prior un-restored boost) holds the fans" >&2
    echo "fan-control.sh: refusing to overwrite its targets. Restore automatic control first with: ./benchmark.sh --fan-speed-normal (or stop the other fan tool), then retry" >&2
    exit 1
  fi
  explain_sudo
  for (( i = 0; i < fan_count; i++ )); do
    if ! smc_key_is_float "F${i}Tg"; then
      echo "fan-control.sh: fan ${i} target key F${i}Tg is not float-typed; this helper supports Apple Silicon SMCs only" >&2
      drop_sudo_credential
      exit 1
    fi
    max_rpm="$(smc_read_number "F${i}Mx")"
    if ! [[ "${max_rpm}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
      echo "fan-control.sh: could not read fan ${i} maximum speed (F${i}Mx)" >&2
      drop_sudo_credential
      exit 1
    fi
    min_rpm="$(smc_read_number "F${i}Mn")"
    if ! [[ "${min_rpm}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
      min_rpm=0
    fi
    target="$(awk -v mx="${max_rpm}" -v mn="${min_rpm}" -v pct="${FAN_BOOST_PERCENT}" \
      'BEGIN { t = mx * pct / 100; if (t < mn) t = mn; printf "%.1f", t }')"
    hex="$(float_to_hex "${target}")"
    # F<i>Md = 1 switches the fan to forced/manual mode; F<i>Tg is the RPM it
    # then holds until the mode bit is cleared.
    AUTO_RESTORE_ON_EXIT=1
    AUTO_RESTORE_FAN_COUNT="${fan_count}"
    if ! run_sudo "${SMC_BIN}" -k "F${i}Md" -w 01 \
        || ! run_sudo "${SMC_BIN}" -k "F${i}Tg" -w "${hex}"; then
      echo "fan-control.sh: WARNING: fan ${i} SMC write command failed" >&2
      failed_fans="${failed_fans:+${failed_fans} }${i}"
      continue
    fi
    # `smc -w` is fire-and-forget: it exits 0 even when the firmware drops
    # the write. Read both keys back and only report success for this fan if
    # the mode and target actually took. The short sleep lets the SMC settle
    # so the read-back does not race the write it is checking.
    sleep 0.2
    if verify_fan_boost_write "${i}" "${target}"; then
      echo "fan-control.sh: fan ${i} forced to ${target} RPM (${FAN_BOOST_PERCENT}% of max ${max_rpm}); read-back verified" >&2
    else
      failed_fans="${failed_fans:+${failed_fans} }${i}"
    fi
  done
  if [[ -n "${failed_fans}" ]]; then
    # Fail atomically: hand every fan back to macOS (the same F<i>Md=00 write
    # `normal` uses, while the sudo credential is still cached) so a reported
    # failure never leaves some fans pinned at the requested target behind the
    # caller's back.
    local rollback_status=0
    restore_fans_to_auto "${fan_count}" || rollback_status="$?"
    if (( rollback_status == 0 )); then
      AUTO_RESTORE_ON_EXIT=0
      drop_sudo_credential
      echo "fan-control.sh: WARNING: boost may not have taken effect for fan(s) ${failed_fans}: the SMC did not accept the write(s), so automatic control was restored and verified for all fans" >&2
    else
      echo "fan-control.sh: URGENT: boost failed for fan(s) ${failed_fans}, and automatic fan restoration could not be verified" >&2
    fi
    echo "fan-control.sh: (some machines gate fan writes behind the SMC's global Ftst force key, which this helper deliberately does not write; use a dedicated fan app there)" >&2
    exit 1
  fi
  AUTO_RESTORE_ON_EXIT=0
  drop_sudo_credential
  echo "fan-control.sh: fan boost active; restore automatic control with: ./benchmark.sh --fan-speed-normal" >&2
}

do_normal() {
  local fan_count i
  fan_count="$(read_fan_count)"
  require_fans "${fan_count}"
  explain_sudo
  AUTO_RESTORE_ON_EXIT=1
  AUTO_RESTORE_FAN_COUNT="${fan_count}"
  if restore_fans_to_auto "${fan_count}"; then
    AUTO_RESTORE_ON_EXIT=0
    drop_sudo_credential
    echo "fan-control.sh: fans returned to macOS automatic control; read-back verified" >&2
    return 0
  fi
  echo "fan-control.sh: ERROR: automatic fan control could not be verified" >&2
  return 1
}

do_status() {
  local fan_count manual_fans
  fan_count="$(read_fan_count)"
  if (( fan_count == 0 )); then
    echo "none"
    return 0
  fi
  # Manual if ANY fan's mode bit is set, not just fan 0's: another controller
  # (or a partially-restored boost) can hold any subset of the fans, and a
  # status that only looked at F0Md would report "auto" while other fans are
  # still forced.
  if ! manual_fans="$(list_manual_fans "${fan_count}")"; then
    echo "fan-control.sh: fan mode status is unreadable" >&2
    return 1
  fi
  if [[ -n "${manual_fans}" ]]; then
    echo "manual"
  else
    echo "auto"
  fi
}

command_name="${1:-}"
case "${command_name}" in
  boost|normal|status) ;;
  *) usage ;;
esac

if ! SMC_BIN="$(find_smc)"; then
  cat >&2 <<EOF
fan-control.sh: no 'smc' command-line tool found. Manual fan control needs
fan-control.sh: the SMC CLI. Install smcFanControl
fan-control.sh: (https://github.com/hholtmann/smcFanControl) -- its app bundle
fan-control.sh: includes the 'smc' tool this script auto-detects -- or point
fan-control.sh: MLXFAST_SMC_BIN at an smc binary.
EOF
  exit 2
fi

case "${command_name}" in
  boost) do_boost ;;
  normal) do_normal ;;
  status) do_status ;;
esac
