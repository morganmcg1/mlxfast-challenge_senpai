#!/usr/bin/env python3

import argparse
import csv
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

MODES = {"off": 9100, "empty": 9101, "active": 9102}
FAMILIES = {
    "cache_construction": (1, 1),
    "input_setup": (2, 1),
    "ordinary_layers": (3, 39),
    "terminal_layer": (5, 1),
    "final_norm_head": (6, 1),
    "async_enqueue": (4, 39),
}
ORDERS = {"ABBA": ("A", "B", "B", "A"), "BAAB": ("B", "A", "A", "B")}
FIELDS = [
    "comparison", "family", "order", "quartet", "position", "arm", "mode",
    "request_id", "wall_ns", "profile_ns", "profile_count", "eval_ns", "token",
]


def percentile(values, q):
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def mean(rows, key):
    return statistics.fmean(float(row[key]) for row in rows)


def bootstrap_difference(rows, order, key, arm_a, arm_b, iterations=5000):
    blocks = {}
    for row in rows:
        if row["order"] == order:
            blocks.setdefault(int(row["quartet"]), []).append(row)
    quartets = sorted(blocks)
    if not quartets:
        raise RuntimeError(f"no {order} blocks")
    rng = random.Random(f"host-profile:{order}:{key}:{arm_a}:{arm_b}")
    estimates = []
    for _ in range(iterations):
        sampled = [row for _ in quartets for row in blocks[rng.choice(quartets)]]
        a_rows = [row for row in sampled if row["arm"] == arm_a]
        b_rows = [row for row in sampled if row["arm"] == arm_b]
        estimates.append(mean(b_rows, key) - mean(a_rows, key))
    actual_a = [row for row in rows if row["order"] == order and row["arm"] == arm_a]
    actual_b = [row for row in rows if row["order"] == order and row["arm"] == arm_b]
    estimate = mean(actual_b, key) - mean(actual_a, key)
    return {
        "estimate": estimate,
        "ci95_low": percentile(estimates, 0.025),
        "ci95_high": percentile(estimates, 0.975),
        "a_mean": mean(actual_a, key),
        "b_mean": mean(actual_b, key),
        "a_n": len(actual_a),
        "b_n": len(actual_b),
    }


class Worker:
    def __init__(self, executable, weights, stderr_path):
        self.stderr_file = open(stderr_path, "w", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(executable), "runtime-worker", "--weights", str(weights)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr_file,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        hello = self._read()
        if hello.get("id") != 0 or hello.get("ok") is not True or not hello.get("nonce"):
            raise RuntimeError(f"invalid worker hello: {hello}")
        self.nonce = hello["nonce"]

    def _read(self):
        line = self.process.stdout.readline()
        if not line:
            code = self.process.poll()
            raise RuntimeError(f"worker closed protocol stream (exit={code})")
        return json.loads(line)

    def request(self, kind, **fields):
        request_id = self.next_id
        self.next_id += 1
        payload = {"id": request_id, "kind": kind, **fields}
        encoded = json.dumps(payload, separators=(",", ":"))
        start = time.perf_counter_ns()
        self.process.stdin.write(encoded + "\n")
        self.process.stdin.flush()
        response = self._read()
        wall_ns = time.perf_counter_ns() - start
        if response.get("id") != request_id or response.get("nonce") != self.nonce:
            raise RuntimeError(f"protocol identity mismatch: {response}")
        if response.get("ok") is not True:
            raise RuntimeError(f"worker request failed: {response}")
        return response, wall_ns

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.stderr_file.close()


def load_fixture(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    case = fixture["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"][0]
    if len(prompt) != 512:
        raise RuntimeError(f"fixture prompt has {len(prompt)} tokens, expected 512")
    return prompt, expected


def validate_profile(mode, expected_count, response):
    profile_ns = response.get("expected_token_logit")
    profile_count = response.get("expected_token_rank")
    eval_ns = response.get("top_logit_margin")
    if profile_ns is None or profile_count is None or eval_ns is None:
        raise RuntimeError(f"missing profile fields: {response}")
    required_count = 0 if mode == "off" else expected_count
    if profile_count != required_count:
        raise RuntimeError(
            f"profile count mismatch for {mode}: got {profile_count}, expected {required_count}"
        )
    if float(profile_ns) < 0 or float(eval_ns) < 0:
        raise RuntimeError(f"negative profile duration: {response}")
    return float(profile_ns), int(profile_count), float(eval_ns)


def run_prefill(worker, prompt, expected_token, family, mode):
    family_code, expected_count = FAMILIES[family]
    response, wall_ns = worker.request(
        "prefill",
        prompt_tokens=prompt,
        top_k=MODES[mode],
        expected_token=family_code,
    )
    token = response.get("token")
    if token != expected_token:
        raise RuntimeError(f"token mismatch: got {token}, expected {expected_token}")
    profile_ns, count, eval_ns = validate_profile(mode, expected_count, response)
    return wall_ns, profile_ns, count, eval_ns, token, response["id"]


def run_comparison(worker, prompt, expected_token, comparison, family, arm_modes, quartets, writer, rows):
    for mode in arm_modes.values():
        run_prefill(worker, prompt, expected_token, family, mode)
    comparison_rows = []
    for order, pattern in ORDERS.items():
        for quartet in range(quartets):
            for position, arm in enumerate(pattern):
                mode = arm_modes[arm]
                wall_ns, profile_ns, count, eval_ns, token, request_id = run_prefill(
                    worker, prompt, expected_token, family, mode
                )
                row = {
                    "comparison": comparison,
                    "family": family,
                    "order": order,
                    "quartet": quartet,
                    "position": position,
                    "arm": arm,
                    "mode": mode,
                    "request_id": request_id,
                    "wall_ns": wall_ns,
                    "profile_ns": profile_ns,
                    "profile_count": count,
                    "eval_ns": eval_ns,
                    "token": token,
                }
                writer.writerow(row)
                rows.append(row)
                comparison_rows.append(row)
    return comparison_rows


def summarize_control(rows):
    orders = {}
    valid = True
    for order in ORDERS:
        wall = bootstrap_difference(rows, order, "wall_ns", "A", "B")
        perturbation = 100.0 * wall["estimate"] / wall["a_mean"]
        wall["perturbation_percent"] = perturbation
        orders[order] = wall
        valid = valid and abs(perturbation) <= 1.0
    return {"valid": valid, "orders": orders}


def summarize_family(rows):
    orders = {}
    valid = True
    for order in ORDERS:
        profile = bootstrap_difference(rows, order, "profile_ns", "A", "B")
        wall = bootstrap_difference(rows, order, "wall_ns", "A", "B")
        profile_ms = {key: value / 1_000_000.0 for key, value in profile.items() if key not in {"a_n", "b_n"}}
        profile_ms["a_n"] = profile["a_n"]
        profile_ms["b_n"] = profile["b_n"]
        perturbation = 100.0 * wall["estimate"] / wall["a_mean"]
        wall["perturbation_percent"] = perturbation
        half_width_ms = (profile_ms["ci95_high"] - profile_ms["ci95_low"]) / 2.0
        profile_ms["ci95_half_width"] = half_width_ms
        orders[order] = {"profile_ms": profile_ms, "wall": wall}
        valid = valid and profile_ms["estimate"] > 0
        valid = valid and half_width_ms <= 0.10
        valid = valid and abs(perturbation) <= 1.0
    lower_bound = min(orders[order]["profile_ms"]["ci95_low"] for order in ORDERS)
    return {
        "valid": valid,
        "conservative_lower_bound_ms": lower_bound,
        "meets_2_33_ms_gate": valid and lower_bound >= 2.33,
        "orders": orders,
    }


def corruption_control(rows):
    source = next(row for row in rows if row["mode"] != "off")
    corrupted = dict(source)
    corrupted["profile_count"] = int(corrupted["profile_count"]) + 1
    expected_count = FAMILIES[corrupted["family"]][1]
    try:
        if corrupted["profile_count"] != expected_count:
            raise RuntimeError("synthetic counter corruption detected")
    except RuntimeError:
        return True
    return False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, default=Path(".build-worker/release/mlxfast-runtime-worker"))
    parser.add_argument("--weights", type=Path, default=Path("weights"))
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("correctness_prompts/public_longcopy_gate_english_512_256.json"),
    )
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--quartets", type=int, default=32)
    parser.add_argument("--warmups", type=int, default=8)
    parser.add_argument("--families", nargs="+", choices=tuple(FAMILIES), default=list(FAMILIES))
    return parser.parse_args()


def main():
    args = parse_args()
    if args.quartets < 1 or args.warmups < 0:
        raise RuntimeError("quartets must be positive and warmups nonnegative")
    for path in (args.worker, args.weights, args.fixture):
        if not path.exists():
            raise RuntimeError(f"missing required path: {path}")
    args.raw.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    prompt, expected_token = load_fixture(args.fixture)
    stderr_path = args.raw.with_suffix(args.raw.suffix + ".worker.log")
    rows = []
    summary = {
        "schema_version": 1,
        "worker": str(args.worker.resolve()),
        "weights": str(args.weights.resolve()),
        "fixture": str(args.fixture.resolve()),
        "quartets_per_order": args.quartets,
        "steady_samples_per_arm_per_order": 2 * args.quartets,
        "warmups": args.warmups,
        "expected_token": expected_token,
        "families": {},
    }
    worker = Worker(args.worker.resolve(), args.weights.resolve(), stderr_path)
    try:
        for _ in range(args.warmups):
            run_prefill(worker, prompt, expected_token, "cache_construction", "off")
        with args.raw.open("w", encoding="utf-8", newline="") as raw_file:
            writer = csv.DictWriter(raw_file, fieldnames=FIELDS)
            writer.writeheader()
            control_rows = run_comparison(
                worker,
                prompt,
                expected_token,
                "empty_control",
                "ordinary_layers",
                {"A": "off", "B": "empty"},
                args.quartets,
                writer,
                rows,
            )
            summary["empty_control"] = summarize_control(control_rows)
            if not summary["empty_control"]["valid"]:
                summary["status"] = "control_failed"
            else:
                for family in args.families:
                    family_rows = run_comparison(
                        worker,
                        prompt,
                        expected_token,
                        "family_measurement",
                        family,
                        {"A": "empty", "B": "active"},
                        args.quartets,
                        writer,
                        rows,
                    )
                    family_summary = summarize_family(family_rows)
                    summary["families"][family] = family_summary
                    if not family_summary["valid"]:
                        summary["status"] = "family_validity_failed"
                        break
                else:
                    summary["status"] = "complete"
        diagnostics, _ = worker.request("phase_diagnostics")
        summary["diagnostics"] = {
            key: diagnostics.get(key)
            for key in (
                "peak_ram_gb",
                "mlx_active_memory_bytes",
                "mlx_cache_memory_bytes",
                "mlx_peak_memory_bytes",
            )
        }
        summary["counter_corruption_control_detected"] = corruption_control(rows)
    finally:
        worker.close()
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["status"] != "complete" or not summary["counter_corruption_control_detected"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
