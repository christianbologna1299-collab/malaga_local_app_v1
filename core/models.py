"""
Helper models and utilities for Banker Analytics M3.
Provides CRUD wrappers with ownership checks, filename sanitization, and file hashing.
"""

import logging
import hashlib
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def sanitize_filename(original_filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.

    Args:
        original_filename: Original filename from user

    Returns:
        Safe filename with only alphanumeric, underscore, dash, and file extension
    """
    # Get filename without path
    base = Path(original_filename).name

    # Remove/replace dangerous characters
    # Keep only: alphanumeric, underscore, dash, dot (for extension)
    safe = re.sub(r'[^\w\-.]', '_', base)

    # Remove multiple underscores
    safe = re.sub(r'_+', '_', safe)

    # Ensure not empty
    if not safe:
        safe = "data"

    return safe


def compute_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    Compute hash of file for integrity and deduplication.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm ('sha256', 'md5', etc.)

    Returns:
        Hex string of file hash
    """
    try:
        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error computing file hash: {e}")
        return ""


def verify_user_owns_analysis(db, user_id: int, analysis_id: int) -> bool:
    """
    Verify that a user owns an analysis.

    Args:
        db: Database connection object
        user_id: User ID to check
        analysis_id: Analysis ID to check

    Returns:
        True if user owns analysis, False otherwise
    """
    analysis = db.get_analysis(analysis_id, user_id)
    return analysis is not None


def verify_user_owns_export(db, user_id: int, export_id: int) -> bool:
    """
    Verify that a user owns an export.

    Args:
        db: Database connection object
        user_id: User ID to check
        export_id: Export ID to check

    Returns:
        True if user owns export, False otherwise
    """
    export = db.get_export(export_id, user_id)
    return export is not None


class AnalysisManager:
    """High-level manager for analysis operations with ownership checks."""

    def __init__(self, db):
        """
        Initialize AnalysisManager.

        Args:
            db: Database connection object
        """
        self.db = db
        self.logger = logging.getLogger(__name__)

    def create_analysis(
        self,
        user_id: int,
        filename: str,
        row_count: int,
        date_min: str = None,
        date_max: str = None,
    ) -> int | None:
        """
        Create analysis with sanitized filename.

        Args:
            user_id: User ID (owner)
            filename: Original filename
            row_count: Number of rows
            date_min: Minimum date (optional)
            date_max: Maximum date (optional)

        Returns:
            Analysis ID if successful
        """
        safe_filename = sanitize_filename(filename)
        return self.db.create_analysis(
            user_id=user_id,
            filename=safe_filename,
            row_count=row_count,
            date_min=date_min,
            date_max=date_max,
        )

    def get_user_analysis(self, user_id: int, analysis_id: int) -> dict | None:
        """
        Get analysis with ownership verification.

        Args:
            user_id: User ID
            analysis_id: Analysis ID

        Returns:
            Analysis dict if owned by user
        """
        return self.db.get_analysis(analysis_id, user_id)

    def list_user_analyses(self, user_id: int) -> list:
        """
        List user's analyses.

        Args:
            user_id: User ID

        Returns:
            List of analysis dicts
        """
        return self.db.list_user_analyses(user_id)

    def create_analysis_file(
        self,
        user_id: int,
        analysis_id: int,
        stored_path: str,
        file_size: int = None,
    ) -> int | None:
        """
        Create analysis file record with automatic hash computation.

        Args:
            user_id: User ID
            analysis_id: Analysis ID
            stored_path: Path to stored file
            file_size: File size in bytes (optional)

        Returns:
            analysis_files ID if successful
        """
        # Compute file hash for integrity
        file_hash = compute_file_hash(stored_path)
        if not file_hash:
            self.logger.error(f"Failed to compute hash for {stored_path}")
            return None

        return self.db.create_analysis_file(
            user_id=user_id,
            analysis_id=analysis_id,
            stored_path=stored_path,
            file_hash=file_hash,
            size_bytes=file_size,
            format="parquet",
        )

    def export_analysis(
        self,
        user_id: int,
        analysis_id: int,
        file_path: str,
        report_kind: str,
        file_size: int = None,
    ) -> int | None:
        """
        Create export record for analysis.

        Args:
            user_id: User ID
            analysis_id: Analysis ID
            file_path: Path to exported file
            report_kind: Type of report ('snapshot_pdf', 'simulator_pdf', etc.)
            file_size: File size in bytes

        Returns:
            Export ID if successful
        """
        return self.db.create_export(
            user_id=user_id,
            analysis_id=analysis_id,
            file_path=file_path,
            report_kind=report_kind,
            file_size=file_size,
        )

    def list_analysis_exports(self, user_id: int, analysis_id: int) -> list:
        """
        List exports for an analysis.

        Args:
            user_id: User ID
            analysis_id: Analysis ID

        Returns:
            List of export dicts
        """
        return self.db.list_exports_for_analysis(analysis_id, user_id)
