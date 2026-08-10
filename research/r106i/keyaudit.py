"""Grouping-key exposure audit for the R106-I above-SLC column.

The above-SLC estimate is the only part of the census that asks whether two
dispatches touched the *same* bytes, and it answers with the trace's buffer
pointer.  Advisor rule 93.4(a) warns that such a key can establish less than
the analysis assumes: MLX recycles allocations, so a shared pointer need not
mean shared bytes, and a logical tensor may move.

This script bounds how much of the result can move if the key means nothing.
Every access is routed to one of two paths:

  streamed  nb > cap.  Charged in full on every traversal, never consulted
            against the resident set, so its cost is independent of the key.
  keyed     nb <= cap.  Charged on first touch, free on a repeat -- the only
            place pointer identity buys anything.

`credited` is exactly what the key bought.  Treating every keyed hit as a miss
gives the no-reuse endpoint, so the true above-SLC total is bracketed by
[aslc, aslc + credited] for any keying discipline at this cache size.
"""
import json
from collections import defaultdict

from traversal import (BW, FAMILIES, GLUE, LMHEAD_MASK_ROWS, SLC, TOKENS,
                       load_rows, operand_mults)


def audit(rows, host, reuse, cap):
    stream = defaultdict(float)
    keyed = defaultdict(float)
    credited = defaultdict(float)
    resident = {}
    used = 0
    order = []
    for r in rows:
        fam = r['fam']
        mult = operand_mults(r, host, reuse, LMHEAD_MASK_ROWS)
        ops = [(p, nb, mult.get(p, 1.0)) for p, nb in r['ins'].items()]
        for p, nb in r['outs'].items():
            if p not in r['ins']:
                ops.append((p, nb, 1.0))
        for p, nb, m in ops:
            if nb > cap:
                stream[fam] += nb * m
                continue
            k = (p, nb)
            if k in resident:
                credited[fam] += nb
                order.remove(k)
                order.append(k)
                continue
            while used + nb > cap and order:
                ev = order.pop(0)
                used -= resident.pop(ev)
            resident[k] = nb
            order.append(k)
            used += nb
            keyed[fam] += nb
    return stream, keyed, credited


def main():
    rows = load_rows()
    out = {}
    for reuse in ('ordered', 'coresident'):
        stream, keyed, credited = audit(rows, 'm5', reuse, SLC)
        fams = [f for f, _ in FAMILIES] + ['other']
        tag = f'm5/{reuse}'
        ts, tk, tc = (sum(d.values()) for d in (stream, keyed, credited))
        rec = {'families': {}, 'total': {}}
        print(f'\n=== {tag}, SLC {SLC >> 20} MiB ===')
        print(f'{"family":<22}{"aSLC GB":>10}{"streamed":>10}{"keyed":>9}'
              f'{"credited":>10}{"key-dep":>9}')
        for f in fams:
            a = stream[f] + keyed[f]
            if not a and not credited[f]:
                continue
            hi = a + credited[f]
            dep = credited[f] / hi if hi else 0.0
            rec['families'][f] = {
                'aslc_gb': a / 1e9, 'streamed_gb': stream[f] / 1e9,
                'keyed_gb': keyed[f] / 1e9, 'credited_gb': credited[f] / 1e9,
                'aslc_hi_gb': hi / 1e9, 'key_dependence': dep}
            print(f'{f:<22}{a/1e9:>10.4f}{stream[f]/1e9:>10.4f}'
                  f'{keyed[f]/1e9:>9.4f}{credited[f]/1e9:>10.4f}{dep:>8.1%}')
        ta = ts + tk
        rec['total'] = {
            'aslc_gb': ta / 1e9, 'streamed_gb': ts / 1e9, 'keyed_gb': tk / 1e9,
            'credited_gb': tc / 1e9, 'aslc_hi_gb': (ta + tc) / 1e9,
            'key_dependence': tc / (ta + tc),
            'aslc_ms': ta / BW * 1e3, 'aslc_hi_ms': (ta + tc) / BW * 1e3,
            'streamed_share': ts / ta}
        rec['glue'] = {
            'aslc_gb': sum(stream[f] + keyed[f] for f in GLUE) / 1e9,
            'credited_gb': sum(credited[f] for f in GLUE) / 1e9,
            'aslc_ms': sum(stream[f] + keyed[f] for f in GLUE) / BW * 1e3,
            'aslc_hi_ms': sum(stream[f] + keyed[f] + credited[f]
                              for f in GLUE) / BW * 1e3}
        rec['experts'] = {
            'aslc_gb': (stream['routed_gather_gemm']
                        + keyed['routed_gather_gemm']) / 1e9,
            'credited_gb': credited['routed_gather_gemm'] / 1e9,
            'streamed_share': (stream['routed_gather_gemm']
                               / (stream['routed_gather_gemm']
                                  + keyed['routed_gather_gemm'])),
            'aslc_ms': (stream['routed_gather_gemm']
                        + keyed['routed_gather_gemm']) / BW * 1e3,
            'aslc_hi_ms': (stream['routed_gather_gemm']
                           + keyed['routed_gather_gemm']
                           + credited['routed_gather_gemm']) / BW * 1e3}
        print(f'{"TOTAL":<22}{ta/1e9:>10.4f}{ts/1e9:>10.4f}{tk/1e9:>9.4f}'
              f'{tc/1e9:>10.4f}{tc/(ta+tc):>8.1%}')
        print(f'  above-SLC bracket   {ta/BW*1e3:7.2f} .. '
              f'{(ta+tc)/BW*1e3:7.2f} ms   per token '
              f'{ta/TOKENS/1e6:6.3f} .. {(ta+tc)/TOKENS/1e6:6.3f} MB')
        print(f'  experts             {rec["experts"]["aslc_ms"]:7.2f} .. '
              f'{rec["experts"]["aslc_hi_ms"]:7.2f} ms   streamed share '
              f'{rec["experts"]["streamed_share"]:.4%}')
        print(f'  glue                {rec["glue"]["aslc_ms"]:7.2f} .. '
              f'{rec["glue"]["aslc_hi_ms"]:7.2f} ms')
        out[tag] = rec
    with open('research/r106i/keyaudit.json', 'w') as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print('\nwrote research/r106i/keyaudit.json')


if __name__ == '__main__':
    main()
