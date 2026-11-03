"""Analytics helpers for the Battery Predictive Maintenance console.

Everything in this file is plain pandas / numpy / scikit-learn so it can be
tested without Streamlit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["timestamp", "voltage", "current", "temperature"]


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------
@dataclass
class Thresholds:
    """Operating limits. Defaults are demonstration values only."""

    voltage_warn: float = 47.5   # V  - below this: warning
    voltage_crit: float = 47.0   # V  - below this: critical
    temp_warn: float = 33.0      # °C - above this: warning
    temp_crit: float = 35.0      # °C - above this: critical
    current_warn: float = 11.0   # A  - above this: warning
    current_crit: float = 12.0   # A  - above this: critical
    nominal_voltage: float = 48.0


# --------------------------------------------------------------------------
# Data cleaning
# --------------------------------------------------------------------------
@dataclass
class CleanResult:
    data: pd.DataFrame | None
    rows_in: int = 0
    rows_dropped: int = 0
    duplicates: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def clean_readings(raw: pd.DataFrame) -> CleanResult:
    """Validate and normalise an uploaded readings table."""
    raw = raw.copy()
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        return CleanResult(
            None, len(raw),
            error="Missing required column(s): " + ", ".join(missing)
            + ". Expected: " + ", ".join(REQUIRED_COLUMNS) + ".",
        )

    df = raw[REQUIRED_COLUMNS].copy()
    rows_in = len(df)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ["voltage", "current", "temperature"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    dropped = rows_in - len(df)

    before = len(df)
    df = df.drop_duplicates()
    dupes = before - len(df)

    if df.empty:
        return CleanResult(None, rows_in, dropped, dupes,
                           error="No valid readings were found in the file.")

    df = df.sort_values("timestamp").reset_index(drop=True)
    notes = []
    if dropped:
        notes.append(f"{dropped} row(s) with missing or invalid values were skipped.")
    if dupes:
        notes.append(f"{dupes} duplicate row(s) inside the file were removed.")
    return CleanResult(df, rows_in, dropped, dupes, None, notes)


# --------------------------------------------------------------------------
# Status / health
# --------------------------------------------------------------------------
OK, WARN, CRIT = "Normal", "Warning", "Critical"


def classify_reading(row: pd.Series, t: Thresholds) -> tuple[str, list[str]]:
    """Return (status, reasons) for a single reading."""
    status, reasons = OK, []

    def bump(level: str):
        nonlocal status
        order = {OK: 0, WARN: 1, CRIT: 2}
        if order[level] > order[status]:
            status = level

    v, c, temp = float(row["voltage"]), float(row["current"]), float(row["temperature"])
    if v < t.voltage_crit:
        bump(CRIT); reasons.append(f"Voltage {v:.2f} V is below the critical limit ({t.voltage_crit:.1f} V)")
    elif v < t.voltage_warn:
        bump(WARN); reasons.append(f"Voltage {v:.2f} V is below the warning limit ({t.voltage_warn:.1f} V)")
    if temp > t.temp_crit:
        bump(CRIT); reasons.append(f"Temperature {temp:.1f} °C is above the critical limit ({t.temp_crit:.0f} °C)")
    elif temp > t.temp_warn:
        bump(WARN); reasons.append(f"Temperature {temp:.1f} °C is above the warning limit ({t.temp_warn:.0f} °C)")
    if c > t.current_crit:
        bump(CRIT); reasons.append(f"Current {c:.2f} A is above the critical limit ({t.current_crit:.1f} A)")
    elif c > t.current_warn:
        bump(WARN); reasons.append(f"Current {c:.2f} A is above the warning limit ({t.current_warn:.1f} A)")
    return status, reasons


def add_status_column(df: pd.DataFrame, t: Thresholds) -> pd.DataFrame:
    out = df.copy()
    out["status"] = [classify_reading(r, t)[0] for _, r in out.iterrows()]
    return out


def _penalty(value: float, warn: float, crit: float, higher_is_worse: bool) -> float:
    """0 inside the safe zone -> 1 at/after the critical limit (linear between)."""
    if higher_is_worse:
        if value <= warn:
            return 0.0
        return float(np.clip((value - warn) / max(crit - warn, 1e-9), 0, 1.5))
    if value >= warn:
        return 0.0
    return float(np.clip((warn - value) / max(warn - crit, 1e-9), 0, 1.5))


def health_score(df: pd.DataFrame, t: Thresholds) -> float:
    """0-100 rule-based indicator built from the most recent readings.

    This is a transparent screening score, *not* a validated state-of-health
    measurement. It weighs latest limits proximity (70 %) and the short-term
    trend (30 %).
    """
    if df.empty:
        return float("nan")
    latest = df.iloc[-1]
    p_v = _penalty(latest["voltage"], t.voltage_warn, t.voltage_crit, False)
    p_t = _penalty(latest["temperature"], t.temp_warn, t.temp_crit, True)
    p_c = _penalty(latest["current"], t.current_warn, t.current_crit, True)
    level_penalty = min(1.0, 0.45 * p_v + 0.40 * p_t + 0.15 * p_c)

    trend_penalty = 0.0
    if len(df) >= 4:
        tail = df.tail(min(len(df), 8))
        x = np.arange(len(tail))
        v_slope = np.polyfit(x, tail["voltage"], 1)[0]
        t_slope = np.polyfit(x, tail["temperature"], 1)[0]
        trend_penalty = min(1.0, max(0.0, -v_slope) / 0.25 * 0.5 + max(0.0, t_slope) / 0.8 * 0.5)

    score = 100 * (1 - (0.7 * level_penalty + 0.3 * trend_penalty))
    return float(np.clip(score, 0, 100))


def overall_status(df: pd.DataFrame, t: Thresholds) -> tuple[str, list[str]]:
    """Status of the latest reading, escalated if the short-term trend is adverse."""
    status, reasons = classify_reading(df.iloc[-1], t)
    for note in trend_notes(df):
        reasons.append(note)
        if status == OK:
            status = WARN
    return status, reasons


def trend_notes(df: pd.DataFrame, window: int = 3) -> list[str]:
    notes = []
    if len(df) >= window:
        tail = df.tail(window)
        v, tmp = tail["voltage"].tolist(), tail["temperature"].tolist()
        if all(v[i] > v[i + 1] for i in range(len(v) - 1)):
            notes.append(f"Voltage fell across the last {window} readings")
        if all(tmp[i] < tmp[i + 1] for i in range(len(tmp) - 1)):
            notes.append(f"Temperature rose across the last {window} readings")
    return notes


# --------------------------------------------------------------------------
# Trends & projection
# --------------------------------------------------------------------------
def add_derived(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    out = df.copy()
    out["power_w"] = out["voltage"] * out["current"]
    w = max(1, min(window, len(out)))
    for col in ["voltage", "current", "temperature"]:
        out[f"{col}_avg"] = out[col].rolling(w, min_periods=1).mean()
    return out


def slope_per_hour(df: pd.DataFrame, column: str) -> float | None:
    """Least-squares slope of `column` in units per hour."""
    if len(df) < 3:
        return None
    hours = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds() / 3600
    if hours.nunique() < 2:
        return None
    return float(np.polyfit(hours, df[column], 1)[0])


def project_crossing(df: pd.DataFrame, column: str, limit: float, rising: bool) -> dict:
    """Linear extrapolation to the time a limit would be reached.

    Returns {'status': ..., 'hours': float|None, 'slope': float|None}.
    Intentionally conservative: a straight line through a handful of points is
    only a rough indication.
    """
    slope = slope_per_hour(df, column)
    if slope is None:
        return {"status": "insufficient", "hours": None, "slope": None}
    current = float(df[column].iloc[-1])
    already = current >= limit if rising else current <= limit
    if already:
        return {"status": "reached", "hours": 0.0, "slope": slope}
    moving_toward = slope > 1e-6 if rising else slope < -1e-6
    if not moving_toward:
        return {"status": "stable", "hours": None, "slope": slope}
    hours = (limit - current) / slope
    return {"status": "projected", "hours": float(hours), "slope": slope}


def fmt_hours(h: float | None) -> str:
    if h is None:
        return "—"
    if h < 1:
        return f"{h * 60:.0f} min"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} days"


# --------------------------------------------------------------------------
# Anomaly detection
# --------------------------------------------------------------------------
def run_isolation_forest(df: pd.DataFrame, sensitivity: float = 0.1, seed: int = 42) -> pd.DataFrame:
    """Flag unusual readings. `sensitivity` is the expected outlier share (0.01-0.3)."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    features = ["voltage", "current", "temperature"]
    X = StandardScaler().fit_transform(df[features].astype(float))
    model = IsolationForest(n_estimators=200, contamination=float(sensitivity), random_state=seed)
    out = df.copy()
    out["model_result"] = model.fit_predict(X)
    out["anomaly_score"] = model.decision_function(X)
    out["Assessment"] = out["model_result"].map({1: "Within baseline", -1: "Unusual"})
    return out


def zscore_outliers(df: pd.DataFrame, column: str, z: float = 2.5) -> pd.Series:
    std = df[column].std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(False, index=df.index)
    return ((df[column] - df[column].mean()).abs() / std) > z
