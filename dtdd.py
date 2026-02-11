"""
DoesTheDogDie.com API client with local JSON file caching.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

DTDD_BASE = "https://www.doesthedogdie.com"
CACHE_DIR = Path(__file__).parent / ".cache"


class DTDDClient:
    def __init__(self, api_key: str, cache_ttl: int = 604800, api_delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-API-KEY": api_key,
        })
        self.cache_ttl = cache_ttl
        self.api_delay = api_delay
        self._last_request_time = 0.0
        CACHE_DIR.mkdir(exist_ok=True)

    def _rate_limit(self):
        """Enforce delay between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.api_delay:
            time.sleep(self.api_delay - elapsed)
        self._last_request_time = time.time()

    def _get_cache(self, key: str) -> dict | None:
        """Read from local JSON cache if fresh."""
        path = CACHE_DIR / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            if time.time() - data.get("_cached_at", 0) < self.cache_ttl:
                return data.get("_payload")
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def _set_cache(self, key: str, payload: dict):
        """Write to local JSON cache."""
        path = CACHE_DIR / f"{key}.json"
        path.write_text(json.dumps({
            "_cached_at": time.time(),
            "_payload": payload,
        }, indent=2))

    def search(self, query: str) -> list[dict]:
        """Search DTDD by title string. Returns list of matching items."""
        cache_key = f"search_{query.lower().replace(' ', '_')}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        self._rate_limit()
        resp = self.session.get(f"{DTDD_BASE}/dddsearch", params={"q": query})
        resp.raise_for_status()
        items = resp.json().get("items", [])
        self._set_cache(cache_key, items)
        return items

    def search_by_imdb(self, imdb_id: str) -> list[dict]:
        """Search DTDD by IMDB ID (e.g., 'tt1234567'). Returns list of matching items."""
        cache_key = f"imdb_{imdb_id}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        self._rate_limit()
        resp = self.session.get(f"{DTDD_BASE}/dddsearch", params={"imdb": imdb_id})
        resp.raise_for_status()
        items = resp.json().get("items", [])
        self._set_cache(cache_key, items)
        return items

    def get_media(self, item_id: int) -> dict:
        """Get full trigger/warning data for a DTDD media item."""
        cache_key = f"media_{item_id}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        self._rate_limit()
        resp = self.session.get(f"{DTDD_BASE}/media/{item_id}")
        resp.raise_for_status()
        data = resp.json()
        self._set_cache(cache_key, data)
        return data

    def clear_cache(self):
        """Remove all cached files."""
        if CACHE_DIR.exists():
            for f in CACHE_DIR.glob("*.json"):
                f.unlink()
            print(f"Cache cleared ({CACHE_DIR})")
