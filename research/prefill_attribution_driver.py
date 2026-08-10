#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import platform
import random
import select
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


FENCE_PREFIX = "mlxfast: prefill-fence "


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values, quantile):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of no values")
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def summarize(samples_ms, bootstrap_samples, bootstrap_seed):
    median_ms = statistics.median(samples_ms)
    rng = random.Random(bootstrap_seed)
    medians = []
    for _ in range(bootstrap_samples):
        medians.append(statistics.median(rng.choices(samples_ms, k=len(samples_ms))))
    ci_lower_ms = percentile(medians, 0.025)
    ci_upper_ms = percentile(medians, 0.975)
    return {
        "count": len(samples_ms),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "mean_ms": statistics.fmean(samples_ms),
        "median_ms": median_ms,
        "p50_ms": percentile(samples_ms, 0.50),
        "p95_ms": percentile(samples_ms, 0.95),
        "stdev_ms": statistics.stdev(samples_ms) if len(samples_ms) > 1 else 0.0,
        "bootstrap": {
            "iterations": bootstrap_samples,
            "seed": bootstrap_seed,
            "median_95ci_lower_ms": ci_lower_ms,
            "median_95ci_upper_ms": ci_upper_ms,
            "conservative_half_width_ms": max(
                median_ms - ci_lower_ms,
                ci_upper_ms - median_ms,
            ),
        },
    }


def run_text(command, timeout_seconds=30):
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as error:
        return {"command": command, "error": str(error)}


def emit_status(payload, stream=sys.stdout):
    compact = {
        key: payload[key]
        for key in ("status", "label", "finished_at_utc", "statistics", "error_type", "error")
        if key in payload
    }
    print(json.dumps(compact, sort_keys=True), file=stream)


def load_fixture(path, case_index):
    raw = path.read_bytes()
    payload = json.loads(raw)
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture must contain a non-empty cases array")
    if case_index < 0 or case_index >= len(cases):
        raise ValueError(f"fixture case index {case_index} is out of range")
    case = cases[case_index]
    prompt_tokens = case.get("prompt_tokens")
    expected_tokens = case.get("expected_tokens")
    if not isinstance(prompt_tokens, list) or not prompt_tokens:
        raise ValueError("fixture case has no prompt_tokens")
    if not isinstance(expected_tokens, list) or not expected_tokens:
        raise ValueError("fixture case has no expected_tokens")
    if not all(isinstance(token, int) for token in prompt_tokens + expected_tokens):
        raise ValueError("fixture tokens must all be integers")
    prompt_json = json.dumps(prompt_tokens, separators=(",", ":")).encode()
    return {
        "path": str(path.resolve()),
        "sha256": sha256_bytes(raw),
        "case_index": case_index,
        "case_name": case.get("name"),
        "prompt_tokens": prompt_tokens,
        "prompt_token_count": len(prompt_tokens),
        "prompt_tokens_compact_json_sha256": sha256_bytes(prompt_json),
        "expected_token_count": len(expected_tokens),
        "fixture_expected_first_token": expected_tokens[0],
        "prompt_first_16": prompt_tokens[:16],
        "prompt_last_16": prompt_tokens[-16:],
    }


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def parse_fence_records(path):
    records = []
    for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.startswith(FENCE_PREFIX):
            continue
        try:
            record = json.loads(line[len(FENCE_PREFIX) :])
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"invalid prefill fence JSON at {path}:{line_number}: {line!r}"
            ) from error
        record["stderr_line_number"] = line_number
        records.append(record)
    return records


def attach_fence_records(warmups, samples, records, expected_mode):
    requested_count = len(warmups) + len(samples)
    if len(records) < requested_count:
        raise RuntimeError(
            f"found {len(records)} fence records for {requested_count} requested prefills"
        )
    initialization_records = records[:-requested_count]
    request_records = records[-requested_count:]
    expected_census = {
        "site_count": 10,
        "completed_site_count": 10,
        "dispatch_count": 10,
        "query_row_count": 5_120,
        "key_row_count": 5_120,
        "heads_per_group": 1,
    }
    for record in request_records:
        if record.get("mode") != expected_mode:
            raise RuntimeError(
                f"fence mode {record.get('mode')!r} does not match {expected_mode!r}"
            )
        for field, expected in expected_census.items():
            if record.get(field) != expected:
                raise RuntimeError(
                    f"fence {field} {record.get(field)!r} does not match {expected}"
                )
        for field in ("boundary_ns", "measurement_ns"):
            if not isinstance(record.get(field), int) or record[field] < 0:
                raise RuntimeError(f"invalid fence field {field}: {record.get(field)!r}")
    for request, fence in zip([*warmups, *samples], request_records):
        request["fence"] = fence
    return initialization_records


def read_json_line(process, timeout_seconds, description):
    if process.stdout is None:
        raise RuntimeError("worker stdout pipe is unavailable")
    ready, _, _ = select.select([process.stdout], [], [], timeout_seconds)
    if not ready:
        raise TimeoutError(f"timed out waiting for worker {description}")
    line = process.stdout.readline()
    if line == "":
        raise RuntimeError(
            f"worker closed protocol output during {description}; exit={process.poll()}"
        )
    try:
        return json.loads(line)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"worker returned invalid JSON during {description}: {line!r}"
        ) from error


def validate_response(response, request_id, nonce, expected_token):
    if response.get("id") != request_id:
        raise RuntimeError(
            f"worker response id {response.get('id')} does not match {request_id}"
        )
    if response.get("nonce") != nonce:
        raise RuntimeError("worker response nonce changed")
    if response.get("ok") is not True:
        raise RuntimeError(f"worker request failed: {response.get('error', 'unknown error')}")
    if response.get("token") != expected_token:
        raise RuntimeError(
            f"worker token {response.get('token')} does not match expected {expected_token}"
        )


def send_prefill(process, request_id, nonce, prompt_tokens, expected_token, timeout_seconds):
    if process.stdin is None:
        raise RuntimeError("worker stdin pipe is unavailable")
    request = {
        "id": request_id,
        "kind": "prefill",
        "prompt_tokens": prompt_tokens,
    }
    wire = json.dumps(request, separators=(",", ":")) + "\n"
    start_wall_time_ns = time.time_ns()
    start_perf_counter_ns = time.perf_counter_ns()
    process.stdin.write(wire)
    process.stdin.flush()
    response = read_json_line(process, timeout_seconds, f"response {request_id}")
    end_perf_counter_ns = time.perf_counter_ns()
    end_wall_time_ns = time.time_ns()
    validate_response(response, request_id, nonce, expected_token)
    return {
        "request_id": request_id,
        "start_wall_time_ns": start_wall_time_ns,
        "end_wall_time_ns": end_wall_time_ns,
        "start_perf_counter_ns": start_perf_counter_ns,
        "end_perf_counter_ns": end_perf_counter_ns,
        "elapsed_ms": (end_perf_counter_ns - start_perf_counter_ns) / 1_000_000,
        "token": response.get("token"),
    }


def close_worker(process):
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    try:
        return process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=5)


def arm_sample_values(arm, metric):
    if metric == "elapsed_ms":
        return [sample[metric] for sample in arm["samples"]]
    if metric == "boundary_ms":
        return [sample["fence"]["boundary_ns"] / 1_000_000 for sample in arm["samples"]]
    if metric == "measurement_ms":
        return [sample["fence"]["measurement_ns"] / 1_000_000 for sample in arm["samples"]]
    raise ValueError(f"unknown arm metric: {metric}")


def balanced_arm_comparison(
    arms, baseline_mode, candidate_mode, metric, bootstrap_samples, seed
):
    if len(arms) < 8 or len(arms) % 4:
        raise ValueError("matrix comparison requires complete mirrored four-arm blocks")

    block_data = []
    strata = {"ABBA": [], "BAAB": []}
    for block_index in range(len(arms) // 4):
        block = arms[block_index * 4 : block_index * 4 + 4]
        modes = [arm["controls"]["fence_mode"] for arm in block]
        if modes == [baseline_mode, candidate_mode, candidate_mode, baseline_mode]:
            order_name = "ABBA"
        elif modes == [candidate_mode, baseline_mode, baseline_mode, candidate_mode]:
            order_name = "BAAB"
        else:
            raise ValueError(f"invalid mirrored block order: {modes}")
        values = [arm_sample_values(arm, metric) for arm in block]
        medians = [statistics.median(samples) for samples in values]
        baseline_medians = [
            median for median, mode in zip(medians, modes) if mode == baseline_mode
        ]
        candidate_medians = [
            median for median, mode in zip(medians, modes) if mode == candidate_mode
        ]
        baseline_ms = statistics.fmean(baseline_medians)
        candidate_ms = statistics.fmean(candidate_medians)
        block_data.append(
            {
                "block_index": block_index,
                "order_name": order_name,
                "order": modes,
                "values": values,
                "arm_medians_ms": medians,
                "baseline_ms": baseline_ms,
                "candidate_ms": candidate_ms,
                "delta_ms": candidate_ms - baseline_ms,
            }
        )
        strata[order_name].append(block_index)
    if not all(strata.values()):
        raise ValueError("matrix comparison requires both ABBA and BAAB blocks")

    baseline_ms = statistics.fmean(block["baseline_ms"] for block in block_data)
    candidate_ms = statistics.fmean(block["candidate_ms"] for block in block_data)
    delta_ms = statistics.fmean(block["delta_ms"] for block in block_data)

    rng = random.Random(seed)
    deltas_ms = []
    for _ in range(bootstrap_samples):
        resampled_block_deltas = []
        for order_name in ("ABBA", "BAAB"):
            block_indices = strata[order_name]
            for selected_index in rng.choices(block_indices, k=len(block_indices)):
                selected = block_data[selected_index]
                medians = [
                    statistics.median(rng.choices(values, k=len(values)))
                    for values in selected["values"]
                ]
                baseline_medians = [
                    median
                    for median, mode in zip(medians, selected["order"])
                    if mode == baseline_mode
                ]
                candidate_medians = [
                    median
                    for median, mode in zip(medians, selected["order"])
                    if mode == candidate_mode
                ]
                resampled_block_deltas.append(
                    statistics.fmean(candidate_medians)
                    - statistics.fmean(baseline_medians)
                )
        deltas_ms.append(statistics.fmean(resampled_block_deltas))
    ci_lower_ms = percentile(deltas_ms, 0.025)
    ci_upper_ms = percentile(deltas_ms, 0.975)
    return {
        "metric": metric,
        "baseline_mode": baseline_mode,
        "candidate_mode": candidate_mode,
        "baseline_arm_count": sum(
            arm["controls"]["fence_mode"] == baseline_mode for arm in arms
        ),
        "candidate_arm_count": sum(
            arm["controls"]["fence_mode"] == candidate_mode for arm in arms
        ),
        "samples_per_arm": [len(arm_sample_values(arm, metric)) for arm in arms],
        "balanced_baseline_ms": baseline_ms,
        "balanced_candidate_ms": candidate_ms,
        "delta_ms": delta_ms,
        "perturbation_percent": delta_ms / baseline_ms * 100 if baseline_ms else None,
        "blocks": [
            {key: value for key, value in block.items() if key != "values"}
            for block in block_data
        ],
        "bootstrap": {
            "method": "stratified mirrored-block and within-arm request resampling",
            "iterations": bootstrap_samples,
            "seed": seed,
            "delta_95ci_lower_ms": ci_lower_ms,
            "delta_95ci_upper_ms": ci_upper_ms,
            "conservative_half_width_ms": max(
                delta_ms - ci_lower_ms,
                ci_upper_ms - delta_ms,
            ),
        },
    }


def parse_matrix_order(value):
    order = [mode.strip() for mode in value.split(",") if mode.strip()]
    allowed = {"off", "control", "full-qk-h1"}
    if any(mode not in allowed for mode in order):
        raise ValueError(f"matrix order contains unsupported mode: {order}")
    if len(order) < 8 or len(order) % 8 or len(set(order)) != 2:
        raise ValueError("matrix order must contain complete mirrored eight-arm superblocks")
    baseline_mode, candidate_mode = order[:2]
    expected = [
        baseline_mode,
        candidate_mode,
        candidate_mode,
        baseline_mode,
        candidate_mode,
        baseline_mode,
        baseline_mode,
        candidate_mode,
    ]
    for start in range(0, len(order), 8):
        if order[start : start + 8] != expected:
            raise ValueError("matrix order must repeat mirrored A-B-B-A then B-A-A-B")
    return order, baseline_mode, candidate_mode


def matrix_child_command(args, mode, arm_index, output_path):
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        str(args.worker.resolve()),
        "--weights",
        str(args.weights.resolve()),
        "--fixture",
        str(args.fixture.resolve()),
        "--case-index",
        str(args.case_index),
        "--output",
        str(output_path),
        "--label",
        f"{args.label}-arm{arm_index:02d}-{mode}",
        "--warmups",
        str(args.warmups),
        "--repeats",
        str(args.repeats),
        "--expected-prompt-tokens",
        str(args.expected_prompt_tokens),
        "--hello-timeout-seconds",
        str(args.hello_timeout_seconds),
        "--request-timeout-seconds",
        str(args.request_timeout_seconds),
        "--bootstrap-samples",
        str(args.bootstrap_samples),
        "--bootstrap-seed",
        str(args.bootstrap_seed),
        "--fence-mode",
        mode,
    ]
    if args.required_samples is not None:
        command.extend(["--required-samples", str(args.required_samples)])
    if args.expected_token is not None:
        command.extend(["--expected-token", str(args.expected_token)])
    if args.cool_gate is not None:
        command.extend(["--cool-gate", str(args.cool_gate.resolve())])
    return command


def run_matrix(args):
    started_at_utc = utc_now()
    output_path = args.output.resolve()
    fixture = load_fixture(args.fixture, args.case_index)
    base = {
        "schema_version": 2,
        "status": "running",
        "label": args.label,
        "started_at_utc": started_at_utc,
        "command": [sys.executable, *sys.argv],
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
        "git": run_text(["git", "rev-parse", "HEAD"]),
        "fixture": {key: value for key, value in fixture.items() if key != "prompt_tokens"},
        "controls": {
            "warmups_per_arm": args.warmups,
            "repeats_per_arm": args.repeats,
            "bootstrap_samples": args.bootstrap_samples,
            "bootstrap_seed": args.bootstrap_seed,
        },
        "arms": [],
    }
    try:
        if args.inspect_only:
            raise ValueError("inspect-only is not supported with matrix-order")
        if args.worker_stderr is not None:
            raise ValueError("worker-stderr cannot be shared across matrix arms")
        order, baseline_mode, candidate_mode = parse_matrix_order(args.matrix_order)
        base["controls"].update(
            {
                "matrix_order": order,
                "baseline_mode": baseline_mode,
                "candidate_mode": candidate_mode,
                "ordering": "A-B-B-A then B-A-A-B",
                "fresh_worker_per_arm": True,
            }
        )
        arm_directory = output_path.with_name(output_path.stem + "-arms")
        arm_directory.mkdir(parents=True, exist_ok=True)
        arm_timeout_seconds = (
            args.hello_timeout_seconds
            + (args.warmups + args.repeats) * args.request_timeout_seconds
            + 1_200
        )
        for arm_index, mode in enumerate(order):
            arm_output_path = arm_directory / f"{arm_index:02d}-{mode}.json"
            command = matrix_child_command(args, mode, arm_index, arm_output_path)
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=arm_timeout_seconds,
            )
            arm_record = {
                "arm_index": arm_index,
                "mode": mode,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output_path": str(arm_output_path),
            }
            if arm_output_path.is_file():
                arm_record["output_sha256"] = sha256_file(arm_output_path)
                arm_record["result"] = json.loads(arm_output_path.read_text())
            base["arms"].append(arm_record)
            atomic_write_json(output_path, base)
            if result.returncode != 0:
                raise RuntimeError(f"matrix arm {arm_index} failed with status {result.returncode}")

        results = [arm["result"] for arm in base["arms"]]
        worker_hashes = {arm["worker"]["sha256"] for arm in results}
        if len(worker_hashes) != 1:
            raise RuntimeError(f"matrix arms used different worker binaries: {worker_hashes}")
        tokens = {sample["token"] for arm in results for sample in arm["samples"]}
        if len(tokens) != 1:
            raise RuntimeError(f"matrix arms returned different tokens: {tokens}")
        census_fields = (
            "site_count",
            "completed_site_count",
            "dispatch_count",
            "query_row_count",
            "key_row_count",
            "heads_per_group",
        )
        observed_census = {
            field: sorted(
                {
                    sample["fence"][field]
                    for arm in results
                    for sample in arm["samples"]
                }
            )
            for field in census_fields
        }
        inconsistent_census = {
            field: values for field, values in observed_census.items() if len(values) != 1
        }
        if inconsistent_census:
            raise RuntimeError(
                f"matrix arms returned inconsistent dispatch census: {inconsistent_census}"
            )

        metrics = ("elapsed_ms", "boundary_ms", "measurement_ms")
        comparisons = {
            metric: balanced_arm_comparison(
                results,
                baseline_mode,
                candidate_mode,
                metric,
                args.bootstrap_samples,
                args.bootstrap_seed + len(metric),
            )
            for metric in metrics
        }
        mirrored_blocks = [
            {
                "block_index": block_index,
                "order": comparisons["elapsed_ms"]["blocks"][block_index]["order"],
                "metrics": {
                    metric: comparisons[metric]["blocks"][block_index]
                    for metric in metrics
                },
            }
            for block_index in range(len(results) // 4)
        ]
        base.update(
            {
                "status": "succeeded",
                "finished_at_utc": utc_now(),
                "worker_sha256": next(iter(worker_hashes)),
                "observed_tokens": sorted(tokens),
                "observed_census": observed_census,
                "comparisons": comparisons,
                "mirrored_blocks": mirrored_blocks,
                "statistics": comparisons["elapsed_ms"],
            }
        )
        atomic_write_json(output_path, base)
        emit_status(base)
        return 0
    except Exception as error:
        base.update(
            {
                "status": "failed",
                "finished_at_utc": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        atomic_write_json(output_path, base)
        emit_status(base, stream=sys.stderr)
        return 2


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Measure repeated complete Laguna 512-token prefills through one runtime worker."
        )
    )
    parser.add_argument(
        "--worker",
        type=Path,
        default=Path(".build-worker/release/mlxfast-runtime-worker"),
    )
    parser.add_argument("--weights", type=Path, default=Path("weights"))
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("correctness_prompts/public_longcopy_gate_english_512_256.json"),
    )
    parser.add_argument("--case-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-stderr", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=64)
    parser.add_argument("--required-samples", type=int)
    parser.add_argument("--expected-prompt-tokens", type=int, default=512)
    parser.add_argument("--expected-token", type=int)
    parser.add_argument("--hello-timeout-seconds", type=float, default=300)
    parser.add_argument("--request-timeout-seconds", type=float, default=300)
    parser.add_argument("--bootstrap-samples", type=int, default=20_000)
    parser.add_argument("--bootstrap-seed", type=int, default=646)
    parser.add_argument(
        "--fence-mode",
        choices=("off", "control", "full-qk-h1"),
        default="off",
    )
    parser.add_argument(
        "--matrix-order",
        help="comma-separated mirrored order; each arm gets its own worker",
    )
    parser.add_argument("--cool-gate", type=Path)
    parser.add_argument("--inspect-only", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.matrix_order is not None:
        return run_matrix(args)
    started_at_utc = utc_now()
    output_path = args.output.resolve()
    fixture = load_fixture(args.fixture, args.case_index)
    expected_token = (
        args.expected_token
        if args.expected_token is not None
        else fixture["fixture_expected_first_token"]
    )
    required_samples = args.required_samples if args.required_samples is not None else args.repeats
    base = {
        "schema_version": 1,
        "status": "running",
        "label": args.label,
        "started_at_utc": started_at_utc,
        "command": [sys.executable, *sys.argv],
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
        "git": run_text(["git", "rev-parse", "HEAD"]),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "uname": list(platform.uname()),
            "sysctl": run_text(
                ["sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"]
            ),
        },
        "fixture": {key: value for key, value in fixture.items() if key != "prompt_tokens"},
        "controls": {
            "expected_prompt_tokens": args.expected_prompt_tokens,
            "expected_token": expected_token,
            "required_samples": required_samples,
            "warmups": args.warmups,
            "repeats": args.repeats,
            "fence_mode": args.fence_mode,
        },
    }
    try:
        if args.warmups < 0 or args.repeats <= 0:
            raise ValueError("warmups must be non-negative and repeats must be positive")
        if args.bootstrap_samples <= 0:
            raise ValueError("bootstrap-samples must be positive")
        if fixture["prompt_token_count"] != args.expected_prompt_tokens:
            raise ValueError(
                f"prompt token count {fixture['prompt_token_count']} does not match "
                f"expected {args.expected_prompt_tokens}"
            )
        if args.inspect_only:
            base.update({"status": "inspected", "finished_at_utc": utc_now()})
            atomic_write_json(output_path, base)
            emit_status(base)
            return 0

        worker_path = args.worker.resolve()
        weights_path = args.weights.resolve()
        if not worker_path.is_file():
            raise FileNotFoundError(f"worker not found: {worker_path}")
        if not weights_path.is_dir():
            raise FileNotFoundError(f"weights directory not found: {weights_path}")
        stderr_path = (
            args.worker_stderr.resolve()
            if args.worker_stderr is not None
            else output_path.with_suffix(output_path.suffix + ".worker.stderr.log")
        )
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        base["worker"] = {
            "path": str(worker_path),
            "sha256": sha256_file(worker_path),
            "weights_path": str(weights_path),
            "stderr_path": str(stderr_path),
        }
        if args.cool_gate is not None:
            cool_gate = args.cool_gate.resolve()
            cool_result = run_text(
                [str(cool_gate), "--local-cool-gate-only"],
                timeout_seconds=900,
            )
            base["cool_gate"] = cool_result
            if cool_result.get("returncode") != 0:
                raise RuntimeError("cool gate failed")

        worker_environment = os.environ.copy()
        worker_environment["DARKBLOOM_PREFILL_FENCE_MODE"] = args.fence_mode
        with stderr_path.open("w") as worker_stderr:
            process = subprocess.Popen(
                [str(worker_path), "runtime-worker", "--weights", str(weights_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=worker_stderr,
                text=True,
                bufsize=1,
                env=worker_environment,
            )
            base["worker"]["pid"] = process.pid
            try:
                hello = read_json_line(process, args.hello_timeout_seconds, "protocol hello")
                nonce = hello.get("nonce")
                if hello.get("id") != 0 or hello.get("ok") is not True or not nonce:
                    raise RuntimeError(f"invalid worker protocol hello: {hello}")
                warmups = []
                next_request_id = 1
                for warmup_index in range(args.warmups):
                    record = send_prefill(
                        process,
                        next_request_id,
                        nonce,
                        fixture["prompt_tokens"],
                        expected_token,
                        args.request_timeout_seconds,
                    )
                    record["warmup_index"] = warmup_index
                    warmups.append(record)
                    next_request_id += 1
                samples = []
                for sample_index in range(args.repeats):
                    record = send_prefill(
                        process,
                        next_request_id,
                        nonce,
                        fixture["prompt_tokens"],
                        expected_token,
                        args.request_timeout_seconds,
                    )
                    record["sample_index"] = sample_index
                    samples.append(record)
                    next_request_id += 1
            finally:
                worker_returncode = close_worker(process)

        base["worker"]["returncode"] = worker_returncode
        base["worker"]["stderr_sha256"] = sha256_file(stderr_path)
        if worker_returncode != 0:
            raise RuntimeError(f"worker exited with status {worker_returncode}")
        if len(samples) != required_samples:
            raise RuntimeError(
                f"measured sample count {len(samples)} does not match required {required_samples}"
            )
        fence_records = parse_fence_records(stderr_path)
        initialization_fence_records = attach_fence_records(
            warmups,
            samples,
            fence_records,
            args.fence_mode,
        )
        observed_census = {
            field: sorted({sample["fence"][field] for sample in samples})
            for field in (
                "site_count",
                "completed_site_count",
                "dispatch_count",
                "query_row_count",
                "key_row_count",
                "heads_per_group",
            )
        }
        samples_ms = [sample["elapsed_ms"] for sample in samples]
        boundary_ms = [sample["fence"]["boundary_ns"] / 1_000_000 for sample in samples]
        measurement_ms = [
            sample["fence"]["measurement_ns"] / 1_000_000 for sample in samples
        ]
        base.update(
            {
                "status": "succeeded",
                "finished_at_utc": utc_now(),
                "warmup_records": warmups,
                "samples": samples,
                "fence": {
                    "mode": args.fence_mode,
                    "record_count": len(fence_records),
                    "initialization_records": initialization_fence_records,
                    "observed_census": observed_census,
                    "boundary_statistics": summarize(
                        boundary_ms,
                        args.bootstrap_samples,
                        args.bootstrap_seed + 1,
                    ),
                    "measurement_statistics": summarize(
                        measurement_ms,
                        args.bootstrap_samples,
                        args.bootstrap_seed + 2,
                    ),
                },
                "statistics": summarize(
                    samples_ms,
                    args.bootstrap_samples,
                    args.bootstrap_seed,
                ),
            }
        )
        atomic_write_json(output_path, base)
        emit_status(base)
        return 0
    except Exception as error:
        base.update(
            {
                "status": "failed",
                "finished_at_utc": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        atomic_write_json(output_path, base)
        emit_status(base, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
