#!/usr/bin/env python3
import argparse
import copy
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import time
from pathlib import Path

FAMILIES = (
    "sliding_attention",
    "full_attention",
    "o_proj",
    "routed_gate_up",
    "shared_gate_up",
    "down_residual",
    "lm_head",
)
ORDER_MODES = {
    "ABBA": ("control", "family", "family", "control"),
    "BAAB": ("family", "control", "control", "family"),
}
EXPECTED_PER_STEP = {
    "sliding_attention": 30,
    "o_proj": 40,
    "routed_gate_up": 39,
    "shared_gate_up": 39,
    "down_residual": 39,
    "lm_head": 1,
}
EXPECTED_TOTAL = {
    "sliding_attention": 3_840,
    "full_attention": 1_270,
    "o_proj": 5_120,
    "routed_gate_up": 4_992,
    "shared_gate_up": 4_992,
    "down_residual": 4_992,
    "lm_head": 128,
}
STEADY_START = 64
BOOTSTRAP_SAMPLES = 10_000


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def bootstrap_difference(left, right, seed):
    rng = random.Random(seed)
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        left_mean = sum(rng.choice(left) for _ in left) / len(left)
        right_mean = sum(rng.choice(right) for _ in right) / len(right)
        draws.append(left_mean - right_mean)
    return percentile(draws, 0.025), percentile(draws, 0.975)


def bootstrap_ratio_percent(numerator, denominator, seed):
    rng = random.Random(seed)
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        n_mean = sum(rng.choice(numerator) for _ in numerator) / len(numerator)
        d_mean = sum(rng.choice(denominator) for _ in denominator) / len(denominator)
        draws.append(100.0 * (n_mean / d_mean - 1.0))
    return percentile(draws, 0.025), percentile(draws, 0.975)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def route_digest(indices, weight_bits):
    encoded = json.dumps([indices, weight_bits], separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class Worker:
    def __init__(self, binary, weights):
        self.process = subprocess.Popen(
            [binary, "runtime-worker", "--weights", weights],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        hello_line = self.process.stdout.readline()
        if not hello_line:
            raise RuntimeError(f"worker exited before hello: {self.process.poll()}")
        hello = json.loads(hello_line)
        if hello.get("id") != 0 or not hello.get("ok") or not hello.get("nonce"):
            raise RuntimeError(f"invalid worker hello: {hello}")
        self.nonce = hello["nonce"]

    def request(self, kind, **fields):
        request_id = self.next_id
        self.next_id += 1
        request = {"id": request_id, "kind": kind, **fields}
        encoded = json.dumps(request, separators=(",", ":"))
        started_ns = time.perf_counter_ns()
        self.process.stdin.write(encoded + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        finished_ns = time.perf_counter_ns()
        if not line:
            raise RuntimeError(f"worker exited during {kind}: {self.process.poll()}")
        response = json.loads(line)
        if response.get("id") != request_id:
            raise RuntimeError(f"response id mismatch for {kind}: {response.get('id')}")
        if response.get("nonce") != self.nonce:
            raise RuntimeError(f"response nonce mismatch for {kind}")
        if not response.get("ok"):
            raise RuntimeError(f"worker {kind} failed: {response.get('error')}")
        return response, finished_ns - started_ns

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        return self.process.wait(timeout=30)


def expected_census(step):
    result = dict(EXPECTED_PER_STEP)
    if step > 0:
        result["full_attention"] = 10
    return result


def run_block(
    worker,
    family,
    mode,
    order,
    slot,
    prompt_tokens,
    expected_tokens,
    route_reference,
    collect,
):
    worker.request(
        "research_probe_config", probe_family=family, probe_mode=mode
    )
    begin, _ = worker.request("decode_begin", seed_tokens=prompt_tokens)
    if begin.get("seed_token") != expected_tokens[0]:
        raise RuntimeError(
            f"seed token mismatch: {begin.get('seed_token')} != {expected_tokens[0]}"
        )

    samples = []
    for step in range(128):
        response, whole_token_ns = worker.request(
            "decode_step", token=expected_tokens[step]
        )
        actual = response.get("token")
        expected = expected_tokens[step + 1]
        cache_position = response.get("cache_position")
        census = response.get("probe_census")
        route_indices = response.get("probe_route_indices")
        route_weight_bits = response.get("probe_route_weight_bits")
        route_layer_count = response.get("probe_route_layer_count")
        if actual != expected:
            raise RuntimeError(
                f"token mismatch family={family} mode={mode} step={step}: "
                f"{actual} != {expected}"
            )
        if cache_position != 513 + step:
            raise RuntimeError(
                f"cache mismatch family={family} mode={mode} step={step}: "
                f"{cache_position} != {513 + step}"
            )
        if census != expected_census(step):
            raise RuntimeError(
                f"census mismatch family={family} mode={mode} step={step}: {census}"
            )
        if route_layer_count != 39 or len(route_indices or []) != 312:
            raise RuntimeError(
                f"route index shape mismatch family={family} mode={mode} step={step}: "
                f"layers={route_layer_count} values={len(route_indices or [])}"
            )
        if len(route_weight_bits or []) != 312:
            raise RuntimeError(
                f"route weight shape mismatch family={family} mode={mode} step={step}: "
                f"values={len(route_weight_bits or [])}"
            )
        digest = route_digest(route_indices, route_weight_bits)
        route = {
            "step": step,
            "input_token": expected_tokens[step],
            "expected_token": expected,
            "layer_count": route_layer_count,
            "indices": route_indices,
            "weight_bits": route_weight_bits,
            "sha256": digest,
        }
        if step not in route_reference:
            route_reference[step] = route
        elif route_reference[step] != route:
            raise RuntimeError(
                f"route mismatch family={family} mode={mode} step={step}: {digest}"
            )
        expected_calls = 0 if mode == "off" else expected_census(step).get(family, 0)
        if response.get("probe_measured_call_count") != expected_calls:
            raise RuntimeError(
                f"measured call mismatch family={family} mode={mode} step={step}: "
                f"{response.get('probe_measured_call_count')} != {expected_calls}"
            )
        if collect:
            samples.append(
                {
                    "step": step,
                    "position": 513 + step,
                    "input_token": expected_tokens[step],
                    "expected_token": expected,
                    "actual_token": actual,
                    "cache_position": cache_position,
                    "route_layer_count": route_layer_count,
                    "route_sha256": digest,
                    "probe_duration_ns": response.get("probe_duration_ns"),
                    "measured_calls": response.get("probe_measured_call_count"),
                    "census": census,
                    "whole_token_ns": whole_token_ns,
                }
            )
    if not collect:
        return None
    totals = {
        name: sum(row["census"].get(name, 0) for row in samples)
        for name in FAMILIES
    }
    if totals != EXPECTED_TOTAL:
        raise RuntimeError(f"block census totals mismatch: {totals}")
    return {
        "family": family,
        "mode": mode,
        "order": order,
        "slot": slot,
        "samples": samples,
        "census_totals": totals,
    }


def steady_values(blocks, order, mode, field):
    return [
        row[field]
        for block in blocks
        if block["order"] == order and block["mode"] == mode
        for row in block["samples"]
        if row["step"] >= STEADY_START
    ]


def summarize_family(family, blocks):
    result = {"family": family, "orders": {}}
    order_estimates = []
    order_bounds = []
    for order_index, order in enumerate(ORDER_MODES):
        family_probe = steady_values(blocks, order, "family", "probe_duration_ns")
        control_probe = steady_values(blocks, order, "control", "probe_duration_ns")
        family_whole = steady_values(blocks, order, "family", "whole_token_ns")
        control_whole = steady_values(blocks, order, "control", "whole_token_ns")
        off_whole = steady_values(blocks, order, "off", "whole_token_ns")
        probe_estimate = (statistics.mean(family_probe) - statistics.mean(control_probe)) / 1_000.0
        probe_ci_ns = bootstrap_difference(
            family_probe, control_probe, seed=645_000 + 10 * order_index + FAMILIES.index(family)
        )
        probe_ci_us = [value / 1_000.0 for value in probe_ci_ns]
        family_perturb = 100.0 * (statistics.mean(family_whole) / statistics.mean(off_whole) - 1.0)
        control_perturb = 100.0 * (statistics.mean(control_whole) / statistics.mean(off_whole) - 1.0)
        family_perturb_ci = bootstrap_ratio_percent(
            family_whole, off_whole, seed=645_100 + 10 * order_index + FAMILIES.index(family)
        )
        control_perturb_ci = bootstrap_ratio_percent(
            control_whole, off_whole, seed=645_200 + 10 * order_index + FAMILIES.index(family)
        )
        result["orders"][order] = {
            "steady_samples_per_selector": len(family_probe),
            "off_steady_samples": len(off_whole),
            "family_minus_control_us_per_token": probe_estimate,
            "family_minus_control_ci95_us_per_token": probe_ci_us,
            "family_whole_token_perturbation_percent": family_perturb,
            "family_whole_token_perturbation_ci95_percent": list(family_perturb_ci),
            "control_whole_token_perturbation_percent": control_perturb,
            "control_whole_token_perturbation_ci95_percent": list(control_perturb_ci),
            "family_probe_p50_us": percentile(family_probe, 0.5) / 1_000.0,
            "control_probe_p50_us": percentile(control_probe, 0.5) / 1_000.0,
            "off_whole_token_p50_ms": percentile(off_whole, 0.5) / 1_000_000.0,
        }
        order_estimates.append(probe_estimate)
        order_bounds.extend(probe_ci_us)
    combined = statistics.mean(order_estimates)
    lower = min(order_bounds)
    upper = max(order_bounds)
    perturbation_ok = all(
        -1.0 <= value <= 1.0
        for order in result["orders"].values()
        for key in (
            "family_whole_token_perturbation_ci95_percent",
            "control_whole_token_perturbation_ci95_percent",
        )
        for value in order[key]
    )
    result["combined"] = {
        "family_bound_us_per_token": combined,
        "conservative_ci95_hull_us_per_token": [lower, upper],
        "ci95_half_width_us_per_token": (upper - lower) / 2.0,
        "order_effect_us_per_token": order_estimates[0] - order_estimates[1],
        "precision_within_5us": (upper - lower) / 2.0 <= 5.0,
        "whole_token_perturbation_within_1_percent": perturbation_ok,
        "actionable": perturbation_ok and (upper - lower) / 2.0 <= 5.0,
    }
    return result


def validate_result(result):
    errors = []
    route_manifest = result.get("route_manifest", [])
    route_by_step = {route.get("step"): route for route in route_manifest}
    if len(route_manifest) != 128 or len(route_by_step) != 128:
        errors.append(f"route manifest count {len(route_manifest)}")
    for step, route in route_by_step.items():
        indices = route.get("indices", [])
        weight_bits = route.get("weight_bits", [])
        if route.get("layer_count") != 39 or len(indices) != 312 or len(weight_bits) != 312:
            errors.append(f"route manifest shape step {step}")
        if route.get("sha256") != route_digest(indices, weight_bits):
            errors.append(f"route manifest digest step {step}")

    blocks = result.get("blocks", [])
    if len(blocks) != len(FAMILIES) * len(ORDER_MODES) * 6:
        errors.append(f"block count {len(blocks)}")
    for block_index, block in enumerate(blocks):
        samples = block.get("samples", [])
        if len(samples) != 128:
            errors.append(f"block {block_index} sample count {len(samples)}")
            continue
        totals = {name: 0 for name in FAMILIES}
        for step, row in enumerate(samples):
            if row.get("step") != step:
                errors.append(f"block {block_index} step index {step}")
            if row.get("actual_token") != row.get("expected_token"):
                errors.append(f"block {block_index} token step {step}")
            if row.get("cache_position") != 513 + step:
                errors.append(f"block {block_index} cache step {step}")
            route = route_by_step.get(step, {})
            if row.get("route_layer_count") != 39:
                errors.append(f"block {block_index} route count step {step}")
            if row.get("route_sha256") != route.get("sha256"):
                errors.append(f"block {block_index} route digest step {step}")
            expected = expected_census(step)
            if row.get("census") != expected:
                errors.append(f"block {block_index} census step {step}")
            for name in FAMILIES:
                totals[name] += row.get("census", {}).get(name, 0)
        if totals != EXPECTED_TOTAL:
            errors.append(f"block {block_index} census total")
    if errors:
        raise ValueError("; ".join(errors[:20]))
    return {
        "ok": True,
        "blocks": len(blocks),
        "samples": sum(len(block["samples"]) for block in blocks),
        "route_steps": len(route_manifest),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", default=".build-worker/release/mlxfast-runtime-worker")
    parser.add_argument("--weights", default="weights")
    parser.add_argument(
        "--fixture", default="correctness_prompts/public_longcopy_gate_english_512_256.json"
    )
    parser.add_argument("--output", default="/tmp/pr645-r2-decode-probes.json")
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text())
    case = fixture["cases"][0]
    prompt_tokens = case["prompt_tokens"]
    expected_tokens = case["expected_tokens"]
    if len(prompt_tokens) != 512 or len(expected_tokens) < 129:
        raise RuntimeError("fixture does not contain the required 512+128 trajectory")

    started = time.time()
    worker = Worker(args.worker, args.weights)
    blocks = []
    route_reference = {}
    try:
        run_block(
            worker,
            "lm_head",
            "off",
            "warmup",
            -1,
            prompt_tokens,
            expected_tokens,
            route_reference,
            collect=False,
        )
        for family in FAMILIES:
            for order, selector_modes in ORDER_MODES.items():
                blocks.append(
                    run_block(
                        worker,
                        family,
                        "off",
                        order,
                        -1,
                        prompt_tokens,
                        expected_tokens,
                        route_reference,
                        collect=True,
                    )
                )
                for slot, mode in enumerate(selector_modes):
                    blocks.append(
                        run_block(
                            worker,
                            family,
                            mode,
                            order,
                            slot,
                            prompt_tokens,
                            expected_tokens,
                            route_reference,
                            collect=True,
                        )
                    )
                blocks.append(
                    run_block(
                        worker,
                        family,
                        "off",
                        order,
                        4,
                        prompt_tokens,
                        expected_tokens,
                        route_reference,
                        collect=True,
                    )
                )
    finally:
        worker_exit = worker.close()

    result = {
        "schema_version": 3,
        "assignment": "PR645-r2-decode-critical-path-attribution",
        "instrumentation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "worker_sha256": sha256_file(args.worker),
        "fixture_sha256": sha256_file(args.fixture),
        "fixture_case": case["name"],
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "node": platform.node(),
        },
        "protocol": {
            "persistent_worker": True,
            "warmup_trajectories": 1,
            "steady_start_step": STEADY_START,
            "steady_samples_per_selector_order": 128,
            "selector_orders": ORDER_MODES,
            "family_fence": "asyncEval(inputs), GPU synchronize, timestamp, asyncEval(output), GPU synchronize",
            "control_fence": "asyncEval(inputs), GPU synchronize, timestamp, empty GPU synchronize",
            "route_validation": "all 39 sparse layers: exact eight UInt32 IDs and exact eight Float32 weight bit patterns",
        },
        "worker_exit": worker_exit,
        "elapsed_seconds": time.time() - started,
        "route_manifest": [route_reference[step] for step in range(128)],
        "blocks": blocks,
        "family_summaries": [
            summarize_family(family, [block for block in blocks if block["family"] == family])
            for family in FAMILIES
        ],
    }
    validation = validate_result(result)
    corrupted = copy.deepcopy(result)
    corrupted["blocks"][0]["samples"][0]["census"]["sliding_attention"] += 1
    try:
        validate_result(corrupted)
        corruption_control = {"ok": False, "error": "corruption was not detected"}
    except ValueError as error:
        corruption_control = {"ok": True, "detected_error": str(error)}
    result["validation"] = validation
    result["positive_census_corruption_control"] = corruption_control
    result["terminal_no_go"] = not all(
        summary["combined"]["actionable"] for summary in result["family_summaries"]
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    compact = {
        "output": args.output,
        "elapsed_seconds": result["elapsed_seconds"],
        "validation": validation,
        "positive_census_corruption_control": corruption_control,
        "terminal_no_go": result["terminal_no_go"],
        "family_summaries": result["family_summaries"],
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
