"""Generate Part-0 bound-identification variants from a rendered probe kernel.

usage: python3 diag.py probe_orig.metal

All variants produce deliberately wrong output; only their timing is meaningful.
Each is a minimal textual delta from the shipped kernel so the instruction
stream stays comparable.

  probe_ctl.metal    byte-different, compile-identical control (comment only)
  probe_d1.metal     kv_head forced to 0: issued bytes unchanged, unique bytes
                     2.097 -> 0.262 MB per layer, everything L2-hot
  probe_d2.metal     loads intact, online softmax deleted (adds only)
  probe_d3.metal     arithmetic intact, ring pointer advance masked by
                     params[1] (== 0 at runtime) so every load hits the same
                     two rows and is L1-hot; the mask is opaque to the
                     compiler, so the loads cannot be hoisted or CSE'd
"""
import sys

src = open(sys.argv[1]).read()

LOOP_START = "        int i = sg;\n"
LOOP_END = "        // Combine:"


def loop_body(text):
    head, rest = text.split(LOOP_START, 1)
    body, tail = rest.split(LOOP_END, 1)
    return head, body, LOOP_END + tail


def write(name, text):
    open(name, "w").write(text)
    print("%s (%d bytes)" % (name, len(text)))


write("probe_ctl.metal", "// compile-identical control\n" + src)

d1 = src.replace(
    "uint kv_head = head0 / gqa;", "uint kv_head = 0; // DIAG1")
assert d1 != src
write("probe_d1.metal", d1)

head, body, tail = loop_body(src)
d2_body = """        for (; i + BN < N; i += 2 * BN) {
            const device bfloat* pipe_keys_b = pair_keys + inner_k_stride;
            const device bfloat* pipe_values_b = pair_values + inner_v_stride;
            const bool sub_a = uint(i) == widx;
            const bool sub_b = uint(i + BN) == widx;
            U pipe_ka[4];
            U pipe_kb[4];
            T_LOAD_K(pipe_ka, sub_a, pair_keys);
            T_LOAD_K(pipe_kb, sub_b, pipe_keys_b);
            bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
            bfloat pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3;
            T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
                pair_values);
            T_LOAD_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3, sub_b,
                pipe_values_b);
            pair_o0[0] += pipe_ka[0] + pipe_kb[0];
            pair_o0[1] += pipe_ka[1] + pipe_kb[1];
            pair_o0[2] += pipe_ka[2] + pipe_kb[2];
            pair_o0[3] += pipe_ka[3] + pipe_kb[3];
            pair_o1[0] += U(pipe_va0) + U(pipe_vb0);
            pair_o1[1] += U(pipe_va1) + U(pipe_vb1);
            pair_o1[2] += U(pipe_va2) + U(pipe_vb2);
            pair_o1[3] += U(pipe_va3) + U(pipe_vb3);
            pair_keys += 2 * inner_k_stride;
            pair_values += 2 * inner_v_stride;
        }

"""
write("probe_d2.metal", head + LOOP_START + d2_body + tail)

d3 = src.replace(
    LOOP_START,
    "        const int addr_mask = int(params[1]); // DIAG3\n" + LOOP_START)
d3 = d3.replace(
    "            pair_keys += 2 * inner_k_stride;\n"
    "            pair_values += 2 * inner_v_stride;",
    "            pair_keys += (2 * inner_k_stride) & addr_mask;\n"
    "            pair_values += (2 * inner_v_stride) & addr_mask;")
assert "addr_mask;" in d3
write("probe_d3.metal", d3)

# Second round: split the 31.9 us/layer between the phase-3 loop, the epilogue,
# and the irreducible dispatch + phase-1/2 floor.
#   probe_d4.metal  loop deleted, epilogue intact (seeded from runtime values
#                   so the epilogue cannot be constant-folded)
#   probe_d5.metal  loop intact, epilogue replaced by a direct per-simdgroup
#                   write (no threadgroup transpose, no barriers, no simd_sum)
#   probe_d6.metal  neither loop nor epilogue
SEED = """        for (int j = 0; j < v_per_thread; ++j) {
            pair_o0[j] = pair_q0[j];
            pair_o1[j] = pair_q1[j];
        }
        pair_max0 = pair_q0[0];
        pair_max1 = pair_q1[0];
        pair_sum0 = pair_q0[1];
        pair_sum1 = pair_q1[1];

"""
DIRECT_WRITE = """        if (lane == 0) {
            device bfloat* pair_out0 =
                attended + head0 * head_dim + sg * v_per_thread;
            device bfloat* pair_out1 =
                attended + head1 * head_dim + sg * v_per_thread;
            for (int p = 0; p < v_per_thread; ++p) {
                pair_out0[p] = static_cast<bfloat>(
                    pair_o0[p] / pair_sum0 + pair_max0);
                pair_out1[p] = static_cast<bfloat>(
                    pair_o1[p] / pair_sum1 + pair_max1);
            }
        }
}
"""

pre, epilogue = src.split(LOOP_END, 1)

write("probe_d4.metal", head + SEED + LOOP_END + epilogue)
write("probe_d5.metal", pre + DIRECT_WRITE)
write("probe_d6.metal", head + SEED + DIRECT_WRITE)

# Load-width pair: same bytes per threadgroup (262 kB), same number of integer
# accumulate ops (64/thread), no epilogue, no float math. Only the load
# instruction count differs, so d8a vs d8b isolates per-instruction issue cost
# from bandwidth.
#   probe_d8a.metal  32 loads/thread of 8 B  (shipped width: one row per warp)
#   probe_d8b.metal  16 loads/thread of 16 B (two contiguous rows per warp)
LOAD_WIDTH = """        const device uint2* wk2 = (const device uint2*)(
            k_cache + (size_t)kv_head * (window * head_dim));
        const device uint2* wv2 = (const device uint2*)(
            v_cache + (size_t)kv_head * (window * head_dim));
        const device uint4* wk4 = (const device uint4*)(
            k_cache + (size_t)kv_head * (window * head_dim));
        const device uint4* wv4 = (const device uint4*)(
            v_cache + (size_t)kv_head * (window * head_dim));
        uint acc = 0;
%s
        pair_o0[0] += float(acc & 0xffu);

"""
NARROW = """        wk2 += sg * 32 + lane;
        wv2 += sg * 32 + lane;
        for (int j = 0; j < 16; ++j) {
            uint2 kk = wk2[j * 1024];
            uint2 vv = wv2[j * 1024];
            acc += kk.x + kk.y + vv.x + vv.y;
        }"""
WIDE = """        wk4 += sg * 32 + lane;
        wv4 += sg * 32 + lane;
        for (int j = 0; j < 8; ++j) {
            uint4 kk = wk4[j * 1024];
            uint4 vv = wv4[j * 1024];
            acc += kk.x + kk.y + kk.z + kk.w;
            acc += vv.x + vv.y + vv.z + vv.w;
        }"""
write("probe_d8a.metal",
      head + SEED + (LOAD_WIDTH % NARROW) + DIRECT_WRITE)
write("probe_d8b.metal",
      head + SEED + (LOAD_WIDTH % WIDE) + DIRECT_WRITE)

# probe_d7.metal: empty kernel at the same launch geometry. Separates the
# per-dispatch launch/drain cost from phase 1/2 work inside d6.
SIG_END = "[[thread_index_in_simdgroup]]) {\n"
signature = src.split(SIG_END, 1)[0] + SIG_END
write("probe_d7.metal", signature + """        if (thread_position_in_grid.x == 0) {
            attended[0] = bfloat(scale_arr[0]);
        }
}
""")
