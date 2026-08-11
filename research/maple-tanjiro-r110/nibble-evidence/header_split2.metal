===QMVHEADER_BEGIN split=2===
static inline float laguna_nvfp4_scale(uint8_t bits) {
if (bits < 16u) {
    ushort fast_raw = ushort(bits) << 7;
    return float(as_type<half>(fast_raw));
}
    ushort raw = ushort(uint(bits) << 7);
    half converted = as_type<half>(raw);
    half signed_value = converted;
        return float(signed_value);
}

static inline float laguna_nvfp4_qdot_codes_16(
    uint2 codes,
    const thread float* input,
    float scale
) {
    float accum;
    {
        const uint c = codes.x;
        const uint p0 =
            ((c << 9) & 0x0E000E00u) | ((c << 12) & 0x80008000u);
        const uint p1 =
            ((c << 5) & 0x0E000E00u) | ((c << 8) & 0x80008000u);
        const uint p2 =
            ((c << 1) & 0x0E000E00u) | ((c << 4) & 0x80008000u);
        const uint p3 =
            ((c >> 3) & 0x0E000E00u) | (c & 0x80008000u);
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum =
            (input[0] * v04.x +
             input[1] * v15.x +
             input[2] * v26.x +
             input[3] * v37.x);
        accum +=
            (input[4] * v04.y +
             input[5] * v15.y +
             input[6] * v26.y +
             input[7] * v37.y);
    }
    {
        const uint c = codes.y;
        const uint p0 =
            ((c << 9) & 0x0E000E00u) | ((c << 12) & 0x80008000u);
        const uint p1 =
            ((c << 5) & 0x0E000E00u) | ((c << 8) & 0x80008000u);
        const uint p2 =
            ((c << 1) & 0x0E000E00u) | ((c << 4) & 0x80008000u);
        const uint p3 =
            ((c >> 3) & 0x0E000E00u) | (c & 0x80008000u);
        const float2 v04 = float2(as_type<half2>(p0));
        const float2 v15 = float2(as_type<half2>(p1));
        const float2 v26 = float2(as_type<half2>(p2));
        const float2 v37 = float2(as_type<half2>(p3));
        accum +=
            (input[8] * v04.x +
             input[9] * v15.x +
             input[10] * v26.x +
             input[11] * v37.x);
        accum +=
            (input[12] * v04.y +
             input[13] * v15.y +
             input[14] * v26.y +
             input[15] * v37.y);
    }
    return scale * accum;
}

static inline float laguna_nvfp4_qdot_16(
    const device uint8_t* weight,
    const thread float* input,
    float scale
) {
    const device uint2* packed = (const device uint2*)weight;
    return laguna_nvfp4_qdot_codes_16(packed[0], input, scale);
}
===QMVHEADER_END===
