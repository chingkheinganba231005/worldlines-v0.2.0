"""Polite access to Wikipedia year articles (raw wikitext) for the validation labels."""
from __future__ import annotations

import random
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

USER_AGENT = ("WORLDLINE/0.2 (https://github.com/chingkheinganba231005/worldlines-v0.2.0; research observatory; "
              "contact via GitHub issues)")


def fetch_year_article(year: int, attempts: int = 6, sleeper=time.sleep) -> str:
    if not 2000 <= year <= 2100:
        raise ValueError("year out of range")
    url = f"https://en.wikipedia.org/w/index.php?title={quote(str(year))}&action=raw"
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
                text = response.read(4_000_000).decode("utf-8")
            if "== Events ==" not in text and "==Events==" not in text:
                raise ValueError("unexpected page content (no Events section)")
            return text
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last = exc
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                break
            sleeper(min(60, 5 * 2 ** attempt + random.random() * 3))
    raise RuntimeError(f"could not fetch Wikipedia year article {year}: {last}")
