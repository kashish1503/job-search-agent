from __future__ import annotations

from .ats import ATSDiscovery
from .manual import ManualURLDiscovery
from .ollama_web import OllamaWebDiscovery

try:  # optional: needs httpx/beautifulsoup
    from .watch import WatchDiscovery
except Exception:  # pragma: no cover - dependency missing
    WatchDiscovery = None


PLUGIN_TYPES = {
    "ollama_web": OllamaWebDiscovery,
    "ats": ATSDiscovery,
    "manual": ManualURLDiscovery,
}
if WatchDiscovery is not None:
    PLUGIN_TYPES["watch"] = WatchDiscovery


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
