"""Streamlit presentation for the daily reporting dashboard.

This module is the temporary page composition point while the existing tabs
are incrementally extracted into focused presentation-page modules. It only
coordinates widgets and application services; data preparation now happens in
``reporting.application.reporting_pipeline``.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
import plotly.express as px

from reporting.application.reporting_pipeline import prepare_reporting_dataset
from reporting.application.completion_status import calculate_completion_status
from reporting.application.report_export import generate_dashboard_excel_report
from reporting.application.dashboard_metrics import (
    calculate_dashboard_metrics,
    calculate_daily_trend,
    calculate_location_summaries,
    calculate_sex_breakdowns,
)
from reporting.domain.column_mapping import suggest_mapping, apply_mapping, REQUIRED_FIELDS
from reporting.domain.data_processing import load_raw, prepare_raw_columns, NUMERIC_COLS
from reporting.domain.master_reference import (
    completion_report,
    district_options, filter_by_district, districts_for_zones, districts_for_centers, normalize_name,
    find_unmatched_zones, find_unmatched_centers,
)
from reporting.infrastructure.excel_reports import build_report, build_completion_report
from reporting.infrastructure.google_sheets import fetch_google_sheet
from reporting.infrastructure.mapping_repository import load_saved_mapping, save_mapping
from reporting.infrastructure.master_reference_repository import (
    MasterListError, load_master, read_master_upload,
)
from reporting.infrastructure.phase_repository import (
    list_phases, get_active_phase, set_active_phase, create_phase,
    update_active_phase, update_phase, delete_phase, phase_dates, read_master_file,
    load_zone_assignments, save_zone_assignment,
    load_center_assignments, save_center_assignment,
)
from reporting.infrastructure.settings import get_flag, get_setting
from reporting.infrastructure.storage import StorageError, get_store
from reporting.presentation.auth import (
    is_default_pin_active, pin_is_managed_by_settings, set_pin, verify_pin,
)

# Activity dates, office name, response sheet and master list all come from
# the active phase (phase_repository); admins create phases in the app.

# Reports for a day are expected in by 4pm local time. Set the
# REPORTING_TIMEZONE setting to the office's IANA time zone.
REPORTING_TIMEZONE = str(get_setting("REPORTING_TIMEZONE", "Africa/Blantyre"))

# DEMO_MODE locks phase and data-source settings, and keeps name corrections
# and column mappings in the visitor's own session (see settings.py).
DEMO_MODE = get_flag("DEMO_MODE")


def _load_mapping():
    if DEMO_MODE:
        return dict(st.session_state.get("demo_mapping", {}))
    return load_saved_mapping()


def _save_mapping(mapping):
    if DEMO_MODE:
        st.session_state["demo_mapping"] = dict(mapping)
    else:
        save_mapping(mapping)


def _zone_assignments():
    if DEMO_MODE:
        return dict(st.session_state.get("demo_zone_assignments", {}))
    return load_zone_assignments()


def _assign_zone(raw_zone, correct_zone):
    if DEMO_MODE:
        st.session_state.setdefault("demo_zone_assignments", {})[raw_zone] = correct_zone
    else:
        save_zone_assignment(raw_zone, correct_zone)


def _center_assignments():
    if DEMO_MODE:
        return list(st.session_state.get("demo_center_assignments", []))
    return load_center_assignments()


def _assign_center(zone, raw_center, correct_center):
    if DEMO_MODE:
        st.session_state.setdefault("demo_center_assignments", []).append(
            {"zone": zone, "raw_center": raw_center, "center": correct_center}
        )
    else:
        save_center_assignment(zone, raw_center, correct_center)


def _default_report_range(phase_start, phase_end):
    """Default date range for the Trend and Reporting Status pickers:
    phase start through today, capped at the phase end — admins can still
    manually drag the picker up to the phase end / today, whichever is later.

    Before 4pm, today's reports aren't expected to be in yet, so the
    effective 'today' for default purposes rolls back to yesterday —
    otherwise today would show as an (unfairly) incomplete day.
    Uses the office's local time explicitly, since the server itself
    almost certainly runs in UTC."""
    now = datetime.now(ZoneInfo(REPORTING_TIMEZONE))
    effective_today = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    default_end = min(effective_today, phase_end)
    if default_end < phase_start:
        default_end = phase_start
    max_bound = max(phase_end, now.date())
    return phase_start, default_end, max_bound


st.set_page_config(page_title="Daily Reporting Dashboard", page_icon="🪪", layout="wide")
# Hide the hosting toolbar's Fork / GitHub / Deploy buttons. The toolbar itself
# stays visible because it holds the button that re-opens a collapsed sidebar.
st.markdown(
    "<style>[data-testid='stToolbarActions'], .stDeployButton "
    "{ display: none !important; }</style>",
    unsafe_allow_html=True,
)


def _read_master_upload(uploaded):
    """(bytes, filename) of a valid uploaded master list, (None, None) when
    nothing was uploaded. Shows the problem and stops on an invalid file."""
    if uploaded is None:
        return None, None
    data = uploaded.getvalue()
    try:
        read_master_upload(data, uploaded.name)
    except MasterListError as exc:
        st.error(str(exc))
        st.stop()
    return data, uploaded.name


def _check_master_sheet(url):
    """Make sure a linked master list sheet can be read before saving it."""
    if url:
        try:
            load_master(sheet_url=url)
        except MasterListError as exc:
            st.error(str(exc))
            st.stop()


MASTER_HELP = (
    "Master list of zones and centers, with columns District, Zone and Center. "
    "Link a Google Sheet (shared as 'Anyone with the link can view', like the "
    "response sheet) or upload an Excel or CSV file. A linked sheet is used "
    "when both are given."
)


def _render_create_phase_form():
    st.markdown("**Create a new phase**")
    st.caption(
        "A phase is one activity: the office running it, its dates, the response "
        "sheet, the master list of zones and centers, and its name corrections."
    )
    new_office = st.text_input("Office name", key="new_phase_office",
                               placeholder="e.g. Lakeside District Registration Office")
    new_title = st.text_input("Title", key="new_phase_title",
                              placeholder="e.g. Birth and ID registration, phase 4, Oct 2026")
    c1, c2 = st.columns(2)
    new_start = c1.date_input("Start date", key="new_phase_start")
    new_end = c2.date_input("End date", key="new_phase_end")
    new_url = st.text_input("Response Google Sheet URL (optional, can be set later)",
                            key="new_phase_url")
    st.caption(MASTER_HELP)
    new_master_url = st.text_input("Master list Google Sheet URL", key="new_phase_master_url")
    new_master = st.file_uploader("Or upload the master list (.xlsx or .csv)",
                                  type=["xlsx", "csv"], key="new_phase_master")
    if st.button("Create phase"):
        if not new_title.strip():
            st.error("Give the phase a title.")
        elif new_end < new_start:
            st.error("End date must be on or after the start date.")
        elif not new_master_url.strip() and new_master is None:
            st.error("Add the master list: link a Google Sheet or upload a file.")
        else:
            _check_master_sheet(new_master_url.strip())
            master_bytes, master_name = _read_master_upload(new_master)
            created = create_phase(
                new_title.strip(), new_start, new_end,
                office_name=new_office.strip(),
                google_sheet_url=new_url.strip(),
                master_sheet_url=new_master_url.strip(),
                master_bytes=master_bytes, master_filename=master_name,
            )
            set_active_phase(created["id"])
            st.cache_data.clear()
            st.success(f"Phase '{new_title.strip()}' created and activated.")
            st.rerun()


try:
    phase = get_active_phase()
except StorageError as exc:
    st.title("🧾 Daily Reporting Dashboard")
    st.error(f"Couldn't load the saved settings. {exc}")
    st.stop()
office_name = (phase or {}).get("office_name", "").strip()
st.title(f"🧾 {office_name}" if office_name else "🧾 Daily Reporting Dashboard")
if office_name:
    st.caption("Daily Reporting Dashboard")
st.caption(
    "Note: Birth Registration and National ID (NID) Registration are "
    "two separate activities captured on the same form — they're tracked "
    "side-by-side below, not as a before/after pipeline."
)
if DEMO_MODE:
    _demo_pin = get_setting("ADMIN_PIN")
    st.info(
        "**Demo with fictional data.** Every office, place and figure here is made up. "
        + (f"Log in as admin in the sidebar with PIN **{_demo_pin}** to try zone and "
           "center name corrections and the Excel exports. " if _demo_pin else "")
        + "Phase settings are locked, and any corrections you make are only visible to you."
    )

# ------------------------------------------------------------------
# Session state init
# ------------------------------------------------------------------
if "sheet_refresh_token" not in st.session_state:
    st.session_state.sheet_refresh_token = 0
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ------------------------------------------------------------------
# Admin login (sidebar)
# ------------------------------------------------------------------
st.sidebar.header("Admin")
if st.session_state.is_admin:
    st.sidebar.success("Admin mode active.")
    if st.sidebar.button("Log out"):
        st.session_state.is_admin = False
        st.rerun()
    if is_default_pin_active():
        st.sidebar.warning("Still using the default PIN (1234) — change it below.")
    if not pin_is_managed_by_settings() and not DEMO_MODE:
        with st.sidebar.expander("Change admin PIN"):
            new_pin = st.text_input("New PIN", type="password", key="new_pin_input")
            if st.button("Update PIN"):
                if new_pin and len(new_pin) >= 4:
                    set_pin(new_pin)
                    st.sidebar.success("PIN updated.")
                else:
                    st.sidebar.error("PIN must be at least 4 characters.")
else:
    pin_attempt = st.sidebar.text_input("Enter admin PIN", type="password", key="pin_attempt")
    if st.sidebar.button("Log in"):
        if verify_pin(pin_attempt):
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.sidebar.error("Incorrect PIN.")

is_admin = st.session_state.is_admin
# Admins manage phases and data sources, except in the locked demo.
can_manage = is_admin and not DEMO_MODE

# ------------------------------------------------------------------
# Active phase (activity): office name, title, dates, sheets and master
# list all come from here; admins create/switch phases without code changes.
# ------------------------------------------------------------------
if phase is None:
    if can_manage:
        st.info("No phase has been set up yet. Create the first one below.")
        _render_create_phase_form()
    else:
        st.info("No activity has been set up yet. An admin needs to log in and create a phase.")
    st.stop()

phase_start, phase_end = phase_dates(phase)
st.info(f"**Activity:** {phase['title']}  ({phase_start.strftime('%d %b %Y')} – {phase_end.strftime('%d %b %Y')})")

if is_admin and DEMO_MODE:
    st.caption("Phase and data-source settings are locked in this demo.")
if can_manage:
    with st.expander("🗃️ Phases / Activities (admin)"):
        st.caption(f"Phases, name corrections and the admin PIN are saved in {get_store().describe()}.")
        all_phases = list_phases()
        labels = {p["id"]: f"{p['title']} ({p['start_date']} – {p['end_date']})" for p in all_phases}
        ids = [p["id"] for p in all_phases]
        picked = st.selectbox(
            "Active phase", ids,
            index=ids.index(phase["id"]),
            format_func=lambda i: labels[i],
            key="phase_picker",
        )
        if picked != phase["id"] and st.button("Switch to selected phase"):
            set_active_phase(picked)
            st.rerun()

        sel_phase = next(p for p in all_phases if p["id"] == picked)

        st.divider()
        st.markdown("**Edit selected phase**")
        e_office = st.text_input("Office name", value=sel_phase.get("office_name", ""),
                                 key=f"edit_office_{picked}")
        e_title = st.text_input("Title", value=sel_phase["title"], key=f"edit_title_{picked}")
        ec1, ec2 = st.columns(2)
        e_start = ec1.date_input("Start date", value=date.fromisoformat(sel_phase["start_date"]),
                                 key=f"edit_start_{picked}")
        e_end = ec2.date_input("End date", value=date.fromisoformat(sel_phase["end_date"]),
                               key=f"edit_end_{picked}")
        e_url = st.text_input("Response Google Sheet URL", value=sel_phase.get("google_sheet_url", ""),
                              key=f"edit_url_{picked}")
        st.caption(MASTER_HELP)
        e_master_url = st.text_input("Master list Google Sheet URL",
                                     value=sel_phase.get("master_sheet_url", ""),
                                     key=f"edit_master_url_{picked}")
        if sel_phase.get("master_path"):
            st.caption("An uploaded master list file is stored for this phase.")
        e_master = st.file_uploader(
            "Upload or replace the master list file (optional, .xlsx or .csv)",
            type=["xlsx", "csv"], key=f"edit_master_{picked}",
        )
        if st.button("Save changes", key=f"edit_save_{picked}"):
            if not e_title.strip():
                st.error("Title can't be empty.")
            elif e_end < e_start:
                st.error("End date must be on or after the start date.")
            elif not e_master_url.strip() and e_master is None and not sel_phase.get("master_path"):
                st.error("Add the master list: link a Google Sheet or upload a file.")
            else:
                if e_master_url.strip() != sel_phase.get("master_sheet_url", ""):
                    _check_master_sheet(e_master_url.strip())
                master_bytes, master_name = _read_master_upload(e_master)
                update_phase(
                    picked, title=e_title.strip(), office_name=e_office.strip(),
                    start_date=e_start, end_date=e_end,
                    google_sheet_url=e_url.strip(), master_sheet_url=e_master_url.strip(),
                    master_bytes=master_bytes, master_filename=master_name,
                )
                st.cache_data.clear()
                st.success("Phase updated.")
                st.rerun()

        st.markdown("**Delete selected phase**")
        st.caption(
            "Deletes the phase, its name-correction assignments, and its uploaded "
            "master list file (if any). The submitted data in its Google Sheet is "
            "NOT touched. This cannot be undone."
        )
        del_ok = st.checkbox(
            f"Yes, permanently delete '{sel_phase['title']}'", key=f"del_confirm_{picked}"
        )
        if st.button("Delete phase", key=f"del_btn_{picked}", disabled=not del_ok):
            ok, msg = delete_phase(picked)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

        st.divider()
        _render_create_phase_form()

# ------------------------------------------------------------------
# Data source: Google Sheet (live) or manual upload
# ------------------------------------------------------------------
raw_df = None
saved_url = phase.get("google_sheet_url", "")

if can_manage:
    st.subheader("Data Source (admin)")
    source_mode = st.radio(
        "Where should the data come from?",
        ["Google Sheet (live)", "Upload Excel file"],
        horizontal=True,
    )

    if source_mode == "Google Sheet (live)":
        sheet_url = st.text_input(
            "Google Sheet URL (must be shared as 'Anyone with the link can view')",
            value=saved_url,
            placeholder="https://docs.google.com/spreadsheets/d/....../edit",
        )
        col_a, col_b = st.columns([1, 4])
        refresh_clicked = col_a.button("🔄 Refresh now")

        if sheet_url:
            if sheet_url != saved_url:
                update_active_phase(google_sheet_url=sheet_url)
            if refresh_clicked:
                st.session_state.sheet_refresh_token += 1

            @st.cache_data(ttl=900, show_spinner="Fetching latest responses from Google Sheets...")
            def _cached_fetch(url, refresh_token):
                return fetch_google_sheet(url)

            try:
                fetched = _cached_fetch(sheet_url, st.session_state.sheet_refresh_token)
                raw_df = prepare_raw_columns(fetched)
                col_b.success(f"Loaded {len(raw_df)} rows from Google Sheets.", icon="✅")
            except RuntimeError as e:
                st.error(str(e))
        else:
            st.info("Paste the Google Sheet URL above to load data automatically.")
    else:
        st.caption("Note: an uploaded file is only visible in this admin session — "
                   "regular viewers will still see the connected Google Sheet, not this upload.")
        uploaded_file = st.file_uploader("Upload the Excel file (.xlsx)", type=["xlsx"])
        if uploaded_file is not None:
            raw_df = load_raw(uploaded_file)

else:
    if saved_url:
        @st.cache_data(ttl=900, show_spinner="Loading latest data...")
        def _cached_fetch_viewer(url):
            return fetch_google_sheet(url)

        try:
            fetched = _cached_fetch_viewer(saved_url)
            raw_df = prepare_raw_columns(fetched)
        except RuntimeError as e:
            st.error(f"Couldn't load the connected data source: {e}")
    else:
        st.info("No data source has been connected yet. An admin needs to log in and connect one.")

if raw_df is None:
    st.stop()

# ------------------------------------------------------------------
# Column mapping — resilient to header drift (renamed/reordered columns)
# ------------------------------------------------------------------
raw_headers = list(raw_df.columns)
saved_mapping = _load_mapping()

mapping = {h: c for h, c in saved_mapping.items() if h in raw_headers}
already_mapped_canonicals = set(mapping.values())

confident, suggestions, unmapped = suggest_mapping(
    [h for h in raw_headers if h not in mapping]
)
for h, c in confident.items():
    if c not in already_mapped_canonicals:
        mapping[h] = c
        already_mapped_canonicals.add(c)

needs_review = {
    c: cands for c, cands in suggestions.items()
    if c not in already_mapped_canonicals
}

if needs_review or len(mapping) < len(REQUIRED_FIELDS):
    if is_admin:
        with st.expander("🗂️ Column Mapping — please confirm", expanded=True):
            st.write(
                "Some columns couldn't be confidently matched to what this app expects. "
                "Pick the right source column for each field below (or 'None' to skip)."
            )
            options = ["(none)"] + raw_headers
            for canonical in REQUIRED_FIELDS:
                if canonical in already_mapped_canonicals:
                    continue
                candidates = suggestions.get(canonical, [])
                default_idx = 0
                if candidates:
                    best_header = candidates[0][0]
                    if best_header in options:
                        default_idx = options.index(best_header)
                choice = st.selectbox(
                    f"**{canonical}**" + (f"  _(best guess: {candidates[0][0]}, {candidates[0][1]:.0%} similar)_" if candidates else "  _(no match found)_"),
                    options, index=default_idx, key=f"map_{canonical}"
                )
                if choice != "(none)":
                    mapping[choice] = canonical

            if st.button("Confirm mapping"):
                _save_mapping(mapping)
                st.rerun()
    else:
        st.warning("The data connection needs setup by an admin before this can be shown.")
        st.stop()

missing_required = [c for c in REQUIRED_FIELDS if c not in mapping.values()]
if missing_required:
    if is_admin:
        st.error(f"Missing required column(s): {', '.join(missing_required)}. Please map them above.")
    else:
        st.warning("The data connection needs setup by an admin before this can be shown.")
    st.stop()

raw_df = apply_mapping(raw_df, mapping)


# ------------------------------------------------------------------
# Master list of zones and centers for this phase (linked sheet or upload)
# ------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner="Loading the master list of zones and centers...")
def _cached_master(sheet_url, master_name, master_version, refresh_token):
    # master_version changes on every upload, so a new file is never served from cache.
    data = read_master_file(master_name) if master_name and not sheet_url else None
    return load_master(sheet_url=sheet_url, file_bytes=data, filename=master_name)


try:
    master_df = _cached_master(
        phase.get("master_sheet_url", ""), phase.get("master_path", ""),
        phase.get("master_version", ""), st.session_state.sheet_refresh_token,
    )
except (MasterListError, StorageError) as exc:
    if is_admin:
        st.error(f"{exc} Fix it under Phases / Activities above.")
    else:
        st.warning("The master list of zones and centers needs setup by an admin before this can be shown.")
    st.stop()


# Cache the full cleaning + assignment pipeline. Streamlit reruns this whole
# script on every widget interaction (a filter change, a button click
# anywhere on the page) — without caching, ~1000 rows of cleaning, dedup,
# and date-correction would redo identical work dozens of times per minute
# even though the underlying data only changes once per fetch cycle.
@st.cache_data(show_spinner=False)
def _cached_pipeline(raw_df, zone_assignments, center_assignments, master_df, p_start, p_end):
    dataset = prepare_reporting_dataset(
        raw_df, zone_assignments, center_assignments, master_df, p_start, p_end
    )
    return dataset.cleaned_data, dataset.quality_report, dataset.master_reference


zone_assignments = _zone_assignments()
center_assignments = _center_assignments()
cleaned_df, report, master_df = _cached_pipeline(
    raw_df, zone_assignments, center_assignments,
    master_df, phase_start, phase_end,
)

# ------------------------------------------------------------------
# Data quality review panel
# ------------------------------------------------------------------
with st.expander("🔍 Data Quality Review", expanded=False):
    st.write(f"**Duplicate/resubmitted rows auto-removed (kept latest by timestamp):** {report['duplicates_removed_count']}")
    if len(report["duplicates_found"]):
        st.dataframe(report["duplicates_found"][["Timestamp", "ZONE NAME", "CENTER NAME", "Date"] + NUMERIC_COLS])

    DIAG_COLS = ["ZONE NAME", "CENTER NAME", "Date",
                 "Total Male Births Registered", "Total Female Births Registered",
                 "Total Males Processed", "Total Females Processed"]

    if len(report["missing_numeric_rows"]):
        st.warning(f"{len(report['missing_numeric_rows'])} row(s) had missing numeric values (filled with 0).")
        cols_present = [c for c in DIAG_COLS if c in report["missing_numeric_rows"].columns]
        st.dataframe(report["missing_numeric_rows"][cols_present].astype(str))

    if len(report["negative_rows"]):
        st.warning(f"{len(report['negative_rows'])} row(s) had negative numbers.")
        cols_present = [c for c in DIAG_COLS if c in report["negative_rows"].columns]
        st.dataframe(report["negative_rows"][cols_present].astype(str))

    if len(report["non_integer_rows"]):
        st.warning(
            f"{len(report['non_integer_rows'])} row(s) have a non-whole-number value "
            "(e.g. 0.01) in a count column — these are almost certainly data entry "
            "errors and are worth checking with the reporting center."
        )
        st.dataframe(report["non_integer_rows"][
            [c for c in DIAG_COLS if c in report["non_integer_rows"].columns]
        ])

    if len(report.get("out_of_range_rows", [])):
        st.warning(
            f"{len(report['out_of_range_rows'])} row(s) have a date outside the "
            f"activity window ({phase_start.strftime('%d %b')}–{phase_end.strftime('%d %b %Y')}) "
            "that couldn't be auto-corrected — likely data entry errors. They are "
            "excluded from all figures (the date filter is bounded to the activity "
            "window). Fix the date in the source sheet to include them."
        )
        st.dataframe(report["out_of_range_rows"].astype(str))

    if len(report["date_corrected_rows"]):
        st.info(
            f"{len(report['date_corrected_rows'])} row(s) had a date outside the "
            f"activity window ({phase_start.strftime('%d %b')}–{phase_end.strftime('%d %b')}) "
            "that resolved correctly once day/month were swapped — auto-corrected. "
            "This usually means a spreadsheet locale mismatch, not a data entry mistake."
        )
        st.dataframe(report["date_corrected_rows"])

    st.subheader("Zone Assignment")
    st.caption(
        "Submitted zone names that don't match any of the predefined zones "
        "from the official campaign registry. Assign each to the correct zone."
    )

    @st.cache_data(show_spinner=False)
    def _cached_unmatched_zones(cleaned_df, master_df):
        return find_unmatched_zones(cleaned_df, master_df)

    unmatched_zones = _cached_unmatched_zones(cleaned_df, master_df)
    if not unmatched_zones:
        st.write("All submitted zone names match the master reference. ✅")
    else:
        st.warning(f"{len(unmatched_zones)} submitted zone name(s) need assignment.")
        if is_admin:
            zone_options = sorted(master_df["Zone"].unique())
            for u in unmatched_zones:
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**'{u['zone']}'**")
                default_idx = zone_options.index(u["suggested_zone"]) if u["suggested_zone"] in zone_options else 0
                chosen = c2.selectbox("Correct zone", zone_options, index=default_idx,
                                       key=f"zoneassign_{u['zone']}", label_visibility="collapsed")
                if c3.button("Assign", key=f"zoneassign_btn_{u['zone']}"):
                    _assign_zone(u["zone"], chosen)
                    st.rerun()
        else:
            st.dataframe(pd.DataFrame(unmatched_zones))

    st.subheader("Center Assignment")
    st.caption(
        "Submitted center names that don't match any known center. If the "
        "zone is also valid, choices are scoped to that zone's centers; "
        "otherwise you can pick from the full list — independent of whether "
        "Zone Assignment above has been resolved."
    )

    @st.cache_data(show_spinner=False)
    def _cached_unmatched_centers(cleaned_df, master_df):
        return find_unmatched_centers(cleaned_df, master_df)

    unmatched_centers = _cached_unmatched_centers(cleaned_df, master_df)
    if not unmatched_centers:
        st.write("All submitted center names match the master reference. ✅")
    else:
        st.warning(f"{len(unmatched_centers)} submitted center name(s) need assignment.")
        if is_admin:
            all_centers_sorted = sorted(master_df["Center"].unique())
            for u in unmatched_centers:
                zone_matches = master_df["Zone"].str.upper() == u["zone"].strip().upper()
                center_options = sorted(master_df.loc[zone_matches, "Center"].unique())
                if not center_options:
                    center_options = all_centers_sorted  # zone itself doesn't match — pick from everything
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**'{u['zone']}' / '{u['center']}'**")
                default_idx = center_options.index(u["suggested_center"]) if u["suggested_center"] in center_options else 0
                chosen = c2.selectbox("Correct center", center_options, index=default_idx,
                                       key=f"centerassign_{u['zone']}_{u['center']}", label_visibility="collapsed")
                if c3.button("Assign", key=f"centerassign_btn_{u['zone']}_{u['center']}"):
                    _assign_center(u["zone"], u["center"], chosen)
                    st.rerun()
        else:
            st.dataframe(pd.DataFrame(unmatched_centers))

# Everything below only counts rows mapped to the master list (the sidebar
# filters are master-driven), so surface how much data is being held back —
# otherwise unmapped submissions would vanish from the totals silently.
_n_unmapped = int((~(
    cleaned_df["ZONE NAME"].apply(normalize_name).isin(set(master_df["Zone_norm"]))
    & cleaned_df["CENTER NAME"].apply(normalize_name).isin(set(master_df["Center_norm"]))
)).sum())
if _n_unmapped:
    st.warning(
        f"{_n_unmapped} submitted row(s) have a zone or center not yet mapped "
        "to the master reference list and are excluded from all figures below. "
        "Resolve them in Zone/Center Assignment (Data Quality Review) to include them."
    )

# ------------------------------------------------------------------
# District scope — everything below (sidebar filters, KPIs, charts,
# reporting status, exports) sees only the selected district's data.
# A submitted row's district comes from its (assignment-corrected) zone
# looked up in the master list; rows whose zone is still unmapped can't
# be placed in a district, so they only appear under ALL.
# ------------------------------------------------------------------
district_choice = st.radio(
    "District",
    ["ALL"] + district_options(master_df),
    horizontal=True,
    key="district_scope",
)
if district_choice != "ALL":
    cleaned_df, master_df = filter_by_district(cleaned_df, master_df, district_choice)
    if cleaned_df.empty:
        st.warning(f"No submissions mapped to {district_choice} yet.")
        st.stop()

# ------------------------------------------------------------------
# Sidebar filters
# ------------------------------------------------------------------
st.sidebar.header("Filters")
# Zone/Center options come from the master reference list (already scoped by
# the district toggle) — NOT from submitted data — so a center that hasn't
# reported at all is still selectable and visible downstream. Submitted rows
# are matched on normalized names; rows whose zone or center isn't mapped to
# the master list are excluded from these views entirely (resolve them in
# Zone/Center Assignment above to bring them in).
zones = sorted(master_df["Zone"].unique())
selected_zones = st.sidebar.multiselect("Zone", zones, default=zones)
selected_zone_norms = {normalize_name(z) for z in selected_zones}

centers_available = sorted(master_df.loc[master_df["Zone_norm"].isin(selected_zone_norms), "Center"].unique())
selected_centers = st.sidebar.multiselect("Center", centers_available, default=centers_available)
selected_center_norms = {normalize_name(c) for c in selected_centers}

# The date filter is bounded by the ACTIVE PHASE's window — never by the
# data. A mistyped date (e.g. 8 Sep in a July campaign) used to stretch
# this picker months wide; such rows are now flagged in Data Quality
# Review instead and excluded by these bounds.
min_date = phase_start
max_date = phase_end
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

zc_mask = (
    cleaned_df["ZONE NAME"].apply(normalize_name).isin(selected_zone_norms)
    & cleaned_df["CENTER NAME"].apply(normalize_name).isin(selected_center_norms)
)

filtered = cleaned_df[
    zc_mask
    & (cleaned_df["Date"].dt.date >= start_date)
    & (cleaned_df["Date"].dt.date <= end_date)
].copy()

# Zone/Center filtered but NOT date-filtered — for tabs (Trend) that use
# their own dedicated date range picker instead of the sidebar's.
filtered_zone_center_only = cleaned_df[zc_mask].copy()

# Standardize display casing to the master list's spelling, so one center
# submitted under two casings can't split into two rows in groupbys/charts.
_zone_disp = dict(zip(master_df["Zone_norm"], master_df["Zone"]))
_center_disp = dict(zip(master_df["Center_norm"], master_df["Center"]))
for _df in (filtered, filtered_zone_center_only):
    _df["ZONE NAME"] = _df["ZONE NAME"].apply(lambda z: _zone_disp[normalize_name(z)])
    _df["CENTER NAME"] = _df["CENTER NAME"].apply(lambda c: _center_disp[normalize_name(c)])

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ------------------------------------------------------------------
# KPIs
# ------------------------------------------------------------------
metrics = calculate_dashboard_metrics(filtered)
total_birth = metrics.total_birth_registrations
total_male_birth = metrics.male_births
total_female_birth = metrics.female_births
total_nid = metrics.total_nid_registrations
total_male_nid = metrics.male_nid_registrations
total_female_nid = metrics.female_nid_registrations

st.subheader("Birth Registration")
b1, b2, b3 = st.columns(3)
b1.metric("Total Birth Registrations", f"{total_birth:,}")
b2.metric("Male", f"{total_male_birth:,}")
b3.metric("Female", f"{total_female_birth:,}")

st.subheader("National ID (NID) Registration")
n1, n2, n3 = st.columns(3)
n1.metric("Total NID Registrations", f"{total_nid:,}")
n2.metric("Male", f"{total_male_nid:,}")
n3.metric("Female", f"{total_female_nid:,}")

st.divider()

# ------------------------------------------------------------------
# Per-zone / per-center summaries
# ------------------------------------------------------------------
summaries = calculate_location_summaries(filtered, selected_zones, selected_centers)
zone_summary = summaries.by_zone
# Include every selected master-list zone, even ones with no submissions yet —
# a zone that hasn't reported shows up with zeros instead of vanishing.
# Under ALL, zones from both districts are mixed in one table — label each
# with its district so the view stays readable. (Redundant when a single
# district is selected, so skipped there.)
if district_choice == "ALL":
    zone_summary.insert(0, "District", districts_for_zones(zone_summary.index, master_df))

center_summary = summaries.by_center
# Same as zone_summary: every selected master-list center appears, zeros
# for centers that haven't reported.

# ------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["By Zone", "By Center", "Trend Over Time", "Male vs Female", "Reporting Status"]
)

with tab1:
    fig = px.bar(zone_summary.reset_index(), x="ZONE NAME", y="Total Birth Registrations",
                 title="Birth Registrations by Zone", text_auto=True)
    st.plotly_chart(fig, width='stretch')

    nid_sorted = zone_summary.reset_index().sort_values("Total NID Registrations", ascending=False)
    fig_nid = px.bar(nid_sorted, x="ZONE NAME", y="Total NID Registrations",
                      title="NID Registrations by Zone", text_auto=True)
    st.plotly_chart(fig_nid, width='stretch')

    st.dataframe(zone_summary)

with tab2:
    n_centers = len(center_summary)
    if n_centers > 5:
        top_n = st.slider("Show top N centers", 5, min(50, n_centers), min(15, n_centers))
    else:
        top_n = n_centers  # too few centers for a slider: show them all
    top_centers = center_summary.head(top_n)
    fig = px.bar(top_centers.reset_index(), x="CENTER NAME", y="Total Birth Registrations",
                 title=f"Birth Registrations — Top {top_n} Centers", text_auto=True)
    fig.update_xaxes(tickangle=45)
    st.plotly_chart(fig, width='stretch')

    nid_top_sorted = center_summary.reset_index().sort_values("Total NID Registrations", ascending=False).head(top_n)
    fig_nid = px.bar(nid_top_sorted, x="CENTER NAME", y="Total NID Registrations",
                      title=f"NID Registrations — Top {top_n} Centers", text_auto=True)
    fig_nid.update_xaxes(tickangle=45)
    st.plotly_chart(fig_nid, width='stretch')

    st.dataframe(center_summary)

with tab3:
    default_start_3, default_end_3, max_bound_3 = _default_report_range(phase_start, phase_end)
    range_3 = st.date_input(
        "Date range", value=(default_start_3, default_end_3),
        min_value=phase_start, max_value=max_bound_3,
        key="trend_range",
    )
    if isinstance(range_3, tuple) and len(range_3) == 2:
        start_3, end_3 = range_3
    else:
        start_3, end_3 = default_start_3, default_end_3

    trend = calculate_daily_trend(filtered_zone_center_only, start_3, end_3)
    if len(trend) > 1:
        fig = px.line(trend, x="Date", y=["Total Birth Registrations", "Total NID Registrations"], markers=True,
                      title="Birth & NID Registrations Over Time")
        # Same month throughout the activity — show day-of-month, not month names,
        # and force one tick per actual day so it can't be misread as spanning months.
        fig.update_xaxes(tickformat="%d %b", dtick="D1")
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Only one date in the selected range — trend chart will populate as more days are added.")
    st.dataframe(trend)

with tab4:
    sex_breakdowns = calculate_sex_breakdowns(filtered)
    st.markdown("**Birth Registration — Male vs Female**")
    zone_mf_birth = sex_breakdowns.birth_by_zone
    fig = px.bar(zone_mf_birth, x="ZONE NAME", y=["Male", "Female"], barmode="stack",
                 title="Birth Registrations by Zone — Male vs Female")
    st.plotly_chart(fig, width='stretch')

    overall_birth = sex_breakdowns.overall_birth
    fig_pie = px.pie(overall_birth, names="Sex", values="Count", title="Overall Birth Registration Male/Female Split")
    st.plotly_chart(fig_pie, width='stretch')

    st.markdown("**NID Registration — Male vs Female**")
    zone_mf_nid = sex_breakdowns.nid_by_zone
    fig2 = px.bar(zone_mf_nid, x="ZONE NAME", y=["Male", "Female"], barmode="stack",
                  title="NID Registrations by Zone — Male vs Female")
    st.plotly_chart(fig2, width='stretch')

    overall_nid = sex_breakdowns.overall_nid
    fig_pie2 = px.pie(overall_nid, names="Sex", values="Count", title="Overall NID Registration Male/Female Split")
    st.plotly_chart(fig_pie2, width='stretch')

with tab5:
    st.caption(
        f"Activity runs {phase_start.strftime('%d %b')} to {phase_end.strftime('%d %b %Y')}. "
        "Pick a zone and date range to see each center's submissions."
    )
    default_start_5, default_end_5, max_bound_5 = _default_report_range(phase_start, phase_end)
    range_5 = st.date_input(
        "Date range", value=(default_start_5, default_end_5),
        min_value=phase_start, max_value=max_bound_5,
        key="reporting_status_range",
    )
    if isinstance(range_5, tuple) and len(range_5) == 2:
        start_5, end_5 = range_5
    else:
        start_5, end_5 = default_start_5, default_end_5

    zone_options_5 = sorted(master_df["Zone"].unique())
    picked_zone = st.selectbox("Zone", zone_options_5, key="reporting_status_zone")

    completion_status = calculate_completion_status(
        cleaned_df, master_df, picked_zone, start_5, end_5
    )
    matrix = completion_status.matrix
    day_cols = [c for c in matrix.columns if c != "Center"]
    st.metric(
        f"Reports submitted in {picked_zone}",
        f"{completion_status.total_submitted} / {completion_status.total_expected}  :  "
        f"{completion_status.percentage}%",
    )
    st.dataframe(
        matrix,
        hide_index=True,
        column_config={
            c: st.column_config.NumberColumn(c, format="%d") for c in day_cols
        },
    )

    st.divider()
    st.caption(
        "Exports completion for every predefined zone and center over the date "
        "range above. Only counts submissions already mapped to a predefined "
        "zone/center (via the Zone/Center Assignment above) — unmapped "
        "submissions are excluded, not guessed at."
    )
    if st.button("📊 Generate Zone & Center Completion Report"):
        district_completion, zone_completion, center_completion = completion_report(
            cleaned_df, master_df, start_5, end_5
        )
        st.session_state.completion_report_bytes = build_completion_report(
            district_completion, zone_completion, center_completion, start_5, end_5
        )

    if st.session_state.get("completion_report_bytes"):
        st.download_button(
            "Download Completion Report",
            data=st.session_state.completion_report_bytes,
            file_name="zone_center_completion_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.divider()

# ------------------------------------------------------------------
# Export — admin only
# ------------------------------------------------------------------
if is_admin:
    st.subheader("📤 Export Report (admin)")
    st.caption("Report generation only runs when you click below — it doesn't rebuild on every page interaction.")
    if st.button("Generate Excel Report"):
        kpis = {
            "Total Birth Registrations": total_birth,
            "Male Births": total_male_birth,
            "Female Births": total_female_birth,
            "Total NID Registrations": total_nid,
            "Male NID": total_male_nid,
            "Female NID": total_female_nid,
            "Number of Zones": filtered["ZONE NAME"].nunique(),
            "Number of Centers": filtered["CENTER NAME"].nunique(),
            "Office": office_name,
            "Date Range": f"{start_date} to {end_date}",
            "District": district_choice,
            "Activity": phase["title"],
        }
        # The export always carries district labels — even under ALL — so the
        # workbook can separate each district into its own section/charts.
        zone_export = zone_summary.copy()
        if "District" not in zone_export.columns:
            zone_export.insert(0, "District", districts_for_zones(zone_export.index, master_df))
        center_export = center_summary.copy()
        if "District" not in center_export.columns:
            center_export.insert(0, "District", districts_for_centers(center_export.index, master_df))
        filtered_export = filtered.copy()
        filtered_export["District"] = districts_for_zones(filtered_export["ZONE NAME"], master_df)
        st.session_state.excel_report_bytes = build_report(filtered_export, report, zone_export, center_export, kpis)

    if st.session_state.get("excel_report_bytes"):
        st.download_button(
            "Download Excel Report",
            data=st.session_state.excel_report_bytes,
            file_name="daily_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
