"""
Very lightweight PIN-based admin gate.

This is NOT enterprise-grade security — it's meant to stop casual viewers
from accidentally messing with the data connection or uploading files, not
to protect against a determined attacker. If this app is ever deployed
somewhere beyond trusted local/internal use, swap this for real auth
(e.g. streamlit-authenticator, or hosting behind SSO).
"""
import hashlib
import hmac

from reporting.infrastructure.config_repository import load_config, save_config
from reporting.infrastructure.settings import get_setting

_SALT = "nrbc-app-v1"  # fixed salt: obscures the PIN in config.json, not cryptographically hardened
DEFAULT_PIN = "1234"


def _hash(pin: str) -> str:
    return hashlib.sha256((_SALT + pin).encode()).hexdigest()


def _load_config() -> dict:
    return load_config()


def _save_config(data: dict) -> None:
    save_config(data)


def get_pin_hash() -> str:
    data = _load_config()
    if "admin_pin_hash" not in data:
        # first run: initialize with the default PIN
        data["admin_pin_hash"] = _hash(DEFAULT_PIN)
        _save_config(data)
    return data["admin_pin_hash"]


def _configured_pin():
    """The ADMIN_PIN setting, or None when the PIN is managed in the app."""
    pin = get_setting("ADMIN_PIN")
    return str(pin) if pin not in (None, "") else None


def pin_is_managed_by_settings() -> bool:
    return _configured_pin() is not None


def verify_pin(pin: str) -> bool:
    configured = _configured_pin()
    if configured is not None:
        return hmac.compare_digest(str(pin), configured)
    return hmac.compare_digest(_hash(pin), get_pin_hash())


def set_pin(new_pin: str) -> None:
    if pin_is_managed_by_settings():
        raise RuntimeError("The admin PIN is set by the ADMIN_PIN setting.")
    data = _load_config()
    data["admin_pin_hash"] = _hash(new_pin)
    _save_config(data)


def is_default_pin_active() -> bool:
    if pin_is_managed_by_settings():
        return False
    return get_pin_hash() == _hash(DEFAULT_PIN)
