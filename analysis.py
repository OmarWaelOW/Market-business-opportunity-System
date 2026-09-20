"""Small subprocess bridge to the standalone R analysis scripts."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config import ARIMA_ORDER, MIN_FORECAST_MONTHS
from db import read_table


ROOT = Path(__file__).parent


def _find_rscript() -> str | None:
    """Find Rscript on PATH or in the standard Windows R installation folder."""
    on_path = shutil.which("Rscript")
    if on_path:
        return on_path
    candidates = [
        Path(r"C:\Program Files\R") / version / "bin" / "Rscript.exe"
        for version in sorted(Path(r"C:\Program Files\R").glob("R-*"), reverse=True)
    ]
    return next((str(candidate) for candidate in candidates if candidate.exists()), None)


@dataclass
class AnalysisResult:
    data: pd.DataFrame | None = None
    error: str | None = None


def _run(script: str, frame: pd.DataFrame, args: list[str]) -> AnalysisResult:
    rscript = _find_rscript()
    if not rscript:
        return AnalysisResult(error="Rscript is not installed or is not on PATH. Install R to run this analysis; the rest of the app is available without it.")
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        input_path = folder / "input.csv"
        output_path = folder / "output.csv"
        frame.to_csv(input_path, index=False)
        command = [rscript, str(ROOT / script), str(input_path), str(output_path), *args]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "Unknown R error"
            return AnalysisResult(error=f"The R analysis could not run: {detail}")
        if not output_path.exists():
            return AnalysisResult(error="The R analysis returned no results.")
        output = pd.read_csv(output_path)
        if output.empty:
            return AnalysisResult(error="There is not enough data for a meaningful analysis yet.")
        return AnalysisResult(data=output)


def run_forecast(connection, horizon: int) -> AnalysisResult:
    frame = read_table(connection, "input_cost_signals", "price_date")
    if frame.empty or frame["price_date"].nunique() < MIN_FORECAST_MONTHS:
        return AnalysisResult(error=f"At least {MIN_FORECAST_MONTHS} months of input-cost history are needed for an ARIMA forecast.")
    frame = frame.rename(columns={"price_date": "date", "input_type": "input", "price_egp": "price"})
    order = ",".join(str(value) for value in ARIMA_ORDER)
    return _run("forecasting.R", frame[["date", "input", "price"]], [str(horizon), order])


def run_clustering(connection, clusters: int) -> AnalysisResult:
    frame = read_table(connection, "regional_signals", "region")
    if frame["region"].nunique() < clusters:
        return AnalysisResult(error=f"At least {clusters} distinct regions are needed for clustering.")
    grouped = frame.groupby("region", as_index=False).agg(
        demand_growth=("demand_growth", "mean"),
        supplier_coverage=("supplier_coverage", "mean"),
        opportunity_gap=("opportunity_gap", "mean"),
    )
    return _run("clustering.R", grouped, [str(clusters)])