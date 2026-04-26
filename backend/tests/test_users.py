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

from echogtfs.models import User
from echogtfs.routers.users import change_own_password
from echogtfs.schemas import PasswordChange
from echogtfs.security import hash_password


class TestPasswordChange(unittest.TestCase):
    """Test password change endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = AsyncMock()
        
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
            result = await change_own_password(payload, self.test_user, self.mock_db)
            
            # Should return None (204 No Content)
            self.assertIsNone(result)
            
            # Database commit should be called
            self.mock_db.commit.assert_awaited_once()
            
            # Verify the hashed password was updated
            self.assertNotEqual(self.test_user.hashed_password, hash_password(self.test_password))
        
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
                await change_own_password(payload, self.test_user, self.mock_db)
            
            self.assertEqual(context.exception.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(context.exception.detail, "Current password is incorrect")
            
            # Database commit should NOT be called
            self.mock_db.commit.assert_not_awaited()
        
        asyncio.run(run_test())
    
    def test_change_password_same_as_current(self):
        """Test that user can set the same password (edge case, but should work)."""
        async def run_test():
            payload = PasswordChange(
                current_password=self.test_password,
                new_password=self.test_password
            )
            
            # Execute the password change
            result = await change_own_password(payload, self.test_user, self.mock_db)
            
            # Should succeed
            self.assertIsNone(result)
            self.mock_db.commit.assert_awaited_once()
        
        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
