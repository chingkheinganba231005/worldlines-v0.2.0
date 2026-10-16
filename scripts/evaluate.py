#!/usr/bin/env python3
"""Synthetic benchmark: locked training/calibration/evaluation periods, no research claims."""
from pathlib import Path
import argparse
import csv
import json
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from worldline.core import build_snapshot
from worldline.demo import generate_windows, START


def candidates(rows, field, threshold, gate):
    flags, result, previous = [], [], -100
    for t,row in enumerate(rows):
        value=row.get(field)
        high=value is not None and value > threshold and (row['coverage_ok'] or not gate)
        flags.append(high)
        if high and sum(flags[-3:]) >= 2 and t-previous>=7:
            if row['phase']=='evaluation': result.append(row['date'])
            previous=t
    return result


def experiment(seed,controls):
    windows=generate_windows(seed=seed,controls=controls)
    snap=build_snapshot(windows)
    rows=snap['history']
    shift_windows=[('2025-06-20','2025-07-04'),('2025-08-09','2025-08-28')] if controls else []
    outcomes=[]
    for name,field,gate in [('Forecast surprise','surprise_raw',True),('Topic displacement','js_topic',False),('Raw news volume','raw_mentions',False)]:
        calibration=[r[field] for r in rows if r['phase']=='calibration' and r.get(field) is not None and r['coverage_ok']]
        threshold=float(np.quantile(calibration,.975))
        alarms=candidates(rows,field,threshold,gate)
        true_alerts=[d for d in alarms if any(a<=d<=b for a,b in shift_windows)]
        false_alerts=[d for d in alarms if d not in true_alerts]
        delay=[]
        for a,b in shift_windows:
            hit=next((d for d in alarms if a<=d<=b),None)
            if hit:
                from datetime import date
                delay.append((date.fromisoformat(hit)-date.fromisoformat(a)).days)
        eval_days=sum(r['phase']=='evaluation' for r in rows)
        outcomes.append({'seed':seed,'case':'injected_controls' if controls else 'stationary_null',
            'detector':name,'threshold':threshold,'calibration_n':len(calibration),'evaluation_days':eval_days,
            'candidate_dates':alarms,'candidate_count':len(alarms),'false_candidates_per_30_days':30*len(false_alerts)/eval_days,
            'injected_episodes_detected':len(delay),'injected_episodes_total':len(shift_windows),
            'episode_detection_delays_days':delay,'candidate_precision':len(true_alerts)/len(alarms) if alarms else None})
    usable=[r for r in rows if r['phase']=='evaluation' and r['coverage_ok'] and r['baselines']['adaptive_error'] is not None]
    errors={key:float(np.mean([r['baselines'][key] for r in usable])) for key in ['adaptive_error','frozen_error','persistence_error']}
    return outcomes,{'seed':seed,'case':'injected_controls' if controls else 'stationary_null','mean_ilr_euclidean_error':errors}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=5);args=parser.parse_args()
    if not 1<=args.seeds<=100: parser.error('seeds must be between 1 and 100')
    results=[];errors=[]
    for seed in range(73129,73129+args.seeds):
        for controls in [False,True]:
            rows,err=experiment(seed,controls);results.extend(rows);errors.append(err)
    out={'kind':'synthetic_software_benchmark','real_world_validation':False,'seed_count':args.seeds,
         'protocol':'45 initial training windows. Calibration through day119. Evaluation days120–239. Thresholds fixed at calibration .975 quantile. Two of three exceedances plus seven-day cooldown. Synthetic episode matching only; not verified news.',
         'limitations':['Thresholds, pseudocount and ridge penalty are design choices, not tuned on an external validation corpus.',
                        'Forecast errors measure ILR coordinates; covariance intervals and empirical ranks remain unvalidated.',
                        'The synthetic generator encodes assumptions; performance here cannot establish real-world superiority.',
                        'Two injected long episodes permit repeated alerts; episode detection and candidate precision are different quantities.'],
         'results':results,'forecast_comparisons':errors}
    (ROOT/'research/results.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    fields=['seed','case','detector','threshold','calibration_n','evaluation_days','candidate_count','false_candidates_per_30_days','injected_episodes_detected','injected_episodes_total','candidate_precision']
    with (ROOT/'research/results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(results)
    report=['# Reproducible synthetic experiment results','',out['protocol'],'',
            '**These are software checks on a synthetic generator, not evidence of research novelty or real-world skill.**','',
            '| Detector | Mean null candidates / 30 days | Injected episodes detected | Mean injected-case false candidates / 30 days |',
            '|---|---:|---:|---:|']
    for name in ['Forecast surprise','Topic displacement','Raw news volume']:
        null=[r for r in results if r['detector']==name and r['case']=='stationary_null']
        injected=[r for r in results if r['detector']==name and r['case']=='injected_controls']
        report.append(f"| {name} | {np.mean([r['false_candidates_per_30_days'] for r in null]):.2f} | {sum(r['injected_episodes_detected'] for r in injected)} / {sum(r['injected_episodes_total'] for r in injected)} | {np.mean([r['false_candidates_per_30_days'] for r in injected]):.2f} |")
    report+=['','Do not assume the more sophisticated detector wins: both displacement and surprise have different targets. Read the per-seed tables and failed detections. The published dashboard uses a trailing descriptive rank rule, while this benchmark freezes a raw-score threshold from the dedicated calibration period; these are explicitly different alarm experiments.','',
             'Reproduce with `python scripts/evaluate.py --seeds 5`. Full thresholds, candidate dates, detection delays and forecast-error comparisons are in `results.json`.']
    (ROOT/'research/results.md').write_text('\n'.join(report)+'\n')
    print('\n'.join(report))

if __name__=='__main__': main()
