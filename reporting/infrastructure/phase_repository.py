"""
Phase (activity/campaign) management.

A "phase" is one data-collection activity. Each phase carries its own office
name, title, date window, response sheet, master list of zones and centers,
and zone/center name corrections. Admins create phases in the app, so no
office, location or campaign is built into the code.

Phases and uploaded master lists are saved through the storage layer
(storage.py): phases.json and masters/ next to the app, or MongoDB when
MONGODB_URI is set. The local files are created at runtime and never committed.

When phases.json doesn't exist yet, the first phase can come from the
`initial_phase` setting (see settings.py). Hosts like Streamlit Community
Cloud reset local files on restart, so this keeps a deployment set up.
"""
import os
import uuid
from datetime import date

from reporting.infrastructure.settings import get_table
from reporting.infrastructure.storage import StorageError, get_store

PHASES_KEY = "phases"
MASTER_FILE_TYPES = (".csv", ".xlsx")


def _empty() -> dict:
    return {"active_phase": None, "phases": []}


def _save(data: dict) -> None:
    try:
        get_store().save_json(PHASES_KEY, data)
    except StorageError as exc:
        raise RuntimeError(f"Could not save the phase settings. {exc}") from exc


def _initial_phase():
    """The phase described by the initial_phase setting, or None."""
    cfg = get_table("initial_phase")
    if not cfg:
        return None
    try:
        start = date.fromisoformat(str(cfg["start_date"]))
        end = date.fromisoformat(str(cfg["end_date"]))
    except (KeyError, ValueError):
        return None
    return {
        "id": "phase-initial",
        "office_name": str(cfg.get("office_name", "")),
        "title": str(cfg.get("title", "")) or "Activity",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "google_sheet_url": str(cfg.get("response_sheet_url", "")),
        "master_sheet_url": str(cfg.get("master_sheet_url", "")),
        "master_path": "",
        "zone_assignments": {},
        "center_assignments": [],
    }


def _load() -> dict:
    """Saved phases. Raises StorageError when the store can't be read."""
    data = get_store().load_json(PHASES_KEY)
    if data is not None:
        data.setdefault("phases", [])
        data.setdefault("active_phase", None)
        return data
    initial = _initial_phase()
    if initial is None:
        return _empty()
    data = {"active_phase": initial["id"], "phases": [initial]}
    try:
        _save(data)
    except RuntimeError:
        pass  # read-only disk: keep using the setting
    return data


def list_phases() -> list:
    return _load()["phases"]


def get_active_phase():
    """The active phase, or None when no phase has been created yet."""
    data = _load()
    if not data["phases"]:
        return None
    for p in data["phases"]:
        if p["id"] == data.get("active_phase"):
            return p
    return data["phases"][0]


def set_active_phase(phase_id: str) -> None:
    data = _load()
    if any(p["id"] == phase_id for p in data["phases"]):
        data["active_phase"] = phase_id
        _save(data)


def phase_dates(phase: dict):
    """Parsed (start_date, end_date) for a phase."""
    return date.fromisoformat(phase["start_date"]), date.fromisoformat(phase["end_date"])


def read_master_file(name: str):
    """Bytes of an uploaded master list saved under `name`, or None."""
    return get_store().load_file(name) if name else None


def _remove_master_file(phase: dict) -> None:
    if phase.get("master_path"):
        get_store().delete_file(phase["master_path"])


def _store_master_file(phase_id: str, master_bytes: bytes, filename: str) -> str:
    """Save an uploaded master list (CSV or Excel) and return its stored name."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in MASTER_FILE_TYPES:
        raise ValueError("The master list must be a .csv or .xlsx file.")
    name = f"masters/{phase_id}{ext}"
    try:
        get_store().save_file(name, master_bytes)
    except StorageError as exc:
        raise RuntimeError(f"Could not save the master list. {exc}") from exc
    return name


def create_phase(title: str, start_date: date, end_date: date, office_name: str = "",
                 google_sheet_url: str = "", master_sheet_url: str = "",
                 master_bytes: bytes = None, master_filename: str = None) -> dict:
    """Create a phase. Its master list comes from a linked Google Sheet
    (master_sheet_url) or an uploaded CSV/Excel file."""
    data = _load()
    phase_id = f"phase-{uuid.uuid4().hex[:8]}"
    master_path = ""
    master_version = ""
    if master_bytes:
        master_path = _store_master_file(phase_id, master_bytes, master_filename)
        master_version = uuid.uuid4().hex[:8]
    phase = {
        "id": phase_id,
        "office_name": office_name,
        "title": title,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "google_sheet_url": google_sheet_url,
        "master_sheet_url": master_sheet_url,
        "master_path": master_path,
        "master_version": master_version,
        "zone_assignments": {},
        "center_assignments": [],
    }
    data["phases"].append(phase)
    if not data.get("active_phase"):
        data["active_phase"] = phase_id
    _save(data)
    return phase


def update_active_phase(**fields) -> None:
    """Update simple fields (e.g. google_sheet_url) on the active phase."""
    data = _load()
    for p in data["phases"]:
        if p["id"] == data.get("active_phase"):
            p.update(fields)
            break
    _save(data)


def update_phase(phase_id: str, title: str = None, start_date: date = None,
                 end_date: date = None, office_name: str = None,
                 google_sheet_url: str = None, master_sheet_url: str = None,
                 master_bytes: bytes = None, master_filename: str = None) -> bool:
    """Edit any phase's fields; only the arguments provided are changed.
    An uploaded master file replaces the phase's stored list."""
    data = _load()
    for p in data["phases"]:
        if p["id"] != phase_id:
            continue
        if title is not None:
            p["title"] = title
        if office_name is not None:
            p["office_name"] = office_name
        if start_date is not None:
            p["start_date"] = start_date.isoformat()
        if end_date is not None:
            p["end_date"] = end_date.isoformat()
        if google_sheet_url is not None:
            p["google_sheet_url"] = google_sheet_url
        if master_sheet_url is not None:
            p["master_sheet_url"] = master_sheet_url
        if master_bytes:
            _remove_master_file(p)
            p["master_path"] = _store_master_file(phase_id, master_bytes, master_filename)
            p["master_version"] = uuid.uuid4().hex[:8]
        _save(data)
        return True
    return False


def delete_phase(phase_id: str):
    """Delete a phase and its uploaded master list. Deleting the active
    phase activates the first remaining one. Returns (ok, message)."""
    data = _load()
    target = next((p for p in data["phases"] if p["id"] == phase_id), None)
    if target is None:
        return False, "Phase not found."
    data["phases"] = [p for p in data["phases"] if p["id"] != phase_id]
    if data.get("active_phase") == phase_id:
        data["active_phase"] = data["phases"][0]["id"] if data["phases"] else None
    _save(data)
    _remove_master_file(target)
    return True, f"Phase '{target['title']}' deleted."


# ---------------------------------------------------------------------------
# Phase-scoped zone/center assignments, namespaced per phase so one
# activity's name fixes never leak into another's.
# ---------------------------------------------------------------------------

def load_zone_assignments() -> dict:
    phase = get_active_phase()
    return phase.get("zone_assignments", {}) if phase else {}


def save_zone_assignment(raw_zone: str, correct_zone: str) -> None:
    data = _load()
    for p in data["phases"]:
        if p["id"] == data.get("active_phase"):
            p.setdefault("zone_assignments", {})[raw_zone] = correct_zone
            break
    _save(data)


def load_center_assignments() -> list:
    phase = get_active_phase()
    return phase.get("center_assignments", []) if phase else []


def save_center_assignment(zone: str, raw_center: str, correct_center: str) -> None:
    def norm(s):
        return " ".join(str(s).strip().upper().split())
    data = _load()
    for p in data["phases"]:
        if p["id"] == data.get("active_phase"):
            assignments = p.setdefault("center_assignments", [])
            assignments[:] = [
                a for a in assignments
                if not (norm(a["zone"]) == norm(zone) and norm(a["raw_center"]) == norm(raw_center))
            ]
            assignments.append({"zone": zone, "raw_center": raw_center, "center": correct_center})
            break
    _save(data)
