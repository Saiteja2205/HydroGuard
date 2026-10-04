"""CSV loading for the shared HydroGuard data pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.data.validator import REQUIRED_COLUMNS


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load a water-quality CSV.

    Lines starting with ``#`` are comments (used to mark DEMO/TEST files).
    It does not invent values for missing sensor observations.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    frame = pd.read_csv(csv_path, comment="#")
    if frame.empty:
        raise ValueError(f"CSV is empty after reading comments: {csv_path}")

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(missing)
            + f". Expected: {', '.join(REQUIRED_COLUMNS)}"
        )
    return frame
