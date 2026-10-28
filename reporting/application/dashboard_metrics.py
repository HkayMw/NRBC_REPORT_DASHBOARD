"""Application calculations used by the dashboard presentation."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DashboardMetrics:
    total_birth_registrations: int
    male_births: int
    female_births: int
    total_nid_registrations: int
    male_nid_registrations: int
    female_nid_registrations: int


@dataclass(frozen=True)
class LocationSummaries:
    """Zone and center totals for the current dashboard selection."""

    by_zone: pd.DataFrame
    by_center: pd.DataFrame


@dataclass(frozen=True)
class SexBreakdowns:
    birth_by_zone: pd.DataFrame
    nid_by_zone: pd.DataFrame
    overall_birth: pd.DataFrame
    overall_nid: pd.DataFrame


def calculate_dashboard_metrics(data: pd.DataFrame) -> DashboardMetrics:
    """Calculate the six headline totals for an already-filtered dataset."""
    return DashboardMetrics(
        total_birth_registrations=int(data["Total Birth Registrations"].sum()),
        male_births=int(data["Total Male Births Registered"].sum()),
        female_births=int(data["Total Female Births Registered"].sum()),
        total_nid_registrations=int(data["Total NID Registrations"].sum()),
        male_nid_registrations=int(data["Total Males Processed"].sum()),
        female_nid_registrations=int(data["Total Females Processed"].sum()),
    )


def calculate_location_summaries(data: pd.DataFrame, selected_zones: list[str],
                                 selected_centers: list[str]) -> LocationSummaries:
    """Aggregate selected locations while retaining zero-report master locations."""
    aggregations = {
        "Total Birth Registrations": ("Total Birth Registrations", "sum"),
        "Male Births": ("Total Male Births Registered", "sum"),
        "Female Births": ("Total Female Births Registered", "sum"),
        "Total NID Registrations": ("Total NID Registrations", "sum"),
        "Male NID": ("Total Males Processed", "sum"),
        "Female NID": ("Total Females Processed", "sum"),
    }
    by_zone = (
        data.groupby("ZONE NAME").agg(**aggregations)
        .reindex(sorted(selected_zones)).fillna(0).astype(int)
        .sort_values("Total Birth Registrations", ascending=False)
    )
    by_center = (
        data.groupby("CENTER NAME").agg(**aggregations)
        .reindex(sorted(set(selected_centers))).fillna(0).astype(int)
        .sort_values("Total Birth Registrations", ascending=False)
    )
    return LocationSummaries(by_zone=by_zone, by_center=by_center)


def calculate_daily_trend(data: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """Return daily birth and NID totals for the requested inclusive date range."""
    selected = data[
        (data["Date"].dt.date >= start_date) & (data["Date"].dt.date <= end_date)
    ]
    return selected.groupby(selected["Date"].dt.date).agg(
        **{
            "Total Birth Registrations": ("Total Birth Registrations", "sum"),
            "Total NID Registrations": ("Total NID Registrations", "sum"),
        }
    ).reset_index().sort_values("Date")


def calculate_sex_breakdowns(data: pd.DataFrame) -> SexBreakdowns:
    """Build zone-level and overall sex breakdowns for both activity types."""
    birth_by_zone = data.groupby("ZONE NAME").agg(
        Male=("Total Male Births Registered", "sum"),
        Female=("Total Female Births Registered", "sum"),
    ).reset_index()
    birth_by_zone["Total"] = birth_by_zone["Male"] + birth_by_zone["Female"]

    nid_by_zone = data.groupby("ZONE NAME").agg(
        Male=("Total Males Processed", "sum"),
        Female=("Total Females Processed", "sum"),
    ).reset_index()
    nid_by_zone["Total"] = nid_by_zone["Male"] + nid_by_zone["Female"]
    return SexBreakdowns(
        birth_by_zone=birth_by_zone.sort_values("Total", ascending=False),
        nid_by_zone=nid_by_zone.sort_values("Total", ascending=False),
        overall_birth=pd.DataFrame({"Sex": ["Male", "Female"], "Count": [
            int(birth_by_zone["Male"].sum()), int(birth_by_zone["Female"].sum())
        ]}),
        overall_nid=pd.DataFrame({"Sex": ["Male", "Female"], "Count": [
            int(nid_by_zone["Male"].sum()), int(nid_by_zone["Female"].sum())
        ]}),
    )
