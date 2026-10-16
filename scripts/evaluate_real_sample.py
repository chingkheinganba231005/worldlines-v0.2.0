#!/usr/bin/env python3
"""Descriptive four-slot comparison. No forecasting, calibration or event truth labels."""
from collections import Counter
from pathlib import Path
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from worldline.core import jsd,transport,smoothed_counts

sample=json.loads((ROOT/'dist/data/gdelt_sample.json').read_text())
roots=[f'{i:02d}' for i in range(1,21)]
# CAMEO QuadClass groups: verbal cooperation 01–05, material cooperation06–09,
# verbal conflict10–14, material conflict15–20. Geometry is an explicit prior.
groups=[0]*5+[1]*4+[2]*5+[3]*6
cost=np.array([[0 if i==j else .5 if groups[i]==groups[j] else 1 for j in range(20)] for i in range(20)])
reference=smoothed_counts([sample['history'][0]['cameo_root_counts'].get(k,0) for k in roots])
reference_sources=Counter(e.get('publisher') or 'unknown' for e in sample['history'][0]['events'])
rows=[]
for row in sample['history']:
    p=smoothed_counts([row['cameo_root_counts'].get(k,0) for k in roots])
    sources=Counter(e.get('publisher') or 'unknown' for e in row['events'])
    keys=sorted(set(sources)|set(reference_sources))
    rows.append({'date':row['date'],'provider_records':row['provider_record_count'], 'publisher_domains':len(sources),
                 'js_nats_to_first_slot':jsd(p,reference),'taxonomy_ot_to_first_slot':transport(p,reference,cost),
                 'source_mix_js_nats_to_first_slot':jsd([sources.get(k,0) for k in keys],[reference_sources.get(k,0) for k in keys])})
result={'mode':'historical_sample','claim':'Descriptive metadata comparison, not validated historical displacement or surprise',
        'reference':sample['history'][0]['date']+' 01:30 UTC archive; one small reference sample, not a baseline year',
        'sample_policy':'One 15-minute archive at the same UTC slot per day. Incomplete daily coverage.',
        'taxonomy':'CAMEO20 roots, alpha0.5 smoothing','cost_matrix':cost.tolist(),
        'caveats':['Provider record IDs are not verified real-world event clusters.','Source mix differs and is not adjusted.',
                   'Four slots cannot estimate a meaningful predictive forecast or calibrated false-alert rate.',
                   'No official event-impact labels were collected; no accuracy claim can be made.'],
        'rows':rows,'archives':sample['archives']}
(ROOT/'research/real_sample_results.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# Bounded real-data experiment','',result['claim']+'.', '',result['sample_policy'],'',
       '| UTC date | Provider records | Publisher domains | Topic JSD (nats) | Taxonomy OT | Source-mix JSD (nats) |',
       '|---|---:|---:|---:|---:|---:|']
for r in rows:
    lines.append(f"| {r['date']} | {r['provider_records']} | {r['publisher_domains']} | {r['js_nats_to_first_slot']:.4f} | {r['taxonomy_ot_to_first_slot']:.4f} | {r['source_mix_js_nats_to_first_slot']:.4f} |")
lines+=['','All comparisons use the first small archive as reference. These exploratory numbers are **not** promoted to dashboard historical displacement, anomaly percentiles or alerts. Large source-mix differences make apparent topic shifts especially hard to interpret.','',
        'Five sanity checks: fixed UTC slot; strictly distinct provider IDs after deduplication; codebook-validated root codes; archive checksums retained; no publisher fulltext or verified-event claims. Forecasting is withheld because history is inadequate.','',
        'Reproduce after acquiring the sample with `python scripts/evaluate_real_sample.py`. Exact metadata and caveats are in `real_sample_results.json`.']
(ROOT/'research/real_sample_results.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
