#!/usr/bin/env python3

import argparse
import json
import mmap
import re
import struct
from collections import Counter
from pathlib import Path

GATE_PATTERN = re.compile(r"model\.layers\.(\d+)\.mlp\.gate\.weight$")
ROWS = 256
COLUMNS = 2048
RAW_ROW_BYTES = COLUMNS * 2
COMPACT_ROW_BYTES = COLUMNS + COLUMNS // 2 + 16
OFFSET_BYTES_PER_ROW = 4
BANDWIDTH_BYTES_PER_SECOND = 140.2e9


def padded_header(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


def index_serializer(raw, data):
    variants = (
        lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(),
        lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n",
        lambda value: json.dumps(value, ensure_ascii=False, indent=2).encode(),
        lambda value: json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n",
        lambda value: json.dumps(value, ensure_ascii=False, indent=4).encode(),
        lambda value: json.dumps(
            value, ensure_ascii=False, indent=2, separators=(",", " : ")
        ).encode(),
    )
    for serializer in variants:
        if serializer(data) == raw:
            return serializer
    raise ValueError("unrecognized model.safetensors.index.json formatting")


def read_header(path):
    with path.open("rb") as handle:
        header_size = struct.unpack("<Q", handle.read(8))[0]
        raw_header = handle.read(header_size)
    return header_size, raw_header, json.loads(raw_header)


def target_layer(name, metadata):
    match = GATE_PATTERN.fullmatch(name)
    if not match:
        return None
    if metadata.get("dtype") != "BF16" or metadata.get("shape") != [ROWS, COLUMNS]:
        return None
    return int(match.group(1))


def load_index(weights):
    return json.loads((weights / "model.safetensors.index.json").read_bytes())


def read_tensor(weights, index, name, dtype, shape=None):
    shard = weights / index["weight_map"][name]
    header_size, _, header = read_header(shard)
    metadata = header[name]
    if metadata.get("dtype") != dtype:
        raise ValueError(f"unexpected dtype for {name}: {metadata.get('dtype')}")
    if shape is not None and metadata.get("shape") != shape:
        raise ValueError(f"unexpected shape for {name}: {metadata.get('shape')}")
    start, end = metadata["data_offsets"]
    with shard.open("rb") as handle:
        handle.seek(8 + header_size + start)
        tensor = handle.read(end - start)
    if len(tensor) != end - start:
        raise ValueError(f"truncated tensor data for {name}")
    return tensor, metadata


def verify_roundtrip(reference, transformed):
    reference_index = load_index(reference)
    transformed_index = load_index(transformed)
    tensor_names = sorted(
        (name for name in reference_index["weight_map"] if GATE_PATTERN.fullmatch(name)),
        key=lambda name: int(GATE_PATTERN.fullmatch(name).group(1)),
    )
    layers = [int(GATE_PATTERN.fullmatch(name).group(1)) for name in tensor_names]
    if layers != list(range(1, 40)):
        raise ValueError(f"expected sparse layers 1...39, found {layers}")

    compact_rows = 0
    fallback_rows = 0
    reconstructed_words = 0
    for name in tensor_names:
        raw, _ = read_tensor(reference, reference_index, name, "BF16", [ROWS, COLUMNS])
        payload, payload_metadata = read_tensor(
            transformed, transformed_index, name, "U8"
        )
        if payload_metadata.get("shape") != [len(payload)]:
            raise ValueError(f"unexpected payload shape for {name}: {payload_metadata.get('shape')}")
        offsets, _ = read_tensor(
            transformed,
            transformed_index,
            f"{name}_row_offsets",
            "U32",
            [ROWS],
        )
        tagged_offsets = struct.unpack(f"<{ROWS}I", offsets)
        cursor = 0
        for row, tagged_offset in enumerate(tagged_offsets):
            fallback = tagged_offset & 0x80000000 != 0
            start = tagged_offset & 0x7FFFFFFF
            next_start = (
                tagged_offsets[row + 1] & 0x7FFFFFFF if row + 1 < ROWS else len(payload)
            )
            expected_size = RAW_ROW_BYTES if fallback else COMPACT_ROW_BYTES
            if start != cursor or next_start - start != expected_size:
                raise ValueError(
                    f"invalid row span for {name} row {row}: "
                    f"start={start}, next={next_start}, expected={expected_size}"
                )

            raw_row = raw[row * RAW_ROW_BYTES : (row + 1) * RAW_ROW_BYTES]
            high_bytes = raw_row[1::2]
            palette_values = sorted(set(high_bytes))
            if fallback:
                if len(palette_values) <= 16:
                    raise ValueError(f"unnecessary fallback for {name} row {row}")
                reconstructed = payload[start:next_start]
                fallback_rows += 1
            else:
                if len(palette_values) > 16:
                    raise ValueError(f"ineligible compact row for {name} row {row}")
                lows = payload[start : start + COLUMNS]
                packed = payload[start + COLUMNS : start + COLUMNS + COLUMNS // 2]
                palette = payload[start + COLUMNS + COLUMNS // 2 : next_start]
                expected_palette = bytes(palette_values + [0] * (16 - len(palette_values)))
                if palette != expected_palette:
                    raise ValueError(f"noncanonical palette for {name} row {row}")
                reconstructed = bytearray(RAW_ROW_BYTES)
                reconstructed[0::2] = lows
                reconstructed[1::2] = bytes(
                    palette[(packed[column // 2] >> (4 * (column & 1))) & 0xF]
                    for column in range(COLUMNS)
                )
                compact_rows += 1
            if reconstructed != raw_row:
                raise ValueError(f"roundtrip mismatch for {name} row {row}")
            reconstructed_words += COLUMNS
            cursor = next_start
        if cursor != len(payload):
            raise ValueError(f"unreferenced payload bytes for {name}: {len(payload) - cursor}")

    return {
        "reference": str(reference),
        "transformed": str(transformed),
        "layers": len(tensor_names),
        "rows": len(tensor_names) * ROWS,
        "compact_rows": compact_rows,
        "fallback_rows": fallback_rows,
        "reconstructed_bf16_words": reconstructed_words,
        "all_words_exact": True,
        "row_spans_contiguous": True,
        "palettes_canonical": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=Path, default=Path("weights"))
    parser.add_argument("--transformed", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    weights = args.weights.resolve()
    files = sorted(path for path in weights.rglob("*") if path.is_file())
    tree_bytes = sum(path.stat().st_size for path in files)
    layers = []
    shard_headers = {}

    for shard in sorted(weights.glob("*.safetensors")):
        header_size, raw_header, header = read_header(shard)
        if padded_header(header) != raw_header:
            raise ValueError(f"unrecognized safetensors header formatting: {shard}")
        shard_headers[shard.name] = (header_size, header)
        with shard.open("rb") as handle:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            data_start = 8 + header_size
            for name, metadata in header.items():
                layer = target_layer(name, metadata)
                if layer is None:
                    continue
                start, end = metadata["data_offsets"]
                tensor = mapped[data_start + start : data_start + end]
                if len(tensor) != ROWS * RAW_ROW_BYTES:
                    raise ValueError(f"unexpected tensor size for {name}: {len(tensor)}")
                cardinalities = []
                for row in range(ROWS):
                    row_start = row * RAW_ROW_BYTES
                    high_bytes = tensor[row_start + 1 : row_start + RAW_ROW_BYTES : 2]
                    cardinalities.append(len(set(high_bytes)))
                histogram = Counter(cardinalities)
                eligible = sum(count for cardinality, count in histogram.items() if cardinality <= 16)
                layers.append(
                    {
                        "layer": layer,
                        "tensor": name,
                        "shard": shard.name,
                        "row_cardinalities": cardinalities,
                        "cardinality_histogram": dict(sorted(histogram.items())),
                        "eligible_rows": eligible,
                        "fallback_rows": ROWS - eligible,
                    }
                )
            mapped.close()

    layers.sort(key=lambda item: item["layer"])
    if len(layers) != 39 or [item["layer"] for item in layers] != list(range(1, 40)):
        raise ValueError(f"expected sparse layers 1...39, found {[item['layer'] for item in layers]}")

    histogram = Counter(
        cardinality for layer in layers for cardinality in layer["row_cardinalities"]
    )
    eligible_rows = sum(item["eligible_rows"] for item in layers)
    fallback_rows = len(layers) * ROWS - eligible_rows
    raw_bytes = len(layers) * ROWS * RAW_ROW_BYTES
    compact_bytes = eligible_rows * COMPACT_ROW_BYTES
    fallback_bytes = fallback_rows * RAW_ROW_BYTES
    row_offset_bytes = len(layers) * ROWS * OFFSET_BYTES_PER_ROW
    candidate_router_bytes = compact_bytes + fallback_bytes + row_offset_bytes
    net_removed_bytes = raw_bytes - candidate_router_bytes

    candidate_shard_sizes = {}
    candidate_tensor_data_bytes = 0
    safetensors_header_delta = 0
    for shard_name, (old_header_size, header) in shard_headers.items():
        new_header = {}
        cursor = 0
        for name, metadata in header.items():
            if name == "__metadata__":
                new_header[name] = metadata
                continue
            layer = target_layer(name, metadata)
            if layer is None:
                size = metadata["data_offsets"][1] - metadata["data_offsets"][0]
                replacement = dict(metadata)
                replacement["data_offsets"] = [cursor, cursor + size]
                new_header[name] = replacement
                cursor += size
                continue
            layer_data = layers[layer - 1]
            payload_size = (
                layer_data["eligible_rows"] * COMPACT_ROW_BYTES
                + layer_data["fallback_rows"] * RAW_ROW_BYTES
            )
            new_header[name] = {
                "dtype": "U8",
                "shape": [payload_size],
                "data_offsets": [cursor, cursor + payload_size],
            }
            cursor += payload_size
            offsets_name = f"{name}_row_offsets"
            new_header[offsets_name] = {
                "dtype": "U32",
                "shape": [ROWS],
                "data_offsets": [cursor, cursor + ROWS * OFFSET_BYTES_PER_ROW],
            }
            cursor += ROWS * OFFSET_BYTES_PER_ROW
        new_header_size = len(padded_header(new_header))
        candidate_shard_sizes[shard_name] = 8 + new_header_size + cursor
        candidate_tensor_data_bytes += cursor
        safetensors_header_delta += new_header_size - old_header_size

    index_path = weights / "model.safetensors.index.json"
    raw_index = index_path.read_bytes()
    index = json.loads(raw_index)
    serialize_index = index_serializer(raw_index, index)
    new_weight_map = {}
    for name, shard_name in index["weight_map"].items():
        new_weight_map[name] = shard_name
        metadata = shard_headers[shard_name][1].get(name)
        if metadata is not None and target_layer(name, metadata) is not None:
            new_weight_map[f"{name}_row_offsets"] = shard_name
    new_index = dict(index)
    new_index["metadata"] = dict(index.get("metadata", {}))
    new_index["metadata"]["total_size"] = candidate_tensor_data_bytes
    new_index["weight_map"] = new_weight_map
    candidate_index_bytes = len(serialize_index(new_index))
    index_delta = candidate_index_bytes - len(raw_index)

    current_shard_bytes = sum((weights / name).stat().st_size for name in shard_headers)
    candidate_shard_bytes = sum(candidate_shard_sizes.values())
    projected_tree_bytes = (
        tree_bytes - current_shard_bytes - len(raw_index)
        + candidate_shard_bytes + candidate_index_bytes
    )

    result = {
        "schema_version": 1,
        "weights": str(weights),
        "representation": {
            "eligible_row": {
                "low_bytes": COLUMNS,
                "packed_high_byte_indices": COLUMNS // 2,
                "high_byte_palette": 16,
                "total_bytes": COMPACT_ROW_BYTES,
            },
            "fallback_row_bytes": RAW_ROW_BYTES,
            "row_metadata": "one U32 byte offset with high bit marking raw fallback",
            "row_metadata_bytes": row_offset_bytes,
            "alignment_bytes": 0,
            "palette_order": "ascending unsigned high byte",
        },
        "census": {
            "sparse_layers": len(layers),
            "rows_per_layer": ROWS,
            "total_rows": len(layers) * ROWS,
            "cardinality_histogram": dict(sorted(histogram.items())),
            "eligible_rows": eligible_rows,
            "fallback_rows": fallback_rows,
            "eligible_row_percentage": eligible_rows / (len(layers) * ROWS) * 100,
            "layers": layers,
        },
        "payload": {
            "raw_router_bytes": raw_bytes,
            "compact_eligible_bytes": compact_bytes,
            "raw_fallback_bytes": fallback_bytes,
            "metadata_bytes": row_offset_bytes,
            "candidate_router_bytes": candidate_router_bytes,
            "gross_removed_weight_bytes": raw_bytes - compact_bytes - fallback_bytes,
            "net_removed_payload_bytes_per_decode_token": net_removed_bytes,
            "bandwidth_bytes_per_second": BANDWIDTH_BYTES_PER_SECOND,
            "bandwidth_only_saving_us_per_token": net_removed_bytes
            / BANDWIDTH_BYTES_PER_SECOND
            * 1e6,
        },
        "tree": {
            "current_exact_bytes": tree_bytes,
            "current_gib": tree_bytes / 1024**3,
            "candidate_tensor_data_bytes": candidate_tensor_data_bytes,
            "safetensors_header_delta_bytes": safetensors_header_delta,
            "index_delta_bytes": index_delta,
            "projected_exact_bytes": projected_tree_bytes,
            "projected_gib": projected_tree_bytes / 1024**3,
            "cap_bytes": 25 * 1024**3,
            "candidate_shard_sizes": candidate_shard_sizes,
            "candidate_index_bytes": candidate_index_bytes,
        },
        "gate": {
            "eligible_at_least_80_percent": eligible_rows * 5 >= len(layers) * ROWS * 4,
            "saving_more_than_55_us": net_removed_bytes / BANDWIDTH_BYTES_PER_SECOND * 1e6 > 55,
            "tree_at_most_25_gib": projected_tree_bytes <= 25 * 1024**3,
        },
    }
    if args.transformed:
        result["roundtrip"] = verify_roundtrip(weights, args.transformed.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
