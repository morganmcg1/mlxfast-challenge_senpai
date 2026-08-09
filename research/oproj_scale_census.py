#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

NUM_LAYERS = 40
ROWS = 2048
HEAD_DIM = 128
GROUP_SIZE = 16
ROW_ALIGNMENT = 32
EXPECTED_FULL_LAYERS = list(range(0, NUM_LAYERS, 4))
EXPECTED_SLIDING_LAYERS = [i for i in range(NUM_LAYERS) if i not in EXPECTED_FULL_LAYERS]
QKV_DELETION_BYTES = 6_225_920


def parse_args():
    parser = argparse.ArgumentParser(description="Audit retained decode OProj NVFP4 scale banks")
    parser.add_argument("--raw-dir", type=Path, default=Path(".agent_tmp/oproj-scale-census-raw"))
    parser.add_argument(
        "--extract-stderr",
        type=Path,
        help="extract sandbox-safe OProj census frames from benchmark stderr and exit",
    )
    parser.add_argument("--config", type=Path, default=Path("weights/config.json"))
    parser.add_argument("--output-json", type=Path, default=Path("research/oproj_scale_census.json"))
    parser.add_argument("--output-md", type=Path, default=Path("research/oproj_scale_census.md"))
    parser.add_argument("--wandb", action="store_true")
    parser.add_argument(
        "--wandb-only",
        action="store_true",
        help="upload existing JSON/Markdown without regenerating measurement metadata",
    )
    parser.add_argument(
        "--wandb-output", type=Path, default=Path("research/oproj_scale_census_wandb.json")
    )
    return parser.parse_args()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def decode_frame_payload(payload):
    return base64.b64decode(payload.replace("-", ""), validate=True)


def extract_stderr(capture_path, raw_dir):
    pattern = re.compile(
        r"OPROJ_CENSUS (runtime|scale|dispatch) pid=(\d+)"
        r"(?: layer=(\d+))? chunk=(\d+)/(\d+) payload=(\S+)$"
    )
    processes = {}
    with capture_path.open(errors="strict") as capture:
        for line_number, line in enumerate(capture, 1):
            match = pattern.search(line.rstrip("\n"))
            if not match:
                continue
            kind, pid_text, layer_text, chunk_text, count_text, payload = match.groups()
            pid = int(pid_text)
            layer = int(layer_text) if layer_text is not None else None
            chunk = int(chunk_text)
            count = int(count_text)
            if chunk < 0 or count < 1 or chunk >= count:
                raise RuntimeError(f"invalid census chunk at line {line_number}")
            process = processes.setdefault(
                pid, {"runtime": {}, "scale": {}, "dispatch": []}
            )
            if kind == "dispatch":
                if layer is not None or chunk != 0 or count != 1:
                    raise RuntimeError(f"invalid dispatch frame at line {line_number}")
                process["dispatch"].append(decode_frame_payload(payload))
                continue
            key = layer if kind == "scale" else None
            if kind == "scale" and (layer is None or not 0 <= layer < NUM_LAYERS):
                raise RuntimeError(f"invalid scale layer at line {line_number}")
            if kind == "runtime" and layer is not None:
                raise RuntimeError(f"invalid runtime frame at line {line_number}")
            chunks = process[kind].setdefault(key, {"count": count, "payloads": {}})
            if chunks["count"] != count:
                raise RuntimeError(f"inconsistent census chunk count at line {line_number}")
            existing = chunks["payloads"].get(chunk)
            if existing is not None and existing != payload:
                raise RuntimeError(f"conflicting census chunk at line {line_number}")
            chunks["payloads"][chunk] = payload

    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True)
    complete_processes = 0
    for pid, process in processes.items():
        process_dir = raw_dir / f"pid-{pid}"
        process_dir.mkdir()
        for key, chunks in process["runtime"].items():
            payloads = chunks["payloads"]
            if sorted(payloads) != list(range(chunks["count"])):
                raise RuntimeError(f"incomplete runtime metadata for pid {pid}")
            (process_dir / "runtime.json").write_bytes(
                decode_frame_payload("".join(payloads[index] for index in sorted(payloads)))
            )
        for layer, chunks in process["scale"].items():
            payloads = chunks["payloads"]
            if sorted(payloads) != list(range(chunks["count"])):
                raise RuntimeError(f"incomplete layer {layer} scale bank for pid {pid}")
            (process_dir / f"layer-{layer:02d}.bin").write_bytes(
                decode_frame_payload("".join(payloads[index] for index in sorted(payloads)))
            )
        if process["dispatch"]:
            with (process_dir / "dispatch.jsonl").open("wb") as output:
                for record in process["dispatch"]:
                    output.write(record + b"\n")
        if process["runtime"] and len(process["scale"]) == NUM_LAYERS and process["dispatch"]:
            complete_processes += 1
    if complete_processes < 1:
        raise RuntimeError("stderr capture contained no complete OProj census process")
    print(
        f"extracted {complete_processes} complete OProj census process(es) "
        f"from {capture_path} into {raw_dir}"
    )


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def quantiles(values):
    return {
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def command_output(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def histogram(data):
    counts = [0] * 256
    for value, count in Counter(data).items():
        counts[value] = count
    return counts


def histogram_summary(data):
    hist = histogram(data)
    total = len(data)
    count_0_63 = sum(hist[:64])
    count_0_127 = sum(hist[:128])
    return {
        "count": total,
        "min": min(data),
        "max": max(data),
        "count_0_63": count_0_63,
        "count_64_127": sum(hist[64:128]),
        "count_128_255": sum(hist[128:]),
        "count_gt_63": total - count_0_63,
        "count_gt_127": total - count_0_127,
        "fraction_0_63": count_0_63 / total,
        "fraction_0_127": count_0_127 / total,
        "histogram_256": hist,
    }


def align_up(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def insert_at_bit_offset(value, bits, bit_offset):
    storage = bytearray(3)
    for bit in range(bits):
        if value & (1 << bit):
            position = bit_offset + bit
            storage[position // 8] |= 1 << (position % 8)
    return bytes(storage)


def extract_at_bit_offset(storage, bits, bit_offset):
    value = 0
    for bit in range(bits):
        position = bit_offset + bit
        value |= ((storage[position // 8] >> (position % 8)) & 1) << bit
    return value


def exhaustive_bit_position_test(bits):
    mismatches = []
    cases = 0
    for bit_offset in range(8):
        for value in range(1 << bits):
            storage = insert_at_bit_offset(value, bits, bit_offset)
            decoded = extract_at_bit_offset(storage, bits, bit_offset)
            cases += 1
            if decoded != value:
                mismatches.append(
                    {"offset": bit_offset, "value": value, "decoded": decoded}
                )
    return {
        "cases": cases,
        "legal_values": 1 << bits,
        "bit_offsets": list(range(8)),
        "mismatches": len(mismatches),
        "first_mismatches": mismatches[:8],
    }


def pack_row(row, bits, stride):
    payload = bytearray()
    if bits == 7:
        for start in range(0, len(row), 8):
            values = row[start : start + 8]
            word = (
                values[0]
                | values[1] << 7
                | values[2] << 14
                | values[3] << 21
                | values[4] << 28
                | values[5] << 35
                | values[6] << 42
                | values[7] << 49
            )
            payload.extend(word.to_bytes(7, "little"))
    elif bits == 6:
        for start in range(0, len(row), 4):
            values = row[start : start + 4]
            word = values[0] | values[1] << 6 | values[2] << 12 | values[3] << 18
            payload.extend(word.to_bytes(3, "little"))
    else:
        raise ValueError(f"unsupported packed width: {bits}")
    if len(payload) > stride:
        raise ValueError(f"packed payload {len(payload)} exceeds row stride {stride}")
    payload.extend(bytes(stride - len(payload)))
    return bytes(payload)


def unpack_row(packed, count, bits):
    decoded = bytearray()
    if bits == 7:
        for start in range(0, count * 7 // 8, 7):
            word = int.from_bytes(packed[start : start + 7], "little")
            decoded.extend((word >> shift) & 0x7F for shift in range(0, 56, 7))
    elif bits == 6:
        for start in range(0, count * 6 // 8, 3):
            word = int.from_bytes(packed[start : start + 3], "little")
            decoded.extend((word >> shift) & 0x3F for shift in range(0, 24, 6))
    else:
        raise ValueError(f"unsupported packed width: {bits}")
    return bytes(decoded[:count])


def expected_layer_type(config, layer):
    layer_types = config.get("layer_types")
    if layer_types is not None:
        kind = str(layer_types[layer]).lower()
        return "full" if "full" in kind else "sliding"
    return "full" if layer in EXPECTED_FULL_LAYERS else "sliding"


def expected_heads(config, kind, layer):
    per_layer = config.get("num_attention_heads_per_layer")
    if per_layer is not None:
        return int(per_layer[layer])
    if kind == "full":
        return int(config.get("num_attention_heads", 48))
    return int(config.get("sliding_attention_heads", 64))


def validate_config(config):
    if int(config.get("num_hidden_layers", -1)) != NUM_LAYERS:
        raise RuntimeError(f"expected exactly {NUM_LAYERS} hidden layers")
    layer_types = config.get("layer_types")
    per_layer_heads = config.get("num_attention_heads_per_layer")
    if not isinstance(layer_types, list) or len(layer_types) != NUM_LAYERS:
        raise RuntimeError("expected a 40-entry layer_types configuration")
    if not isinstance(per_layer_heads, list) or len(per_layer_heads) != NUM_LAYERS:
        raise RuntimeError("expected a 40-entry num_attention_heads_per_layer configuration")
    full_layers = [layer for layer in range(NUM_LAYERS) if expected_layer_type(config, layer) == "full"]
    if full_layers != EXPECTED_FULL_LAYERS:
        raise RuntimeError(f"unexpected full-attention layer indexes: {full_layers}")
    observed_heads = [expected_heads(config, expected_layer_type(config, layer), layer) for layer in range(NUM_LAYERS)]
    expected = [48 if layer in EXPECTED_FULL_LAYERS else 64 for layer in range(NUM_LAYERS)]
    if observed_heads != expected:
        raise RuntimeError(f"unexpected OProj head streams: {observed_heads}")


def load_process(raw_dir, config):
    candidates = []
    for process_dir in sorted(raw_dir.glob("pid-*")):
        files = [process_dir / f"layer-{layer:02d}.bin" for layer in range(NUM_LAYERS)]
        if all(path.is_file() for path in files):
            trace_path = process_dir / "dispatch.jsonl"
            trace_count = 0
            if trace_path.is_file():
                trace_count = sum(1 for line in trace_path.read_text().splitlines() if line.strip())
            candidates.append((trace_count, process_dir, files))
    if not candidates:
        raise RuntimeError(f"no process directory with all {NUM_LAYERS} banks under {raw_dir}")
    _, process_dir, files = max(candidates, key=lambda item: item[0])

    layers = []
    for layer, path in enumerate(files):
        kind = expected_layer_type(config, layer)
        heads = expected_heads(config, kind, layer)
        groups_per_row = heads * HEAD_DIM // GROUP_SIZE
        expected_bytes = ROWS * groups_per_row
        data = path.read_bytes()
        if len(data) != expected_bytes:
            raise RuntimeError(
                f"layer {layer} {kind}: expected {expected_bytes} bytes, got {len(data)}"
            )
        layers.append(
            {
                "layer": layer,
                "type": kind,
                "heads": heads,
                "groups_per_row": groups_per_row,
                "path": str(path),
                "data": data,
            }
        )
    return process_dir, layers


def parse_trace(process_dir, layers):
    trace_path = process_dir / "dispatch.jsonl"
    if not trace_path.is_file():
        raise RuntimeError(f"missing runtime dispatch trace: {trace_path}")
    records = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    expected_layers = list(range(NUM_LAYERS))
    cycles = []
    for start in range(max(0, len(records) - NUM_LAYERS + 1)):
        window = records[start : start + NUM_LAYERS]
        if [record.get("layer") for record in window] != expected_layers:
            continue
        valid = True
        for layer, record in zip(layers, window):
            expected_label_prefix = f"laguna_oproj_act_h{layer['heads']}_v1"
            raw_label_prefix = f"laguna_gated_affine_oproj_nvfp4_qmv_h{layer['heads']}_v1"
            valid &= record.get("heads") == layer["heads"]
            valid &= record.get("codes_shape") == [ROWS, layer["heads"] * HEAD_DIM // 8]
            valid &= record.get("scales_shape") == [ROWS, layer["groups_per_row"]]
            valid &= record.get("attention_output_shape") == [1, 1, layer["heads"] * HEAD_DIM]
            valid &= record.get("gate_shape") == [1, 1, layer["heads"]]
            valid &= record.get("codes_dtype") == "uint32"
            valid &= record.get("scales_dtype") == "uint8"
            label = record.get("kernel_label", "")
            valid &= label.startswith(expected_label_prefix) or label.startswith(raw_label_prefix)
        if valid:
            cycles.append({"start_record": start, "records": window})
    if not cycles:
        raise RuntimeError("no exact 40-layer one-token OProj NVFP4 contraction cycle in trace")

    first = cycles[0]
    runtime_path = process_dir / "runtime.json"
    runtime = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {}
    label_counts = Counter(record["kernel_label"] for record in first["records"])
    return {
        "trace_path": str(trace_path),
        "record_count": len(records),
        "complete_cycles": len(cycles),
        "selected_cycle_start": first["start_record"],
        "selected_cycle_contractions": len(first["records"]),
        "selected_cycle_layers": [record["layer"] for record in first["records"]],
        "selected_cycle_unique_layers": len({record["layer"] for record in first["records"]}),
        "kernel_label_counts": dict(sorted(label_counts.items())),
        "gate_is_activated_counts": dict(
            sorted(Counter(str(record["gate_is_activated"]).lower() for record in first["records"]).items())
        ),
        "records": first["records"],
        "runtime": runtime,
    }


def analyze_format(layers, bits):
    mask = (1 << bits) - 1
    exhaustive = exhaustive_bit_position_test(bits)
    source_hash = hashlib.sha256()
    encoded_hash = hashlib.sha256()
    decoded_hash = hashlib.sha256()
    layer_results = []
    mismatches = 0
    total_encoded = 0
    total_padding = 0
    total_fallback = 0
    packed_layers = 0

    for layer in layers:
        data = layer["data"]
        source_hash.update(data)
        groups_per_row = layer["groups_per_row"]
        payload_per_row = groups_per_row * bits // 8
        stride = align_up(payload_per_row, ROW_ALIGNMENT)
        legal = max(data) <= mask
        layer_encoded = bytearray()
        layer_decoded = bytearray()
        if legal:
            packed_layers += 1
            for row_index in range(ROWS):
                start = row_index * groups_per_row
                row = data[start : start + groups_per_row]
                packed = pack_row(row, bits, stride)
                decoded = unpack_row(packed, groups_per_row, bits)
                layer_encoded.extend(packed)
                layer_decoded.extend(decoded)
                if decoded != row:
                    mismatches += 1
            padding = ROWS * (stride - payload_per_row)
            fallback = 0
        else:
            layer_encoded.extend(data)
            layer_decoded.extend(data)
            padding = 0
            fallback = len(data)
        encoded_hash.update(layer_encoded)
        decoded_hash.update(layer_decoded)
        total_encoded += len(layer_encoded)
        total_padding += padding
        total_fallback += fallback
        layer_results.append(
            {
                "layer": layer["layer"],
                "type": layer["type"],
                "heads": layer["heads"],
                "legal": legal,
                "source_bytes": len(data),
                "payload_bytes_per_row": payload_per_row if legal else None,
                "row_stride_bytes": stride if legal else groups_per_row,
                "padding_bytes": padding,
                "fallback_bytes": fallback,
                "encoded_bytes": len(layer_encoded),
                "source_sha256": sha256(data),
                "encoded_sha256": sha256(layer_encoded),
                "decoded_sha256": sha256(layer_decoded),
            }
        )

    source_bytes = sum(len(layer["data"]) for layer in layers)
    ideal_encoded = source_bytes * bits // 8
    ideal_savings = source_bytes - ideal_encoded
    metadata_bytes = len(layers)
    gpu_savings = source_bytes - total_encoded
    storage_savings = gpu_savings - metadata_bytes
    return {
        "bits": bits,
        "mask": mask,
        "bit_order": "LSB-first within each value and row-local byte stream",
        "row_alignment_bytes": ROW_ALIGNMENT,
        "tail_rule": "fixed row widths end on byte boundaries; zero padding to 32-byte row stride",
        "fallback_rule": "retain the entire layer as U8 when any scale exceeds the mask",
        "format_tag_metadata": "one CPU-side byte per layer; not fetched by the GPU contraction",
        "exhaustive": exhaustive,
        "observed_row_roundtrip_mismatches": mismatches,
        "source_sha256": source_hash.hexdigest(),
        "encoded_sha256": encoded_hash.hexdigest(),
        "decoded_sha256": decoded_hash.hexdigest(),
        "decoded_matches_source_hash": decoded_hash.hexdigest() == source_hash.hexdigest(),
        "source_bytes_per_token": source_bytes,
        "ideal_encoded_bytes_per_token": ideal_encoded,
        "ideal_gpu_bytes_saved_per_token": ideal_savings,
        "ideal_gpu_mib_saved_per_token": ideal_savings / (1024 * 1024),
        "encoded_gpu_bytes_per_token": total_encoded,
        "padding_bytes_per_token": total_padding,
        "fallback_bytes_per_token": total_fallback,
        "metadata_bytes_resident_cpu": metadata_bytes,
        "packed_layers": packed_layers,
        "fallback_layers": len(layers) - packed_layers,
        "gpu_bytes_saved_per_token": gpu_savings,
        "total_storage_bytes_saved": storage_savings,
        "gpu_mib_saved_per_token": gpu_savings / (1024 * 1024),
        "layers": layer_results,
    }


def build_report(raw_dir, config_path):
    config = json.loads(config_path.read_text())
    validate_config(config)
    process_dir, layers = load_process(raw_dir, config)
    trace = parse_trace(process_dir, layers)
    gpu_architecture = trace["runtime"].get("gpu_architecture")
    gpu_generation = trace["runtime"].get("gpu_generation")
    if gpu_generation is None and gpu_architecture:
        match = re.search(r"g(\d+)", gpu_architecture)
        gpu_generation = int(match.group(1)) if match else None

    layer_results = []
    pooled = bytearray()
    by_type = {"full": bytearray(), "sliding": bytearray()}
    row_maxima = {"pooled": [], "full": [], "sliding": []}
    for layer in layers:
        data = layer["data"]
        groups = layer["groups_per_row"]
        maxima = [max(data[row * groups : (row + 1) * groups]) for row in range(ROWS)]
        summary = histogram_summary(data)
        layer_results.append(
            {
                "layer": layer["layer"],
                "type": layer["type"],
                "heads": layer["heads"],
                "source_shape": [ROWS, layer["heads"] * HEAD_DIM],
                "scale_shape": [ROWS, groups],
                "scale_bytes": len(data),
                "min": summary["min"],
                "max": summary["max"],
                "count_0_63": summary["count_0_63"],
                "count_64_127": summary["count_64_127"],
                "count_128_255": summary["count_128_255"],
                "count_gt_63": summary["count_gt_63"],
                "count_gt_127": summary["count_gt_127"],
                "fraction_0_63": summary["fraction_0_63"],
                "fraction_0_127": summary["fraction_0_127"],
                "row_max_quantiles": quantiles(maxima),
                "rows_max_gt_63": sum(value > 63 for value in maxima),
                "rows_max_gt_127": sum(value > 127 for value in maxima),
                "sha256": sha256(data),
            }
        )
        pooled.extend(data)
        by_type[layer["type"]].extend(data)
        row_maxima["pooled"].extend(maxima)
        row_maxima[layer["type"]].extend(maxima)

    distributions = {"pooled": histogram_summary(pooled)}
    distributions.update({kind: histogram_summary(data) for kind, data in by_type.items()})
    row_max_report = {}
    for kind, values in row_maxima.items():
        row_max_report[kind] = {
            "count": len(values),
            "quantiles": quantiles(values),
            "rows_max_gt_63": sum(value > 63 for value in values),
            "rows_max_gt_127": sum(value > 127 for value in values),
        }

    formats = {str(bits): analyze_format(layers, bits) for bits in (7, 6)}
    expected_full_bytes = len(EXPECTED_FULL_LAYERS) * ROWS * (48 * HEAD_DIM // GROUP_SIZE)
    expected_sliding_bytes = len(EXPECTED_SLIDING_LAYERS) * ROWS * (64 * HEAD_DIM // GROUP_SIZE)
    expected_total_bytes = expected_full_bytes + expected_sliding_bytes
    if len(pooled) != expected_total_bytes:
        raise RuntimeError(f"expected {expected_total_bytes} pooled bytes, got {len(pooled)}")

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    gate_7 = formats["7"]["fallback_layers"] == 0 and formats["7"]["gpu_bytes_saved_per_token"] >= 4 * 1024 * 1024
    gate_6 = formats["6"]["fallback_layers"] == 0 and formats["6"]["gpu_bytes_saved_per_token"] >= 8 * 1024 * 1024
    recommendation = (
        "prioritize_6bit_prototype" if gate_6 else "prioritize_7bit_prototype" if gate_7 else "no_prototype"
    )
    report = {
        "schema_version": 1,
        "assignment": {
            "base_commit": "446762e6c04e9e79f1a77756bbda0d0da92c147d",
            "measurement_commit": commit,
            "pr_number": 515,
            "audit_only": True,
        },
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "hardware_model": command_output("sysctl", "-n", "hw.model"),
            "chip": command_output("sysctl", "-n", "machdep.cpu.brand_string"),
            "os_version": command_output("sw_vers", "-productVersion"),
            "runtime_gpu_architecture": gpu_architecture,
            "runtime_gpu_generation": gpu_generation,
            "runtime_pid": trace["runtime"].get("pid"),
        },
        "reproduction": {
            "measurement": "bash research/run_oproj_scale_census.sh",
            "analysis": "python3 research/oproj_scale_census.py",
            "wandb_upload": "python3 research/oproj_scale_census.py --wandb-only",
        },
        "source": {
            "raw_process_dir": str(process_dir),
            "config": str(config_path),
            "layers": NUM_LAYERS,
            "full_layer_count": len(EXPECTED_FULL_LAYERS),
            "sliding_layer_count": len(EXPECTED_SLIDING_LAYERS),
            "full_layers": EXPECTED_FULL_LAYERS,
            "sliding_layers": EXPECTED_SLIDING_LAYERS,
            "rows_per_layer": ROWS,
            "head_dim": HEAD_DIM,
            "group_size": GROUP_SIZE,
            "full_scale_bytes_per_token": expected_full_bytes,
            "sliding_scale_bytes_per_token": expected_sliding_bytes,
            "total_scale_bytes_per_token": expected_total_bytes,
            "pooled_sha256": sha256(pooled),
        },
        "layers": layer_results,
        "distributions": distributions,
        "row_maxima": row_max_report,
        "reachability": trace,
        "formats": formats,
        "decision": {
            "seven_bit_gate": gate_7,
            "six_bit_gate": gate_6,
            "recommendation": recommendation,
            "qkv_assignment_provided_deletion_bytes": QKV_DELETION_BYTES,
            "qkv_evidence_source": "assignment-provided PR #514 deletion only; no cross-branch inspection",
        },
        "static_kernel_risk": {
            "current": {
                "scale_loads_per_32_groups": 32,
                "unique_scale_bytes_per_32_groups": 32,
                "decode": "one U8 load, left shift by 7, half bitcast, float conversion",
                "coalescing": "32 lanes read 32 adjacent row-major scale bytes per 512-K block",
            },
            "7bit": {
                "unique_scale_bytes_per_32_groups": 28,
                "naive_conditional_byte_loads_per_32_groups": 56,
                "bit_start_cycle": list(range(8)),
                "extra_integer_work": "bit offset, byte address, one variable shift, one mask, conditional second byte",
                "register_risk": "approximately 2-3 additional integer temporaries per lane",
                "coalescing_risk": "overlapping loads cover 28 contiguous bytes; H48 rows require 16 bytes of 32-byte alignment padding",
            },
            "6bit": {
                "unique_scale_bytes_per_32_groups": 24,
                "naive_conditional_byte_loads_per_32_groups": 48,
                "bit_start_cycle": [0, 6, 4, 2],
                "extra_integer_work": "bit offset, byte address, one variable shift, one mask, conditional second byte",
                "register_risk": "approximately 2-3 additional integer temporaries per lane",
                "coalescing_risk": "overlapping loads cover 24 contiguous bytes; all row strides remain 32-byte aligned",
            },
            "transfer_conclusion": "OProj bit-packing trades scale traffic for per-scale extraction on the hot contraction; assignment-provided QKV deletion removes 6,225,920 bytes without this row-local unpack path, so measured transfer is uncertain.",
        },
    }
    return report


def render_markdown(report):
    source = report["source"]
    pooled = report["distributions"]["pooled"]
    rows = report["row_maxima"]["pooled"]
    reach = report["reachability"]
    lines = [
        "# Decode OProj NVFP4 Scale Census",
        "",
        f"- Measurement commit: `{report['assignment']['measurement_commit']}`",
        f"- Host: `{report['host']['hardware_model']}` / `{report['host']['chip']}` / macOS `{report['host']['os_version']}`",
        f"- Runtime GPU architecture / generation: `{report['host']['runtime_gpu_architecture']}` / `{report['host']['runtime_gpu_generation']}`",
        f"- Complete one-token 40-layer cycles: {reach['complete_cycles']}",
        f"- Selected cycle contractions / unique layers: {reach['selected_cycle_contractions']} / {reach['selected_cycle_unique_layers']}",
        f"- Retained U8 scale bytes, sliding / full / total: {source['sliding_scale_bytes_per_token']:,} / {source['full_scale_bytes_per_token']:,} / {source['total_scale_bytes_per_token']:,}",
        f"- Pooled scale range: {pooled['min']}..{pooled['max']}",
        f"- Scale counts 0..63 / 64..127 / 128..255: {pooled['count_0_63']:,} / {pooled['count_64_127']:,} / {pooled['count_128_255']:,}",
        f"- Explicit scale counts >63 / >127: {pooled['count_gt_63']:,} / {pooled['count_gt_127']:,}",
        f"- Row-max p50 / p90 / p99 / max: {rows['quantiles']['p50']} / {rows['quantiles']['p90']} / {rows['quantiles']['p99']} / {rows['quantiles']['max']}",
        f"- Rows with max >63 / >127: {rows['rows_max_gt_63']:,} / {rows['rows_max_gt_127']:,}",
        "",
        "## Reachability",
        "",
        "| Kernel label | Layers in selected token |",
        "|---|---:|",
    ]
    for label, count in reach["kernel_label_counts"].items():
        lines.append(f"| `{label}` | {count} |")
    lines.extend(
        [
            "",
            "The selected trace window contains consecutive layers 0..39 exactly once, with B=L=1 shapes, H48 on full-attention layers, H64 on sliding layers, UInt32 codes, and UInt8 scales.",
            "",
            "## Layer census",
            "",
            "| Layer | Type | Heads | Scale shape | Min | Max | <=63 | 64..127 | >=128 | Rows >63 | Rows >127 |",
            "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for layer in report["layers"]:
        lines.append(
            f"| {layer['layer']} | {layer['type']} | {layer['heads']} | {layer['scale_shape']} | {layer['min']} | {layer['max']} | {layer['count_0_63']:,} | {layer['count_64_127']:,} | {layer['count_128_255']:,} | {layer['rows_max_gt_63']:,} | {layer['rows_max_gt_127']:,} |"
        )
    lines.extend(
        [
            "",
            "## Packing audit",
            "",
            "Row-local values are serialized LSB-first and each row starts on a 32-byte boundary. A one-byte CPU format tag per layer selects packed versus whole-layer U8 fallback; no GPU metadata is fetched. The decoder never reads beyond a row.",
            "",
            "| Bits | Packed / fallback layers | Ideal bytes | Ideal saved | Real GPU bytes | Padding | Fallback bytes | Real saved | MiB saved | Metadata | Exhaustive cases | Mismatches | Hash match |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for bits in (7, 6):
        fmt = report["formats"][str(bits)]
        lines.append(
            f"| {bits} | {fmt['packed_layers']} / {fmt['fallback_layers']} | {fmt['ideal_encoded_bytes_per_token']:,} | {fmt['ideal_gpu_bytes_saved_per_token']:,} | {fmt['encoded_gpu_bytes_per_token']:,} | {fmt['padding_bytes_per_token']:,} | {fmt['fallback_bytes_per_token']:,} | {fmt['gpu_bytes_saved_per_token']:,} | {fmt['gpu_mib_saved_per_token']:.3f} | {fmt['metadata_bytes_resident_cpu']} B CPU | {fmt['exhaustive']['cases']:,} | {fmt['observed_row_roundtrip_mismatches']} | {fmt['decoded_matches_source_hash']} |"
        )
    lines.extend(
        [
            "",
            "## Static execution risk",
            "",
            "- Current path: one U8 scale load per lane and 32 adjacent scale bytes per 32 groups, followed by the existing left-shift/half decode.",
            "- 7-bit: 28 unique bytes but 56 naive conditional byte-load instructions per 32 groups, all eight bit starts, variable shift/mask, and 16 bytes H48 row padding for 32-byte alignment.",
            "- 6-bit: 24 unique bytes but 48 naive conditional byte-load instructions per 32 groups, bit-start cycle 0/6/4/2, variable shift/mask, and aligned H48/H64 row strides.",
            "- Both add roughly 2-3 integer temporaries per lane; physical bandwidth may fall while load-instruction and register pressure rise.",
            f"- Assignment-provided QKV scale-bank deletion is {report['decision']['qkv_assignment_provided_deletion_bytes']:,} bytes; no PR #514 branch or code was inspected.",
            "",
            "## Decision",
            "",
            f"- 7-bit gate: **{report['decision']['seven_bit_gate']}**",
            f"- 6-bit gate: **{report['decision']['six_bit_gate']}**",
            f"- Recommendation: **{report['decision']['recommendation']}**",
            "",
            "## Reproduction",
            "",
            f"- Measurement: `{report['reproduction']['measurement']}`",
            f"- Analysis: `{report['reproduction']['analysis']}`",
            f"- W&B upload: `{report['reproduction']['wandb_upload']}`",
            "",
            "Full 256-bin pooled/full/sliding histograms, per-layer hashes, trace records, and per-format hashes are in `research/oproj_scale_census.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def log_wandb(report, json_path, md_path, output_path):
    import wandb

    decision = report["decision"]
    pooled = report["distributions"]["pooled"]
    rows = report["row_maxima"]["pooled"]
    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-cedar",
        job_type="audit",
        name="oproj-scale-census-pr515",
        config={
            "pr_number": 515,
            "base_commit": report["assignment"]["base_commit"],
            "measurement_commit": report["assignment"]["measurement_commit"],
            "gpu_architecture": report["host"]["runtime_gpu_architecture"],
            "gpu_generation": report["host"]["runtime_gpu_generation"],
            "audit_only": True,
            "row_alignment_bytes": ROW_ALIGNMENT,
            "qkv_assignment_provided_deletion_bytes": QKV_DELETION_BYTES,
        },
    )
    metrics = {
        "audit/layers": report["source"]["layers"],
        "audit/scale_bytes_per_token": report["source"]["total_scale_bytes_per_token"],
        "audit/scale_min": pooled["min"],
        "audit/scale_max": pooled["max"],
        "audit/scales_gt63": pooled["count_64_127"] + pooled["count_128_255"],
        "audit/scales_gt127": pooled["count_128_255"],
        "audit/rows_max_gt63": rows["rows_max_gt_63"],
        "audit/rows_max_gt127": rows["rows_max_gt_127"],
        "audit/complete_decode_cycles": report["reachability"]["complete_cycles"],
        "audit/roundtrip_mismatches_7bit": report["formats"]["7"]["observed_row_roundtrip_mismatches"],
        "audit/roundtrip_mismatches_6bit": report["formats"]["6"]["observed_row_roundtrip_mismatches"],
        "audit/7bit_ideal_gpu_bytes_saved_per_token": report["formats"]["7"]["ideal_gpu_bytes_saved_per_token"],
        "audit/6bit_ideal_gpu_bytes_saved_per_token": report["formats"]["6"]["ideal_gpu_bytes_saved_per_token"],
        "audit/7bit_encoded_gpu_bytes_per_token": report["formats"]["7"]["encoded_gpu_bytes_per_token"],
        "audit/6bit_encoded_gpu_bytes_per_token": report["formats"]["6"]["encoded_gpu_bytes_per_token"],
        "audit/7bit_gpu_bytes_saved_per_token": report["formats"]["7"]["gpu_bytes_saved_per_token"],
        "audit/6bit_gpu_bytes_saved_per_token": report["formats"]["6"]["gpu_bytes_saved_per_token"],
        "audit/7bit_gate": int(decision["seven_bit_gate"]),
        "audit/6bit_gate": int(decision["six_bit_gate"]),
    }
    run.log(metrics)
    for key, value in metrics.items():
        run.summary[key] = value
    artifact = wandb.Artifact("oproj-scale-census-pr515", type="audit")
    artifact.add_file(str(json_path))
    artifact.add_file(str(md_path))
    run.log_artifact(artifact)
    run_id = run.id
    run_url = run.url
    run.finish()
    metadata = {"run_id": run_id, "url": run_url, "state": "finished"}
    output_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"WANDB_RUN_ID={run_id}")
    print(f"WANDB_RUN_URL={run_url}")


def main():
    args = parse_args()
    if args.extract_stderr:
        if args.wandb or args.wandb_only:
            raise SystemExit("--extract-stderr cannot be combined with W&B upload")
        extract_stderr(args.extract_stderr, args.raw_dir)
        return
    if args.wandb and args.wandb_only:
        raise SystemExit("--wandb and --wandb-only are mutually exclusive")
    if args.wandb_only:
        report = json.loads(args.output_json.read_text())
        log_wandb(report, args.output_json, args.output_md, args.wandb_output)
        return

    report = build_report(args.raw_dir, args.config)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output_md.write_text(render_markdown(report))
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(json.dumps(report["decision"], sort_keys=True))
    if args.wandb:
        log_wandb(report, args.output_json, args.output_md, args.wandb_output)


if __name__ == "__main__":
    main()
