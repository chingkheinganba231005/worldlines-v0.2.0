"""Bounded official GDELT Events ingestion. No publisher text is fetched."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import io
import math
from pathlib import Path
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import zipfile
from typing import Any
from .schemas import ProviderRecord

PARSER_VERSION = 'gdelt-events-2.0-v1'
PREFIX = 'https://data.gdeltproject.org/gdeltv2/'
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
RIGHTS = 'GDELT dataset metadata; attribute The GDELT Project. Linked publisher content retains upstream rights.'
COLUMNS = ['GLOBALEVENTID','SQLDATE','MonthYear','Year','FractionDate']
for actor in ('Actor1', 'Actor2'):
    COLUMNS += [actor+s for s in ('Code','Name','CountryCode','KnownGroupCode','EthnicCode','Religion1Code','Religion2Code','Type1Code','Type2Code','Type3Code')]
COLUMNS += ['IsRootEvent','EventCode','EventBaseCode','EventRootCode','QuadClass','GoldsteinScale','NumMentions','NumSources','NumArticles','AvgTone']
for actor in ('Actor1','Actor2','Action'):
    COLUMNS += [actor+'Geo_'+s for s in ('Type','FullName','CountryCode','ADM1Code','ADM2Code','Lat','Long','FeatureID')]
COLUMNS += ['DATEADDED','SOURCEURL']
assert len(COLUMNS) == 61 and COLUMNS[59] == 'DATEADDED'

class ProviderError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def source_url(value):
    """Return safe web link only; other GDELT citations remain metadata."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return None, None
    if parts.scheme in {'https', 'http'} and parts.hostname and not parts.username and not parts.password:
        return value, parts.hostname.lower()
    return None, None


def parse_tsv(payload: bytes, observed_at: str | None = None, *, synthetic=False, max_records=100000):
    if len(payload) > MAX_UNCOMPRESSED_BYTES:
        raise ProviderError('uncompressed data exceeds limit')
    observed_at = observed_at or utc_now()
    datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    try:
        stream = io.StringIO(payload.decode('utf-8-sig', errors='strict'), newline='')
        rows = csv.reader(stream, delimiter='\t', quoting=csv.QUOTE_NONE)
        records: list[dict[str, Any]] = []
        for line, row in enumerate(rows, 1):
            if not row:
                continue
            if len(records) >= max_records:
                raise ProviderError('record limit exceeded; refusing silent truncation')
            if len(row) != 61:
                raise ProviderError(f'line {line}: expected 61 fields, received {len(row)}')
            data = dict(zip(COLUMNS, row))
            try:
                if not re.fullmatch(r'[0-9]+', data['GLOBALEVENTID']):
                    raise ValueError('invalid record ID')
                if not re.fullmatch(r'[0-9]{8}', data['SQLDATE']) or not re.fullmatch(r'[0-9]{14}', data['DATEADDED']):
                    raise ValueError('invalid date format')
                occurrence = datetime.strptime(data['SQLDATE'], '%Y%m%d').replace(tzinfo=timezone.utc)
                availability = datetime.strptime(data['DATEADDED'], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
                if not re.fullmatch(r'[0-9]{2}', data['EventRootCode']) or not 1 <= int(data['EventRootCode']) <= 20:
                    raise ValueError('invalid CAMEO root')
                for key in ('NumMentions', 'NumSources', 'NumArticles'):
                    if int(data[key]) < 0:
                        raise ValueError('negative count')
                for key in ('GoldsteinScale', 'AvgTone'):
                    if not math.isfinite(float(data[key])):
                        raise ValueError('non-finite number')
            except ValueError as exc:
                raise ProviderError(f'line {line}: malformed required metadata: {exc}') from exc
            url, publisher = source_url(data['SOURCEURL'])
            clock_flags = []
            observed_dt = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
            if observed_dt.tzinfo is None:
                raise ProviderError('observed_at must be timezone-aware')
            if availability > observed_dt:
                clock_flags.append('provider_availability_after_retrieval_clock_skew_or_provider_timestamp_issue')
            record = ProviderRecord(
                id='gdelt:'+data['GLOBALEVENTID'], raw_source_id=data['GLOBALEVENTID'],
                event_time_utc=occurrence.isoformat().replace('+00:00', 'Z'),
                available_at_utc=availability.isoformat().replace('+00:00', 'Z'),
                observed_at_utc=observed_at, ingested_at_utc=utc_now(), source_url=url,
                source_citation=data['SOURCEURL'], publisher=publisher,
                label=f"{data['Actor1Name'] or 'Unspecified actor'} → CAMEO {data['EventCode']} → {data['Actor2Name'] or 'Unspecified actor'}",
                source_diversity_count=int(data['NumSources']), is_synthetic=synthetic,
                parser_version=PARSER_VERSION, source_checksum=hashlib.sha256('\t'.join(row).encode()).hexdigest(),
                metadata_rights=RIGHTS,
                credibility_flags=['automated_unverified_extraction','provider_id_is_not_verified_event_cluster','publisher_diversity_is_not_independence','occurrence_date_day_resolution','article_publication_time_unknown'] + clock_flags,
                raw_metadata=data,
            )
            records.append(record.model_dump())
        return records
    except UnicodeError as exc:
        raise ProviderError('invalid UTF-8 archive') from exc


def validate_feed_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'data.gdeltproject.org' or parts.query or parts.fragment:
        raise ProviderError('only official HTTPS GDELT data URLs are allowed')
    if not re.fullmatch(r'/gdeltv2/(?:lastupdate\.txt|[0-9]{14}\.export\.CSV\.zip)', parts.path):
        raise ProviderError('unsupported GDELT path')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('redirect refused; use official direct archive URL')


class GDELTClient:
    """Finite retries and process-local cooldown after repeated failed requests."""
    def __init__(self, *, timeout=20, attempts=3, sleeper=time.sleep, opener=None):
        self.timeout, self.attempts = timeout, min(max(attempts, 1), 3)
        self.sleeper, self.opener = sleeper, opener or build_opener(NoRedirect())
        self.failures, self.open_until = 0, 0.0

    def fetch(self, url):
        validate_feed_url(url)
        if time.monotonic() < self.open_until:
            raise ProviderError('provider circuit open; retry after cooldown')
        last = None
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers={'User-Agent':'WORLDLINE-research/0.1 (bounded metadata ingestion)'})
                with self.opener.open(request, timeout=self.timeout) as response:
                    validate_feed_url(response.geturl())
                    size = response.headers.get('Content-Length')
                    if size and int(size) > MAX_ARCHIVE_BYTES:
                        raise ProviderError('archive exceeds download byte limit')
                    payload = response.read(MAX_ARCHIVE_BYTES + 1)
                    if len(payload) > MAX_ARCHIVE_BYTES:
                        raise ProviderError('archive exceeds download byte limit')
                self.failures = 0
                return payload
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last = exc
                if isinstance(exc, HTTPError) and exc.code != 429 and exc.code < 500:
                    break
                if attempt + 1 < self.attempts:
                    self.sleeper(min(8.0, 0.5 * 2**attempt + random.random() * 0.25))
        self.failures += 1
        if self.failures >= 3:
            self.open_until = time.monotonic() + 60
        raise ProviderError(f'official GDELT request failed: {type(last).__name__}: {last}') from last

    def latest_export(self):
        payload = self.fetch(PREFIX+'lastupdate.txt')
        for line in payload.decode('ascii').splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2].endswith('.export.CSV.zip'):
                url = parts[2].replace('http://data.gdeltproject.org/', 'https://data.gdeltproject.org/', 1)
                validate_feed_url(url)
                return url
        raise ProviderError('lastupdate manifest contains no Events archive')


def unpack_archive(payload):
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ProviderError('archive exceeds byte limit')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) != 1:
                raise ProviderError('expected exactly one TSV member')
            member = entries[0]
            if '/' in member.filename or '\\' in member.filename or not re.fullmatch(r'[0-9]{14}\.export\.CSV', member.filename):
                raise ProviderError('unexpected archive member path/name')
            if member.file_size > MAX_UNCOMPRESSED_BYTES or member.file_size > max(member.compress_size, 1) * 250:
                raise ProviderError('archive expansion limit exceeded')
            with archive.open(member) as stream:
                payload = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
                if len(payload) > MAX_UNCOMPRESSED_BYTES:
                    raise ProviderError('archive expanded beyond limit')
                return payload
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ProviderError('invalid or encrypted archive') from exc
