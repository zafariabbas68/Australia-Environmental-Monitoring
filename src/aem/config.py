"""Configuration loader for the AEM pipeline."""

from pathlib import Path
from typing import Any, Optional
import yaml

from aem import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config"


def load_config(name: str = "config") -> dict[str, Any]:
    """Load a YAML config file from config/."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def get(cfg: dict, path: str, default: Optional[Any] = None) -> Any:
    """Retrieve a nested value using dot notation."""
    keys = path.split(".")
    value = cfg
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value


def config_version(cfg: dict) -> str:
    """Return the pipeline version recorded in config."""
    return cfg.get("project", {}).get("version", "unknown")
