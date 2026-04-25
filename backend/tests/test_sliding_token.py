"""
Tests for sliding token (session renewal) functionality.

Ensures that authenticated requests automatically extend the session
by issuing a new token with extended expiration.
"""

import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from fastapi import Request, Response
from starlette.datastructures import Headers

# Set required env vars before importing settings
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-sliding-token-tests")

from echogtfs.config import settings
from echogtfs.main import SlidingTokenMiddleware
from echogtfs.models import User
from echogtfs.security import create_access_token


class TestSlidingToken(unittest.IsolatedAsyncioTestCase):
    """Test sliding token middleware functionality."""

    async def test_sliding_token_issued_on_authenticated_request(self):
        """Test that a new token is issued when user is authenticated."""
        # Create middleware instance
        middleware = SlidingTokenMiddleware(app=MagicMock())
        
        # Create mock request with authenticated user
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.__dict__ = {
            "user": User(
                id=1,
                username="testuser",
                email="test@example.com",
                hashed_password="hashed",
                is_active=True,
                is_superuser=False,
            )
        }
        
        # Create mock response (successful)
        response = Response(content=b'{"message": "success"}', status_code=200)
        
        # Mock call_next to return our response
        async def mock_call_next(req):
            return response
        
        # Call middleware
        result = await middleware.dispatch(request, mock_call_next)
        
        # Check that X-New-Token header is present
        self.assertIn("X-New-Token", result.headers)
        
        # Verify the new token is valid
        new_token = result.headers["X-New-Token"]
        payload = jwt.decode(new_token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], "testuser")
        
        # Verify token has a future expiration
        exp = datetime.fromtimestamp(payload["exp"], UTC)
        now = datetime.now(UTC)
        self.assertGreater(exp, now)

    async def test_no_token_issued_on_unauthenticated_request(self):
        """Test that no new token is issued for unauthenticated requests."""
        # Create middleware instance
        middleware = SlidingTokenMiddleware(app=MagicMock())
        
        # Create mock request WITHOUT authenticated user
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.__dict__ = {}
        
        # Create mock response (successful)
        response = Response(content=b'{"message": "public"}', status_code=200)
        
        # Mock call_next to return our response
        async def mock_call_next(req):
            return response
        
        # Call middleware
        result = await middleware.dispatch(request, mock_call_next)
        
        # Check that X-New-Token header is NOT present
        self.assertNotIn("X-New-Token", result.headers)

    async def test_no_token_issued_on_error_response(self):
        """Test that no new token is issued for error responses."""
        # Create middleware instance
        middleware = SlidingTokenMiddleware(app=MagicMock())
        
        # Create mock request with authenticated user
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.__dict__ = {
            "user": User(
                id=1,
                username="testuser",
                email="test@example.com",
                hashed_password="hashed",
                is_active=True,
                is_superuser=False,
            )
        }
        
        # Create mock response (error)
        response = Response(content=b'{"detail": "Not found"}', status_code=404)
        
        # Mock call_next to return our response
        async def mock_call_next(req):
            return response
        
        # Call middleware
        result = await middleware.dispatch(request, mock_call_next)
        
        # Check that X-New-Token header is NOT present (because of error response)
        self.assertNotIn("X-New-Token", result.headers)

    def test_token_expiration_uses_configured_value(self):
        """Test that new token uses configured expiration time."""
        # Create token with default expiration
        token = create_access_token("testuser")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        
        # Calculate expected expiration (should be ~30 minutes from now by default)
        exp = datetime.fromtimestamp(payload["exp"], UTC)
        now = datetime.now(UTC)
        expected_exp = now + timedelta(minutes=settings.access_token_expire_minutes)
        
        # Allow 5 second tolerance for test execution time
        self.assertAlmostEqual(
            exp.timestamp(), 
            expected_exp.timestamp(), 
            delta=5
        )


if __name__ == "__main__":
    unittest.main()
