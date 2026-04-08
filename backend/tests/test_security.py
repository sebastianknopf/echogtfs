"""
Unit tests for security module.

Tests password hashing, verification, and JWT token creation.
"""

import unittest
from datetime import timedelta

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from echogtfs.security import (
    create_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing(unittest.TestCase):
    """Test password hashing and verification."""
    
    def test_hash_password(self):
        """Test that password hashing produces a valid hash."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        # Hash should be a string
        self.assertIsInstance(hashed, str)
        
        # Hash should not be the plain password
        self.assertNotEqual(hashed, password)
        
        # Hash should be long enough (bcrypt produces ~60 char hashes)
        self.assertGreater(len(hashed), 50)
    
    def test_hash_password_different_for_same_input(self):
        """Test that hashing same password twice produces different hashes (due to salt)."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Different hashes due to different salts
        self.assertNotEqual(hash1, hash2)
    
    def test_verify_password_correct(self):
        """Test that correct password verifies successfully."""
        password = "my_secure_password"
        hashed = hash_password(password)
        
        result = verify_password(password, hashed)
        self.assertTrue(result)
    
    def test_verify_password_incorrect(self):
        """Test that incorrect password fails verification."""
        password = "my_secure_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        result = verify_password(wrong_password, hashed)
        self.assertFalse(result)
    
    def test_verify_password_empty_string(self):
        """Test that empty password is handled correctly."""
        password = "my_secure_password"
        hashed = hash_password(password)
        
        result = verify_password("", hashed)
        self.assertFalse(result)
    
    def test_verify_password_case_sensitive(self):
        """Test that password verification is case-sensitive."""
        password = "MyPassword123"
        hashed = hash_password(password)
        
        # Different case should fail
        self.assertFalse(verify_password("mypassword123", hashed))
        self.assertFalse(verify_password("MYPASSWORD123", hashed))
        
        # Exact match should succeed
        self.assertTrue(verify_password("MyPassword123", hashed))
    
    def test_hash_password_special_characters(self):
        """Test hashing passwords with special characters."""
        password = "P@$$w0rd!#%&*()_+-=[]{}|;:,.<>?"
        hashed = hash_password(password)
        
        # Should verify correctly
        self.assertTrue(verify_password(password, hashed))
    
    def test_hash_password_unicode(self):
        """Test hashing passwords with unicode characters."""
        password = "пароль密码🔒"
        hashed = hash_password(password)
        
        # Should verify correctly
        self.assertTrue(verify_password(password, hashed))


class TestJWT(unittest.TestCase):
    """Test JWT token creation and validation."""
    
    def test_create_access_token(self):
        """Test JWT token creation."""
        username = "testuser"
        token = create_access_token(username)
        
        # Token should be a string
        self.assertIsInstance(token, str)
        
        # Token should have three parts (header.payload.signature)
        parts = token.split(".")
        self.assertEqual(len(parts), 3)
    
    def test_create_access_token_with_custom_expiry(self):
        """Test JWT token creation with custom expiration."""
        username = "testuser"
        expires_delta = timedelta(hours=1)
        token = create_access_token(username, expires_delta=expires_delta)
        
        # Token should be created
        self.assertIsInstance(token, str)
        
        # Decode and verify expiration
        import jwt
        from echogtfs.config import settings
        
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], username)
        self.assertIn("exp", payload)
    
    def test_create_access_token_decode(self):
        """Test that created token can be decoded correctly."""
        import jwt
        from echogtfs.config import settings
        
        username = "testuser"
        token = create_access_token(username)
        
        # Decode token
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        
        # Verify subject
        self.assertEqual(payload["sub"], username)
        
        # Verify expiration exists
        self.assertIn("exp", payload)
    
    def test_create_access_token_different_users(self):
        """Test that different users get different tokens."""
        token1 = create_access_token("user1")
        token2 = create_access_token("user2")
        
        # Tokens should be different
        self.assertNotEqual(token1, token2)
        
        # Verify they decode to different subjects
        import jwt
        from echogtfs.config import settings
        
        payload1 = jwt.decode(token1, settings.secret_key, algorithms=[settings.algorithm])
        payload2 = jwt.decode(token2, settings.secret_key, algorithms=[settings.algorithm])
        
        self.assertEqual(payload1["sub"], "user1")
        self.assertEqual(payload2["sub"], "user2")
    
    def test_create_access_token_empty_subject(self):
        """Test token creation with empty subject."""
        token = create_access_token("")
        
        import jwt
        from echogtfs.config import settings
        
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], "")
    
    def test_create_access_token_special_characters(self):
        """Test token creation with special characters in subject."""
        username = "user@example.com"
        token = create_access_token(username)
        
        import jwt
        from echogtfs.config import settings
        
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], username)


class TestSecurityIntegration(unittest.TestCase):
    """Integration tests for security workflow."""
    
    def test_password_hash_and_verify_workflow(self):
        """Test complete workflow of hashing and verifying password."""
        # Simulate user registration
        plain_password = "user_password_123"
        hashed_password = hash_password(plain_password)
        
        # Store hashed_password in database (simulated)
        stored_hash = hashed_password
        
        # Simulate user login - correct password
        login_password = "user_password_123"
        is_valid = verify_password(login_password, stored_hash)
        self.assertTrue(is_valid)
        
        # Simulate user login - incorrect password
        wrong_password = "wrong_password"
        is_valid = verify_password(wrong_password, stored_hash)
        self.assertFalse(is_valid)
    
    def test_create_token_for_authenticated_user(self):
        """Test creating JWT token after successful authentication."""
        import jwt
        from echogtfs.config import settings
        
        # Simulate authentication
        username = "authenticated_user"
        password = "secure_password"
        hashed = hash_password(password)
        
        # Verify password
        if verify_password(password, hashed):
            # Create token for authenticated user
            token = create_access_token(username)
            
            # Verify token contains correct username
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            self.assertEqual(payload["sub"], username)


if __name__ == '__main__':
    unittest.main()
