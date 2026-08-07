# Relocated commentary — `BaseConfiguration.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/BaseConfiguration.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `63ab67c8`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `BaseConfiguration`

_relocated from lines 7-12 at base 63ab67c8_


`BaseConfiguration` provides the metadata necessary to identify the model architecture
(`modelType`) and describes the quantization parameters used to compress the model's weights.
It is designed to be decoded directly from a model repository's `config.json`.

Typically used the ``GenericModelFactory`` implementations during load.

## `Quantization`

_relocated from lines 19-21 at base 63ab67c8_


MLX uses group-wise quantization to reduce memory footprint. This struct
defines how weights are grouped and the precision (bits) used for each group.

## `line27`

_relocated from lines 25-27 at base 63ab67c8_

- Parameters:
  - groupSize: The number of weights that share the same scale and bias.
  - bits: The bit-depth of the quantized weights (e.g., 4 or 8).

## `mode`

_relocated from lines 43-45 at base 63ab67c8_


Affine quantization (asymmetric) uses both a scale and a zero-point
to map floating point values to integers.

## `PerLayerQuantization`

_relocated from lines 67-70 at base 63ab67c8_


This allows for "Mixed-Precision" or "Heterogeneous" quantization, where
sensitive layers (like the embedding head) can be kept at higher precision
while the rest of the model is compressed.

## `quantization`

_relocated from lines 87-88 at base 63ab67c8_

- Parameter layer: The path/name of the layer.
- Returns: The `Quantization` settings to apply, or `nil` if the layer should be skipped.

## `QuantizationContainer`

_relocated from lines 104-118 at base 63ab67c8_


```
"quantization": {
    "group_size": 64,
    "bits": 4,
    "model.embed_tokens": {
        "group_size": 32,
        "bits": 4
    },
    "model.layers.0.self_attn.q_norm": false,
```

Quantization configs in MLX often interleave global keys (like `bits`) with
specific layer keys (like `model.layers.0...`). This container uses manual
decoding to separate these interleaved values.
