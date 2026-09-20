"""SQLite persistence and workbook import helpers for the market opportunity app."""

from __future__ import annotations

import io
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from config import PRIORITY_HIGH_MIN_GAP, PRIORITY_MEDIUM_MIN_GAP


REGIONAL_COLUMNS = [
    "region", "signal_observed", "source", "signal_date", "demand_growth",
    "supplier_coverage", "opportunity_gap", "priority",
]
COMPETITOR_COLUMNS = [
    "move_date", "competitor", "move_observed", "source", "impact",
    "implication", "action_owner",
]
INPUT_COLUMNS = [
    "price_date", "input_type", "price_egp", "prior_price_egp", "trend",
    "source", "note",
]


def connect(db_path: str | Path = "market_opportunities.db") -> sqlite3.Connection:
    # Streamlit reruns the script on different worker threads while reusing the cached connection.
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS regional_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL, signal_observed TEXT NOT NULL, source TEXT,
            signal_date TEXT NOT NULL, demand_growth INTEGER NOT NULL,
            supplier_coverage INTEGER NOT NULL, opportunity_gap INTEGER NOT NULL,
            priority TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '',
            data_source TEXT NOT NULL DEFAULT 'real'
        );
        CREATE TABLE IF NOT EXISTS competitor_moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            move_date TEXT NOT NULL, competitor TEXT NOT NULL,
            move_observed TEXT NOT NULL, source TEXT, impact INTEGER NOT NULL,
            implication TEXT, action_owner TEXT, created_by TEXT NOT NULL DEFAULT '',
            data_source TEXT NOT NULL DEFAULT 'real'
        );
        CREATE TABLE IF NOT EXISTS input_cost_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_date TEXT NOT NULL, input_type TEXT NOT NULL,
            price_egp REAL NOT NULL, prior_price_egp REAL, trend TEXT,
            source TEXT, note TEXT, created_by TEXT NOT NULL DEFAULT '',
            data_source TEXT NOT NULL DEFAULT 'real'
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE, password_hash BLOB NOT NULL,
            display_name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    for table in ("regional_signals", "competitor_moves", "input_cost_signals"):
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "created_by" not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN created_by TEXT NOT NULL DEFAULT ''")
        if "data_source" not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN data_source TEXT NOT NULL DEFAULT 'real'")
    connection.commit()


def _priority(gap: int) -> str:
    return "High" if gap >= PRIORITY_HIGH_MIN_GAP else "Medium" if gap >= PRIORITY_MEDIUM_MIN_GAP else "Low"


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _date_text(value: object, default: str | None = None) -> str:
    if pd.isna(value) or value in (None, ""):
        return default or date.today().isoformat()
    parsed = pd.to_datetime(value, errors="coerce")
    return default or (parsed.date().isoformat() if not pd.isna(parsed) else str(value))


def _quarter_date(value: object) -> str:
    text = _text(value)
    if "Q" in text:
        year, quarter = text.split(" Q")
        month = (int(quarter) - 1) * 3 + 1
        return f"{year}-{month:02d}-01"
    return _date_text(value)


def add_regional_signal(connection: sqlite3.Connection, values: dict) -> None:
    gap = int(values["demand_growth"]) - int(values["supplier_coverage"])
    connection.execute(
        """INSERT INTO regional_signals
        (region, signal_observed, source, signal_date, demand_growth,
         supplier_coverage, opportunity_gap, priority, created_by, data_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (values["region"], values["signal_observed"], values.get("source", ""),
         values["signal_date"].isoformat(), values["demand_growth"],
         values["supplier_coverage"], gap, _priority(gap), values.get("created_by", ""),
         values.get("data_source", "real")),
    )
    connection.commit()


def add_competitor_move(connection: sqlite3.Connection, values: dict) -> None:
    connection.execute(
        """INSERT INTO competitor_moves
        (move_date, competitor, move_observed, source, impact, implication, action_owner,
         created_by, data_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (values["move_date"].isoformat(), values["competitor"], values["move_observed"],
         values.get("source", ""), values["impact"], values.get("implication", ""),
         values.get("action_owner", ""), values.get("created_by", ""),
         values.get("data_source", "real")),
    )
    connection.commit()


def prior_input_price(connection: sqlite3.Connection, input_type: str, price_date: date):
    row = connection.execute(
        """SELECT price_egp FROM input_cost_signals
        WHERE input_type = ? AND price_date < ? ORDER BY price_date DESC LIMIT 1""",
        (input_type, price_date.isoformat()),
    ).fetchone()
    return row["price_egp"] if row else None


def add_input_cost(connection: sqlite3.Connection, values: dict) -> None:
    prior = prior_input_price(connection, values["input_type"], values["price_date"])
    current = float(values["price_egp"])
    trend = "Rising" if prior is not None and current > prior else "Falling" if prior is not None and current < prior else "Stable"
    connection.execute(
        """INSERT INTO input_cost_signals
        (price_date, input_type, price_egp, prior_price_egp, trend, source, note,
         created_by, data_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (values["price_date"].isoformat(), values["input_type"], current, prior, trend,
         values.get("source", ""), values.get("note", ""), values.get("created_by", ""),
         values.get("data_source", "real")),
    )
    connection.commit()


def update_record(connection: sqlite3.Connection, table: str, record_id: int, values: dict) -> None:
    allowed = {
        "regional_signals": {"region", "signal_observed", "source", "signal_date", "demand_growth", "supplier_coverage", "created_by"},
        "competitor_moves": {"move_date", "competitor", "move_observed", "source", "impact", "implication", "action_owner", "created_by"},
        "input_cost_signals": {"price_date", "input_type", "price_egp", "source", "note", "created_by"},
    }
    if table not in allowed or not set(values).issubset(allowed[table]):
        raise ValueError("Unsupported update fields")
    if table == "regional_signals":
        values = dict(values)
        values["opportunity_gap"] = int(values["demand_growth"]) - int(values["supplier_coverage"])
        values["priority"] = _priority(values["opportunity_gap"])
        allowed[table].update({"opportunity_gap", "priority"})
    elif table == "input_cost_signals":
        values = dict(values)
        current = float(values["price_egp"])
        date_value = values["price_date"]
        input_type = values["input_type"]
        prior_row = connection.execute(
            """SELECT price_egp FROM input_cost_signals
            WHERE input_type = ? AND price_date < ? AND id != ?
            ORDER BY price_date DESC LIMIT 1""",
            (input_type, date_value, record_id),
        ).fetchone()
        prior = prior_row["price_egp"] if prior_row else None
        values["prior_price_egp"] = prior
        values["trend"] = "Rising" if prior is not None and current > prior else "Falling" if prior is not None and current < prior else "Stable"
        allowed[table].update({"prior_price_egp", "trend"})
    assignments = ", ".join(f"{field} = ?" for field in values)
    connection.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        [*values.values(), record_id],
    )
    connection.commit()


def delete_record(connection: sqlite3.Connection, table: str, record_id: int) -> None:
    if table not in {"regional_signals", "competitor_moves", "input_cost_signals"}:
        raise ValueError("Unsupported table")
    connection.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    connection.commit()


def user_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def create_user(connection: sqlite3.Connection, username: str, password_hash: bytes, display_name: str) -> None:
    connection.execute(
        "INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, datetime('now'))",
        (username.strip(), password_hash, display_name.strip()),
    )
    connection.commit()


def get_user(connection: sqlite3.Connection, username: str):
    return connection.execute(
        "SELECT id, username, password_hash, display_name FROM users WHERE username = ?",
        (username.strip(),),
    ).fetchone()


def _header_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).lower()).strip()


def _read_workbook_with_headers(source: object) -> dict[str, pd.DataFrame]:
    raw_sheets = pd.read_excel(source, sheet_name=None, header=None, engine="openpyxl")
    sheets = {}
    required_terms = {
        "regional": {"region", "demand growth", "supplier coverage"},
        "competitor": {"date", "competitor", "impact"},
        "input": {"date", "input", "price"},
    }
    for sheet_name, raw in raw_sheets.items():
        kind = next((key for key in required_terms if key in sheet_name.lower()), None)
        if kind is None:
            continue
        header_row = None
        for row_number in range(min(10, len(raw))):
            values = {_header_key(value) for value in raw.iloc[row_number].tolist() if _text(value)}
            if all(any(term in value for value in values) for term in required_terms[kind]):
                header_row = row_number
                break
        if header_row is None:
            raise ValueError(f"Could not find the column header row in sheet '{sheet_name}'.")
        frame = raw.iloc[header_row + 1:].copy()
        frame.columns = [_text(value) for value in raw.iloc[header_row].tolist()]
        sheets[sheet_name] = frame.dropna(how="all")
    return sheets


def _column(frame: pd.DataFrame, *terms: str) -> str | None:
    for name in frame.columns:
        key = _header_key(name)
        if all(term in key for term in terms):
            return name
    return None


def import_workbook(
    connection: sqlite3.Connection,
    file_data: bytes | str | Path,
    filename: str = "",
    created_by: str = "",
) -> dict[str, int]:
    source = io.BytesIO(file_data) if isinstance(file_data, bytes) else file_data
    sheets = _read_workbook_with_headers(source)
    synthetic = "synthetic" in filename.lower() or any("synthetic" in name.lower() for name in sheets)
    data_source = "synthetic" if synthetic else "real"
    counts = {"regional": 0, "competitor": 0, "input_cost": 0, "duplicates": 0}
    for sheet_name, frame in sheets.items():
        normalized = sheet_name.lower()
        if "regional" in normalized:
            columns = {
                "region": _column(frame, "region"),
                "signal": _column(frame, "signal", "observed"),
                "source": _column(frame, "source"),
                "quarter": _column(frame, "quarter"),
                "demand": _column(frame, "demand", "growth"),
                "coverage": _column(frame, "supplier", "coverage"),
            }
            for _, row in frame.iterrows():
                if not columns["region"] or not _text(row[columns["region"]]):
                    continue
                demand = int(row[columns["demand"]])
                coverage = int(row[columns["coverage"]])
                signal_date = row[columns["quarter"]] if columns["quarter"] else date.today()
                region = _text(row[columns["region"]])
                normalized_date = _quarter_date(signal_date)
                duplicate = connection.execute(
                    "SELECT 1 FROM regional_signals WHERE region = ? AND signal_date = ?",
                    (region, normalized_date),
                ).fetchone()
                if duplicate:
                    counts["duplicates"] += 1
                    continue
                connection.execute(
                    """INSERT INTO regional_signals
                    (region, signal_observed, source, signal_date, demand_growth,
                    supplier_coverage, opportunity_gap, priority, created_by, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (region, _text(row[columns["signal"]]), _text(row[columns["source"]]),
                     normalized_date, demand, coverage, demand - coverage,
                     _priority(demand - coverage), created_by, data_source),
                )
                counts["regional"] += 1
        elif "competitor" in normalized:
            columns = {
                "date": _column(frame, "date"),
                "competitor": _column(frame, "competitor"),
                "move": _column(frame, "move", "observed"),
                "source": _column(frame, "source"),
                "impact": _column(frame, "impact"),
                "implication": _column(frame, "implication"),
                "owner": _column(frame, "action", "owner"),
            }
            for _, row in frame.iterrows():
                if not columns["date"] or not _text(row[columns["date"]]):
                    continue
                move_date = _date_text(row[columns["date"]])
                competitor = _text(row[columns["competitor"]])
                move = _text(row[columns["move"]])
                duplicate = connection.execute(
                    "SELECT 1 FROM competitor_moves WHERE move_date = ? AND competitor = ? AND move_observed = ?",
                    (move_date, competitor, move),
                ).fetchone()
                if duplicate:
                    counts["duplicates"] += 1
                    continue
                connection.execute(
                    """INSERT INTO competitor_moves
                    (move_date, competitor, move_observed, source, impact, implication, action_owner,
                     created_by, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (move_date, competitor, move, _text(row[columns["source"]]),
                     int(row[columns["impact"]]), _text(row[columns["implication"]]),
                     _text(row[columns["owner"]]), created_by, data_source),
                )
                counts["competitor"] += 1
        elif "input" in normalized:
            columns = {
                "date": _column(frame, "date"),
                "input": _column(frame, "input"),
                "price": _column(frame, "price"),
                "prior": _column(frame, "prior", "price"),
                "trend": _column(frame, "trend"),
                "source": _column(frame, "source"),
                "note": _column(frame, "note") or _column(frame, "action"),
            }
            for _, row in frame.iterrows():
                if not columns["date"] or not _text(row[columns["date"]]):
                    continue
                price = float(row[columns["price"]])
                price_date = _date_text(row[columns["date"]])
                input_type = _text(row[columns["input"]])
                duplicate = connection.execute(
                    "SELECT 1 FROM input_cost_signals WHERE price_date = ? AND input_type = ?",
                    (price_date, input_type),
                ).fetchone()
                if duplicate:
                    counts["duplicates"] += 1
                    continue
                prior = None if not columns["prior"] or pd.isna(row[columns["prior"]]) else float(row[columns["prior"]])
                trend = _text(row[columns["trend"]]) if columns["trend"] else ""
                trend = trend or ("Rising" if prior is not None and price > prior else "Falling" if prior is not None and price < prior else "Stable")
                connection.execute(
                    """INSERT INTO input_cost_signals
                    (price_date, input_type, price_egp, prior_price_egp, trend, source, note,
                     created_by, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (price_date, input_type, price, prior, trend, _text(row[columns["source"]]),
                     _text(row[columns["note"]]), created_by, data_source),
                )
                counts["input_cost"] += 1
    connection.commit()
    return counts


def import_input_csv(connection: sqlite3.Connection, file_data: bytes, created_by: str = "") -> dict[str, int]:
    frame = pd.read_csv(io.BytesIO(file_data))
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    aliases = {
        "date": next((column for column in frame.columns if column in {"date", "price_date"}), None),
        "input": next((column for column in frame.columns if column in {"input", "input_type"}), None),
        "price": next((column for column in frame.columns if column in {"price_(egp)", "price_egp", "price"}), None),
    }
    if any(value is None for value in aliases.values()):
        raise ValueError("CSV must include Date, Input, and Price (EGP) columns.")
    count = 0
    duplicates = 0
    for _, row in frame.iterrows():
        if not _text(row[aliases["date"]]):
            continue
        price = float(row[aliases["price"]])
        price_date = _date_text(row[aliases["date"]])
        input_type = _text(row[aliases["input"]])
        duplicate = connection.execute(
            "SELECT 1 FROM input_cost_signals WHERE price_date = ? AND input_type = ?",
            (price_date, input_type),
        ).fetchone()
        if duplicate:
            duplicates += 1
            continue
        connection.execute(
            """INSERT INTO input_cost_signals
            (price_date, input_type, price_egp, prior_price_egp, trend, source, note,
             created_by, data_source)
            VALUES (?, ?, ?, NULL, 'Stable', '', '', ?, 'real')""",
            (price_date, input_type, price, created_by),
        )
        count += 1
    connection.commit()
    return {"input_cost": count, "duplicates": duplicates}


def read_table(connection: sqlite3.Connection, table: str, order_by: str) -> pd.DataFrame:
    allowed = {"regional_signals", "competitor_moves", "input_cost_signals"}
    if table not in allowed:
        raise ValueError("Unsupported table")
    return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY {order_by}", connection)