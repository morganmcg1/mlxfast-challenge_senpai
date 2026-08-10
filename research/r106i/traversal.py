"""R106-I prefill TRAVERSAL-byte census.

Extends research/r106i/census.py (BINDING) with a per-operand traversal model
built from tile geometry read out of the MLX sources.  Every operand of every
dispatch in prefill forward #1 gets a multiplicity; TRAVERSAL = footprint x
multiplicity, BINDING = footprint x 1, so TRAVERSAL/BINDING is a pure read
multiplicity ratio.

HOST  = 'm4' uses the traced M4 kernels/grids verbatim.
        'm5' substitutes the _nax kernels the ranked M5 selects.
REUSE = 'ordered'    x-fastest issue: a GEMM weight tile is re-read once per
                     m-tile (upper bound).
        'coresident' the whole grid is in flight: weight multiplicity 1
                     (lower bound).
"""
import json
import math
import re
import sys
from collections import OrderedDict, defaultdict

sys.path.insert(0, 'research/r106i')
from census import FAMILIES, family, parse_args, parse_bufs, prod  # noqa: E402

TSV = 'research/artifacts/fern-r106g/dispatch_raw.tsv'
LO, HI = 6115, 7334
TOKENS = 512
BW = 546.2e9

# Routing histogram, research/artifacts/route-histogram-prefill512.json,
# 38 MoE layers x 256 experts, 4096 rows/layer.
CHUNKS_BM64 = 8379 / 38.0        # sum_e ceil(rows_e/64) per layer
NONEMPTY = (9728 - 1971) / 38.0  # non-zero-row experts per layer
LMHEAD_MASK_ROWS = 128           # exact-rescore survivors (null-cell bracket)
BF16_VOCAB = 100352 * 2048 * 2

HOST = 'm5'
REUSE = 'ordered'
SLC = 24 * 1024 * 1024


def gather_weight_mult(host):
    """Expert-weight traversal multiplicity for one gather-GEMM dispatch."""
    if host == 'm5':
        # fp_gather_qmm_rhs_expert_nax: BM=64, grid.y is the expert id, one
        # expert per threadgroup, row interval by laguna_sorted_lower_bound.
        return CHUNKS_BM64 / 256.0
    # M4 nvfp4_gather_qmm_rhs_nt bm=16: threadgroups may straddle experts, so
    # every non-empty expert costs at least one extra boundary incidence.
    incid = math.ceil(4096 / 16.0) + (NONEMPTY - 1) * 15.0 / 16.0
    return incid / 256.0


def steel_mult(host, reuse, M, N, grid):
    if host == 'm5':
        # steel_matmul_regular_axpby_nax bm=64 bn=128, never split-K.
        a = math.ceil(N / 128.0)
        b = math.ceil(M / 64.0)
    else:
        a, b = grid[0], grid[1]
    return a, (1.0 if reuse == 'coresident' else b)


def qmm_mult(host, reuse, M, N):
    bm = bn = 64 if host == 'm5' else 32
    a = math.ceil(N / bn)
    b = math.ceil(M / bm)
    return a, (1.0 if reuse == 'coresident' else b)


def causal_krows(Lq, Lk, bq=32):
    return sum(min((j + 1) * bq, Lk) for j in range(Lq // bq))


def load_rows():
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
                'args': parse_args(p[5]),
                'ins': parse_bufs(p[8]), 'outs': parse_bufs(p[9]),
                'fam': family(p[1]),
            })
    return rows


ESZ = {'bfloat16': 2, 'float16': 2, 'float32': 4, 'int32': 4, 'uint32': 4,
       'uint8': 1, 'int8': 1, 'uint16': 2, 'int64': 8, 'bool_': 1}


def abytes(arg):
    return prod(arg[2]) * ESZ.get(arg[1], 1)


def operand_mults(r, host, reuse, lmhead_rows):
    """Return {ptr: multiplicity} for the inputs of one dispatch."""
    k, args, grid = r['kernel'], r['args'], r['grid']
    a = {i: arg for arg in args for i in [arg[0]]}
    mult = {}

    def assign(idx, m):
        if idx in a:
            nb = abytes(a[idx])
            for ptr, pb in r['ins'].items():
                if pb == nb:
                    mult[ptr] = m

    if k.startswith('steel_gemm_splitk_nt') or k.startswith('steel_gemm_fused_nt'):
        M, K = a[0][2][-2], a[0][2][-1]
        N = a[1][2][-1]
        am, bm_ = steel_mult(host, reuse, M, N, grid)
        assign(0, am)
        assign(1, bm_)
    elif k.startswith('nvfp4_gather_qmm_rhs'):
        N = a[4][2][-1]
        bn = 64 if host == 'm5' else 32
        am = math.ceil(N / bn)
        wm = gather_weight_mult(host)
        assign(0, am)
        assign(1, wm)
        assign(2, wm)
    elif k.startswith('nvfp4_qmm_t'):
        M, N = a[2][2][-2], a[3][2][-1]
        am, bm_ = qmm_mult(host, reuse, M, N)
        assign(2, am)
        assign(0, bm_)
        assign(1, bm_)
    elif k.startswith('steel_attention'):
        H, Lq = a[0][2][1], a[0][2][2]
        Hkv, Lk = a[1][2][1], a[1][2][2]
        kv = H * causal_krows(Lq, Lk) / float(Hkv * Lk)
        assign(1, kv)
        assign(2, kv)
    elif k.startswith('gather_front'):
        tb, ob = abytes(a[0]), abytes(a[2])
        assign(0, ob / float(tb))
    elif 'lmhead_exact' in k:
        for ptr, pb in r['ins'].items():
            if pb == BF16_VOCAB:
                mult[ptr] = lmhead_rows * 2048 * 2 / float(BF16_VOCAB)
    elif 'routed_nvfp4_swiglu_qmv_packed_top8keys' in k or \
         'routed_shared_nvfp4_down_residual' in k:
        for ptr, pb in r['ins'].items():
            if pb >= 64 * 1024 * 1024:
                mult[ptr] = 8.0 / 256.0
    return mult


class SLCache:
    """Buffer-granular LRU standing in for the system level cache.

    A buffer larger than the cache is streamed: it is charged in full at every
    traversal and is assumed not to evict the resident set, because the routed
    weight stream is consumed tile-by-tile with expert-local reuse far below
    buffer granularity.  Smaller buffers are charged only on a miss.
    """

    def __init__(self, cap):
        self.cap = cap
        self.d = OrderedDict()
        self.used = 0

    def access(self, key, nb, mult):
        if nb > self.cap:
            return nb * mult
        if key in self.d:
            self.d.move_to_end(key)
            return 0.0
        while self.used + nb > self.cap and self.d:
            self.used -= self.d.popitem(last=False)[1]
        self.d[key] = nb
        self.used += nb
        return float(nb)


def census(rows, host, reuse, slc, lmhead_rows=LMHEAD_MASK_ROWS):
    bind = defaultdict(float)
    trav = defaultdict(float)
    aslc = defaultdict(float)
    cnt = defaultdict(int)
    cache = SLCache(slc)
    for r in rows:
        fam = r['fam']
        cnt[fam] += 1
        mult = operand_mults(r, host, reuse, lmhead_rows)
        ops = [(p, nb, mult.get(p, 1.0)) for p, nb in r['ins'].items()]
        for p, nb in r['outs'].items():
            if p not in r['ins']:
                ops.append((p, nb, 1.0))
        for p, nb, m in ops:
            bind[fam] += nb
            trav[fam] += nb * m
            aslc[fam] += cache.access((p, nb), nb, m)
    return bind, trav, aslc, cnt


GLUE = ('elementwise', 'sort_scatter', 'moe_tail', 'qk_norm_rope',
        'rms_norm', 'router')


def report(rows):
    out = {}
    order = [f for f, _ in FAMILIES] + ['other']
    for host in ('m5', 'm4'):
        for reuse in ('ordered', 'coresident'):
            bind, trav, aslc, cnt = census(rows, host, reuse, SLC)
            tb, tt, ta = sum(bind.values()), sum(trav.values()), sum(aslc.values())
            tag = f'{host}/{reuse}'
            out[tag] = {
                'families': {f: {'n': cnt[f], 'bind_gb': bind[f] / 1e9,
                                 'trav_gb': trav[f] / 1e9,
                                 'aslc_gb': aslc[f] / 1e9,
                                 'tb': trav[f] / bind[f] if bind[f] else 0.0,
                                 'sb': aslc[f] / bind[f] if bind[f] else 0.0}
                             for f in order if cnt[f]},
                'total': {'bind_gb': tb / 1e9, 'trav_gb': tt / 1e9,
                          'aslc_gb': ta / 1e9, 'tb': tt / tb, 'sb': ta / tb},
                'per_token_mb': {'bind': tb / TOKENS / 1e6,
                                 'trav': tt / TOKENS / 1e6,
                                 'aslc': ta / TOKENS / 1e6},
                'floor_ms': {'trav': tt / BW * 1e3, 'aslc': ta / BW * 1e3,
                             'bind': tb / BW * 1e3},
                'glue_aslc_ms': sum(aslc[f] for f in GLUE) / BW * 1e3,
                'glue_bind_gb': sum(bind[f] for f in GLUE) / 1e9,
                'glue_trav_gb': sum(trav[f] for f in GLUE) / 1e9,
                'experts_aslc_ms': aslc['routed_gather_gemm'] / BW * 1e3,
            }
            print(f'\n=== {tag}, SLC {SLC >> 20} MiB ===')
            print(f'{"family":<22}{"n":>5}{"BIND GB":>11}{"TRAV GB":>11}'
                  f'{"T/B":>8}{"aSLC GB":>11}{"S/B":>8}')
            for f in order:
                if not cnt[f]:
                    continue
                print(f'{f:<22}{cnt[f]:>5}{bind[f]/1e9:>11.4f}{trav[f]/1e9:>11.4f}'
                      f'{trav[f]/bind[f]:>8.3f}{aslc[f]/1e9:>11.4f}'
                      f'{aslc[f]/bind[f]:>8.3f}')
            print(f'{"TOTAL":<22}{len(rows):>5}{tb/1e9:>11.4f}{tt/1e9:>11.4f}'
                  f'{tt/tb:>8.3f}{ta/1e9:>11.4f}{ta/tb:>8.3f}')
            print(f'per token MB: bind {tb/TOKENS/1e6:.3f}  trav {tt/TOKENS/1e6:.3f}'
                  f'  aSLC {ta/TOKENS/1e6:.3f}')
            print(f'floor @546.2 GB/s: trav {tt/BW*1e3:.2f} ms  aSLC {ta/BW*1e3:.2f} ms')

    sweep = {}
    print('\n=== SLC sensitivity, m5, above-SLC ms (ordered | coresident) ===')
    print(f'{"MiB":>5}{"total":>18}{"glue":>18}{"experts":>18}')
    for mib in (8, 16, 24, 48, 96):
        cells = []
        for reuse in ('ordered', 'coresident'):
            _, _, aslc, _ = census(rows, 'm5', reuse, mib * 1024 * 1024)
            cells.append((sum(aslc.values()) / BW * 1e3,
                          sum(aslc[f] for f in GLUE) / BW * 1e3,
                          aslc['routed_gather_gemm'] / BW * 1e3))
        sweep[mib] = {'ordered': cells[0], 'coresident': cells[1]}
        print(f'{mib:>5}' + ''.join(
            f'{cells[0][i]:>10.2f}|{cells[1][i]:>7.2f}' for i in range(3)))
    out['slc_sweep_ms'] = sweep

    print('\n=== lm_head exact-rescore null cell (rule 79) ===')
    for rowsn in (LMHEAD_MASK_ROWS, 100352):
        _, trav, _, _ = census(rows, 'm5', 'ordered', SLC, lmhead_rows=rowsn)
        print(f'  surviving rows {rowsn:>7}: lm_head TRAV {trav["lm_head"]/1e9:.4f} GB'
              f'   TOTAL TRAV {sum(trav.values())/1e9:.4f} GB')
        out.setdefault('lmhead_null_cell', {})[rowsn] = {
            'lm_head_trav_gb': trav['lm_head'] / 1e9,
            'total_trav_gb': sum(trav.values()) / 1e9}
    return out


if __name__ == '__main__':
    rows = load_rows()
    print(f'prefill forward #1: {len(rows)} dispatches, '
          f'seq {rows[0]["seq"]}..{rows[-1]["seq"]}')
    res = report(rows)
    json.dump(res, open('research/r106i/traversal.json', 'w'), indent=1)
