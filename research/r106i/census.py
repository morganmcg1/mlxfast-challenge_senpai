"""R106-I prefill traversal-byte census.

Reads the committed R106-G dispatch ledger, isolates prefill forward #1
(rows 6115..7334), and reports BINDING bytes per family plus a per-dispatch
TRAVERSAL model built from tile geometry read out of the MLX sources.
"""
import re
import sys
import json
from collections import defaultdict

TSV = 'research/artifacts/fern-r106g/dispatch_raw.tsv'
LO, HI = 6115, 7334  # inclusive seq ids of prefill forward #1

FAMILIES = [
    ('routed_gather_gemm', r'gather_qmm_rhs|gather_qmm_rhs_expert'),
    ('lm_head', r'lmhead|argmax'),
    ('moe_tail', r'sorted_moe_tail'),
    ('sort_scatter', r'sort|scatter|arange|gather_front|partition'),
    ('router', r'router_tournament'),
    ('qk_norm_rope', r'qk_norm|rope'),
    ('attention_core', r'steel_attention|sdpa|fused_attn'),
    ('nvfp4_dense_qmm', r'nvfp4_qmm|swiglu_qmv|nvfp4_down_residual|dense_gate_up|dense_down'),
    ('steel_gemm_bf16', r'steel_gemm|gemv'),
    ('rms_norm', r'rms'),
    ('elementwise', r'copy|Multiply|Add|Sigmoid|LogAddExp|AsType|Broadcast|Subtract|^C[VfF]|^v[vsn]|^g[23g]|^s_|^sn_'),
]


def family(name):
    for fam, pat in FAMILIES:
        if re.search(pat, name):
            return fam
    return 'other'


BUF = re.compile(r'(0x[0-9a-f]+)\+(\d+):(\d+)')


def parse_bufs(cell):
    out = {}
    for ptr, off, nb in BUF.findall(cell or ''):
        out[ptr] = max(out.get(ptr, 0), int(nb))
    return out


SHAPE = re.compile(r'(\d+):([a-z0-9_]+)\[([0-9, ]+)\]')
ESIZE = {'bfloat16': 2, 'float16': 2, 'float32': 4, 'int32': 4, 'uint32': 4,
         'uint8': 1, 'int8': 1, 'uint16': 2, 'int64': 8, 'bool_': 1}


def parse_args(cell):
    res = []
    for i, dt, dims in SHAPE.findall(cell or ''):
        shape = [int(x) for x in dims.split(',')]
        res.append((int(i), dt, shape))
    return res


def prod(xs):
    p = 1
    for x in xs:
        p *= x
    return p


def main():
    rows = []
    with open(TSV) as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if len(p) < 10:
                p = p + [''] * (10 - len(p))
            try:
                seq = int(p[0])
            except ValueError:
                continue
            if not (LO <= seq <= HI):
                continue
            rows.append({
                'seq': seq, 'kernel': p[1], 'kind': p[2],
                'grid': tuple(int(v) for v in p[3].split('x')),
                'group': tuple(int(v) for v in p[4].split('x')),
                'args': parse_args(p[5]), 'barrier': p[6], 'enc': p[7],
                'ins': parse_bufs(p[8]), 'outs': parse_bufs(p[9]),
            })

    print(f'prefill forward #1: {len(rows)} dispatches, seq {rows[0]["seq"]}..{rows[-1]["seq"]}')
    print(f'encoders: {len(set(r["enc"] for r in rows))}')
    print(f'barriers set: {sum(1 for r in rows if r["barrier"] == "1")}')

    bind = defaultdict(float)
    cnt = defaultdict(int)
    for r in rows:
        bufs = dict(r['ins'])
        for ptr, nb in r['outs'].items():
            bufs[ptr] = max(bufs.get(ptr, 0), nb)
        fam = family(r['kernel'])
        r['fam'] = fam
        r['bind'] = sum(bufs.values())
        bind[fam] += r['bind']
        cnt[fam] += 1

    tot = sum(bind.values())
    print('\n=== BINDING bytes, prefill forward #1 (M4 trace, host-independent operands) ===')
    print(f'{"family":<22}{"n":>6}{"GB":>12}')
    for fam, _ in FAMILIES + [('other', '')]:
        if cnt[fam]:
            print(f'{fam:<22}{cnt[fam]:>6}{bind[fam]/1e9:>12.4f}')
    print(f'{"TOTAL":<22}{len(rows):>6}{tot/1e9:>12.4f}')

    json.dump({'n': len(rows), 'bind_gb': {k: v / 1e9 for k, v in bind.items()},
               'count': dict(cnt), 'total_gb': tot / 1e9},
              open('research/r106i/binding.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
