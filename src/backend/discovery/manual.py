from __future__ import annotations

from .base import DiscoveryPlugin
from .url_utils import normalize_url


class ManualURLDiscovery(DiscoveryPlugin):
    def __init__(self):
        super().__init__(name="manual", enabled=True)

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        items = []
        for url in (campaign.get("metadata", {}) or {}).get("manual_urls", [])[:limit]:
            normalized = normalize_url(url)
            items.append(
                {
                    "url": url,
                    "original_url": normalized["original_url"],
                    "canonical_url": normalized["canonical_url"],
                    "title": "",
                    "company": "",
                    "snippet": "",
                    "source": self.name,
                    "query": "manual_import",
                    "confidence": 1.0,
                    "metadata": {},
                }
            )
        return items
