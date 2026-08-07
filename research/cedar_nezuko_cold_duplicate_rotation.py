#!/usr/bin/env python3

import argparse
import csv
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

MARKER = "DARKBLOOM_COLD_DUPLICATE"
DIGEST_MARKER = "DARKBLOOM_COLD_DUPLICATE_DIGEST"
FAULT_MARKER = "DARKBLOOM_COLD_DUPLICATE_FAULT"
STORAGE_MARKER = "DARKBLOOM_COLD_DUPLICATE_STORAGE"
SPARSE_LAYER_COUNT = 39
EXPERT_BYTES_PER_SELECTED_ROW = 1_179_648
SELECTED_EXPERTS_PER_LAYER = 8
TRAFFIC_BYTES_PER_DUPLICATE = (
    EXPERT_BYTES_PER_SELECTED_ROW * SELECTED_EXPERTS_PER_LAYER * SPARSE_LAYER_COUNT
)
EXPECTED_STORAGE_PROOF = {
    "layers": str(SPARSE_LAYER_COUNT),
    "experts": "256",
    "weight_row_bytes": "1048576",
    "packed_scale_row_bytes": "131072",
    "expert_row_bytes": str(EXPERT_BYTES_PER_SELECTED_ROW),
    "contiguous": "1",
    "bank_ranges_nonoverlap": "1",
    "expert_rows_nonoverlap": "1",
    "eager_eval": "1",
    "full_bank_pretouch": "1",
}
COMMAND_GRAPH_PROOF = {
    "measurement_activation": (
        "model-observed on the first runtime 512-token seed after constructor warmup decode"
    ),
    "kernel_routine": "lagunaRoutedSwiGLUQMVPackedTop8",
    "mode_dependent_control": {
        "warm_selected_experts": "(indices + 256) % 256",
        "cold_selected_experts": "(indices + 8) % 256",
        "only_difference": "addend selecting expert row addresses",
    },
    "k0_control": (
        "host sparse-layer reachability accounting only; no rotated tensor, duplicate root, "
        "asyncEval, retained MLX root, or blocking probe eval"
    ),
    "duplicate_root_construction_order": "slot 0 through K-1",
    "per_sparse_layer_async_eval_roots": "[indices, duplicate[0...K-1], ordinary]",
    "evaluator_dispatch_order": "ordinary, duplicate[K-1...0], indices dependencies",
    "scratch_root_retention_order": "layer-major, slot 0 through K-1",
    "final_blocking_eval_roots": (
        "[fullHidden, indices layer-major, duplicates layer-major slot-ascending]"
    ),
    "synchronization": (
        "for K=1,2,3,5: one asyncEval per sparse layer and one blocking eval after layer 39"
    ),
    "k_values": [1, 2, 3, 5],
    "warm_cold_command_graph_identical": True,
}
PRETOUCH_PROTOCOL = (
    "Blocking eval of every fused array, then a page-stride CPU read across each complete "
    "256-expert routed weight bank and packed-scale bank in all 39 sparse layers before "
    "constructor warmup. Measurement activates on the first runtime seed after constructor "
    "warmup; the first 16 identical forced-token steps of every arm are discarded before "
    "retained timing."
)
STORAGE_INDEPENDENCE_SCOPE = (
    "All 78 complete routed-bank virtual backing ranges are pairwise non-overlapping; each "
    "bank is expert-first contiguous, making distinct expert rows virtually disjoint. Dynamic "
    "warm/cold top-8 row overlap is recorded for every sparse layer and decode step. This "
    "proves virtual-range separation only."
)
RESIDUAL_CONFOUND = (
    "Cache-set mapping and physical page placement remain uncontrolled; DRAM traffic and "
    "cache residency are not directly measured."
)
MATRIX_BLOCK_ORDERS = [
    "block 1: warm/cold interleaved K=1,2,3,5",
    "block 2: exact reverse of block 1",
    "block 3: repeat block 1",
]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def system_metadata():
    def command_output(argv):
        try:
            return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "mac_model": command_output(["sysctl", "-n", "hw.model"]),
        "memory_bytes": command_output(["sysctl", "-n", "hw.memsize"]),
        "logical_cpu_count": command_output(["sysctl", "-n", "hw.logicalcpu"]),
        "git_head": command_output(["git", "rev-parse", "HEAD"]),
        "python": sys.version,
    }


def worker_environment(schedule, steps_per_arm, digest=False, fault=False):
    exact = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TMPDIR",
        "USER",
    }
    prefixes = ("DARKBLOOM_", "MLX_", "MLXFAST_", "METAL_")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in exact or key.startswith(prefixes)
    }
    for key in list(environment):
        if key.startswith("DARKBLOOM_COLD_DUPLICATE_"):
            del environment[key]
    environment["DARKBLOOM_COLD_DUPLICATE_SCHEDULE"] = schedule
    environment["DARKBLOOM_COLD_DUPLICATE_STEPS_PER_ARM"] = str(steps_per_arm)
    if digest:
        environment["DARKBLOOM_COLD_DUPLICATE_DIGEST"] = "1"
    if fault:
        environment["DARKBLOOM_COLD_DUPLICATE_FAULT"] = "1"
    return environment


class WorkerSession:
    def __init__(
        self,
        worker,
        weights,
        schedule,
        steps_per_arm,
        measurement_path=None,
        digest=False,
        fault=False,
    ):
        self.measurements = []
        self.digests = []
        self.faults = []
        self.storage_proofs = []
        self.diagnostics = []
        self._measurement_file = None
        self._measurement_writer = None
        if measurement_path:
            measurement_path = Path(measurement_path)
            measurement_path.parent.mkdir(parents=True, exist_ok=True)
            self._measurement_file = measurement_path.open("w", newline="")
            self._measurement_writer = csv.DictWriter(
                self._measurement_file,
                fieldnames=[
                    "label",
                    "mode",
                    "duplicate_count",
                    "step",
                    "elapsed_ns",
                    "dispatch_count",
                    "logical_cache_delta_min",
                    "logical_cache_delta_max",
                    "physical_cache_delta_min",
                    "physical_cache_delta_max",
                    "pending_root_count",
                    "top8_rotated_overlap_by_layer",
                ],
                delimiter="\t",
            )
            self._measurement_writer.writeheader()
        environment = worker_environment(
            schedule=schedule,
            steps_per_arm=steps_per_arm,
            digest=digest,
            fault=fault,
        )
        self.process = subprocess.Popen(
            [str(worker), "runtime-worker", "--weights", str(weights)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()
        hello_line = self.process.stdout.readline()
        if not hello_line:
            self._raise_worker_failure("worker exited before hello")
        self.hello = json.loads(hello_line)
        self.session_nonce = self.hello.get("nonce")
        if (
            self.hello.get("id") != 0
            or not self.hello.get("ok")
            or not isinstance(self.session_nonce, str)
            or not self.session_nonce
        ):
            raise RuntimeError(f"worker returned invalid protocol hello: {self.hello}")
        self._next_id = 1

    def _read_stderr(self):
        for encoded in self.process.stderr:
            line = encoded.rstrip("\n")
            try:
                self._parse_marker(line)
            except Exception as error:
                self.diagnostics.append(f"marker parse failure: {error}: {line[:500]}")
            else:
                markers = (
                    MARKER + "\t",
                    DIGEST_MARKER + "\t",
                    FAULT_MARKER + "\t",
                    STORAGE_MARKER + "\t",
                )
                if not line.startswith(markers):
                    if len(self.diagnostics) < 200:
                        self.diagnostics.append(line)

    def _parse_marker(self, line):
        fields = line.split("\t")
        if fields[0] == MARKER and len(fields) == 13:
            row = {
                "label": fields[1],
                "mode": fields[2],
                "duplicate_count": int(fields[3]),
                "step": int(fields[4]),
                "elapsed_ns": int(fields[5]),
                "dispatch_count": int(fields[6]),
                "logical_cache_delta_min": int(fields[7]),
                "logical_cache_delta_max": int(fields[8]),
                "physical_cache_delta_min": int(fields[9]),
                "physical_cache_delta_max": int(fields[10]),
                "pending_root_count": int(fields[11]),
                "top8_rotated_overlap_by_layer": fields[12],
            }
            self.measurements.append(row)
            if self._measurement_writer:
                self._measurement_writer.writerow(row)
                if len(self.measurements) % 100 == 0:
                    self._measurement_file.flush()
        elif fields[0] == DIGEST_MARKER and len(fields) == 9:
            self.digests.append(
                {
                    "label": fields[1],
                    "mode": fields[2],
                    "duplicate_count": int(fields[3]),
                    "step": int(fields[4]),
                    "shape": fields[5],
                    "dtype": fields[6],
                    "byte_count": int(fields[7]),
                    "fnv1a64": fields[8],
                }
            )
        elif fields[0] == FAULT_MARKER and len(fields) == 6:
            self.faults.append(
                {
                    "label": fields[1],
                    "mode": fields[2],
                    "duplicate_count": int(fields[3]),
                    "step": int(fields[4]),
                    "proof": fields[5],
                }
            )
        elif fields[0] == STORAGE_MARKER:
            proof = {}
            for field in fields[1:]:
                key, separator, value = field.partition("=")
                if separator != "=" or not key or key in proof:
                    raise ValueError(f"invalid storage proof field: {field}")
                proof[key] = value
            self.storage_proofs.append(proof)

    def _raise_worker_failure(self, message):
        return_code = self.process.poll()
        if return_code is None:
            try:
                return_code = self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return_code = None
        self._stderr_thread.join(timeout=5)
        tail = "\n".join(self.diagnostics[-20:])
        raise RuntimeError(f"{message}; return_code={return_code}; stderr_tail={tail}")

    def request(self, kind, **payload):
        if self.process.poll() is not None:
            self._raise_worker_failure(f"worker unavailable before {kind}")
        request_id = self._next_id
        self._next_id += 1
        message = {"id": request_id, "kind": kind, **payload}
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            self._raise_worker_failure(f"worker exited during {kind}")
        response = json.loads(response_line)
        if response.get("id") != request_id:
            raise RuntimeError(
                f"response id mismatch for {kind}: expected {request_id}, got {response.get('id')}"
            )
        if response.get("nonce") != self.session_nonce:
            raise RuntimeError(f"response nonce mismatch for {kind}")
        if not response.get("ok") or response.get("error"):
            raise RuntimeError(f"worker returned error for {kind}: {response.get('error')}")
        return response

    def finish(self, expect_success=True):
        if self.process.stdin and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            return_code = self.process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                return_code = self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                return_code = self.process.wait(timeout=15)
        self._stderr_thread.join(timeout=30)
        if self._measurement_file:
            self._measurement_file.flush()
            self._measurement_file.close()
        if expect_success and return_code != 0:
            self._raise_worker_failure("worker returned nonzero status")
        if not expect_success and return_code == 0:
            raise RuntimeError("fault-injection worker unexpectedly returned zero status")
        return return_code

    def abort(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)
        self._stderr_thread.join(timeout=30)
        if self._measurement_file and not self._measurement_file.closed:
            self._measurement_file.close()


def load_fixture(path, needed_steps):
    fixture = json.loads(Path(path).read_text())
    cases = fixture.get("cases")
    if not cases:
        raise ValueError("fixture does not contain cases")
    case = cases[0]
    seed = [int(token) for token in case["prompt_tokens"]]
    expected = [int(token) for token in case["expected_tokens"]]
    if len(seed) != 512:
        raise ValueError(f"expected a 512-token seed, got {len(seed)}")
    source = expected + seed
    forced = []
    while len(forced) < needed_steps:
        forced.extend(source)
    return seed, forced[:needed_steps], case.get("name", "case-0")


def validate_measurements(rows, arms, steps_per_arm):
    expected_by_label = {arm["label"]: arm for arm in arms}
    if len(rows) != len(arms) * steps_per_arm:
        raise RuntimeError(
            f"expected {len(arms) * steps_per_arm} markers, observed {len(rows)}"
        )
    by_label = {label: [] for label in expected_by_label}
    for row in rows:
        if row["label"] not in by_label:
            raise RuntimeError(f"unexpected marker label {row['label']}")
        by_label[row["label"]].append(row)
        arm = expected_by_label[row["label"]]
        if row["mode"] != arm["mode"] or row["duplicate_count"] != arm["k"]:
            raise RuntimeError(f"marker arm mismatch: {row}")
        if row["dispatch_count"] != SPARSE_LAYER_COUNT * arm["k"]:
            raise RuntimeError(f"dispatch count mismatch: {row}")
        if row["logical_cache_delta_min"] != 1 or row["logical_cache_delta_max"] != 1:
            raise RuntimeError(f"logical cache advancement mismatch: {row}")
        if row["physical_cache_delta_min"] != 1 or row["physical_cache_delta_max"] != 1:
            raise RuntimeError(f"physical cache advancement mismatch: {row}")
        if row["pending_root_count"] != 0:
            raise RuntimeError(f"pending roots survived request: {row}")
        overlap_text = row["top8_rotated_overlap_by_layer"]
        if arm["k"] == 0:
            if overlap_text:
                raise RuntimeError(f"K=0 unexpectedly emitted overlap roots: {row}")
        else:
            overlaps = [int(value) for value in overlap_text.split(",")]
            if len(overlaps) != SPARSE_LAYER_COUNT:
                raise RuntimeError(f"expected {SPARSE_LAYER_COUNT} overlaps: {row}")
    for label, label_rows in by_label.items():
        steps = sorted(row["step"] for row in label_rows)
        if steps != list(range(steps_per_arm)):
            raise RuntimeError(f"non-contiguous steps for {label}")


def validate_storage_proofs(proofs):
    if len(proofs) != 1:
        raise RuntimeError(f"expected one storage proof, observed {len(proofs)}")
    proof = proofs[0]
    expected_keys = set(EXPECTED_STORAGE_PROOF) | {"page_bytes", "checksum"}
    if set(proof) != expected_keys:
        raise RuntimeError(f"storage proof keys mismatch: {sorted(proof)}")
    for key, expected in EXPECTED_STORAGE_PROOF.items():
        if proof[key] != expected:
            raise RuntimeError(
                f"storage proof mismatch for {key}: expected {expected}, got {proof[key]}"
            )
    page_bytes = int(proof["page_bytes"])
    if page_bytes <= 0 or page_bytes & (page_bytes - 1):
        raise RuntimeError(f"invalid storage proof page size: {page_bytes}")
    checksum = proof["checksum"]
    if len(checksum) != 16:
        raise RuntimeError(f"invalid storage proof checksum width: {checksum}")
    int(checksum, 16)
    return proof


def correctness_command(args):
    arms = [{"label": "c0", "mode": "warm", "k": 0}]
    for duplicate_count in (1, 2, 3, 5):
        arms.extend(
            [
                {"label": f"w{duplicate_count}", "mode": "warm", "k": duplicate_count},
                {"label": f"c{duplicate_count}", "mode": "cold", "k": duplicate_count},
            ]
        )
    schedule = ",".join(f"{arm['label']}:{arm['mode']}:{arm['k']}" for arm in arms)
    seed, forced, case_name = load_fixture(args.fixture, 1)
    session = WorkerSession(
        args.worker,
        args.weights,
        schedule=schedule,
        steps_per_arm=1,
        digest=True,
    )
    seed_tokens = []
    result_tokens = []
    try:
        for _arm in arms:
            seed_response = session.request("decode_begin", seed_tokens=seed)
            seed_tokens.append(int(seed_response["seed_token"]))
            step_response = session.request("decode_step", token=forced[0])
            result_tokens.append(int(step_response["token"]))
        return_code = session.finish()
    except Exception:
        session.abort()
        raise
    validate_measurements(session.measurements, arms, 1)
    storage_proof = validate_storage_proofs(session.storage_proofs)
    if len(set(seed_tokens)) != 1:
        raise RuntimeError(f"decode_begin token divergence: {seed_tokens}")
    if len(set(result_tokens)) != 1:
        raise RuntimeError(f"decode_step token divergence: {result_tokens}")
    if len(session.digests) != len(arms):
        raise RuntimeError(f"expected {len(arms)} digests, observed {len(session.digests)}")
    digest_keys = {
        (row["shape"], row["dtype"], row["byte_count"], row["fnv1a64"])
        for row in session.digests
    }
    if len(digest_keys) != 1:
        raise RuntimeError(f"dense full-logit digest divergence: {session.digests}")
    result = {
        "status": "passed",
        "fixture_case": case_name,
        "schedule": arms,
        "worker_hello": session.hello,
        "worker_return_code": return_code,
        "decode_begin_tokens": seed_tokens,
        "decode_step_tokens": result_tokens,
        "token_divergence_count": 0,
        "dense_full_logit_digests": session.digests,
        "measurements": session.measurements,
        "storage_proof": storage_proof,
        "storage_independence_scope": STORAGE_INDEPENDENCE_SCOPE,
        "pre_touch_protocol": PRETOUCH_PROTOCOL,
        "command_graph_proof": COMMAND_GRAPH_PROOF,
        "residual_confound": RESIDUAL_CONFOUND,
        "logical_kv_advancement_exact": True,
        "physical_kv_advancement_exact": True,
        "physical_kv_position_directly_observable": True,
        "pending_future_state": False,
        "stderr_diagnostics": session.diagnostics,
        "system": system_metadata(),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


def run_fault_arm(args, seed, token, arm):
    schedule = f"{arm['label']}:{arm['mode']}:{arm['k']}"
    session = WorkerSession(
        args.worker,
        args.weights,
        schedule=schedule,
        steps_per_arm=1,
        fault=True,
    )
    observed_failure = None
    try:
        session.request("decode_begin", seed_tokens=seed)
        try:
            session.request("decode_step", token=token)
        except RuntimeError as error:
            observed_failure = str(error)
        return_code = session.finish(expect_success=False)
    except Exception:
        session.abort()
        raise
    if observed_failure is None:
        raise RuntimeError(f"{arm['mode']} fault injection did not interrupt decode_step")
    expected_proof = f"roots_materialized={SPARSE_LAYER_COUNT}"
    if len(session.faults) != 1 or session.faults[0]["proof"] != expected_proof:
        raise RuntimeError(f"{arm['mode']} fault marker missing or invalid: {session.faults}")
    validate_measurements(session.measurements, [arm], 1)
    return {
        "mode": arm["mode"],
        "worker_hello": session.hello,
        "worker_return_code": return_code,
        "expected_worker_failure": observed_failure,
        "fault_marker": session.faults[0],
        "measurement": session.measurements[0],
        "storage_proof": validate_storage_proofs(session.storage_proofs),
        "stderr_diagnostics": session.diagnostics,
    }


def fault_command(args):
    arms = [
        {"label": "fault-warm", "mode": "warm", "k": 1},
        {"label": "fault-cold", "mode": "cold", "k": 1},
    ]
    seed, forced, case_name = load_fixture(args.fixture, 1)
    sessions = [run_fault_arm(args, seed, forced[0], arm) for arm in arms]
    result = {
        "status": "passed",
        "fixture_case": case_name,
        "schedule": arms,
        "sessions": sessions,
        "fault_markers": [session["fault_marker"] for session in sessions],
        "measurements": [session["measurement"] for session in sessions],
        "storage_independence_scope": STORAGE_INDEPENDENCE_SCOPE,
        "pre_touch_protocol": PRETOUCH_PROTOCOL,
        "command_graph_proof": COMMAND_GRAPH_PROOF,
        "residual_confound": RESIDUAL_CONFOUND,
        "system": system_metadata(),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


def matrix_arms():
    forward = [("warm", 1), ("cold", 1), ("warm", 2), ("cold", 2),
               ("warm", 3), ("cold", 3), ("warm", 5), ("cold", 5)]
    reverse = list(reversed(forward))
    arms = []
    for block, order in ((1, forward), (2, reverse), (3, forward)):
        for position, (mode, duplicate_count) in enumerate(order, start=1):
            arms.append(
                {
                    "label": f"b{block}{mode[0]}{duplicate_count}",
                    "mode": mode,
                    "k": duplicate_count,
                    "block": block,
                    "position": position,
                }
            )
    return arms


def matrix_command(args):
    if args.timed_steps < 1 or args.discard_steps < 0:
        raise ValueError("timed and discarded step counts must be nonnegative")
    steps_per_arm = args.timed_steps + args.discard_steps
    arms = matrix_arms()
    schedule = ",".join(f"{arm['label']}:{arm['mode']}:{arm['k']}" for arm in arms)
    seed, forced, case_name = load_fixture(args.fixture, steps_per_arm)
    started = time.time()
    session = WorkerSession(
        args.worker,
        args.weights,
        schedule=schedule,
        steps_per_arm=steps_per_arm,
        measurement_path=args.raw_output,
    )
    reference_seed_token = None
    reference_tokens = None
    token_divergence_count = 0
    try:
        for arm in arms:
            begin_response = session.request("decode_begin", seed_tokens=seed)
            begin_token = int(begin_response["seed_token"])
            if reference_seed_token is None:
                reference_seed_token = begin_token
            elif begin_token != reference_seed_token:
                token_divergence_count += 1
            arm_tokens = []
            for token in forced:
                response = session.request("decode_step", token=token)
                arm_tokens.append(int(response["token"]))
            if reference_tokens is None:
                reference_tokens = arm_tokens
            else:
                token_divergence_count += sum(
                    candidate != reference
                    for candidate, reference in zip(arm_tokens, reference_tokens)
                )
        return_code = session.finish()
    except Exception:
        session.abort()
        raise
    validate_measurements(session.measurements, arms, steps_per_arm)
    storage_proof = validate_storage_proofs(session.storage_proofs)
    if token_divergence_count:
        raise RuntimeError(f"observed {token_divergence_count} token divergences")
    metadata = {
        "status": "passed",
        "fixture_case": case_name,
        "schedule": arms,
        "schedule_encoding": schedule,
        "matrix_block_orders": MATRIX_BLOCK_ORDERS,
        "timed_steps_per_arm": args.timed_steps,
        "discard_steps_per_arm": args.discard_steps,
        "total_steps_per_arm": steps_per_arm,
        "total_decode_steps": len(arms) * steps_per_arm,
        "raw_output": str(args.raw_output),
        "worker_hello": session.hello,
        "worker_return_code": return_code,
        "reference_seed_token": reference_seed_token,
        "token_divergence_count": token_divergence_count,
        "storage_proof": storage_proof,
        "storage_independence_scope": STORAGE_INDEPENDENCE_SCOPE,
        "pre_touch_protocol": PRETOUCH_PROTOCOL,
        "command_graph_proof": COMMAND_GRAPH_PROOF,
        "residual_confound": RESIDUAL_CONFOUND,
        "logical_kv_advancement_exact": True,
        "physical_kv_advancement_exact": True,
        "physical_kv_position_directly_observable": True,
        "pending_future_state": False,
        "elapsed_wall_seconds": time.time() - started,
        "stderr_diagnostics": session.diagnostics,
        "system": system_metadata(),
    }
    write_json(args.metadata_output, metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True))


def percentile(values, probability):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires observations")
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def median_absolute_deviation(values):
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def theil_sen(points):
    slopes = []
    for index, (left_x, left_y) in enumerate(points):
        for right_x, right_y in points[index + 1 :]:
            if right_x != left_x:
                slopes.append((right_y - left_y) / (right_x - left_x))
    slope = statistics.median(slopes)
    intercept = statistics.median(y - slope * x for x, y in points)
    return slope, intercept


def analyze_command(args):
    metadata = json.loads(Path(args.metadata).read_text())
    storage_proof = validate_storage_proofs([metadata["storage_proof"]])
    expected_metadata = {
        "storage_independence_scope": STORAGE_INDEPENDENCE_SCOPE,
        "pre_touch_protocol": PRETOUCH_PROTOCOL,
        "command_graph_proof": COMMAND_GRAPH_PROOF,
        "residual_confound": RESIDUAL_CONFOUND,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise RuntimeError(f"metadata proof mismatch for {key}")
    with Path(args.raw).open(newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    for row in rows:
        for field in (
            "duplicate_count",
            "step",
            "elapsed_ns",
            "dispatch_count",
            "logical_cache_delta_min",
            "logical_cache_delta_max",
            "physical_cache_delta_min",
            "physical_cache_delta_max",
            "pending_root_count",
        ):
            row[field] = int(row[field])
    arms = metadata["schedule"]
    steps_per_arm = metadata["total_steps_per_arm"]
    discard_steps = metadata["discard_steps_per_arm"]
    validate_measurements(rows, arms, steps_per_arm)
    retained = [row for row in rows if row["step"] >= discard_steps]
    by_label = {arm["label"]: [] for arm in arms}
    for row in retained:
        by_label[row["label"]].append(row)
    arm_summaries = []
    medians = {}
    batch_medians = {}
    for arm in arms:
        elapsed_us = [row["elapsed_ns"] / 1000.0 for row in by_label[arm["label"]]]
        median_us = statistics.median(elapsed_us)
        medians[arm["label"]] = median_us
        batches = [
            elapsed_us[offset : offset + args.bootstrap_block_size]
            for offset in range(0, len(elapsed_us), args.bootstrap_block_size)
        ]
        if any(len(batch) != args.bootstrap_block_size for batch in batches):
            raise ValueError("bootstrap block size must divide retained steps")
        batch_medians[arm["label"]] = [statistics.median(batch) for batch in batches]
        arm_summaries.append(
            {
                **arm,
                "observations": len(elapsed_us),
                "median_elapsed_us": median_us,
                "mad_elapsed_us": median_absolute_deviation(elapsed_us),
                "p05_elapsed_us": percentile(elapsed_us, 0.05),
                "p95_elapsed_us": percentile(elapsed_us, 0.95),
            }
        )

    def fit_from_medians(values):
        block_fits = []
        for block in (1, 2, 3):
            for mode in ("warm", "cold"):
                block_arms = [
                    arm for arm in arms if arm["block"] == block and arm["mode"] == mode
                ]
                points = [(arm["k"], values[arm["label"]]) for arm in block_arms]
                slope, intercept = theil_sen(points)
                residuals = [y - (intercept + slope * x) for x, y in points]
                block_fits.append(
                    {
                        "block": block,
                        "mode": mode,
                        "slope_us_per_step_per_duplicate": slope,
                        "intercept_us_per_step": intercept,
                        "residuals_us": residuals,
                    }
                )
        overall = {
            mode: statistics.median(
                fit["slope_us_per_step_per_duplicate"]
                for fit in block_fits
                if fit["mode"] == mode
            )
            for mode in ("warm", "cold")
        }
        return block_fits, overall

    block_fits, slopes = fit_from_medians(medians)
    ratio = slopes["cold"] / slopes["warm"]
    rng = random.Random(args.bootstrap_seed)
    bootstrap_slopes = {"warm": [], "cold": []}
    bootstrap_ratios = []
    batch_count = len(next(iter(batch_medians.values())))
    if any(len(values) != batch_count for values in batch_medians.values()):
        raise ValueError("bootstrap arms have inconsistent batch counts")
    for _ in range(args.bootstrap_replicates):
        sampled_indices = [rng.randrange(batch_count) for _ in range(batch_count)]
        sampled_medians = {
            label: statistics.median(values[index] for index in sampled_indices)
            for label, values in batch_medians.items()
        }
        _fits, sampled_slopes = fit_from_medians(sampled_medians)
        if sampled_slopes["warm"] <= 0:
            continue
        bootstrap_slopes["warm"].append(sampled_slopes["warm"])
        bootstrap_slopes["cold"].append(sampled_slopes["cold"])
        bootstrap_ratios.append(sampled_slopes["cold"] / sampled_slopes["warm"])
    if len(bootstrap_ratios) < args.bootstrap_replicates * 0.95:
        raise RuntimeError("too many nonpositive warm bootstrap slopes")
    slope_cis = {
        mode: [
            percentile(bootstrap_slopes[mode], 0.025),
            percentile(bootstrap_slopes[mode], 0.975),
        ]
        for mode in ("warm", "cold")
    }
    ratio_ci = [percentile(bootstrap_ratios, 0.025), percentile(bootstrap_ratios, 0.975)]
    for fit in block_fits:
        residuals = fit.pop("residuals_us")
        fit["residual_median_us"] = statistics.median(residuals)
        fit["residual_mad_us"] = median_absolute_deviation(residuals)
        fit["residual_p95_absolute_us"] = percentile([abs(value) for value in residuals], 0.95)

    overlap_values = {"warm": [], "cold": []}
    for row in retained:
        overlap_values[row["mode"]].extend(
            int(value) for value in row["top8_rotated_overlap_by_layer"].split(",")
        )
    overlap_summary = {
        mode: {
            "observations": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": percentile(values, 0.95),
            "maximum": max(values),
            "zero_fraction": sum(value == 0 for value in values) / len(values),
        }
        for mode, values in overlap_values.items()
    }
    ratio_ci_includes_one = ratio_ci[0] <= 1.0 <= ratio_ci[1]
    t2d_eligible = ratio > 1.10 and ratio_ci[0] > 1.0
    modeled_bandwidth = {
        mode: (TRAFFIC_BYTES_PER_DUPLICATE / (slope * 1e-6)) / 1e9
        for mode, slope in slopes.items()
        if slope > 0
    }
    result = {
        "status": "passed",
        "estimator": "per-arm median; per-block four-point Theil-Sen; median of three block slopes",
        "confidence_interval": {
            "method": (
                f"paired non-overlapping {args.bootstrap_block_size}-step block "
                "bootstrap of arm medians"
            ),
            "replicates_requested": args.bootstrap_replicates,
            "replicates_retained": len(bootstrap_ratios),
            "seed": args.bootstrap_seed,
        },
        "measurement_scope": (
            "K>=1 slopes estimate repeated selected-row marginal cost after blocking full-bank "
            "evaluation, symmetric page-stride pretouch, and 16 discarded identical forced-token "
            "steps per arm; retained observations exclude those initialization steps."
        ),
        "storage_proof": storage_proof,
        "storage_independence_scope": metadata["storage_independence_scope"],
        "pre_touch_protocol": metadata["pre_touch_protocol"],
        "command_graph_proof": metadata["command_graph_proof"],
        "residual_confound": metadata["residual_confound"],
        "arm_summaries": arm_summaries,
        "block_fits": block_fits,
        "overall_slope_us_per_step_per_duplicate": slopes,
        "overall_slope_95ci_us_per_step_per_duplicate": slope_cis,
        "cold_to_warm_slope_ratio": ratio,
        "cold_to_warm_slope_ratio_95ci": ratio_ci,
        "ratio_ci_includes_one": ratio_ci_includes_one,
        "preregistered_t2d_eligible": t2d_eligible,
        "preregistered_decision": "continue_to_t2d" if t2d_eligible else "stop_after_t2c",
        "rotated_top8_overlap": overlap_summary,
        "traffic_model": {
            "bytes_per_selected_expert_gate_up": EXPERT_BYTES_PER_SELECTED_ROW,
            "selected_experts_per_sparse_layer": SELECTED_EXPERTS_PER_LAYER,
            "sparse_layers": SPARSE_LAYER_COUNT,
            "modeled_bytes_per_duplicate_per_decode_step": TRAFFIC_BYTES_PER_DUPLICATE,
            "modeled_effective_bandwidth_gb_s": modeled_bandwidth,
            "caveat": "Model-implied weight bytes only. " + RESIDUAL_CONFOUND,
        },
        "input_metadata": metadata,
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


def add_worker_arguments(parser):
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path("weights"))
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("correctness_prompts/public_longcopy_gate_english_512_1024.json"),
    )


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    correctness = subparsers.add_parser("correctness")
    add_worker_arguments(correctness)
    correctness.add_argument("--output", type=Path, required=True)
    correctness.set_defaults(function=correctness_command)

    fault = subparsers.add_parser("fault")
    add_worker_arguments(fault)
    fault.add_argument("--output", type=Path, required=True)
    fault.set_defaults(function=fault_command)

    matrix = subparsers.add_parser("matrix")
    add_worker_arguments(matrix)
    matrix.add_argument("--raw-output", type=Path, required=True)
    matrix.add_argument("--metadata-output", type=Path, required=True)
    matrix.add_argument("--timed-steps", type=int, default=1200)
    matrix.add_argument("--discard-steps", type=int, default=16)
    matrix.set_defaults(function=matrix_command)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--raw", type=Path, required=True)
    analyze.add_argument("--metadata", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--bootstrap-replicates", type=int, default=10000)
    analyze.add_argument("--bootstrap-block-size", type=int, default=30)
    analyze.add_argument("--bootstrap-seed", type=int, default=252)
    analyze.set_defaults(function=analyze_command)

    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
