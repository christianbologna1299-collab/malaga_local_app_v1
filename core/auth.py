"""
Authentication module for Banker Analytics.
Handles password hashing, user registration, login, and session management.
"""

import logging
import bcrypt
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string (bytes decoded to str)
    """
    # Limit password to 72 bytes (bcrypt limit)
    password_bytes = password[:72].encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: Plain text password from user
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        plain_bytes = plain_password[:72].encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False



def create_user(db, username: str, password: str) -> int | None:
    """
    Create a new user with bcrypt-hashed password.

    Args:
        db: Database connection object
        username: Username (must be unique)
        password: Plain text password

    Returns:
        User ID if successful, None if username already exists or error occurs
    """
    try:
        password_hash = hash_password(password)
        result = db.execute_query(
            """
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
            """,
            (username, password_hash),
        )
        # Get the inserted user_id
        user = db.execute_query(
            "SELECT id FROM users WHERE username = ?",
            (username,),
            fetch="one",
        )
        if user:
            logger.info(f"User created: {username}")
            return user["id"]
    except Exception as e:
        logger.error(f"Failed to create user {username}: {e}")
    return None


def authenticate_user(db, username: str, password: str) -> int | None:
    """
    Authenticate a user by username and password.

    Args:
        db: Database connection object
        username: Username
        password: Plain text password

    Returns:
        User ID if authentication successful, None otherwise
    """
    try:
        user = db.execute_query(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,),
            fetch="one",
        )

        if user and verify_password(password, user["password_hash"]):
            logger.info(f"User authenticated: {username}")
            return user["id"]
    except Exception as e:
        logger.error(f"Authentication error for {username}: {e}")

    logger.warning(f"Authentication failed: {username}")
    return None


def login_user(response: Response, user_id: int, username: str):
    """
    Set session cookie for a logged-in user.

    Args:
        response: Starlette Response object to set cookie on
        user_id: User ID from database
        username: Username for display
    """
    response.set_cookie(
        key="user_id",
        value=str(user_id),
        max_age=None,  # Session lifetime (no expiration)
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key="username",
        value=username,
        max_age=None,
        httponly=False,  # Allow access from JS for display
        samesite="lax",
    )
    logger.info(f"User logged in: {username} (ID: {user_id})")


def logout_user(response: Response):
    """
    Clear session cookies for a logged-out user.

    Args:
        response: Starlette Response object to clear cookies on
    """
    response.delete_cookie(key="user_id", samesite="lax")
    response.delete_cookie(key="username", samesite="lax")
    logger.info("User logged out")


def get_current_user(request: Request) -> dict | None:
    """
    Retrieve current user from session cookie.

    Args:
        request: Starlette Request object

    Returns:
        Dict with user_id and username if logged in, None otherwise
    """
    user_id = request.cookies.get("user_id")
    username = request.cookies.get("username")

    if user_id and username:
        try:
            return {
                "user_id": int(user_id),
                "username": username,
            }
        except ValueError:
            return None

    return None
