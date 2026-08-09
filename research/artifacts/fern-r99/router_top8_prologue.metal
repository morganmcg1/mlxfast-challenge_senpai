METAL_FUNC uint laguna_router_top8_extract_round(
    thread const uint* keys, thread uint& mask, uint lane) {
    uint best_ordinal = 0xFFFFFFFFu;
    uint best_index = 256u;
    for (uint j = 0; j < 8; ++j) {
        if ((mask & (1u << j)) != 0u) continue;
        uint e = lane + 32u * j;
        uint o = keys[j];
        if (laguna_router_ordinal_before(o, e, best_ordinal, best_index)) {
            best_ordinal = o;
            best_index = e;
        }
    }
    // Transport the comparator's (ordinal, expert-index) state as one uint2
    // through each butterfly step. simd_shuffle_xor moves both components
    // bit-for-bit from the same source lane; comparator order is unchanged.
    uint2 best_pair = uint2(best_ordinal, best_index);
    for (ushort offset = 16; offset > 0; offset >>= 1) {
        const uint2 other_pair = simd_shuffle_xor(best_pair, offset);
        if (laguna_router_ordinal_before(
            other_pair.x, other_pair.y, best_pair.x, best_pair.y)) {
            best_pair = other_pair;
        }
    }
    best_index = best_pair.y;
    if ((best_index & 31u) == lane) {
        mask |= 1u << (best_index >> 5u);
    }
    return best_index;
}