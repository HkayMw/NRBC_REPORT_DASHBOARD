"""Load a phase's master list of zones and centers.

The list comes from a Google Sheet linked to the phase (shared as "Anyone
with the link can view", like the response sheet) or from an uploaded CSV
or Excel file. It needs three columns: District, Zone and Center.
"""

import io
from pathlib import Path

import pandas as pd

from reporting.domain.master_reference import prepare_master
from reporting.infrastructure.google_sheets import fetch_google_sheet

REQUIRED_MASTER_COLUMNS = ["District", "Zone", "Center"]
_COLUMN_ALIASES = {"centre": "Center", "center": "Center", "zone": "Zone", "district": "District"}


class MasterListError(RuntimeError):
    """The master list is missing, unreachable or has the wrong columns."""


def validate_master(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize headers (case, spacing, 'Centre'), check the required
    columns and drop rows without a zone or center."""
    df = df.rename(columns=lambda c: _COLUMN_ALIASES.get(str(c).strip().lower(), str(c).strip()))
    missing = [c for c in REQUIRED_MASTER_COLUMNS if c not in df.columns]
    if missing:
        raise MasterListError(
            f"The master list is missing column(s): {', '.join(missing)}. "
            "It needs District, Zone and Center columns."
        )
    df = df[REQUIRED_MASTER_COLUMNS].copy()
    for col in REQUIRED_MASTER_COLUMNS:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df = df[(df["Zone"] != "") & (df["Center"] != "")].reset_index(drop=True)
    if df.empty:
        raise MasterListError("The master list has no zones and centers in it.")
    return df


def read_master_upload(data: bytes, filename: str) -> pd.DataFrame:
    """Read and validate an uploaded master list (.csv or .xlsx)."""
    suffix = Path(filename or "").suffix.lower()
    try:
        if suffix == ".xlsx":
            df = pd.read_excel(io.BytesIO(data))
        elif suffix == ".csv":
            df = pd.read_csv(io.BytesIO(data))
        else:
            raise MasterListError("The master list must be a .csv or .xlsx file.")
    except MasterListError:
        raise
    except Exception as exc:
        raise MasterListError(f"Could not read the master list file: {exc}") from exc
    return validate_master(df)


def load_master(sheet_url: str = "", file_path: str | Path | None = None) -> pd.DataFrame:
    """Load, validate and prepare a phase's master list. A linked sheet
    takes priority over an uploaded file."""
    if sheet_url:
        try:
            df = fetch_google_sheet(sheet_url)
        except RuntimeError as exc:
            raise MasterListError(f"Could not load the master list sheet. {exc}") from exc
    elif file_path:
        path = Path(file_path)
        if not path.exists():
            raise MasterListError("The uploaded master list file is missing. Upload it again.")
        df = pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)
    else:
        raise MasterListError("This phase has no master list of zones and centers yet.")
    return prepare_master(validate_master(df))
