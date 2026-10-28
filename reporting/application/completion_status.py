"""Application use case for reporting-completion status."""

from dataclasses import dataclass

import pandas as pd

from reporting.domain.master_reference import zone_center_matrix


@dataclass(frozen=True)
class CompletionStatus:
    matrix: pd.DataFrame
    total_expected: int
    total_submitted: int
    percentage: float


def calculate_completion_status(cleaned_data: pd.DataFrame, master_reference: pd.DataFrame,
                                zone: str, start_date, end_date) -> CompletionStatus:
    """Calculate reporting completion for all master-listed centers in one zone."""
    matrix = zone_center_matrix(cleaned_data, master_reference, zone, start_date, end_date)
    day_columns = [column for column in matrix.columns if column != "Center"]
    total_expected = len(matrix) * len(day_columns)
    total_submitted = int((matrix[day_columns] > 0).sum().sum()) if day_columns else 0
    percentage = round(100 * total_submitted / total_expected, 1) if total_expected else 0.0
    return CompletionStatus(matrix, total_expected, total_submitted, percentage)
