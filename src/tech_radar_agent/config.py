from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/interests.yaml")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Read the YAML config (interest profile and sources) and check its overall shape."""
    with path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)  # Never yaml.load: it can build arbitrary Python objects.

    if not isinstance(config, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    if not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError(f"{path}: `sources` must be a non-empty list")
    if not all(isinstance(source, dict) for source in config["sources"]):
        raise ValueError(f"{path}: every source must be a mapping with at least a `type`")
    return config
