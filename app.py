"""Streamlit composition root for the daily reporting dashboard.

Run with ``streamlit run app.py``. Presentation logic lives in the reporting
package; this file deliberately remains a stable, minimal deployment entry
point.
"""

from reporting.presentation.dashboard import *  # noqa: F403
