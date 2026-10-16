#!/usr/bin/env python3
"""Fetch a bounded metadata sample, with explicit archive slots and provenance."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from worldline.ingest import GDELTClient, PREFIX, ProviderError, RIGHTS, parse_tsv, unpack_archive, utc_now
from worldline.storage import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--start', help='UTC archive slot YYYYMMDDHHMMSS; advance by 15 minutes')
    source.add_argument('--latest', action='store_true', help='fetch one most recent official Events export')
    source.add_argument('--archive', type=Path, help='locally supplied official .export.CSV.zip')
    parser.add_argument('--slots', type=int, default=1, help='1–31 archives; default 1, never full-day coverage')
    parser.add_argument('--daily', action='store_true', help='sample the same UTC slot on successive days; max 4 slots')
    parser.add_argument('--allow-gaps', action='store_true', help='publish successful archives with explicit failures and incomplete coverage')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/data/gdelt_sample.json')
    parser.add_argument('--db', type=Path, default=ROOT/'data/worldline.sqlite')
    args = parser.parse_args(argv)
    if not 1 <= args.slots <= 31:
        parser.error('--slots must be between 1 and 31')
    if args.daily and (not args.start or args.slots > 4):
        parser.error('--daily requires --start and at most 4 slots')
    if (args.latest or args.archive) and args.slots != 1:
        parser.error('--slots applies only with --start')
    client = GDELTClient()
    store = Store(args.db)
    observations, manifests, failures = [], [], []
    try:
        if args.archive:
            urls = [args.archive.resolve().as_uri()]
        elif args.latest:
            urls = [client.latest_export()]
        else:
            try:
                stamp = datetime.strptime(args.start, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            except ValueError:
                parser.error('--start must be a valid YYYYMMDDHHMMSS')
            if stamp.minute % 15 or stamp.second:
                parser.error('--start must align to a 15-minute archive slot')
            urls = [PREFIX+(stamp+timedelta(minutes=(1440 if args.daily else 15)*i)).strftime('%Y%m%d%H%M%S')+'.export.CSV.zip' for i in range(args.slots)]
        for url in urls:
            if args.archive:
                if args.archive.stat().st_size > 16*1024*1024:
                    raise ProviderError('local archive exceeds byte limit')
                payload = args.archive.read_bytes()
            else:
                try:
                    payload = client.fetch(url)
                except ProviderError as exc:
                    if not args.allow_gaps:
                        raise
                    failures.append({'url':url,'error':str(exc),'observed_at_utc':utc_now()})
                    continue
            observed = utc_now()
            records = parse_tsv(unpack_archive(payload), observed_at=observed)
            sha = hashlib.sha256(payload).hexdigest()
            manifest = {'url':url,'sha256':sha,'bytes':len(payload),'observed_at_utc':observed,'record_count':len(records)}
            raw_dir = ROOT/'data/raw'
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir/(sha+'.zip')
            if not raw_path.exists():
                raw_path.write_bytes(payload)
            store.ingest(records, archive=manifest)
            manifests.append(manifest)
            observations.extend(records)
        # Stable deduplication by provider row ID; this is not real-event resolution.
        unique = {row['id']:row for row in observations}
        grouped = defaultdict(list)
        for row in unique.values():
            grouped[row['available_at_utc'][:10]].append(row)
        history = []
        for day, records in sorted(grouped.items()):
            counts = Counter(row['raw_metadata']['EventRootCode'] for row in records)
            history.append({'date':day,'events':records,'provider_record_count':len(records),
                'cameo_root_counts':dict(sorted(counts.items())), 'js_topic':None,'transport_cost':None,
                'predictive_surprise':None,'alert':None,'coverage_status':'bounded archive sample; incomplete day',
                'metric_unavailable_reason':'Insufficient historical coverage and no compatible frozen CAMEO baseline.'})
        if not history:
            raise ProviderError('archives contained no valid records')
        snapshot = {'schema_version':'1.0','mode':'historical_sample','generated_at':utc_now(),
            'data_as_of':max(row['available_at_utc'] for row in unique.values()),
            'history':history,'archives':manifests,'references':[],
            'archive_count_expected':len(urls),'archive_count_received':len(manifests),
            'requested_archives':urls,'acquisition_errors':failures,
            'archive_completeness':len(manifests)/len(urls),
            'coverage_complete_days':False,
            'sampling_interval_minutes':1440 if args.daily else 15,
            'methodology':{'provider':'GDELT 2.0 Events','rights':RIGHTS,'scope':'sociopolitical CAMEO metadata only',
                'sampling':('Same UTC 15-minute archive slot on successive days' if args.daily else 'Contiguous requested 15-minute archive slots')+'; not complete day or world coverage.',
                'deduplication':'Provider record ID only; cross-ID semantic event resolution is not implemented for real data.',
                'availability':'DATEADDED is provider insertion time; observed_at_utc is our actual retrieval time.',
                'verification':'All machine-extracted records provisional; publisher diversity does not establish independence.',
                'titles':'Generated actor/action labels, not article headlines. Full article text is never fetched.',
                'forecast':'No forecast or calibrated alerts from this small sample. Separate synthetic demo for pipeline behavior.'}}
        store.save_snapshot(snapshot)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(snapshot, indent=2, allow_nan=False)+'\n')
        temporary.replace(args.output)
        print(json.dumps({'output':str(args.output),'archives':len(manifests),'records':len(unique),'mode':snapshot['mode']}))
        return 0
    except (ProviderError, OSError) as exc:
        print(f'Backfill failed explicitly: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
