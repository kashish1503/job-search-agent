from __future__ import annotations

from .base import DiscoveryPlugin
from .url_utils import normalize_url

try:
    from .. import scraper
except ImportError:
    import scraper


class Web3Discovery(DiscoveryPlugin):
    def __init__(self):
        super().__init__(name="web3", enabled=True)

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        raw = scraper.scrape_web3career() + scraper.scrape_jobstash() + scraper.scrape_solana_jobs()
        items = []
        for job in raw[:limit]:
            normalized = normalize_url(job.get("url", ""))
            items.append(
                {
                    "url": job.get("url", ""),
                    "original_url": normalized["original_url"],
                    "canonical_url": normalized["canonical_url"],
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "snippet": job.get("description", "")[:500],
                    "source": self.name,
                    "query": "web3_sources",
                    "confidence": 0.8,
                    "metadata": {"job": job},
                }
            )
        return items
