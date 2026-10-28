"""Streamlit composition root for the daily reporting dashboard.

Run with ``streamlit run app.py``. Streamlit re-runs this file on every
interaction, but Python only executes an imported module once per process.
The dashboard page is therefore run as a script on each rerun rather than
imported, so the page renders after every click.
"""

import runpy
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent / "reporting" / "presentation" / "dashboard.py"

runpy.run_path(str(DASHBOARD), run_name="__main__")
