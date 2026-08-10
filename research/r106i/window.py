rows = []
with open('research/artifacts/fern-r106g/dispatch_raw.tsv') as f:
    for line in f:
        p = line.rstrip('\n').split('\t')
        if len(p) < 8:
            continue
        rows.append(p)
print('rows', len(rows))


def idx(pat):
    return [i for i, r in enumerate(rows) if pat in r[1]]


gq = idx('nvfp4_gather_qmm_rhs_nt')
print('gq n', len(gq), 'first', gq[0], 'last', gq[-1])
gaps = sorted(((gq[i + 1] - gq[i], i) for i in range(len(gq) - 1)), reverse=True)
print('top gaps', gaps[:5])
for name in ('decode_nvfp4_qkv', 'decode_embedding_rope_atlas',
             'prefill_sliding_qk_norm_rope', 'prefill_full_qk_norm_yarn',
             'lmhead', 'steel_attention', 'sdpa_vector'):
    h = idx(name)
    print(name, 'n', len(h), 'first', h[0] if h else None, 'last', h[-1] if h else None)
