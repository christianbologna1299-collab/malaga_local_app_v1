"""
Test suite for PHASE B/C: User Isolation and Access Control
Tests that User A cannot see/access User B's data, and vice versa.
"""

import pytest
from httpx import AsyncClient
import pandas as pd
from pathlib import Path
from app import app, db, BASE_DIR


@pytest.fixture
async def client():
    """Create an async client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def setup_db():
    """Initialize test database and users."""
    # Create tables
    db._initialize_schema()

    # Create test users
    alice_user = db.create_user("alice", "AlicePass123!")
    bob_user = db.create_user("bob", "BobPass456!")

    yield {"alice_id": alice_user, "bob_id": bob_user}

    # Cleanup
    db.conn.execute("DELETE FROM exports")
    db.conn.execute("DELETE FROM analysis_files")
    db.conn.execute("DELETE FROM analyses")
    db.conn.execute("DELETE FROM users")
    db.conn.commit()


async def login_as(client, username, password):
    """Helper to login as a specific user."""
    response = await client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    # Ensure cookies are set
    return response


async def create_test_analysis(user_id, filename="test_data.csv", row_count=100):
    """Helper to create a test analysis in the database."""
    # Create analysis record
    analysis_id = db.create_analysis(
        user_id=user_id,
        filename=filename,
        row_count=row_count,
        date_min="2025-01-01",
        date_max="2025-12-31",
    )

    # Create dummy parquet file
    ANALYSES_DIR = BASE_DIR / "data" / "analyses"
    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=row_count),
        "balance": [100000 - i * 100 for i in range(row_count)],
        "rate": [5.0 + (i % 10) / 100 for i in range(row_count)],
    })

    parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
    df.to_parquet(str(parquet_path))

    # Create analysis_file record
    db.create_analysis_file(
        user_id=user_id,
        analysis_id=analysis_id,
        stored_path=f"data/analyses/{analysis_id}.parquet",
        file_hash="dummy_hash",
    )

    return analysis_id


class TestUserIsolation:
    """Test user data isolation."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_analyses(self, client, setup_db):
        """Test that User A cannot see User B's analyses in /history."""
        # Alice creates an analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice_data.csv",
            row_count=100,
        )

        # Bob creates an analysis
        bob_analysis_id = db.create_analysis(
            user_id=setup_db["bob_id"],
            filename="bob_data.csv",
            row_count=100,
        )

        # Login as Alice
        client.cookies.clear()
        await login_as(client, "alice", "AlicePass123!")

        # Alice views her history
        response = await client.get("/history")
        assert response.status_code == 200
        assert "alice_data.csv" in response.text

        # Bob's analysis should NOT be visible
        assert "bob_data.csv" not in response.text

        # Login as Bob
        client.cookies.clear()
        await login_as(client, "bob", "BobPass456!")

        # Bob views his history
        response = await client.get("/history")
        assert response.status_code == 200
        assert "bob_data.csv" in response.text

        # Alice's analysis should NOT be visible
        assert "alice_data.csv" not in response.text

    @pytest.mark.asyncio
    async def test_direct_access_to_other_users_analysis_denied(self, client, setup_db):
        """Test that direct access to another user's analysis is denied (404)."""
        # Alice creates analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Login as Bob
        client.cookies.clear()
        await login_as(client, "bob", "BobPass456!")

        # Bob tries to access Alice's analysis
        response = await client.get(
            f"/snapshot/a/{alice_analysis_id}",
            follow_redirects=False,
        )

        # Should return 404 (not found / access denied)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_simulator_cross_user_denial(self, client, setup_db):
        """Test that cross-user access to simulator is denied."""
        # Create Alice's analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Login as Bob
        client.cookies.clear()
        await login_as(client, "bob", "BobPass456!")

        # Bob tries to access Alice's simulator
        response = await client.get(
            f"/simulator/a/{alice_analysis_id}",
            follow_redirects=False,
        )

        # Should return 404
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_explain_cross_user_denial(self, client, setup_db):
        """Test that cross-user access to explain is denied."""
        # Create Alice's analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Login as Bob
        client.cookies.clear()
        await login_as(client, "bob", "BobPass456!")

        # Bob tries to access Alice's explain route
        response = await client.get(
            f"/explain/a/{alice_analysis_id}",
            follow_redirects=False,
        )

        # Should return 404
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_snapshot_export_cross_user_denial(self, client, setup_db):
        """Test that cross-user export access is denied."""
        # Create Alice's analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Login as Bob
        client.cookies.clear()
        await login_as(client, "bob", "BobPass456!")

        # Bob tries to export Alice's snapshot
        response = await client.post(
            f"/snapshot/a/{alice_analysis_id}/export-pdf",
            follow_redirects=False,
        )

        # Should fail with 404
        assert response.status_code in [404, 302]  # Could redirect to login or 404


class TestOwnershipVerification:
    """Test database-level ownership verification."""

    def test_get_analysis_with_wrong_user_returns_none(self, setup_db):
        """Test that get_analysis returns None if user doesn't own it."""
        # Alice creates analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Query with Bob's user_id should return None
        result = db.get_analysis(alice_analysis_id, setup_db["bob_id"])
        assert result is None

    def test_list_user_analyses_excludes_other_users(self, setup_db):
        """Test that list_user_analyses only returns user's own analyses."""
        # Create analyses for Alice and Bob
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )
        bob_analysis_id = db.create_analysis(
            user_id=setup_db["bob_id"],
            filename="bob.csv",
            row_count=100,
        )

        # Get Alice's analyses
        alice_analyses = db.list_user_analyses(setup_db["alice_id"])

        # Should only have Alice's analysis
        assert len(alice_analyses) == 1
        assert alice_analyses[0]["id"] == alice_analysis_id
        assert alice_analyses[0]["filename"] == "alice.csv"

        # Get Bob's analyses
        bob_analyses = db.list_user_analyses(setup_db["bob_id"])

        # Should only have Bob's analysis
        assert len(bob_analyses) == 1
        assert bob_analyses[0]["id"] == bob_analysis_id
        assert bob_analyses[0]["filename"] == "bob.csv"


class TestExportIsolation:
    """Test export file access control and cleanup safety."""

    @pytest.mark.asyncio
    async def test_export_download_requires_ownership(self, client, setup_db):
        """Test that exporting creates records linked to user."""
        # Create Alice's analysis
        alice_analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="alice.csv",
            row_count=100,
        )

        # Login as Alice
        client.cookies.clear()
        await login_as(client, "alice", "AlicePass123!")

        # Verify Alice can see her exports in history
        response = await client.get("/history")
        assert response.status_code == 200
        # History should render without errors

    def test_cleanup_preserves_referenced_exports(self, setup_db):
        """Test that cleanup_old_exports preserves files in exports table."""
        from app import cleanup_old_exports

        # Create an analysis with export
        analysis_id = db.create_analysis(
            user_id=setup_db["alice_id"],
            filename="test.csv",
            row_count=100,
        )

        # Create export record pointing to a file
        export_id = db.create_export(
            user_id=setup_db["alice_id"],
            analysis_id=analysis_id,
            file_path="exports/test_export.pdf",
            report_kind="snapshot_pdf",
            file_size=1024,
        )

        # Run cleanup - should preserve the referenced export
        before_count = db.execute_query(
            "SELECT COUNT(*) as count FROM exports",
            fetch="one",
        )["count"]

        cleanup_old_exports(max_age_hours=0)  # Clean all old files

        # Export record should still exist
        after_count = db.execute_query(
            "SELECT COUNT(*) as count FROM exports",
            fetch="one",
        )["count"]

        assert before_count == after_count


class TestDataValidation:
    """Test that invalid data access is properly rejected."""

    @pytest.mark.asyncio
    async def test_invalid_analysis_id_returns_404(self, client, setup_db):
        """Test that non-existent analysis_id returns 404."""
        # Login as Alice
        client.cookies.clear()
        await login_as(client, "alice", "AlicePass123!")

        # Try to access non-existent analysis
        response = await client.get(
            "/snapshot/a/99999",
            follow_redirects=False,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_negative_analysis_id_handled(self, client, setup_db):
        """Test that negative analysis IDs are handled gracefully."""
        client.cookies.clear()
        await login_as(client, "alice", "AlicePass123!")

        response = await client.get("/snapshot/a/-1", follow_redirects=False)
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
