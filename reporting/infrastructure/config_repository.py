"""App configuration (admin PIN hash, confirmed column mapping)."""

from reporting.infrastructure.storage import StorageError, get_store

CONFIG_KEY = "config"


def load_config() -> dict:
    """The saved configuration ({} when nothing is saved yet).

    Raises StorageError when the store can't be read, so a temporary
    database problem never looks like an empty configuration that the
    next save would overwrite."""
    return get_store().load_json(CONFIG_KEY) or {}


def save_config(config: dict) -> None:
    try:
        get_store().save_json(CONFIG_KEY, config)
    except StorageError as exc:
        raise RuntimeError("Could not save application configuration.") from exc
