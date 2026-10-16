"""Read-only service for versioned snapshots. Import never touches disk/network."""
from __future__ import annotations
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
from .schemas import Snapshot
from .storage import Store

ROOT = Path(__file__).resolve().parents[2]


def create_app(snapshot_path=None, db_path=None, static_dir=None):
    root = Path(os.environ.get('WORLDLINE_ROOT', ROOT))
    app = FastAPI(title='WORLDLINE observatory', version='0.1.0', description='Read-only observations. Synthetic demonstration is never live data.')
    app.state.snapshot_path = Path(snapshot_path or os.environ.get('WORLDLINE_SNAPSHOT_PATH', root/'dist/data/demo.json'))
    app.state.db_path = Path(db_path or os.environ.get('WORLDLINE_DB_PATH', root/'data/worldline.sqlite'))
    app.state.store = None
    app.state.loaded = None
    app.state.signature = None

    def load():
        try:
            path = app.state.snapshot_path
            stat = path.stat()
            if stat.st_size > 32 * 1024 * 1024:
                raise ValueError('snapshot exceeds size limit')
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature != app.state.signature:
                raw = json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite number')))
                Snapshot.model_validate(raw)
                if app.state.store is None:
                    app.state.store = Store(app.state.db_path)
                app.state.checksum = app.state.store.save_snapshot(raw)
                app.state.loaded, app.state.signature = raw, signature
            return app.state.loaded
        except (OSError, ValueError, ValidationError, sqlite3.Error) as exc:
            raise HTTPException(503, 'snapshot unavailable or invalid; generate a valid snapshot and check storage') from exc

    def envelope(data, snapshot=None):
        snapshot = snapshot or app.state.loaded
        return {'mode': snapshot['mode'] if snapshot else 'unavailable',
                'data_as_of': snapshot.get('data_as_of', snapshot['history'][-1]['date']) if snapshot else None,
                'generated_at': snapshot.get('generated_at') if snapshot else None,
                'data': data}

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=envelope({'error': exc.detail}))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        details = [{'location': list(error['loc']), 'message': error['msg']} for error in exc.errors()]
        return JSONResponse(status_code=422, content=envelope({'error': 'invalid query', 'details': details}))

    @app.middleware('http')
    async def safe_headers(request: Request, call_next):
        allowed = {'/api/v1/history': {'start','end','domain','limit','offset'},
                   '/api/v1/metrics/history': {'start','end','domain','limit','offset'},
                   '/api/v1/events': {'start','end','domain','limit','offset'},
                   '/api/v1/alerts': {'start','end'}}
        if request.url.path.startswith('/api/v1/') and set(request.query_params) - allowed.get(request.url.path, set()):
            return JSONResponse(status_code=422, content=envelope({'error':'unknown query parameter'}))
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def bounds(rows, start, end):
        if start and end and start > end:
            raise HTTPException(422, 'start must be on or before end')
        return [row for row in rows if (not start or row['date'] >= start.isoformat()) and (not end or row['date'] <= end.isoformat())]

    def valid_domain(snapshot, domain):
        if domain is None:
            return
        names = {event.get('domain') for row in snapshot['history'] for event in row.get('events', [])}
        for key in ('topics', 'domains', 'taxonomy'):
            for value in snapshot.get(key, []):
                if isinstance(value, str):
                    names.add(value)
                elif isinstance(value, dict):
                    names.add(value.get('id', value.get('name')))
        if domain not in names:
            raise HTTPException(422, 'unknown domain')

    @app.get('/health')
    def health():
        return envelope({'status': 'ok', 'service': 'worldline'})

    @app.get('/ready')
    def ready():
        snapshot = load()
        return envelope({'status':'ready', 'history_windows':len(snapshot['history'])}, snapshot)

    @app.get('/api/v1/status')
    def status():
        snapshot = load()
        return envelope({'status':'ready', 'history_windows':len(snapshot['history']),
            'snapshot_checksum':app.state.checksum,
            'calibration':'experimental; not validated on real-world event labels'}, snapshot)

    @app.get('/api/v1/metrics/current')
    def current():
        snapshot = load()
        return envelope({key:value for key,value in snapshot['history'][-1].items() if key != 'events'}, snapshot)

    @app.get('/api/v1/metrics/history')
    @app.get('/api/v1/history')
    def history(start: date | None = None, end: date | None = None, domain: str | None = None,
                limit: int = Query(default=366, ge=1, le=3660), offset: int = Query(default=0, ge=0)):
        snapshot = load()
        valid_domain(snapshot, domain)
        rows = bounds(snapshot['history'], start, end)
        # Global metrics are never recomputed by a domain filter. Only observations filter.
        filtered = []
        for row in rows[offset:offset+limit]:
            item = dict(row)
            if domain:
                item['events'] = [event for event in item.get('events', []) if event.get('domain') == domain]
                item['metric_scope'] = 'global; domain filters events only'
            filtered.append(item)
        return envelope({'items':filtered,'total':len(rows),'offset':offset,'limit':limit}, snapshot)

    @app.get('/api/v1/events')
    def events(start: date | None = None, end: date | None = None, domain: str | None = None,
               limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
        snapshot = load()
        valid_domain(snapshot, domain)
        rows = bounds(snapshot['history'], start, end)
        items = [event for row in rows for event in row.get('events', []) if domain is None or event.get('domain') == domain]
        return envelope({'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit}, snapshot)

    @app.get('/api/v1/events/{event_id}')
    def event(event_id: str):
        snapshot = load()
        for row in snapshot['history']:
            for event in row.get('events', []):
                if event.get('id', event.get('event_id')) == event_id:
                    return envelope(event, snapshot)
        raise HTTPException(404, 'event not found')

    @app.get('/api/v1/alerts')
    def alerts(start: date | None = None, end: date | None = None):
        snapshot = load()
        rows = bounds(snapshot['history'], start, end)
        def state(row):
            alert = row.get('alert')
            return alert.get('state') if isinstance(alert, dict) else alert
        values = [{'date':row['date'],'alert':row['alert']} for row in rows if state(row) in ('candidate', 'corroborated', 'resolved')]
        return envelope(values, snapshot)

    @app.get('/api/v1/references')
    def references():
        snapshot = load()
        return envelope(snapshot.get('references'), snapshot)

    @app.get('/api/v1/methodology')
    def methodology():
        snapshot = load()
        return envelope(snapshot.get('methodology'), snapshot)

    directory = Path(static_dir or root/'dist')
    # StaticFiles with check_dir=False avoids requiring generated files at import.
    app.mount('/', StaticFiles(directory=str(directory), html=True, check_dir=False), name='dashboard')
    return app

app = create_app()
