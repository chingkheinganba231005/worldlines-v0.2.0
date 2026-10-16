#!/usr/bin/env python3
"""Verify static deployment and optionally the self-hosted API."""
import argparse
import json
from urllib.parse import urlsplit
from urllib.request import urlopen

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--api', action='store_true')
    args = parser.parse_args()
    if urlsplit(args.url).scheme not in ('https', 'http'):
        parser.error('URL must be http(s)')
    base = args.url.rstrip('/')
    with urlopen(base+'/', timeout=20) as response:
        html = response.read(2*1024*1024).decode()
        assert response.status == 200 and 'worldline' in html.lower(), 'dashboard unavailable'
    with urlopen(base+'/data/demo.json', timeout=20) as response:
        data = json.load(response)
        assert data['history'] and data['mode'] in ('demo','synthetic','synthetic_demo'), 'invalid demo metadata'
    if args.api:
        for path in ('/health','/ready','/api/v1/status','/api/v1/metrics/current','/api/v1/metrics/history','/api/v1/events','/api/v1/alerts','/api/v1/references','/api/v1/methodology'):
            with urlopen(base+path, timeout=20) as response:
                payload = json.load(response)
                assert 'mode' in payload and 'data_as_of' in payload and 'data' in payload, path
    print(json.dumps({'url':base,'mode':data['mode'],'windows':len(data['history']),'api_checked':args.api,'verified':True}))
if __name__ == '__main__':
    main()
