from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscoveryPlugin:
    name: str
    enabled: bool = True

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        raise NotImplementedError
