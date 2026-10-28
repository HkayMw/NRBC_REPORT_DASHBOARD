"""Regression tests for the Streamlit-independent reporting use case."""

from datetime import date
import unittest

import pandas as pd

from reporting.application.reporting_pipeline import prepare_reporting_dataset
from reporting.application.dashboard_metrics import (
    calculate_daily_trend,
    calculate_dashboard_metrics,
    calculate_location_summaries,
    calculate_sex_breakdowns,
)
from reporting.application.completion_status import calculate_completion_status
from reporting.domain.master_reference import prepare_master


class ReportingPipelineTests(unittest.TestCase):
    def test_calculates_completion_status_from_master_centers(self):
        cleaned = pd.DataFrame([{
            "ZONE NAME": "A", "CENTER NAME": "One", "Date": "2026-07-08"
        }])
        cleaned["Date"] = pd.to_datetime(cleaned["Date"])
        master = pd.DataFrame([
            {"District": "D", "Zone": "A", "Center": "One", "Zone_norm": "A", "Center_norm": "ONE"},
            {"District": "D", "Zone": "A", "Center": "Two", "Zone_norm": "A", "Center_norm": "TWO"},
        ])

        status = calculate_completion_status(cleaned, master, "A", date(2026, 7, 8), date(2026, 7, 8))

        self.assertEqual(status.total_expected, 2)
        self.assertEqual(status.total_submitted, 1)
        self.assertEqual(status.percentage, 50.0)

    def test_calculates_dashboard_metrics(self):
        data = pd.DataFrame([{
            "Total Birth Registrations": 3,
            "Total Male Births Registered": 1,
            "Total Female Births Registered": 2,
            "Total NID Registrations": 7,
            "Total Males Processed": 3,
            "Total Females Processed": 4,
        }])

        metrics = calculate_dashboard_metrics(data)

        self.assertEqual(metrics.total_birth_registrations, 3)
        self.assertEqual(metrics.female_nid_registrations, 4)

    def test_includes_selected_locations_with_no_submissions_in_summaries(self):
        data = pd.DataFrame([{
            "ZONE NAME": "A", "CENTER NAME": "One",
            "Total Birth Registrations": 3, "Total Male Births Registered": 1,
            "Total Female Births Registered": 2, "Total NID Registrations": 7,
            "Total Males Processed": 3, "Total Females Processed": 4,
        }])

        summaries = calculate_location_summaries(data, ["A", "B"], ["One", "Two"])

        self.assertEqual(summaries.by_zone.loc["B", "Total Birth Registrations"], 0)
        self.assertEqual(summaries.by_center.loc["Two", "Total NID Registrations"], 0)

    def test_calculates_daily_trend_in_requested_window(self):
        data = pd.DataFrame([
            {"Date": "2026-07-08", "Total Birth Registrations": 2, "Total NID Registrations": 3},
            {"Date": "2026-07-08", "Total Birth Registrations": 1, "Total NID Registrations": 4},
            {"Date": "2026-07-09", "Total Birth Registrations": 5, "Total NID Registrations": 6},
        ])
        data["Date"] = pd.to_datetime(data["Date"])

        trend = calculate_daily_trend(data, date(2026, 7, 8), date(2026, 7, 8))

        self.assertEqual(len(trend), 1)
        self.assertEqual(trend.loc[0, "Total Birth Registrations"], 3)
        self.assertEqual(trend.loc[0, "Total NID Registrations"], 7)

    def test_calculates_birth_and_nid_sex_breakdowns(self):
        data = pd.DataFrame([{
            "ZONE NAME": "A", "Total Male Births Registered": 1,
            "Total Female Births Registered": 2, "Total Males Processed": 3,
            "Total Females Processed": 4,
        }])

        breakdowns = calculate_sex_breakdowns(data)

        self.assertEqual(breakdowns.birth_by_zone.loc[0, "Total"], 3)
        self.assertEqual(breakdowns.nid_by_zone.loc[0, "Total"], 7)
        self.assertEqual(breakdowns.overall_birth.loc[1, "Count"], 2)

    def test_prepares_clean_data_and_applies_an_approved_assignment(self):
        raw = pd.DataFrame([
            {
                "Timestamp": "2026-07-08 09:00:00",
                "ZONE NAME": "Hilltop Zone",
                "CENTER NAME": "Hilltop Primary School",
                "Date": "2026-07-08",
                "Total Male Births Registered": 1,
                "Total Female Births Registered": 2,
                "Total Males Processed": 3,
                "Total Females Processed": 4,
            }
        ])
        master = prepare_master(pd.DataFrame([
            {"District": "North", "Zone": "HILLTOP", "Center": "HILLTOP"}
        ]))

        dataset = prepare_reporting_dataset(
            raw,
            {"Hilltop Zone": "HILLTOP"},
            [{"zone": "HILLTOP", "raw_center": "Hilltop Primary School", "center": "HILLTOP"}],
            master,
            date(2026, 7, 8),
            date(2026, 7, 18),
        )

        self.assertEqual(dataset.cleaned_data.loc[0, "ZONE NAME"], "HILLTOP")
        self.assertEqual(dataset.cleaned_data.loc[0, "CENTER NAME"], "HILLTOP")
        self.assertEqual(dataset.quality_report["duplicates_removed_count"], 0)
        self.assertEqual(dataset.master_reference.loc[0, "Zone_norm"], "HILLTOP")
