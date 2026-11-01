from __future__ import annotations

from .ats import ATSDiscovery
from .hn import HNDiscovery
from .manual import ManualURLDiscovery
from .ollama_web import OllamaWebDiscovery
from .web3 import Web3Discovery


PLUGIN_TYPES = {
    "ollama_web": OllamaWebDiscovery,
    "ats": ATSDiscovery,
    "hn": HNDiscovery,
    "web3": Web3Discovery,
    "manual": ManualURLDiscovery,
}


def get_plugin(name: str):
    plugin_type = PLUGIN_TYPES.get(name)
    return plugin_type() if plugin_type else None


def get_plugins(names: list[str] | None = None):
    selected = names or list(PLUGIN_TYPES.keys())
    plugins = []
    for name in selected:
        plugin = get_plugin(name)
        if plugin:
            plugins.append(plugin)
    return plugins
