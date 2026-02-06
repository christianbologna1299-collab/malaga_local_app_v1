"""
Database-backed session manager for Banker Analytics.
Replaces in-memory SessionManager with SQLite persistence.
Same public API for drop-in replacement.
"""

import logging
import pickle
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
import sqlite3

from core.db import Database

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """SQLite-backed session storage with 30-minute TTL."""

    def __init__(self, ttl_minutes: int = 30, db_path: str = "banker_analytics.db"):
        """
        Initialize DatabaseSessionManager.

        Args:
            ttl_minutes: Session time-to-live in minutes (default 30)
            db_path: Path to SQLite database file
        """
        self.ttl = timedelta(minutes=ttl_minutes)
        self.db = Database(db_path)
        logger.info(f"DatabaseSessionManager initialized with {ttl_minutes}min TTL")

        # Clean up expired sessions on startup
        cleaned = self.cleanup_expired()
        logger.info(f"Startup cleanup: removed {cleaned} expired sessions")

    def store_session(self, df: pd.DataFrame, filename: str) -> str:
        """
        Store a DataFrame in persistent session.

        Args:
            df: Parsed, clean DataFrame with columns: date, balance, rate
            filename: Original filename for reference

        Returns:
            session_id (UUID string)

        Raises:
            ValueError: If df is empty or storage fails
        """
        if df.empty:
            raise ValueError("Cannot store empty DataFrame")

        session_id = str(uuid.uuid4())

        try:
            # Serialize DataFrame
            df_blob = self._serialize_dataframe(df)
            size_bytes = len(df_blob)

            # Store in database
            queries = [
                (
                    """
                    INSERT INTO sessions (session_id, filename, row_count, created_at, accessed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        filename,
                        len(df),
                        datetime.now(),
                        datetime.now(),
                    ),
                ),
                (
                    """
                    INSERT INTO session_dataframes (session_id, dataframe_blob, size_bytes)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, df_blob, size_bytes),
                ),
            ]

            self.db.batch_execute(queries)
            logger.info(
                f"Session stored: {session_id} | {filename} | {len(df)} rows | {size_bytes} bytes"
            )
            return session_id

        except Exception as e:
            logger.error(f"Failed to store session: {e}")
            raise ValueError(f"Session storage failed: {str(e)}")

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session by ID, checking TTL.

        Args:
            session_id: UUID string

        Returns:
            Session dict {df, filename, created_at, row_count} or None if expired/not found
        """
        try:
            # Fetch metadata
            session = self.db.execute_query(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
                fetch="one",
            )

            if not session:
                logger.warning(f"Session not found: {session_id}")
                return None

            # Check TTL
            created_at = datetime.fromisoformat(session["created_at"])
            age = datetime.now() - created_at

            if age > self.ttl:
                logger.info(f"Session expired: {session_id} (age: {age})")
                self.delete_session(session_id)
                return None

            # Update accessed_at (touch the session)
            self.db.execute_query(
                "UPDATE sessions SET accessed_at = ? WHERE session_id = ?",
                (datetime.now(), session_id),
            )

            # Fetch DataFrame blob
            df_record = self.db.execute_query(
                "SELECT dataframe_blob FROM session_dataframes WHERE session_id = ?",
                (session_id,),
                fetch="one",
            )

            if not df_record:
                logger.error(f"DataFrame blob not found for session: {session_id}")
                return None

            # Deserialize DataFrame
            df = self._deserialize_dataframe(df_record["dataframe_blob"])

            logger.debug(f"Session retrieved: {session_id} (age: {age})")

            return {
                "df": df,
                "filename": session["filename"],
                "created_at": created_at,
                "row_count": session["row_count"],
            }

        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """
        Delete session and associated DataFrame.

        Args:
            session_id: Session UUID string

        Returns:
            True if deleted, False if not found
        """
        try:
            # Cascade delete handled by FOREIGN KEY
            result = self.db.execute_query(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )

            logger.info(f"Session deleted: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def list_active_sessions(self) -> list:
        """
        Return list of active session metadata.

        Returns:
            List of dicts {session_id, filename, created_at, row_count, age_seconds}
        """
        try:
            sessions = self.db.execute_query(
                """
                SELECT session_id, filename, created_at, row_count
                FROM sessions
                WHERE status = 'active'
                ORDER BY created_at DESC
                """,
                fetch="all",
            )

            active = []
            expired_ids = []

            for sess in sessions:
                created_at = datetime.fromisoformat(sess["created_at"])
                age = datetime.now() - created_at

                if age > self.ttl:
                    expired_ids.append(sess["session_id"])
                else:
                    active.append(
                        {
                            "session_id": sess["session_id"],
                            "filename": sess["filename"],
                            "created_at": sess["created_at"],
                            "row_count": sess["row_count"],
                            "age_seconds": int(age.total_seconds()),
                        }
                    )

            # Clean up expired
            for sid in expired_ids:
                self.delete_session(sid)

            logger.debug(f"Active sessions: {len(active)}")
            return active

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.

        Returns:
            Count of deleted sessions
        """
        try:
            sessions = self.db.execute_query(
                "SELECT session_id, created_at FROM sessions WHERE status = 'active'",
                fetch="all",
            )

            deleted = 0

            for sess in sessions:
                created_at = datetime.fromisoformat(sess["created_at"])
                age = datetime.now() - created_at

                if age > self.ttl:
                    self.delete_session(sess["session_id"])
                    deleted += 1

            logger.info(f"Cleanup: {deleted} expired sessions removed")
            return deleted

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0

    def _serialize_dataframe(self, df: pd.DataFrame) -> bytes:
        """
        Serialize DataFrame to pickle bytes.

        Args:
            df: Pandas DataFrame

        Returns:
            Pickled bytes
        """
        try:
            return pickle.dumps(df)
        except Exception as e:
            logger.error(f"DataFrame serialization failed: {e}")
            raise ValueError(f"Serialization error: {str(e)}")

    def _deserialize_dataframe(self, blob: bytes) -> pd.DataFrame:
        """
        Deserialize pickle bytes to DataFrame.

        Args:
            blob: Pickled bytes

        Returns:
            Pandas DataFrame

        Raises:
            ValueError: If deserialization fails
        """
        try:
            return pickle.loads(blob)
        except Exception as e:
            logger.error(f"DataFrame deserialization failed: {e}")
            raise ValueError(f"Deserialization error: {str(e)}")
