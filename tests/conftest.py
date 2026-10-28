"""Keep tests independent of a developer's local .streamlit/secrets.toml."""

import pytest

from reporting.infrastructure import settings


@pytest.fixture(autouse=True)
def no_local_secrets(monkeypatch):
    monkeypatch.setattr(settings, "_streamlit_secrets", lambda: {})
