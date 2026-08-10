"""Publish the R106-I prefill traversal-byte census to W&B."""
import json
import wandb

BW = 546.2e9
TOKENS = 512
BIND = json.load(open('research/r106i/binding.json'))
TRAV = json.load(open('research/r106i/traversal.json'))
KEYA = json.load(open('research/r106i/keyaudit.json'))

run = wandb.init(
    project='mlxfast-maple', entity='wandb-applied-ai-team',
    name='r106i-prefill-traversal-census-keyaudit',
    job_type='analysis',
    tags=['r106i', 'prefill', 'census', 'bytes', 'keyaudit', 'maple-fern', 'pr625'],
    config={
        'assignment_id': 'maple-r106-i-prefill-traversal-byte-census',
        'revision_id': 'r106-i-rev1',
        'pr': 625,
        'window': 'prefill forward #1, seq 6115..7334',
        'dispatches': BIND['n'],
        'tokens': TOKENS,
        'trace': 'research/artifacts/fern-r106g/dispatch_raw.tsv',
        'trace_sha256': '0a82cc1ac9b156c9242b40da888613d105beabbea96a57e4262ef46314fc2834',
        'trace_bytes': 2792366,
        'bandwidth_gb_per_s': BW / 1e9,
        'slc_mib': 24,
        'capture_host': 'M4 Pro applegpu_g16s (gen 16, no _nax)',
    })

summary = {'bind_gb': BIND['total_gb'],
           'bind_mb_per_token': BIND['total_gb'] * 1e9 / TOKENS / 1e6,
           'bind_floor_ms': BIND['total_gb'] * 1e9 / BW * 1e3}
for fam, gb in BIND['bind_gb'].items():
    summary[f'bind_gb/{fam}'] = gb

for tag, blk in TRAV.items():
    if tag in ('slc_sweep_ms', 'lmhead_null_cell'):
        continue
    key = tag.replace('/', '_')
    summary[f'{key}/trav_gb'] = blk['total']['trav_gb']
    summary[f'{key}/aslc_gb'] = blk['total']['aslc_gb']
    summary[f'{key}/trav_over_bind'] = blk['total']['tb']
    summary[f'{key}/aslc_over_bind'] = blk['total']['sb']
    summary[f'{key}/trav_floor_ms'] = blk['floor_ms']['trav']
    summary[f'{key}/aslc_floor_ms'] = blk['floor_ms']['aslc']
    summary[f'{key}/glue_aslc_ms'] = blk['glue_aslc_ms']
    summary[f'{key}/experts_aslc_ms'] = blk['experts_aslc_ms']
    for fam, f in blk['families'].items():
        summary[f'{key}/trav_gb/{fam}'] = f['trav_gb']
        summary[f'{key}/tb/{fam}'] = f['tb']

for mib, cell in TRAV['slc_sweep_ms'].items():
    for reuse, (tot, glue, exp) in cell.items():
        summary[f'slc_sweep/{mib}mib/{reuse}/total_ms'] = tot
        summary[f'slc_sweep/{mib}mib/{reuse}/glue_ms'] = glue
        summary[f'slc_sweep/{mib}mib/{reuse}/experts_ms'] = exp

for tag, blk in KEYA.items():
    key = 'keyaudit/' + tag.replace('/', '_')
    for scope in ('total', 'experts', 'glue'):
        for name, val in blk[scope].items():
            summary[f'{key}/{scope}/{name}'] = val
    for fam, f in blk['families'].items():
        summary[f'{key}/key_dependence/{fam}'] = f['key_dependence']
        summary[f'{key}/streamed_gb/{fam}'] = f['streamed_gb']

summary['prior_art/routed_expert_floor_ms'] = 35.64
summary['prior_art/glue_projected_ms'] = 8.04
summary['prior_art/S_total_ms'] = 97.89475
summary['verdict'] = 'V-FLOORS-INFLATED'
run.summary.update(summary)

cols = ['family', 'n', 'bind_gb', 'trav_gb', 'tb', 'aslc_gb', 'sb']
for tag in ('m5/ordered', 'm5/coresident', 'm4/ordered', 'm4/coresident'):
    fams = TRAV[tag]['families']
    tbl = wandb.Table(columns=cols)
    for fam, f in fams.items():
        tbl.add_data(fam, f['n'], f['bind_gb'], f['trav_gb'], f['tb'],
                     f['aslc_gb'], f['sb'])
    run.log({f'census/{tag.replace("/", "_")}': tbl})

kcols = ['family', 'aslc_gb', 'streamed_gb', 'keyed_gb', 'credited_gb',
         'key_dependence']
for tag, blk in KEYA.items():
    tbl = wandb.Table(columns=kcols)
    for fam, f in blk['families'].items():
        tbl.add_data(fam, f['aslc_gb'], f['streamed_gb'], f['keyed_gb'],
                     f['credited_gb'], f['key_dependence'])
    run.log({f'keyaudit/{tag.replace("/", "_")}': tbl})

print('run_id', run.id)
print('url', run.url)
run.finish()
