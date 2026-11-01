from __future__ import annotations

import os

import requests

from .base import DiscoveryPlugin
from .url_utils import normalize_url


OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"
OLLAMA_WEB_FETCH_URL = "https://ollama.com/api/web_fetch"


def _enabled() -> bool:
    explicit = os.environ.get("ENABLE_OLLAMA_WEB_SEARCH")
    if explicit is not None:
        return explicit.lower() in ("1", "true", "yes")
    return bool(os.environ.get("OLLAMA_API_KEY", "").strip())


def _headers() -> dict:
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def ollama_web_search(query: str, max_results: int = 5) -> list[dict]:
    if not _enabled():
        return []
    if "Authorization" not in _headers():
        print("[ollama_web_search] OLLAMA_API_KEY missing, skipping")
        return []
    try:
        response = requests.post(
            OLLAMA_WEB_SEARCH_URL,
            headers=_headers(),
            json={"query": query, "max_results": max(1, min(max_results, 10))},
            timeout=30,
        )
        if response.status_code in (401, 402, 403, 429):
            print(f"[ollama_web_search] unavailable: HTTP {response.status_code}")
            return []
        response.raise_for_status()
        payload = response.json()
        return payload.get("results", []) if isinstance(payload, dict) else []
    except Exception as exc:
        print(f"[ollama_web_search] {exc}")
        return []


def ollama_web_fetch(url: str) -> dict:
    if not _enabled():
        return {}
    if "Authorization" not in _headers():
        print("[ollama_web_fetch] OLLAMA_API_KEY missing, skipping")
        return {}
    try:
        response = requests.post(
            OLLAMA_WEB_FETCH_URL,
            headers=_headers(),
            json={"url": url},
            timeout=30,
        )
        if response.status_code in (401, 402, 403, 429):
            print(f"[ollama_web_fetch] unavailable: HTTP {response.status_code}")
            return {}
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"[ollama_web_fetch] {exc}")
        return {}


class OllamaWebDiscovery(DiscoveryPlugin):
    def __init__(self):
        super().__init__(name="ollama_web", enabled=_enabled())

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        if not self.enabled:
            return []
        max_per_query = int(os.environ.get("OLLAMA_WEB_MAX_RESULTS", "5"))
        discovered: list[dict] = []
        seen = set()
        for query in campaign.get("search_queries", []):
            results = ollama_web_search(query, max_results=max_per_query)
            for result in results:
                url = result.get("url", "")
                if not url:
                    continue
                normalized = normalize_url(url)
                canonical = normalized["canonical_url"]
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                discovered.append(
                    {
                        "url": url,
                        "original_url": normalized["original_url"],
                        "canonical_url": canonical,
                        "title": result.get("title", "")[:200],
                        "company": "",
                        "snippet": result.get("content", "")[:500],
                        "source": self.name,
                        "query": query,
                        "confidence": 0.7,
                        "metadata": {"search_result": result},
                    }
                )
                if len(discovered) >= limit:
                    return discovered
        return discovered
