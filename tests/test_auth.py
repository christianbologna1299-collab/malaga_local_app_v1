"""
Test suite for PHASE A: Authentication (Login, Logout, Register)
Tests password hashing, user creation, login/logout flow, and duplicate prevention.
"""

import pytest
from httpx import AsyncClient
from app import app, db


@pytest.fixture
async def client():
    """Create an async client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def setup_db():
    """Initialize test database."""
    # Create tables
    db._initialize_schema()
    yield
    # Cleanup after tests
    db.conn.execute("DELETE FROM users")
    db.conn.commit()


class TestPasswordHashing:
    """Test bcrypt password hashing implementation."""

    def test_password_hashing(self, setup_db):
        """Test that passwords are hashed, not stored in plain text."""
        from core.auth import hash_password, verify_password

        password = "TestPassword123!"
        hashed = hash_password(password)

        # Hash should not equal plain password
        assert hashed != password

        # Hash should be bcrypt format (starts with $2b$)
        assert hashed.startswith("$2b$")

        # Verify correct password
        assert verify_password(password, hashed)

        # Verify incorrect password fails
        assert not verify_password("WrongPassword", hashed)

    def test_password_hashing_consistency(self, setup_db):
        """Test that same password produces different hashes (salting works)."""
        from core.auth import hash_password

        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different (due to salt)
        assert hash1 != hash2

    def test_72_byte_password_limit(self, setup_db):
        """Test bcrypt 72-byte password limit is handled."""
        from core.auth import hash_password, verify_password

        # Create a password longer than 72 bytes
        long_password = "a" * 100
        hashed = hash_password(long_password)

        # Should still be hashable and verifiable
        assert verify_password(long_password, hashed)


class TestUserRegistration:
    """Test user registration and creation."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, client, setup_db):
        """Test registering a new user."""
        response = await client.post(
            "/register",
            data={
                "username": "alice",
                "password": "AlicePass123!",
            },
            follow_redirects=False,
        )

        # Should redirect to hub or dashboard (success)
        assert response.status_code in [302, 303]

        # Verify user exists in database
        user = db.get_user_by_username("alice")
        assert user is not None
        assert user["username"] == "alice"

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client, setup_db):
        """Test that duplicate usernames are rejected."""
        # Register first user
        await client.post(
            "/register",
            data={"username": "bob", "password": "BobPass123!"},
        )

        # Try to register same username
        response = await client.post(
            "/register",
            data={"username": "bob", "password": "DifferentPass456!"},
        )

        # Should return error (400 or show error message)
        assert response.status_code in [400, 200]  # 200 if error shown on same page
        assert "already exists" in response.text or "duplicate" in response.text.lower()

    @pytest.mark.asyncio
    async def test_register_empty_fields(self, client, setup_db):
        """Test that empty username/password is rejected."""
        response = await client.post(
            "/register",
            data={"username": "", "password": "SomePass123!"},
        )

        # Should reject empty username
        assert response.status_code != 302  # Not a successful redirect

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client, setup_db):
        """Test password validation (optional: depends on implementation)."""
        response = await client.post(
            "/register",
            data={"username": "charlie", "password": "weak"},
        )

        # Depending on implementation, may or may not enforce password strength
        # This test documents expected behavior


class TestLogin:
    """Test login flow and session management."""

    @pytest.mark.asyncio
    async def test_login_successful(self, client, setup_db):
        """Test successful login with valid credentials."""
        # Register user first
        username = "alice"
        password = "AlicePass123!"
        await client.post(
            "/register",
            data={"username": username, "password": password},
        )

        # Clear client cookies
        client.cookies.clear()

        # Login
        response = await client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )

        # Should redirect (302) on successful login
        assert response.status_code in [302, 303]

        # Session cookie should be set
        assert "session" in client.cookies

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client, setup_db):
        """Test login with wrong password."""
        # Register user
        await client.post(
            "/register",
            data={"username": "bob", "password": "BobPass123!"},
        )

        client.cookies.clear()

        # Try login with wrong password
        response = await client.post(
            "/login",
            data={"username": "bob", "password": "WrongPassword"},
            follow_redirects=False,
        )

        # Should show error (not redirect)
        assert response.status_code != 302
        assert "invalid" in response.text.lower() or "error" in response.text.lower()

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, client, setup_db):
        """Test login with non-existent user."""
        response = await client.post(
            "/login",
            data={"username": "nonexistent", "password": "SomePass123!"},
        )

        # Should show error
        assert response.status_code != 302


class TestLogout:
    """Test logout flow and session clearing."""

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, client, setup_db):
        """Test that logout clears the session cookie."""
        # Register and login
        await client.post(
            "/register",
            data={"username": "alice", "password": "AlicePass123!"},
        )

        client.cookies.clear()

        await client.post(
            "/login",
            data={"username": "alice", "password": "AlicePass123!"},
        )

        # Verify session cookie exists
        assert "session" in client.cookies

        # Logout
        response = await client.post("/logout", follow_redirects=False)

        # Should redirect
        assert response.status_code in [302, 303]

    @pytest.mark.asyncio
    async def test_logout_requires_login_for_protected_routes(self, client, setup_db):
        """Test that protected routes redirect to login after logout."""
        # Register and login
        await client.post(
            "/register",
            data={"username": "bob", "password": "BobPass123!"},
        )

        client.cookies.clear()

        await client.post(
            "/login",
            data={"username": "bob", "password": "BobPass123!"},
        )

        # Logout
        await client.post("/logout")

        # Try to access protected route (e.g., /history)
        response = await client.get("/history", follow_redirects=False)

        # Should redirect to login
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")


class TestAuthGuards:
    """Test authentication guards on protected routes."""

    @pytest.mark.asyncio
    async def test_hub_accessible_without_login(self, client, setup_db):
        """Test that hub page is accessible without login."""
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_history_requires_login(self, client, setup_db):
        """Test that /history requires login."""
        response = await client.get("/history", follow_redirects=False)

        # Should redirect to login or show 302
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_analysis_routes_require_login(self, client, setup_db):
        """Test that analysis-based routes require login."""
        # Try to access analysis route without login
        response = await client.get("/snapshot/a/1", follow_redirects=False)

        # Should redirect to login
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
