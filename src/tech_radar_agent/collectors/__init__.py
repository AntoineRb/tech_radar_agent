from typing import Any

from tech_radar_agent.collectors.base import Collector
from tech_radar_agent.collectors.hackernews import HackerNewsCollector

# Every available collector, by the `type` used in the config. Register new sources here.
COLLECTOR_TYPES: dict[str, type[Collector]] = {
    cls.type: cls for cls in (HackerNewsCollector,)
}


def build_collector(source_config: dict[str, Any]) -> Collector:
    """Create a collector from one source entry of the config.

    Example: {"type": "hackernews", "name": "hn-best", "feed": "best", "limit": 50}.
    Every key except `type` is passed to the collector's constructor.
    """
    options = dict(source_config)
    type_name = options.pop("type", None)
    if type_name not in COLLECTOR_TYPES:
        raise ValueError(f"Unknown source type {type_name!r}, expected one of {sorted(COLLECTOR_TYPES)}")
    return COLLECTOR_TYPES[type_name](**options)


__all__ = ["COLLECTOR_TYPES", "Collector", "HackerNewsCollector", "build_collector"]
