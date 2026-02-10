"""
Database tables and CRUD operations for equity research (M5).
"""

import logging

logger = logging.getLogger(__name__)


def init_equity_tables(db) -> None:
    """Create equity_snapshots and equity_model_runs tables.

    Args:
        db: core.db.Database instance
    """
    conn = db._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                asof_date TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_equity_snapshots_ticker
            ON equity_snapshots(ticker)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS equity_model_runs (
                id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                outputs_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES equity_snapshots(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_equity_model_runs_snapshot
            ON equity_model_runs(snapshot_id)
            """
        )
        conn.commit()
        logger.info("Equity tables initialized (equity_snapshots, equity_model_runs)")
    except Exception as e:
        logger.error(f"Error initializing equity tables: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_equity_snapshot(db, snapshot_id: str, ticker: str, asof_date: str, raw_json: str) -> None:
    """Insert a new equity snapshot record."""
    db.execute_query(
        "INSERT INTO equity_snapshots (id, ticker, asof_date, raw_json) VALUES (?, ?, ?, ?)",
        (snapshot_id, ticker, asof_date, raw_json),
    )
    logger.info(f"Equity snapshot created: {snapshot_id} for {ticker}")


def get_equity_snapshot(db, snapshot_id: str) -> dict | None:
    """Retrieve an equity snapshot by ID."""
    result = db.execute_query(
        "SELECT id, ticker, asof_date, raw_json, created_at FROM equity_snapshots WHERE id = ?",
        (snapshot_id,),
        fetch="one",
    )
    return dict(result) if result else None


def insert_equity_model_run(db, model_run_id: str, snapshot_id: str, assumptions_json: str, outputs_json: str) -> None:
    """Insert a new equity model run record."""
    db.execute_query(
        "INSERT INTO equity_model_runs (id, snapshot_id, assumptions_json, outputs_json) VALUES (?, ?, ?, ?)",
        (model_run_id, snapshot_id, assumptions_json, outputs_json),
    )
    logger.info(f"Equity model run created: {model_run_id} for snapshot {snapshot_id}")


def get_equity_model_run(db, model_run_id: str) -> dict | None:
    """Retrieve an equity model run by ID."""
    result = db.execute_query(
        "SELECT id, snapshot_id, assumptions_json, outputs_json, created_at FROM equity_model_runs WHERE id = ?",
        (model_run_id,),
        fetch="one",
    )
    return dict(result) if result else None
