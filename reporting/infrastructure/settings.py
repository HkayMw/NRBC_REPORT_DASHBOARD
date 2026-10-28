"""Deployment settings, read from environment variables or Streamlit secrets.

Settings (all optional):
- ADMIN_PIN: fixed admin PIN. When set, the PIN can't be changed in the app.
- DEMO_MODE: true locks phase and data-source settings and keeps name
  corrections and column mappings per visitor, for a public demo.
- REPORTING_TIMEZONE: IANA time zone for "today" defaults.
- initial_phase: a table (or a JSON string in an environment variable) used
  to create the first phase when none exists. Keys: office_name, title,
  start_date, end_date, response_sheet_url, master_sheet_url.
"""

import json
import os


def _streamlit_secrets():
    """Streamlit secrets (.streamlit/secrets.toml or the host's Secrets box)."""
    import streamlit as st

    return st.secrets


def get_setting(name: str, default=None):
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    try:
        secrets = _streamlit_secrets()
        if name in secrets:
            return secrets[name]
    except Exception:
        pass
    return default


def get_flag(name: str) -> bool:
    value = get_setting(name, False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_table(name: str) -> dict:
    """A settings table as a plain dict ({} when unset or invalid)."""
    value = get_setting(name)
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    try:
        return {str(k): v for k, v in dict(value).items()}
    except (TypeError, ValueError):
        return {}
