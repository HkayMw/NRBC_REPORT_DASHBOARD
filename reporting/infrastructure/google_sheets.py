"""
Fetch form-response data directly from a publicly viewable Google Sheet,
instead of requiring a manual file upload.

Works when the sheet is shared as "Anyone with the link can view" — no
Google API credentials needed, since we use the plain CSV export endpoint.

A direct link to a .csv file (https://... ending in .csv) or a .csv file
inside the project folder (e.g. examples/demo/responses.csv) also works,
which lets the demo run offline.
"""
import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def extract_sheet_id(url_or_id: str) -> str:
    """Accepts a full Google Sheets URL or a bare sheet ID and returns the ID."""
    url_or_id = url_or_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # assume they pasted the bare ID already
    return url_or_id


def extract_gid(url_or_id: str) -> str:
    """Extract the gid (sheet/tab id) from a URL if present, else default '0'."""
    match = re.search(r"[?&#]gid=([0-9]+)", url_or_id)
    if match:
        return match.group(1)
    return "0"


def to_csv_export_url(url_or_id: str) -> str:
    sheet_id = extract_sheet_id(url_or_id)
    gid = extract_gid(url_or_id)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _direct_csv_source(url_or_id: str):
    """A CSV URL or a project-local CSV path to read as-is, else None."""
    src = url_or_id.strip()
    if not src.lower().endswith(".csv"):
        return None
    if src.lower().startswith(("http://", "https://")):
        return src
    path = (PROJECT_ROOT / src).resolve()
    if PROJECT_ROOT in path.parents and path.is_file():
        return path
    return None


def fetch_google_sheet(url_or_id: str) -> pd.DataFrame:
    """Fetch the sheet as a DataFrame. Raises if the sheet isn't public/reachable."""
    direct = _direct_csv_source(url_or_id)
    source = direct if direct is not None else to_csv_export_url(url_or_id)
    try:
        df = pd.read_csv(source)
    except Exception as e:
        raise RuntimeError(
            "Couldn't fetch the Google Sheet. Make sure it's shared as "
            "'Anyone with the link can view' and the URL is correct. "
            f"Original error: {e}"
        )
    return df
