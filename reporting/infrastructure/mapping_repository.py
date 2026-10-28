"""File-backed storage for user-confirmed source-column mappings."""

from reporting.infrastructure.config_repository import load_config, save_config


def load_saved_mapping() -> dict:
    return load_config().get("column_mapping", {})


def save_mapping(mapping: dict) -> None:
    """Persist a confirmed mapping while retaining unrelated configuration."""
    config = load_config()
    config["column_mapping"] = mapping
    save_config(config)
