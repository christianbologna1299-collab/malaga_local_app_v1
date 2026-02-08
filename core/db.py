"""
SQLite Database management for Banker Analytics.
Handles schema initialization, connection pooling, and utility functions.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager with thread-safe operations."""

    def __init__(self, db_path: str = "banker_analytics.db"):
        """
        Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file (relative to working directory)
        """
        self.db_path = Path(db_path)
        logger.info(f"Database path: {self.db_path.resolve()}")

        # Create connection and initialize schema
        self._init_schema()
        logger.info("Database initialized successfully")

    def _get_connection(self):
        """Get a new SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn

    def _init_schema(self):
        """Initialize database schema if not exists."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Create users table (M3: Multi-user support)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create sessions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    row_count INTEGER NOT NULL,
                    status TEXT DEFAULT 'active',
                    csv_hash TEXT,
                    metadata TEXT
                )
                """
            )

            # Create indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON sessions(created_at)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accessed_at
                ON sessions(accessed_at)
                """
            )

            # Create session_dataframes table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS session_dataframes (
                    session_id TEXT PRIMARY KEY,
                    dataframe_blob BLOB NOT NULL,
                    format TEXT DEFAULT 'pickle',
                    size_bytes INTEGER,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )

            # ===== M3: PERSISTENCE TABLES =====

            # Create analyses table (M3: Analysis history and metadata)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    row_count INTEGER NOT NULL,
                    date_min DATE,
                    date_max DATE,
                    analysis_type TEXT,
                    tags TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            # Create index on user_id for fast lookups
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analyses_user_id
                ON analyses(user_id)
                """
            )

            # Create analysis_files table (M3: Disk storage metadata)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    stored_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    size_bytes INTEGER,
                    format TEXT DEFAULT 'parquet',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                )
                """
            )

            # Create scenarios table (M3: Shock results with reproducibility)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rate_shock_bps INTEGER,
                    balance_shock_pct REAL,
                    results_json TEXT NOT NULL,
                    inputs_hash TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                )
                """
            )

            # Create index on analysis_id for scenario lookups
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenarios_analysis_id
                ON scenarios(analysis_id)
                """
            )

            # Create exports table (M3: PDF and future artifact tracking)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_id INTEGER,
                    scenario_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    report_kind TEXT,
                    template_version TEXT,
                    meta_json TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE SET NULL,
                    FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE SET NULL
                )
                """
            )

            # Create index on user_id for export lookups
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_exports_user_id
                ON exports(user_id)
                """
            )

            # ===== FUTURE M3 TABLES (STUBS) =====

            # Create data_sources table (stub for future data integration)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    auth_method TEXT,
                    base_url TEXT,
                    enabled BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create data_fetches table (stub for future automated retrieval)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS data_fetches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_id INTEGER,
                    source_id INTEGER,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    query_params_json TEXT,
                    raw_path TEXT,
                    parsed_summary_json TEXT,
                    checksum TEXT,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE SET NULL,
                    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE SET NULL
                )
                """
            )

            # ===== M3.5: TREND ENGINE TABLES =====

            # Create analysis_trends table (M3.5: Deterministic trend metrics)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_trends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    window_days INTEGER NOT NULL,
                    series_name TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    confidence TEXT,
                    inputs_hash TEXT UNIQUE,
                    trend_engine_version TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                )
                """
            )

            # Create index on analysis_id + series_name for fast trend lookups
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_trends_analysis_id_series
                ON analysis_trends(analysis_id, series_name)
                """
            )

            # Create index on inputs_hash for determinism checks
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_trends_inputs_hash
                ON analysis_trends(inputs_hash)
                """
            )

            # ===== M3.75: AUDIT EVENTS TABLE =====

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER,
                    event_kind TEXT NOT NULL,
                    details_json TEXT,
                    analysis_id INTEGER,
                    session_id TEXT,
                    request_id TEXT,
                    ip_address TEXT
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_user_id
                ON audit_events(user_id)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_event_kind
                ON audit_events(event_kind)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
                ON audit_events(timestamp)
                """
            )

            conn.commit()
            logger.debug("Schema initialized successfully")

        except sqlite3.Error as e:
            logger.error(f"Database schema error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = (), fetch: str = None):
        """
        Execute a SQL query with optional params.

        Args:
            query: SQL query string
            params: Query parameters tuple
            fetch: None (execute only), 'one' (fetchone), 'all' (fetchall)

        Returns:
            Query result or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)

            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            else:
                result = None

            conn.commit()
            return result

        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def batch_execute(self, queries: list):
        """
        Execute multiple queries in a transaction.

        Args:
            queries: List of (query_string, params_tuple) tuples

        Returns:
            True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            for query, params in queries:
                cursor.execute(query, params)
            conn.commit()
            logger.debug(f"Batch executed: {len(queries)} queries")
            return True

        except sqlite3.Error as e:
            logger.error(f"Batch execution error: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def backup(self, backup_path: str = None) -> str:
        """
        Create a backup copy of the database.

        Args:
            backup_path: Optional path for backup file. Default: db_path.backup_{timestamp}

        Returns:
            Path to backup file
        """
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = str(self.db_path).replace(
                ".db", f".backup_{timestamp}.db"
            )

        conn = self._get_connection()
        try:
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()
            logger.info(f"Database backed up to: {backup_path}")
            return backup_path
        finally:
            conn.close()

    def get_size_mb(self) -> float:
        """Get database file size in MB."""
        if self.db_path.exists():
            size_bytes = self.db_path.stat().st_size
            return round(size_bytes / (1024 * 1024), 2)
        return 0.0

    def get_stats(self) -> dict:
        """Get database statistics."""
        session_count = self.execute_query(
            "SELECT COUNT(*) as count FROM sessions WHERE status = 'active'",
            fetch="one",
        )
        total_size = self.execute_query(
            "SELECT SUM(COALESCE(size_bytes, 0)) as total FROM session_dataframes",
            fetch="one",
        )

        return {
            "active_sessions": session_count[0] if session_count else 0,
            "total_size_bytes": total_size[0] if total_size else 0,
            "db_file_size_mb": self.get_size_mb(),
        }

    # ============================================================================
    # USER MANAGEMENT (M3: Multi-user support)
    # ============================================================================

    def create_user(self, username: str, password_hash: str) -> int | None:
        """
        Create a new user.

        Args:
            username: Unique username
            password_hash: Bcrypt-hashed password

        Returns:
            User ID if successful, None if username already exists
        """
        try:
            self.execute_query(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            user = self.execute_query(
                "SELECT id FROM users WHERE username = ?",
                (username,),
                fetch="one",
            )
            if user:
                logger.info(f"User created: {username}")
                return user["id"]
        except sqlite3.IntegrityError:
            logger.warning(f"Username already exists: {username}")
        except Exception as e:
            logger.error(f"Error creating user {username}: {e}")
        return None

    def get_user_by_username(self, username: str) -> dict | None:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            User dict with id, username, password_hash, created_at; None if not found
        """
        try:
            result = self.execute_query(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
                (username,),
                fetch="one",
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting user {username}: {e}")
        return None

    def get_user_by_id(self, user_id: int) -> dict | None:
        """
        Get user by ID.

        Args:
            user_id: User ID to look up

        Returns:
            User dict with id, username, created_at; None if not found
        """
        try:
            result = self.execute_query(
                "SELECT id, username, created_at FROM users WHERE id = ?",
                (user_id,),
                fetch="one",
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting user ID {user_id}: {e}")
        return None

    # ============================================================================
    # ANALYSIS PERSISTENCE (M3: Multi-user analysis history)
    # ============================================================================

    def create_analysis(
        self,
        user_id: int,
        filename: str,
        row_count: int,
        date_min: str = None,
        date_max: str = None,
        analysis_type: str = None,
        tags: str = None,
    ) -> int | None:
        """
        Create an analysis record.

        Args:
            user_id: User ID (owner)
            filename: Original filename
            row_count: Number of rows in dataset
            date_min: Minimum date in data (optional)
            date_max: Maximum date in data (optional)
            analysis_type: Optional analysis type label
            tags: Optional JSON string of tags

        Returns:
            Analysis ID if successful, None otherwise
        """
        try:
            self.execute_query(
                """
                INSERT INTO analyses (user_id, filename, row_count, date_min, date_max, analysis_type, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, filename, row_count, date_min, date_max, analysis_type, tags),
            )
            result = self.execute_query(
                "SELECT id FROM analyses WHERE user_id = ? AND filename = ? ORDER BY id DESC LIMIT 1",
                (user_id, filename),
                fetch="one",
            )
            if result:
                logger.info(f"Analysis created: {result['id']} for user {user_id}")
                return result["id"]
        except Exception as e:
            logger.error(f"Error creating analysis: {e}")
        return None

    def get_analysis(self, analysis_id: int, user_id: int) -> dict | None:
        """
        Get analysis by ID with ownership verification.

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)

        Returns:
            Analysis dict if owned by user, None otherwise
        """
        try:
            result = self.execute_query(
                """
                SELECT id, user_id, filename, uploaded_at, row_count, date_min, date_max, analysis_type, tags
                FROM analyses WHERE id = ? AND user_id = ?
                """,
                (analysis_id, user_id),
                fetch="one",
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting analysis {analysis_id}: {e}")
        return None

    def list_user_analyses(self, user_id: int, limit: int = 50) -> list:
        """
        List all analyses for a user.

        Args:
            user_id: User ID
            limit: Maximum number to return

        Returns:
            List of analysis dicts
        """
        try:
            results = self.execute_query(
                """
                SELECT id, filename, uploaded_at, row_count, date_min, date_max
                FROM analyses WHERE user_id = ? ORDER BY uploaded_at DESC LIMIT ?
                """,
                (user_id, limit),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error listing analyses for user {user_id}: {e}")
        return []

    def create_analysis_file(
        self,
        user_id: int,
        analysis_id: int,
        stored_path: str,
        file_hash: str,
        size_bytes: int = None,
        format: str = "parquet",
    ) -> int | None:
        """
        Create analysis_files record.

        Args:
            user_id: User ID
            analysis_id: Analysis ID
            stored_path: Path where file is stored (e.g., data/analyses/12345.parquet)
            file_hash: SHA256 hash of file
            size_bytes: File size in bytes
            format: File format ('parquet' or 'csv')

        Returns:
            analysis_files ID if successful
        """
        try:
            self.execute_query(
                """
                INSERT INTO analysis_files (user_id, analysis_id, stored_path, file_hash, size_bytes, format)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, analysis_id, stored_path, file_hash, size_bytes, format),
            )
            result = self.execute_query(
                "SELECT id FROM analysis_files WHERE analysis_id = ? ORDER BY id DESC LIMIT 1",
                (analysis_id,),
                fetch="one",
            )
            if result:
                logger.info(f"Analysis file created: {stored_path}")
                return result["id"]
        except Exception as e:
            logger.error(f"Error creating analysis_file: {e}")
        return None

    def get_analysis_file(self, analysis_id: int, user_id: int) -> dict | None:
        """
        Get analysis file by analysis_id with ownership verification.

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)

        Returns:
            analysis_files dict if owned by user
        """
        try:
            result = self.execute_query(
                """
                SELECT id, stored_path, file_hash, size_bytes, format, created_at
                FROM analysis_files WHERE analysis_id = ? AND user_id = ?
                """,
                (analysis_id, user_id),
                fetch="one",
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting analysis file: {e}")
        return None

    # ============================================================================
    # SCENARIO PERSISTENCE (M3: Shock results)
    # ============================================================================

    def create_scenario(
        self,
        user_id: int,
        analysis_id: int,
        rate_shock_bps: int = None,
        balance_shock_pct: float = None,
        results_json: str = None,
        inputs_hash: str = None,
    ) -> int | None:
        """
        Create a scenario (shock result).

        Args:
            user_id: User ID
            analysis_id: Analysis ID
            rate_shock_bps: Rate shock in basis points (optional)
            balance_shock_pct: Balance shock percentage (optional)
            results_json: JSON string of results
            inputs_hash: Optional reproducibility hash

        Returns:
            Scenario ID if successful
        """
        try:
            self.execute_query(
                """
                INSERT INTO scenarios (user_id, analysis_id, rate_shock_bps, balance_shock_pct, results_json, inputs_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, analysis_id, rate_shock_bps, balance_shock_pct, results_json, inputs_hash),
            )
            result = self.execute_query(
                "SELECT id FROM scenarios WHERE analysis_id = ? ORDER BY id DESC LIMIT 1",
                (analysis_id,),
                fetch="one",
            )
            if result:
                logger.info(f"Scenario created: {result['id']} for analysis {analysis_id}")
                return result["id"]
        except Exception as e:
            logger.error(f"Error creating scenario: {e}")
        return None

    def list_scenarios_for_analysis(self, analysis_id: int, user_id: int) -> list:
        """
        List all scenarios for an analysis with ownership verification.

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)

        Returns:
            List of scenario dicts
        """
        try:
            results = self.execute_query(
                """
                SELECT id, created_at, rate_shock_bps, balance_shock_pct
                FROM scenarios WHERE analysis_id = ? AND user_id = ? ORDER BY created_at DESC
                """,
                (analysis_id, user_id),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error listing scenarios: {e}")
        return []

    # ============================================================================
    # EXPORT TRACKING (M3: PDF and future artifacts)
    # ============================================================================

    def create_export(
        self,
        user_id: int,
        file_path: str,
        report_kind: str,
        analysis_id: int = None,
        scenario_id: int = None,
        file_size: int = None,
        template_version: str = None,
        meta_json: str = None,
    ) -> int | None:
        """
        Create an export record (tracks PDFs and future artifacts).

        Args:
            user_id: User ID
            file_path: Path to exported file
            report_kind: Type of report ('snapshot_pdf', 'simulator_pdf', 'explain_pdf', etc.)
            analysis_id: Optional analysis ID (nullable)
            scenario_id: Optional scenario ID (nullable)
            file_size: File size in bytes
            template_version: Optional template version
            meta_json: Optional metadata JSON

        Returns:
            Export ID if successful
        """
        try:
            self.execute_query(
                """
                INSERT INTO exports (user_id, analysis_id, scenario_id, file_path, file_size, report_kind, template_version, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, analysis_id, scenario_id, file_path, file_size, report_kind, template_version, meta_json),
            )
            result = self.execute_query(
                "SELECT id FROM exports WHERE user_id = ? AND file_path = ? ORDER BY id DESC LIMIT 1",
                (user_id, file_path),
                fetch="one",
            )
            if result:
                logger.info(f"Export record created: {report_kind} for analysis {analysis_id}")
                return result["id"]
        except Exception as e:
            logger.error(f"Error creating export: {e}")
        return None

    def list_exports_for_analysis(self, analysis_id: int, user_id: int) -> list:
        """
        List all exports for an analysis with ownership verification.

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)

        Returns:
            List of export dicts
        """
        try:
            results = self.execute_query(
                """
                SELECT id, created_at, file_path, file_size, report_kind
                FROM exports WHERE analysis_id = ? AND user_id = ? ORDER BY created_at DESC
                """,
                (analysis_id, user_id),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error listing exports: {e}")
        return []

    def get_export(self, export_id: int, user_id: int) -> dict | None:
        """
        Get export by ID with ownership verification.

        Args:
            export_id: Export ID
            user_id: User ID (for ownership check)

        Returns:
            Export dict if owned by user
        """
        try:
            result = self.execute_query(
                """
                SELECT id, file_path, file_size, report_kind, created_at
                FROM exports WHERE id = ? AND user_id = ?
                """,
                (export_id, user_id),
                fetch="one",
            )
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting export: {e}")
        return None

    # ============================================================================
    # TREND TRACKING (M3.5: Deterministic trend analysis)
    # ============================================================================

    def trend_exists(self, inputs_hash: str) -> bool:
        """
        Check if trend already exists (determinism gate).

        Args:
            inputs_hash: Determinism hash (hash of file_hash + version + window + series)

        Returns:
            True if trend exists, False otherwise
        """
        try:
            result = self.execute_query(
                "SELECT id FROM analysis_trends WHERE inputs_hash = ? LIMIT 1",
                (inputs_hash,),
                fetch="one",
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error checking trend existence: {e}")
        return False

    def create_trend(
        self,
        user_id: int,
        analysis_id: int,
        window_days: int,
        series_name: str,
        metrics_json: str,
        confidence: str,
        inputs_hash: str,
        trend_engine_version: str = "v1.0",
    ) -> int | None:
        """
        Create a trend record (deterministic).

        Args:
            user_id: User ID
            analysis_id: Analysis ID
            window_days: Window size (30/90/180)
            series_name: Series name ("balance" or "rate")
            metrics_json: Compact JSON of metrics
            confidence: Confidence level ("high"/"medium"/"low")
            inputs_hash: Determinism hash
            trend_engine_version: Version string

        Returns:
            Trend ID if successful, None otherwise
        """
        try:
            self.execute_query(
                """
                INSERT INTO analysis_trends (user_id, analysis_id, window_days, series_name, metrics_json, confidence, inputs_hash, trend_engine_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, analysis_id, window_days, series_name, metrics_json, confidence, inputs_hash, trend_engine_version),
            )
            result = self.execute_query(
                "SELECT id FROM analysis_trends WHERE inputs_hash = ?",
                (inputs_hash,),
                fetch="one",
            )
            if result:
                logger.info(f"Trend created: {series_name} window {window_days} for analysis {analysis_id}")
                return result["id"]
        except sqlite3.IntegrityError:
            logger.debug(f"Trend already exists (inputs_hash: {inputs_hash})")
        except Exception as e:
            logger.error(f"Error creating trend: {e}")
        return None

    def list_trends_for_analysis(self, analysis_id: int, user_id: int) -> list:
        """
        List all trends for an analysis with ownership verification.

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)

        Returns:
            List of trend dicts
        """
        try:
            results = self.execute_query(
                """
                SELECT id, computed_at, window_days, series_name, metrics_json, confidence
                FROM analysis_trends WHERE analysis_id = ? AND user_id = ? ORDER BY series_name, window_days
                """,
                (analysis_id, user_id),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error listing trends: {e}")
        return []

    def list_trend_summary_for_history(self, user_id: int, limit: int = 100, window_days: int = 90) -> list:
        """
        List compact trend summaries for history view (90-day only for speed).

        Args:
            user_id: User ID
            limit: Maximum number of analyses to return
            window_days: Window to filter (default 90)

        Returns:
            List of (analysis_id, balance_trend, rate_trend) tuples
        """
        try:
            results = self.execute_query(
                """
                SELECT DISTINCT analysis_id,
                  MAX(CASE WHEN series_name = 'balance' THEN metrics_json ELSE NULL END) as balance_trend,
                  MAX(CASE WHEN series_name = 'rate' THEN metrics_json ELSE NULL END) as rate_trend
                FROM analysis_trends
                WHERE user_id = ? AND window_days = ?
                GROUP BY analysis_id
                ORDER BY analysis_id DESC
                LIMIT ?
                """,
                (user_id, window_days, limit),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error listing trend summaries: {e}")
        return []

    def get_trends_for_analysis_window(
        self,
        analysis_id: int,
        user_id: int,
        window_days: int,
    ) -> list:
        """
        Get trends for an analysis and specific window (for snapshot detail).

        Args:
            analysis_id: Analysis ID
            user_id: User ID (for ownership check)
            window_days: Window size (30/90/180)

        Returns:
            List of trend dicts for balance + rate series
        """
        try:
            results = self.execute_query(
                """
                SELECT window_days, series_name, metrics_json, confidence, computed_at
                FROM analysis_trends WHERE analysis_id = ? AND user_id = ? AND window_days = ?
                ORDER BY series_name
                """,
                (analysis_id, user_id, window_days),
                fetch="all",
            )
            return [dict(row) for row in (results or [])]
        except Exception as e:
            logger.error(f"Error getting trends for window: {e}")
        return []

