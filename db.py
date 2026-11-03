"""SQLite storage. Fully compatible with the original battery_history.db."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from analytics import Thresholds

DB_PATH = Path(__file__).with_name("battery_history.db")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def initialize() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                voltage REAL NOT NULL,
                current REAL NOT NULL,
                temperature REAL NOT NULL,
                UNIQUE(timestamp, voltage, current, temperature)
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT NOT NULL DEFAULT '',
                action_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Monitoring',
                action_taken TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""")
        # Keep older databases working: add any missing maintenance_log columns.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(maintenance_log)").fetchall()}
        needed = {
            "logged_at": "TEXT NOT NULL DEFAULT ''",
            "action_date": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'Monitoring'",
            "action_taken": "TEXT NOT NULL DEFAULT ''",
            "notes": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in needed.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE maintenance_log ADD COLUMN {name} {definition}")


# ---- readings -------------------------------------------------------------
def save_readings(df: pd.DataFrame) -> tuple[int, int]:
    """Insert readings, ignoring exact duplicates. Returns (inserted, skipped)."""
    records = [
        (pd.Timestamp(r.timestamp).isoformat(sep=" "), float(r.voltage), float(r.current), float(r.temperature))
        for r in df.itertuples(index=False)
    ]
    with connect() as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO readings (timestamp, voltage, current, temperature) VALUES (?, ?, ?, ?)",
            records,
        )
        inserted = conn.total_changes - before
    return inserted, len(records) - inserted


def load_history() -> pd.DataFrame:
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT timestamp, voltage, current, temperature FROM readings ORDER BY timestamp ASC", conn
        )
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna().sort_values("timestamp").reset_index(drop=True)


def clear_readings() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM readings")


# ---- maintenance log ------------------------------------------------------
def add_log_entry(action_date: str, status: str, action_taken: str, notes: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO maintenance_log (logged_at, action_date, status, action_taken, notes) VALUES (?, ?, ?, ?, ?)",
            (pd.Timestamp.now().isoformat(sep=" ", timespec="seconds"), action_date, status, action_taken, notes),
        )


def load_log() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT id, action_date, status, action_taken, notes, logged_at "
            "FROM maintenance_log ORDER BY action_date DESC, id DESC",
            conn,
        )


def delete_log_entry(entry_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM maintenance_log WHERE id = ?", (int(entry_id),))


# ---- settings -------------------------------------------------------------
def load_thresholds() -> Thresholds:
    t = Thresholds()
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'thresholds'").fetchone()
    if row:
        try:
            saved = json.loads(row[0])
            for k, v in saved.items():
                if hasattr(t, k):
                    setattr(t, k, float(v))
        except (ValueError, TypeError):
            pass
    return t


def save_thresholds(t: Thresholds) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('thresholds', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(asdict(t)),),
        )
