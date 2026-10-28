"""Application use case for dashboard Excel exports."""

import pandas as pd

from reporting.application.dashboard_metrics import DashboardMetrics
from reporting.domain.master_reference import districts_for_centers, districts_for_zones
from reporting.infrastructure.excel_reports import build_report


def generate_dashboard_excel_report(filtered_data: pd.DataFrame, quality_report: dict,
                                    zone_summary: pd.DataFrame, center_summary: pd.DataFrame,
                                    metrics: DashboardMetrics, master_reference: pd.DataFrame,
                                    start_date, end_date, district: str,
                                    activity_title: str) -> bytes:
    """Prepare district-labelled data and generate the dashboard workbook."""
    kpis = {
        "Total Birth Registrations": metrics.total_birth_registrations,
        "Male Births": metrics.male_births,
        "Female Births": metrics.female_births,
        "Total NID Registrations": metrics.total_nid_registrations,
        "Male NID": metrics.male_nid_registrations,
        "Female NID": metrics.female_nid_registrations,
        "Number of Zones": filtered_data["ZONE NAME"].nunique(),
        "Number of Centers": filtered_data["CENTER NAME"].nunique(),
        "Date Range": f"{start_date} to {end_date}",
        "District": district,
        "Activity": activity_title,
    }
    zone_export = zone_summary.copy()
    if "District" not in zone_export.columns:
        zone_export.insert(0, "District", districts_for_zones(zone_export.index, master_reference))
    center_export = center_summary.copy()
    if "District" not in center_export.columns:
        center_export.insert(0, "District", districts_for_centers(center_export.index, master_reference))
    filtered_export = filtered_data.copy()
    filtered_export["District"] = districts_for_zones(filtered_export["ZONE NAME"], master_reference)
    return build_report(filtered_export, quality_report, zone_export, center_export, kpis)
