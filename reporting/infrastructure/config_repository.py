"""Small file-backed repository for application configuration."""

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def load_config() -> dict:
    try:
        with CONFIG_PATH.open(encoding="utf-8") as config_file:
            return json.load(config_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
            json.dump(config, config_file, indent=2)
    except OSError as exc:
        raise RuntimeError("Could not save application configuration.") from exc
