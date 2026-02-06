"""
Session management for Milestone 2.
Stores parsed DataFrames in-memory with UUID keys and 30-minute TTL.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class SessionManager:
    """Thread-safe in-memory session storage with TTL."""

    def __init__(self, ttl_minutes: int = 30):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        logger.info(f"SessionManager initialized with {ttl_minutes}min TTL")

    def store_session(
        self, df: pd.DataFrame, filename: str
    ) -> str:
        """
        Store a DataFrame in session.

        Args:
            df: Parsed, clean DataFrame
            filename: Original filename for reference

        Returns:
            session_id (UUID string)

        Raises:
            ValueError: If df is empty
        """
        if df.empty:
            raise ValueError("Cannot store empty DataFrame")

        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "df": df.copy(),
            "filename": filename,
            "created_at": datetime.now(),
            "row_count": len(df),
        }
        logger.info(
            f"Session stored: {session_id} | {filename} | {len(df)} rows"
        )
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session by ID, checking TTL.

        Args:
            session_id: UUID string

        Returns:
            Session dict or None if expired/not found
        """
        if session_id not in self.sessions:
            logger.warning(f"Session not found: {session_id}")
            return None

        session = self.sessions[session_id]
        age = datetime.now() - session["created_at"]

        if age > self.ttl:
            logger.info(f"Session expired: {session_id} (age: {age})")
            self.delete_session(session_id)
            return None

        logger.debug(f"Session retrieved: {session_id} (age: {age})")
        return session

    def delete_session(self, session_id: str) -> bool:
        """
        Delete session by ID.

        Returns:
            True if deleted, False if not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session deleted: {session_id}")
            return True
        return False

    def list_active_sessions(self) -> list:
        """Return list of active session metadata (for debugging)."""
        active = []
        expired_ids = []

        for sid, sess in self.sessions.items():
            age = datetime.now() - sess["created_at"]
            if age > self.ttl:
                expired_ids.append(sid)
            else:
                active.append({
                    "session_id": sid,
                    "filename": sess["filename"],
                    "created_at": sess["created_at"].isoformat(),
                    "row_count": sess["row_count"],
                    "age_seconds": int(age.total_seconds()),
                })

        # Clean up expired
        for sid in expired_ids:
            self.delete_session(sid)

        logger.debug(f"Active sessions: {len(active)}")
        return active

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count deleted."""
        sessions_copy = list(self.sessions.keys())
        deleted = 0
        for sid in sessions_copy:
            if self.get_session(sid) is None:
                deleted += 1
        logger.info(f"Cleanup: {deleted} expired sessions removed")
        return deleted
