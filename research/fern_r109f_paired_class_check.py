import json, math

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

raw = json.load(open('/tmp/subs_now.json'))
if isinstance(raw, dict):
    for k in ('submissions', 'data', 'items', 'results'):
        if isinstance(raw.get(k), list):
            raw = raw[k]
            break
rows = [r for r in raw if isinstance(r, dict)]
print('rows', len(rows))

ids = {'c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9', '88584270-140e-4f28-a924-b00c77b1becd'}


def dec(m):
    d = m.get('decode_seconds_per_token')
    p = m.get('prefill_seconds_per_token')
    bd = m.get('baseline_decode_seconds_per_token')
    bp = m.get('baseline_prefill_seconds_per_token')
    if not (d and p and bd and bp):
        return None
    norm = (REF_D / d) ** 0.75 * (REF_P / p) ** 0.25
    draw = (bd / REF_D) ** 0.75 * (bp / REF_P) ** 0.25
    return norm, draw, d * 1e6, p * 1e6, bd * 1e6, bp * 1e6


for r in rows:
    sha = (r.get('submissionCommitSha') or '')
    if r.get('id') in ids or sha[:7] in ('2771067',):
        v = dec(r.get('officialMetrics') or {})
        if not v:
            print('no legs', r.get('id', '')[:8], sha[:7], r.get('officialScore'))
            continue
        norm, draw, d, p, bd, bp = v
        print('%s %s pub=%.11f norm=%.9f draw=%.6f candD=%.1f candP=%.2f baseD=%.1f baseP=%.2f %s'
              % (r.get('id', '')[:8], sha[:7], r.get('officialScore') or 0, norm, draw, d, p, bd, bp, r.get('createdAt')))

# all draws for reference
draws = []
for r in rows:
    v = dec(r.get('officialMetrics') or {})
    if v:
        draws.append(v[1])
draws.sort()
n = len(draws)
mean = sum(draws) / n
sd = math.sqrt(sum((x - mean) ** 2 for x in draws) / (n - 1))
print('draws n=%d mean=%.6f cv=%.4f%% min=%.6f max=%.6f' % (n, mean, 100 * sd / mean, draws[0], draws[-1]))
