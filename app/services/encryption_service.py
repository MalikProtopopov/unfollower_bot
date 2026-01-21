"""Encryption service for secure credential storage.

Uses Fernet symmetric encryption (AES-128-CBC) for encrypting
sensitive data like Instagram passwords.
"""

import base64
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.utils.logger import logger


class EncryptionError(Exception):
    """Encryption/decryption error."""
    pass


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""

    def __init__(self, secret_key: str | None = None):
        """Initialize encryption service.
        
        Args:
            secret_key: Secret key for encryption. If not provided,
                       uses ENCRYPTION_KEY environment variable.
        """
        self._secret_key = secret_key or os.getenv("ENCRYPTION_KEY")
        
        if not self._secret_key:
            # Generate a warning but don't fail - generate a key from app secret
            app_secret = os.getenv("SECRET_KEY", "default-secret-key-change-me")
            self._secret_key = app_secret
            logger.warning(
                "ENCRYPTION_KEY not set, using derived key from SECRET_KEY. "
                "Set ENCRYPTION_KEY in production for better security."
            )
        
        self._fernet = self._create_fernet(self._secret_key)

    def _create_fernet(self, secret_key: str) -> Fernet:
        """Create Fernet instance from secret key.
        
        Uses PBKDF2 to derive a proper encryption key from the secret.
        
        Args:
            secret_key: Secret key string.
            
        Returns:
            Fernet instance for encryption/decryption.
        """
        # Use PBKDF2 to derive a 32-byte key from the secret
        salt = b"instagram-session-refresh-salt"  # Static salt (could be made configurable)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        return Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt a string.
        
        Args:
            data: Plain text string to encrypt.
            
        Returns:
            Base64-encoded encrypted string.
            
        Raises:
            EncryptionError: If encryption fails.
        """
        if not data:
            return ""
        
        try:
            encrypted = self._fernet.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}")

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt an encrypted string.
        
        Args:
            encrypted_data: Base64-encoded encrypted string.
            
        Returns:
            Decrypted plain text string.
            
        Raises:
            EncryptionError: If decryption fails (invalid key or corrupted data).
        """
        if not encrypted_data:
            return ""
        
        try:
            decrypted = self._fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Decryption failed: invalid token (wrong key or corrupted data)")
            raise EncryptionError("Failed to decrypt: invalid key or corrupted data")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt data: {e}")

    def is_valid_encrypted(self, encrypted_data: str) -> bool:
        """Check if data can be decrypted.
        
        Args:
            encrypted_data: Encrypted string to validate.
            
        Returns:
            True if data can be decrypted, False otherwise.
        """
        try:
            self.decrypt(encrypted_data)
            return True
        except EncryptionError:
            return False


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get singleton encryption service instance.
    
    Returns:
        EncryptionService instance.
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_password(password: str) -> str:
    """Convenience function to encrypt a password.
    
    Args:
        password: Plain text password.
        
    Returns:
        Encrypted password string.
    """
    return get_encryption_service().encrypt(password)


def decrypt_password(encrypted_password: str) -> str:
    """Convenience function to decrypt a password.
    
    Args:
        encrypted_password: Encrypted password string.
        
    Returns:
        Plain text password.
    """
    return get_encryption_service().decrypt(encrypted_password)
