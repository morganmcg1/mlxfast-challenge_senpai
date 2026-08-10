#!/usr/bin/env python3

import csv
import datetime as dt
import gzip
import hashlib
import inspect
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

BASE_SHA = "3b5e22b9fd8d1860ff1a33de5b200fe017ac96cf"
EXPECTED_BRANCH = "cedar-thorfinn/strict-thermal-window-feasibility"
GATE_TIMEOUT_SECONDS = 900
IDLE_SAMPLES = 600
HOLD_SAMPLES = 60
INTERVAL_MS = 1000
RAW_LIMIT_BYTES = 16 * 1024
CSV_LIMIT_BYTES = 4 * 1024
MODEL_PATTERNS = (
    "mlxfast-runtime-worker",
    "mlxfast-swift benchmark",
    "benchmark.sh --local-cool-gate-only",
    "swift test",
    "swift build",
    "xcrun metal",
    "metal -c",
)
FORBIDDEN_GATE_ENV = (
    "MLXFAST_LOCAL_COOL_GATE",
    "MLXFAST_GPU_TEMP_CMD",
    "MLXFAST_MACMON_BIN",
    "MLXFAST_FAN_CONTROL_HELPER",
    "MLXFAST_FAN_BOOST_PERCENT",
    "MLXFAST_LOCAL_COOL_GATE_READER_TIMEOUT_SECONDS",
)
ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "research/m4-strict-thermal-window-feasibility.csv"
RAW_PATH = ROOT / "research/m4-strict-thermal-window-feasibility-raw.log.gz"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_text(args, timeout=60, env=None):
    completed = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout.strip()


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamp is not UTC")
    return parsed


def sample_values(sample):
    if not isinstance(sample, dict) or not isinstance(sample.get("temp"), dict):
        raise ValueError("sample/temp schema invalid")
    timestamp = sample.get("timestamp")
    cpu = sample["temp"].get("cpu_temp_avg")
    gpu = sample["temp"].get("gpu_temp_avg")
    if isinstance(cpu, bool) or not isinstance(cpu, (int, float)):
        raise ValueError("CPU temperature is not numeric")
    if isinstance(gpu, bool) or not isinstance(gpu, (int, float)):
        raise ValueError("GPU temperature is not numeric")
    if not (5 < cpu <= 120 and 5 < gpu <= 120):
        raise ValueError("temperature outside plausibility bounds")
    return parse_timestamp(timestamp), float(cpu), float(gpu)


def validate_stream(samples, expected, started_at=None, finished_at=None):
    if len(samples) != expected:
        return False, f"expected {expected} samples, got {len(samples)}", []
    values = []
    try:
        for sample in samples:
            values.append(sample_values(sample))
    except (KeyError, TypeError, ValueError) as error:
        return False, str(error), []
    timestamps = [value[0] for value in values]
    if any(later <= earlier for earlier, later in zip(timestamps, timestamps[1:])):
        return False, "timestamps are not strictly increasing", []
    if started_at is not None and timestamps[0].replace(microsecond=0) < started_at.replace(microsecond=0):
        return False, "first timestamp predates observation window", []
    if finished_at is not None and timestamps[-1].replace(microsecond=0) > finished_at.replace(microsecond=0):
        return False, "last timestamp follows observation window", []
    if len({value[2] for value in values}) < 2:
        return False, "GPU telemetry is frozen", []
    return True, "valid", values


def classify_five(samples, started_at, finished_at):
    valid, _, values = validate_stream(samples, 5, started_at, finished_at)
    if not valid:
        return "TELEMETRY_FAIL"
    return "PASS" if values[-1][2] <= 40.0 else "HOT_FAIL"


def synthetic_controls():
    base = dt.datetime(2026, 8, 10, 0, 0, tzinfo=dt.timezone.utc)
    finished = base + dt.timedelta(seconds=4)

    def stream(gpus, offset_seconds=0):
        return [
            {
                "timestamp": (base + dt.timedelta(seconds=offset_seconds + index)).isoformat().replace("+00:00", "Z"),
                "temp": {"cpu_temp_avg": 45.0 + index / 10, "gpu_temp_avg": gpu},
            }
            for index, gpu in enumerate(gpus)
        ]

    observed = {
        "changing_39_9": classify_five(stream([40.4, 40.2, 40.1, 40.0, 39.9]), base, finished),
        "changing_40_1": classify_five(stream([40.5, 40.4, 40.3, 40.2, 40.1]), base, finished),
        "stale": classify_five(stream([39.7, 39.8, 39.9, 39.8, 39.9], -600), base, finished),
    }
    expected = {
        "changing_39_9": "PASS",
        "changing_40_1": "HOT_FAIL",
        "stale": "TELEMETRY_FAIL",
    }
    if observed != expected:
        raise RuntimeError(f"synthetic control mismatch: {observed}")
    return observed


def classifier_sha256():
    source = inspect.getsource(parse_timestamp) + inspect.getsource(sample_values)
    source += inspect.getsource(validate_stream) + inspect.getsource(classify_five)
    return hashlib.sha256(source.encode()).hexdigest()


def find_macmon():
    candidates = [shutil.which("macmon"), Path("/opt/homebrew/bin/macmon"), Path("/usr/local/bin/macmon"), Path.home() / "bin/macmon"]
    for candidate in candidates:
        if candidate and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError("macmon is unavailable")


def parse_json_lines(text):
    samples = []
    for line in text.splitlines():
        if line.strip():
            samples.append(json.loads(line))
    return samples


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def fan_status():
    status, output = run_text(["tools/fan-control.sh", "status"], timeout=10)
    if status != 0:
        return "unreadable"
    return output.splitlines()[-1].strip() if output else "unreadable"


def process_matches(output, ignore_pids=()):
    records = []
    for line in output.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) < 4:
            continue
        try:
            pid = int(fields[0])
            ppid = int(fields[1])
        except ValueError:
            continue
        records.append((pid, ppid, line.strip()))

    ignored = {os.getpid(), *ignore_pids}
    while True:
        descendants = {pid for pid, ppid, _ in records if ppid in ignored}
        expanded = ignored | descendants
        if expanded == ignored:
            break
        ignored = expanded

    return [
        line
        for pid, _, line in records
        if pid not in ignored and any(pattern.lower() in line.lower() for pattern in MODEL_PATTERNS)
    ]


def matching_processes(ignore_pids=()):
    status, output = run_text(["ps", "-axo", "pid=,ppid=,comm=,args="], timeout=10)
    if status != 0:
        return ["process inventory failed"]
    return process_matches(output, ignore_pids)


def clean_identity():
    _, head = run_text(["git", "rev-parse", "HEAD"])
    _, branch = run_text(["git", "branch", "--show-current"])
    _, status = run_text(["git", "status", "--porcelain", "--untracked-files=all"])
    ancestor, _ = run_text(["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"])
    return {
        "head": head,
        "branch": branch,
        "clean": status == "",
        "status": status,
        "base_is_ancestor": ancestor == 0,
    }


def host_record(macmon):
    def capture(args):
        status, output = run_text(args, timeout=60)
        return {"status": status, "output": output}

    return {
        "recorded_utc": utc_now(),
        "uname": capture(["uname", "-a"]),
        "model": capture(["sysctl", "-n", "hw.model"]),
        "chip": capture(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "memory_bytes": capture(["sysctl", "-n", "hw.memsize"]),
        "os": capture(["sw_vers"]),
        "xcode": capture(["xcodebuild", "-version"]),
        "swift": capture(["swift", "--version"]),
        "display": capture(["system_profiler", "SPDisplaysDataType", "-json"]),
        "macmon_path": macmon,
        "macmon_version": capture([macmon, "--version"]),
        "gpu_contract_mapping": "M4 Pro -> applegpu_g16s / generation 16; gate-only mode selects no model kernel",
        "ambient_sensor": "not exposed by the gate macmon schema; recorded as N/A",
    }


def project_samples(raw_lines, attempt, phase, samples):
    for index, sample in enumerate(samples):
        if phase == "idle" and index % 5 and index != len(samples) - 1:
            continue
        timestamp, cpu, gpu = sample_values(sample)
        raw_lines.append(f"{attempt},{phase},{timestamp.isoformat().replace('+00:00', 'Z')},{cpu:.3f},{gpu:.3f}")


def stream_stats(values):
    cpus = [value[1] for value in values]
    gpus = [value[2] for value in values]
    return {
        "start": values[0][0].isoformat().replace("+00:00", "Z"),
        "end": values[-1][0].isoformat().replace("+00:00", "Z"),
        "cpu_min": min(cpus),
        "cpu_max": max(cpus),
        "gpu_min": min(gpus),
        "gpu_max": max(gpus),
        "gpu_final": gpus[-1],
    }


def collect_fixed_stream(macmon, samples, timeout):
    command = [macmon, "pipe", "--samples", str(samples), "--interval", str(INTERVAL_MS)]
    observation_started = dt.datetime.now(dt.timezone.utc)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    elapsed = time.monotonic() - started
    observation_finished = dt.datetime.now(dt.timezone.utc)
    parsed = parse_json_lines(completed.stdout)
    valid, reason, values = validate_stream(parsed, samples, observation_started, observation_finished)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stderr": completed.stderr,
        "stdout_sha256": sha256_text(completed.stdout),
        "elapsed_seconds": elapsed,
        "samples": parsed,
        "valid": completed.returncode == 0 and valid,
        "reason": reason if completed.returncode == 0 else f"macmon exit {completed.returncode}: {completed.stderr.strip()}",
        "values": values,
    }


def terminate_group(process, grace=10):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def monitor_gate(stop_event, records, ignore_pids):
    while not stop_event.is_set():
        records.append({
            "utc": utc_now(),
            "fan": fan_status(),
            "processes": matching_processes(ignore_pids),
        })
        stop_event.wait(5)


def classify_gate(exit_code, timed_out, log, audit_valid, audit_values):
    telemetry_markers = (
        "strict local thermal telemetry",
        "GPU temperature reader timed out",
        "requires a working macmon reader",
        "telemetry reader process group",
    )
    hot_markers = (
        "GPU is hot and not cooling down",
        "GPU did not reach 40C within",
    )
    if not audit_valid:
        return "TELEMETRY_FAIL", "parallel strict audit stream invalid"
    if exit_code == 0:
        if "strict persistent macmon confirmed" in log and "GPU cool-down gate passed" in log:
            return "PASS", "authoritative strict gate passed"
        return "INCONCLUSIVE", "exit 0 lacked strict confirmation/pass markers"
    if any(marker in log for marker in telemetry_markers):
        return "TELEMETRY_FAIL", "authoritative gate reported strict telemetry failure"
    if any(marker in log for marker in hot_markers):
        return "HOT_FAIL", "authoritative gate reported bounded hot failure"
    if timed_out and audit_values and min(value[2] for value in audit_values) > 40.0:
        return "HOT_FAIL", "900-second outer bound reached with valid GPU telemetry continuously above 40 C"
    return "INCONCLUSIVE", f"unexpected gate exit {exit_code}"


def run_gate(macmon, attempt, temp_dir):
    gate_log_path = temp_dir / f"attempt-{attempt}-gate.log"
    audit_stdout_path = temp_dir / f"attempt-{attempt}-gate-audit.jsonl"
    audit_stderr_path = temp_dir / f"attempt-{attempt}-gate-audit.stderr"
    gate_env = os.environ.copy()
    gate_env["MLXFAST_LOCAL_FAN_PROMPT"] = "0"
    gate_env["MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY"] = "1"

    with audit_stdout_path.open("w") as audit_stdout, audit_stderr_path.open("w") as audit_stderr:
        audit_observation_started = dt.datetime.now(dt.timezone.utc)
        audit_process = subprocess.Popen(
            [macmon, "pipe", "--samples", "900", "--interval", str(INTERVAL_MS)],
            cwd=ROOT,
            text=True,
            stdout=audit_stdout,
            stderr=audit_stderr,
            start_new_session=True,
        )
        monitor_records = []
        stop_event = threading.Event()
        started_utc = utc_now()
        started = time.monotonic()
        timed_out = False
        with gate_log_path.open("w") as gate_log:
            gate_process = subprocess.Popen(
                ["./benchmark.sh", "--local-cool-gate-only"],
                cwd=ROOT,
                env=gate_env,
                text=True,
                stdout=gate_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            monitor = threading.Thread(
                target=monitor_gate,
                args=(stop_event, monitor_records, {gate_process.pid}),
                daemon=True,
            )
            monitor.start()
            try:
                gate_process.wait(timeout=GATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate_group(gate_process)
        elapsed = time.monotonic() - started
        stop_event.set()
        monitor.join(timeout=10)
        terminate_group(audit_process)
        audit_observation_finished = dt.datetime.now(dt.timezone.utc)
        ended_utc = utc_now()

    gate_log = gate_log_path.read_text(errors="replace")
    audit_text = audit_stdout_path.read_text(errors="replace")
    try:
        audit_samples = parse_json_lines(audit_text)
        audit_valid, audit_reason, audit_values = validate_stream(
            audit_samples,
            len(audit_samples),
            audit_observation_started,
            audit_observation_finished,
        )
        if len(audit_samples) < 2:
            audit_valid = False
            audit_reason = "fewer than two parallel audit samples"
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        audit_samples = []
        audit_values = []
        audit_valid = False
        audit_reason = str(error)
    classification, reason = classify_gate(
        gate_process.returncode,
        timed_out,
        gate_log,
        audit_valid,
        audit_values,
    )
    fan_states = [record["fan"] for record in monitor_records]
    process_hits = [process for record in monitor_records for process in record["processes"]]
    return {
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "elapsed_seconds": elapsed,
        "exit_code": gate_process.returncode,
        "timed_out": timed_out,
        "log": gate_log,
        "log_sha256": sha256_text(gate_log),
        "audit_text_sha256": sha256_text(audit_text),
        "audit_samples": audit_samples,
        "audit_values": audit_values,
        "audit_valid": audit_valid,
        "audit_reason": audit_reason,
        "fan_states": fan_states,
        "process_hits": process_hits,
        "classification": classification,
        "reason": reason,
    }


def authoritative_final(log):
    matches = re.findall(r"strict persistent macmon confirmed[^\n]*final=([0-9]+(?:\.[0-9]+)?)C", log)
    if matches:
        return float(matches[-1])
    matches = re.findall(r"current ([0-9]+(?:\.[0-9]+)?)C", log)
    return float(matches[-1]) if matches else None


def write_artifacts(rows, raw_lines):
    raw_text = "attempt,phase,timestamp_utc,cpu_temp_c,gpu_temp_c\n" + "\n".join(raw_lines) + "\n"
    with RAW_PATH.open("wb") as raw_file:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_file, compresslevel=9, mtime=0) as compressed:
            compressed.write(raw_text.encode())
    raw_size = RAW_PATH.stat().st_size
    if raw_size > RAW_LIMIT_BYTES:
        raise RuntimeError(f"compressed raw artifact is {raw_size} bytes, exceeds {RAW_LIMIT_BYTES}")
    raw_sha = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()

    fieldnames = [
        "attempt", "idle_start_utc", "idle_end_utc", "idle_samples", "idle_wall_seconds",
        "idle_cpu_min_c", "idle_cpu_max_c", "idle_gpu_min_c", "idle_gpu_max_c", "idle_gpu_final_c",
        "idle_raw_sha256", "fan_before", "fan_during", "fan_after", "process_clear",
        "gate_start_utc", "gate_end_utc", "gate_wall_seconds", "gate_exit_code", "gate_class",
        "gate_reason", "gate_audit_samples", "gate_gpu_min_c", "gate_gpu_max_c", "gate_gpu_final_c",
        "gate_authoritative_final_c", "gate_log_sha256", "gate_audit_sha256", "hold_samples",
        "hold_gpu_min_c", "hold_gpu_max_c", "hold_all_le_40", "hold_raw_sha256", "decision",
        "stop_reason", "raw_artifact_sha256",
    ]
    with CSV_PATH.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["raw_artifact_sha256"] = raw_sha
            writer.writerow(row)
    csv_size = CSV_PATH.stat().st_size
    if csv_size > CSV_LIMIT_BYTES:
        raise RuntimeError(f"CSV artifact is {csv_size} bytes, exceeds {CSV_LIMIT_BYTES}")
    return {
        "raw_path": str(RAW_PATH.relative_to(ROOT)),
        "raw_bytes": raw_size,
        "raw_sha256": raw_sha,
        "csv_path": str(CSV_PATH.relative_to(ROOT)),
        "csv_bytes": csv_size,
        "csv_sha256": hashlib.sha256(CSV_PATH.read_bytes()).hexdigest(),
    }


def main():
    controls = synthetic_controls()
    control_record = {
        "controls": controls,
        "classifier_sha256": classifier_sha256(),
        "controls_utc": utc_now(),
    }
    print(json.dumps({"synthetic_controls": control_record}, sort_keys=True), flush=True)
    if len(sys.argv) == 2 and sys.argv[1] == "--controls-only":
        return 0
    resume_after_a1 = len(sys.argv) == 2 and sys.argv[1] == "--resume-after-a1-monitor-fix"
    if len(sys.argv) != 1 and not resume_after_a1:
        raise RuntimeError(
            "usage: run_m4_strict_thermal_window_feasibility.py "
            "[--controls-only|--resume-after-a1-monitor-fix]"
        )

    for name in FORBIDDEN_GATE_ENV:
        if name in os.environ:
            raise RuntimeError(f"forbidden inherited gate override is set: {name}")
    identity = clean_identity()
    if identity["branch"] != EXPECTED_BRANCH or not identity["clean"] or not identity["base_is_ancestor"]:
        raise RuntimeError(f"tree/input identity invalid: {identity}")
    macmon = find_macmon()
    initial_fan = fan_status()
    initial_processes = matching_processes()
    if initial_fan != "auto":
        raise RuntimeError(f"initial fan state is {initial_fan}, expected auto")
    if initial_processes:
        raise RuntimeError(f"initial competing process detected: {initial_processes}")
    host = host_record(macmon)
    print(json.dumps({"identity": identity, "host": host, "initial_fan": initial_fan}, sort_keys=True), flush=True)

    prior_attempts = 1 if resume_after_a1 else 0
    start_attempt = 2 if resume_after_a1 else 1
    rows = []
    raw_lines = []
    passes = 0
    consecutive_hot = 0
    decision = "INCONCLUSIVE"
    stop_reason = "protocol did not reach a terminal decision"
    protocol_started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="m4-strict-thermal-window-") as temporary:
        temp_dir = Path(temporary)
        for attempt in range(start_attempt, 4):
            if time.monotonic() - protocol_started >= 6000:
                stop_reason = "100-minute total assignment wall budget reached"
                break
            identity_now = clean_identity()
            fan_before = fan_status()
            processes_before = matching_processes()
            if identity_now != identity or fan_before != "auto" or processes_before:
                stop_reason = f"pre-attempt operational drift: identity={identity_now}, fan={fan_before}, processes={processes_before}"
                break

            idle = collect_fixed_stream(macmon, IDLE_SAMPLES, timeout=660)
            if idle["samples"]:
                try:
                    project_samples(raw_lines, attempt, "idle", idle["samples"])
                except (KeyError, TypeError, ValueError):
                    pass
            if not idle["valid"]:
                stop_reason = f"attempt {attempt} idle telemetry invalid: {idle['reason']}"
                break
            idle_stats = stream_stats(idle["values"])
            fan_after_idle = fan_status()
            processes_after_idle = matching_processes()
            identity_after_idle = clean_identity()
            if fan_after_idle != "auto" or processes_after_idle or identity_after_idle != identity:
                stop_reason = f"attempt {attempt} pre-gate drift: fan={fan_after_idle}, processes={processes_after_idle}, identity={identity_after_idle}"
                break

            gate = run_gate(macmon, attempt, temp_dir)
            raw_lines.append(f"# attempt {attempt} complete authoritative gate log follows")
            raw_lines.extend(f"# {line}" for line in gate["log"].splitlines())
            if gate["audit_samples"]:
                try:
                    project_samples(raw_lines, attempt, "gate", gate["audit_samples"])
                except (KeyError, TypeError, ValueError):
                    pass
            fan_after = fan_status()
            process_after = matching_processes()
            process_hits = gate["process_hits"] + process_after
            fan_states = [fan_before, fan_after_idle] + gate["fan_states"] + [fan_after]
            gate_class = gate["classification"]
            gate_reason = gate["reason"]
            if any(state != "auto" for state in fan_states):
                gate_class = "INCONCLUSIVE"
                gate_reason = f"fan state was not continuously auto: {fan_states}"
            if process_hits:
                gate_class = "INCONCLUSIVE"
                gate_reason = f"competing/model process observed: {process_hits}"
            if clean_identity() != identity:
                gate_class = "INCONCLUSIVE"
                gate_reason = "tree/input identity drifted during gate"

            hold = None
            hold_all = None
            if gate_class == "PASS":
                hold = collect_fixed_stream(macmon, HOLD_SAMPLES, timeout=90)
                if hold["samples"]:
                    try:
                        project_samples(raw_lines, attempt, "hold", hold["samples"])
                    except (KeyError, TypeError, ValueError):
                        pass
                hold_fan = fan_status()
                hold_processes = matching_processes()
                if not hold["valid"] or hold_fan != "auto" or hold_processes or clean_identity() != identity:
                    gate_class = "INCONCLUSIVE"
                    gate_reason = f"post-pass hold operational failure: valid={hold['valid']}, reason={hold['reason']}, fan={hold_fan}, processes={hold_processes}"
                else:
                    hold_all = all(value[2] <= 40.0 for value in hold["values"])
                    if not hold_all:
                        gate_class = "HOLD_FAIL"
                        gate_reason = "a 60-second post-pass hold sample exceeded 40 C"

            gate_values = gate["audit_values"]
            gate_stats = stream_stats(gate_values) if gate_values else None
            hold_stats = stream_stats(hold["values"]) if hold and hold["valid"] else None
            row = {
                "attempt": attempt,
                "idle_start_utc": idle_stats["start"],
                "idle_end_utc": idle_stats["end"],
                "idle_samples": len(idle["samples"]),
                "idle_wall_seconds": f"{idle['elapsed_seconds']:.3f}",
                "idle_cpu_min_c": f"{idle_stats['cpu_min']:.3f}",
                "idle_cpu_max_c": f"{idle_stats['cpu_max']:.3f}",
                "idle_gpu_min_c": f"{idle_stats['gpu_min']:.3f}",
                "idle_gpu_max_c": f"{idle_stats['gpu_max']:.3f}",
                "idle_gpu_final_c": f"{idle_stats['gpu_final']:.3f}",
                "idle_raw_sha256": idle["stdout_sha256"],
                "fan_before": fan_before,
                "fan_during": "auto" if gate["fan_states"] and all(state == "auto" for state in gate["fan_states"]) else "/".join(sorted(set(gate["fan_states"]))) or "unreadable",
                "fan_after": fan_after,
                "process_clear": not process_hits,
                "gate_start_utc": gate["started_utc"],
                "gate_end_utc": gate["ended_utc"],
                "gate_wall_seconds": f"{gate['elapsed_seconds']:.3f}",
                "gate_exit_code": gate["exit_code"],
                "gate_class": gate_class,
                "gate_reason": gate_reason,
                "gate_audit_samples": len(gate["audit_samples"]),
                "gate_gpu_min_c": f"{gate_stats['gpu_min']:.3f}" if gate_stats else "NA",
                "gate_gpu_max_c": f"{gate_stats['gpu_max']:.3f}" if gate_stats else "NA",
                "gate_gpu_final_c": f"{gate_stats['gpu_final']:.3f}" if gate_stats else "NA",
                "gate_authoritative_final_c": authoritative_final(gate["log"]) if gate["log"] else "NA",
                "gate_log_sha256": gate["log_sha256"],
                "gate_audit_sha256": gate["audit_text_sha256"],
                "hold_samples": len(hold["samples"]) if hold else 0,
                "hold_gpu_min_c": f"{hold_stats['gpu_min']:.3f}" if hold_stats else "NA",
                "hold_gpu_max_c": f"{hold_stats['gpu_max']:.3f}" if hold_stats else "NA",
                "hold_all_le_40": hold_all if hold_all is not None else "NA",
                "hold_raw_sha256": hold["stdout_sha256"] if hold else "NA",
            }
            rows.append(row)
            print(json.dumps({"attempt": row}, sort_keys=True), flush=True)

            if gate_class == "PASS":
                passes += 1
                consecutive_hot = 0
            elif gate_class == "HOT_FAIL":
                consecutive_hot += 1
                if consecutive_hot >= 2:
                    decision = "NO-GO"
                    stop_reason = "two consecutive valid bounded hot failures"
                    break
            elif gate_class == "HOLD_FAIL":
                decision = "NO-GO"
                stop_reason = "a passing gate could not sustain the 60-second <=40 C hold"
                break
            else:
                decision = "INCONCLUSIVE"
                stop_reason = gate_reason
                break

        total_attempts = prior_attempts + len(rows)
        if decision == "INCONCLUSIVE" and total_attempts == 3:
            decision = "GO" if passes >= 2 else "NO-GO"
            stop_reason = f"completed three attempts with {passes} qualifying passes"
        elif decision == "INCONCLUSIVE" and consecutive_hot >= 2:
            decision = "NO-GO"
            stop_reason = "two consecutive valid bounded hot failures"

    for row in rows:
        row["decision"] = decision
        row["stop_reason"] = stop_reason
    artifacts = write_artifacts(rows, raw_lines)
    final = {
        "decision": decision,
        "stop_reason": stop_reason,
        "passes": passes,
        "attempts": prior_attempts + len(rows),
        "prior_attempts": prior_attempts,
        "rows_recorded": len(rows),
        "consecutive_hot": consecutive_hot,
        "protocol_wall_seconds": time.monotonic() - protocol_started,
        "identity": identity,
        "host": host,
        "synthetic_controls": control_record,
        "artifacts": artifacts,
        "fan_final": fan_status(),
        "processes_final": matching_processes(),
        "wandb": "N/A",
        "model_or_benchmark_run": False,
    }
    print(json.dumps({"terminal_summary": final}, sort_keys=True), flush=True)
    return 0 if decision in ("GO", "NO-GO") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"fatal": str(error), "utc": utc_now()}, sort_keys=True), flush=True)
        raise
