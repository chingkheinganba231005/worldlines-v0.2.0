from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.error import HTTPError
import zipfile
from fastapi.testclient import TestClient
from worldline.api import create_app, ROOT as API_ROOT
from worldline.ingest import COLUMNS, GDELTClient, ProviderError, parse_tsv, unpack_archive, validate_feed_url
from worldline.storage import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/'data/fixtures/gdelt_toy.tsv'

class ProviderTests(unittest.TestCase):
    def test_availability_is_not_event_date_and_no_fake_headline(self):
        record = parse_tsv(FIXTURE.read_bytes(), observed_at='2026-10-14T00:00:00Z', synthetic=True)[0]
        self.assertEqual(record['event_time_utc'], '2020-01-01T00:00:00Z')
        self.assertEqual(record['available_at_utc'], '2020-01-02T00:15:00Z')
        self.assertEqual(record['observed_at_utc'], '2026-10-14T00:00:00Z')
        self.assertEqual(record['label_kind'], 'generated_actor_action_label')
        self.assertNotIn('title', record)
        self.assertIsNone(record['independent_source_count'])
        self.assertEqual(record['source_diversity_count'], 2)
        self.assertTrue(record['is_synthetic'])
        self.assertEqual(len(record['raw_metadata']), 61)
        self.assertEqual(record['raw_metadata']['Actor1Geo_ADM2Code'], '')

    def test_provider_clock_skew_is_flagged(self):
        record = parse_tsv(FIXTURE.read_bytes(), observed_at='2020-01-01T00:00:00Z')[0]
        self.assertIn('provider_availability_after_retrieval_clock_skew_or_provider_timestamp_issue',record['credibility_flags'])

    def test_reject_malformed_and_nonfinite(self):
        with self.assertRaises(ProviderError):
            parse_tsv(b'not\ta\trecord')
        row = FIXTURE.read_text().strip().split('\t')
        row[COLUMNS.index('AvgTone')] = 'nan'
        with self.assertRaises(ProviderError):
            parse_tsv('\t'.join(row).encode())
        with self.assertRaises(ProviderError):
            parse_tsv(FIXTURE.read_bytes()*2, max_records=1)

    def test_network_scope(self):
        validate_feed_url('https://data.gdeltproject.org/gdeltv2/20200101000000.export.CSV.zip')
        for url in ('http://data.gdeltproject.org/gdeltv2/lastupdate.txt',
                    'https://evil.example/gdeltv2/lastupdate.txt',
                    'https://data.gdeltproject.org/gdeltv2/../secret',
                    'https://data.gdeltproject.org/gdeltv2/lastupdate.txt?q=x'):
            with self.assertRaises(ProviderError):
                validate_feed_url(url)

    def test_archive_validation(self):
        for name, valid in [('20200102001500.export.CSV', True),('../20200102001500.export.CSV', False)]:
            memory = io.BytesIO()
            with zipfile.ZipFile(memory, 'w') as archive:
                archive.writestr(name, FIXTURE.read_bytes())
            if valid:
                self.assertEqual(unpack_archive(memory.getvalue()), FIXTURE.read_bytes())
            else:
                with self.assertRaises(ProviderError):
                    unpack_archive(memory.getvalue())
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('20200102001500.export.CSV', 'x'*1000000)
        with self.assertRaises(ProviderError):
            unpack_archive(memory.getvalue())

    def test_retry_bound_and_circuit(self):
        class Down:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                raise HTTPError(request.full_url, 429, 'limited', {}, None)
        provider = Down()
        client = GDELTClient(opener=provider, sleeper=lambda seconds:None)
        for _ in range(4):
            with self.assertRaises(ProviderError):
                client.fetch('https://data.gdeltproject.org/gdeltv2/lastupdate.txt')
        self.assertEqual(provider.calls, 9)

class StorageTests(unittest.TestCase):
    def test_idempotence_revisions_and_immutable_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/'test.sqlite')
            records = parse_tsv(FIXTURE.read_bytes(), synthetic=True)
            self.assertEqual(store.ingest(records), 1)
            self.assertEqual(store.ingest(records), 0)
            revised = deepcopy(records)
            revised[0]['source_checksum'] = 'different'
            self.assertEqual(store.ingest(revised), 1)
            snapshot = {'mode':'synthetic_demo','history':[{'date':'2020-01-01'}]}
            self.assertEqual(store.save_snapshot(snapshot), store.save_snapshot(snapshot))
            self.assertEqual(store.counts()['snapshots'], 1)
            with store.connect() as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("UPDATE snapshots SET mode='live'")
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute('DELETE FROM snapshots')

class APITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.snapshot = root/'demo.json'
        self.snapshot.write_text(json.dumps({'mode':'synthetic_demo','generated_at':'2026-01-03T00:00:00Z',
            'taxonomy':[{'id':'science'}], 'references':[], 'methodology':{'experimental':True},
            'history':[{'date':'2026-01-01','events':[{'id':'one','domain':'science'}],'alert':None,'js_topic':0.0},
                       {'date':'2026-01-02','events':[{'id':'two','domain':'science'}],'alert':'candidate','js_topic':0.1}]}))
        self.client = TestClient(create_app(self.snapshot, root/'test.sqlite', root))
    def tearDown(self):
        self.client.close()
        self.directory.cleanup()
    def test_repository_root_and_default_snapshot_path(self):
        self.assertEqual(API_ROOT, ROOT)
        default_app = create_app(db_path=Path(self.directory.name)/'default.sqlite')
        self.assertEqual(default_app.state.snapshot_path, ROOT/'dist/data/demo.json')
        if (ROOT/'dist/data/demo.json').exists():
            with TestClient(default_app) as client:
                self.assertEqual(client.get('/ready').status_code, 200)

    def test_alert_dict_states(self):
        data = json.loads(self.snapshot.read_text())
        data['history'][0]['alert'] = {'state':'none','reason':'calibrating'}
        data['history'][1]['alert'] = {'state':'candidate','reason':'experimental'}
        self.snapshot.write_text(json.dumps(data))
        self.assertEqual(len(self.client.get('/api/v1/alerts').json()['data']), 1)

    def test_installed_package_uses_explicit_asset_root(self):
        from unittest.mock import patch
        root = Path(self.directory.name)
        (root/'dist/data').mkdir(parents=True)
        (root/'dist/data/demo.json').write_text(self.snapshot.read_text())
        (root/'dist/index.html').write_text('<h1>WORLDLINE</h1>')
        # A non-editable installation lives in site-packages, not the asset tree.
        with patch('worldline.api.ROOT', root/'not-the-assets'), patch.dict('os.environ', {'WORLDLINE_ROOT':str(root)}):
            installed = create_app()
            with TestClient(installed) as client:
                self.assertEqual(client.get('/ready').status_code, 200)
                self.assertEqual(client.get('/').status_code, 200)

    def test_routes_envelopes(self):
        for path in ('/health','/ready','/api/v1/status','/api/v1/metrics/current','/api/v1/history','/api/v1/metrics/history','/api/v1/events','/api/v1/events/one','/api/v1/alerts','/api/v1/references','/api/v1/methodology'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, (path,response.text))
            self.assertIn('mode', response.json())
            self.assertIn('data_as_of', response.json())
        self.assertEqual(self.client.get('/api/v1/alerts').json()['data'][0]['date'],'2026-01-02')
    def test_filters_and_invalid_requests(self):
        response = self.client.get('/api/v1/events?start=2026-01-02&end=2026-01-02&domain=science')
        self.assertEqual(response.json()['data']['total'], 1)
        self.assertEqual(self.client.get('/api/v1/events/missing').status_code, 404)
        for query in ('start=nope','start=2026-01-02&end=2026-01-01','limit=0','domain=unknown','offset=-1','unknown=1'):
            self.assertEqual(self.client.get('/api/v1/events?'+query).status_code, 422, query)
        response = self.client.get('/api/v1/history?domain=science').json()['data']['items'][0]
        self.assertIn('global',response['metric_scope'])
    def test_absent_or_invalid_snapshot(self):
        self.snapshot.unlink()
        self.assertEqual(self.client.get('/ready').status_code,503)
        self.snapshot.write_text('{not json')
        self.assertEqual(self.client.get('/api/v1/status').status_code,503)
    def test_mutation_methods_not_supported(self):
        response = self.client.post('/api/v1/events',json={})
        self.assertEqual(response.status_code,405)
        self.assertIn('mode',response.json())
        response = self.client.get('/api/v1/no_such_route')
        self.assertEqual(response.status_code,404)
        self.assertIn('mode',response.json())

if __name__ == '__main__':
    unittest.main()
