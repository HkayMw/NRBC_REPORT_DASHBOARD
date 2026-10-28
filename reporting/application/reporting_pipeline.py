"""Application use case for preparing master-reconciled reporting data."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from reporting.domain.data_processing import clean_data
from reporting.domain.master_reference import apply_center_assignments, apply_zone_assignments


@dataclass(frozen=True)
class ReportingDataset:
    """Output of the load-and-reconcile reporting use case."""

    cleaned_data: pd.DataFrame
    quality_report: dict
    master_reference: pd.DataFrame


def prepare_reporting_dataset(raw_data: pd.DataFrame, zone_assignments: dict,
                              center_assignments: list, master_reference: pd.DataFrame,
                              activity_start: date, activity_end: date) -> ReportingDataset:
    """Clean source rows and apply approved name assignments for one phase.

    master_reference is the phase's prepared master list (see
    master_reference_repository.load_master)."""
    cleaned_data, quality_report = clean_data(raw_data, activity_start, activity_end)
    cleaned_data = apply_zone_assignments(cleaned_data, zone_assignments)
    cleaned_data = apply_center_assignments(cleaned_data, center_assignments)
    return ReportingDataset(cleaned_data, quality_report, master_reference)
