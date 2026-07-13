"""
Unit tests for users router endpoints.

Tests user password change functionality.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from fastapi import HTTPException, status

from echogtfs.services.database.models import User
from echogtfs.routers.users import change_own_password
from echogtfs.validation.schemas import PasswordChange
from echogtfs.security import hash_password, verify_password


class TestPasswordChange(unittest.TestCase):
    """Test password change endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_repository = AsyncMock()
        
        # Create a test user with a known hashed password
        self.test_password = "current_password_123"
        self.test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password(self.test_password),
            is_active=True,
            is_superuser=False,
            is_technical_contact=False,
        )
    
    def test_change_password_success(self):
        """Test successful password change with correct current password."""
        async def run_test():
            payload = PasswordChange(
                current_password=self.test_password,
                new_password="new_secure_password_456"
            )
            
            # Execute the password change
            result = await change_own_password(payload, self.test_user, self.mock_repository)
            
            # Should return None (204 No Content)
            self.assertIsNone(result)
            
            # Repository update should be called with a new hash for the new password
            self.mock_repository.update_user.assert_awaited_once()
            call_kwargs = self.mock_repository.update_user.await_args.kwargs
            self.assertNotEqual(call_kwargs["hashed_password"], self.test_user.hashed_password)
            self.assertTrue(verify_password(payload.new_password, call_kwargs["hashed_password"]))
        
        asyncio.run(run_test())
    
    def test_change_password_wrong_current_password(self):
        """Test password change fails with incorrect current password."""
        async def run_test():
            payload = PasswordChange(
                current_password="wrong_password",
                new_password="new_secure_password_456"
            )
            
            # Should raise 401 Unauthorized
            with self.assertRaises(HTTPException) as context:
                await change_own_password(payload, self.test_user, self.mock_repository)
            
            self.assertEqual(context.exception.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(context.exception.detail, "Current password is incorrect")
            
            # Repository update should NOT be called
            self.mock_repository.update_user.assert_not_awaited()
        
        asyncio.run(run_test())
    
    def test_change_password_same_as_current(self):
        """Test that user can set the same password (edge case, but should work)."""
        async def run_test():
            payload = PasswordChange(
                current_password=self.test_password,
                new_password=self.test_password
            )
            
            # Execute the password change
            result = await change_own_password(payload, self.test_user, self.mock_repository)
            
            # Should succeed
            self.assertIsNone(result)
            self.mock_repository.update_user.assert_awaited_once()
        
        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
