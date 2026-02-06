"""
Test suite for PHASE B/C: Analysis History and Reproducibility
Tests that analyses can be reopened and KPIs are regenerated deterministically.
"""

import pytest
from httpx import AsyncClient
import pandas as pd
from pathlib import Path
from app import app, db, BASE_DIR
from core.kpi import compute_kpis


@pytest.fixture
async def client():
    """Create an async client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def setup_db():
    """Initialize test database and create test user."""
    db._initialize_schema()
    user_id = db.create_user("alice", "AlicePass123!")
    yield {"user_id": user_id}

    # Cleanup
    db.conn.execute("DELETE FROM analysis_files")
    db.conn.execute("DELETE FROM analyses")
    db.conn.execute("DELETE FROM users")
    db.conn.commit()


@pytest.fixture
def sample_dataframe():
    """Create a reproducible sample DataFrame."""
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=100),
        "balance": [100000 - i * 500 for i in range(100)],
        "rate": [5.0 + (i % 20) * 0.05 for i in range(100)],
    })


async def login_as(client, username="alice", password="AlicePass123!"):
    """Helper to login."""
    response = await client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return response


class TestAnalysisHistory:
    """Test analysis persistence and history."""

    @pytest.mark.asyncio
    async def test_analysis_appears_in_history(self, client, setup_db, sample_dataframe):
        """Test that uploaded analysis appears in /history."""
        # Login
        client.cookies.clear()
        await login_as(client)

        # Create and save analysis
        ANALYSES_DIR = BASE_DIR / "data" / "analyses"
        ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="sample_data.csv",
            row_count=len(sample_dataframe),
            date_min=str(sample_dataframe["date"].min().date()),
            date_max=str(sample_dataframe["date"].max().date()),
        )

        # Save parquet file
        parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
        sample_dataframe.to_parquet(str(parquet_path))

        # Create analysis_file record
        db.create_analysis_file(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            stored_path=f"data/analyses/{analysis_id}.parquet",
            file_hash="test_hash",
        )

        # View history
        response = await client.get("/history")
        assert response.status_code == 200
        assert "sample_data.csv" in response.text
        assert str(analysis_id) in response.text

    @pytest.mark.asyncio
    async def test_analysis_metadata_preserved(self, client, setup_db, sample_dataframe):
        """Test that analysis metadata is correctly preserved."""
        client.cookies.clear()
        await login_as(client)

        # Create analysis
        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="metadata_test.csv",
            row_count=len(sample_dataframe),
            date_min="2025-01-01",
            date_max="2025-04-10",
        )

        # Retrieve and verify
        retrieved = db.get_analysis(analysis_id, setup_db["user_id"])
        assert retrieved is not None
        assert retrieved["filename"] == "metadata_test.csv"
        assert retrieved["row_count"] == len(sample_dataframe)
        assert retrieved["date_min"] == "2025-01-01"
        assert retrieved["date_max"] == "2025-04-10"


class TestDeterministicKPIs:
    """Test that KPIs are computed deterministically."""

    def test_kpi_computation_is_deterministic(self, sample_dataframe):
        """Test that same DataFrame produces identical KPIs."""
        # Compute KPIs twice
        kpis_1 = compute_kpis(sample_dataframe)
        kpis_2 = compute_kpis(sample_dataframe)

        # Compare key metrics
        assert kpis_1["start_balance"] == kpis_2["start_balance"]
        assert kpis_1["end_balance"] == kpis_2["end_balance"]
        assert kpis_1["balance_avg"] == kpis_2["balance_avg"]
        assert kpis_1["rate_avg"] == kpis_2["rate_avg"]
        assert kpis_1["balance_min"] == kpis_2["balance_min"]
        assert kpis_1["balance_max"] == kpis_2["balance_max"]

    def test_kpi_values_correct(self, sample_dataframe):
        """Test that KPI values are calculated correctly."""
        kpis = compute_kpis(sample_dataframe)

        # Verify expected values based on sample data
        assert kpis["start_balance"] == 100000  # First row balance
        assert kpis["end_balance"] == 100000 - 99 * 500  # Last row balance
        assert kpis["row_count"] == len(sample_dataframe)

    def test_kpi_computation_tolerates_float_rounding(self, sample_dataframe):
        """Test that KPI computation is tolerant of float rounding."""
        kpis = compute_kpis(sample_dataframe)

        # Average should be within expected range
        # (100000 + 50000) / 2 = 75000
        assert abs(kpis["balance_avg"] - 75000) < 1.0

    def test_different_dataframes_produce_different_kpis(self):
        """Test that different data produces different KPIs."""
        df1 = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=100),
            "balance": [100000] * 100,
            "rate": [5.0] * 100,
        })

        df2 = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=100),
            "balance": [50000] * 100,
            "rate": [3.0] * 100,
        })

        kpis1 = compute_kpis(df1)
        kpis2 = compute_kpis(df2)

        # KPIs should differ
        assert kpis1["start_balance"] != kpis2["start_balance"]
        assert kpis1["rate_avg"] != kpis2["rate_avg"]


class TestAnalysisReopening:
    """Test reopening analyses and regenerating results."""

    @pytest.mark.asyncio
    async def test_reopen_analysis_loads_snapshot(self, client, setup_db, sample_dataframe):
        """Test that reopening analysis shows snapshot correctly."""
        client.cookies.clear()
        await login_as(client)

        # Create and save analysis
        ANALYSES_DIR = BASE_DIR / "data" / "analyses"
        ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="reopen_test.csv",
            row_count=len(sample_dataframe),
            date_min=str(sample_dataframe["date"].min().date()),
            date_max=str(sample_dataframe["date"].max().date()),
        )

        parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
        sample_dataframe.to_parquet(str(parquet_path))

        db.create_analysis_file(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            stored_path=f"data/analyses/{analysis_id}.parquet",
            file_hash="test_hash",
        )

        # Reopen analysis (GET /snapshot/a/{analysis_id})
        response = await client.get(f"/snapshot/a/{analysis_id}")
        assert response.status_code == 200

        # Should show filename in response
        assert "reopen_test.csv" in response.text

    @pytest.mark.asyncio
    async def test_reopen_simulator_with_shocks(self, client, setup_db, sample_dataframe):
        """Test that simulator works with reopened analysis."""
        client.cookies.clear()
        await login_as(client)

        # Create analysis
        ANALYSES_DIR = BASE_DIR / "data" / "analyses"
        ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="simulator_test.csv",
            row_count=len(sample_dataframe),
            date_min=str(sample_dataframe["date"].min().date()),
            date_max=str(sample_dataframe["date"].max().date()),
        )

        parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
        sample_dataframe.to_parquet(str(parquet_path))

        db.create_analysis_file(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            stored_path=f"data/analyses/{analysis_id}.parquet",
            file_hash="test_hash",
        )

        # Open simulator
        response = await client.get(f"/simulator/a/{analysis_id}")
        assert response.status_code == 200

        # Should show form
        assert "Configure Scenario" in response.text or "rate_shock" in response.text

    @pytest.mark.asyncio
    async def test_reopen_explain_with_rules(self, client, setup_db, sample_dataframe):
        """Test that explain route works with reopened analysis."""
        client.cookies.clear()
        await login_as(client)

        # Create analysis
        ANALYSES_DIR = BASE_DIR / "data" / "analyses"
        ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="explain_test.csv",
            row_count=len(sample_dataframe),
            date_min=str(sample_dataframe["date"].min().date()),
            date_max=str(sample_dataframe["date"].max().date()),
        )

        parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
        sample_dataframe.to_parquet(str(parquet_path))

        db.create_analysis_file(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            stored_path=f"data/analyses/{analysis_id}.parquet",
            file_hash="test_hash",
        )

        # Open explain
        response = await client.get(f"/explain/a/{analysis_id}")
        assert response.status_code == 200

        # Should show explanation sections
        assert "What Matters" in response.text or "what_matters" in response.text.lower()


class TestExportHistory:
    """Test export persistence and history access."""

    def test_export_creates_database_record(self, setup_db):
        """Test that exports are recorded in database."""
        # Create analysis
        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="export_test.csv",
            row_count=100,
        )

        # Create export record
        export_id = db.create_export(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            file_path="exports/snapshot_12345.pdf",
            report_kind="snapshot_pdf",
            file_size=512000,
        )

        assert export_id is not None

        # Retrieve export and verify
        exports = db.list_exports_for_analysis(analysis_id, setup_db["user_id"])
        assert len(exports) == 1
        assert exports[0]["report_kind"] == "snapshot_pdf"
        assert exports[0]["file_size"] == 512000

    def test_multiple_exports_per_analysis(self, setup_db):
        """Test that multiple exports can be linked to one analysis."""
        analysis_id = db.create_analysis(
            user_id=setup_db["user_id"],
            filename="multi_export.csv",
            row_count=100,
        )

        # Create multiple exports
        export_id_1 = db.create_export(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            file_path="exports/snapshot_1.pdf",
            report_kind="snapshot_pdf",
            file_size=512000,
        )

        export_id_2 = db.create_export(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            file_path="exports/simulator_2.pdf",
            report_kind="simulator_pdf",
            file_size=620000,
        )

        export_id_3 = db.create_export(
            user_id=setup_db["user_id"],
            analysis_id=analysis_id,
            file_path="exports/explain_3.pdf",
            report_kind="explain_pdf",
            file_size=450000,
        )

        # Retrieve and verify all exports are present
        exports = db.list_exports_for_analysis(analysis_id, setup_db["user_id"])
        assert len(exports) == 3

        report_kinds = {e["report_kind"] for e in exports}
        assert report_kinds == {"snapshot_pdf", "simulator_pdf", "explain_pdf"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
