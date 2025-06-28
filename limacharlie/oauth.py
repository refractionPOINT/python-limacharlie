"""
OAuth utilities for token management.
"""

import time


class OAuthManager:
    """Utility class for OAuth token management."""
    
    @staticmethod
    def is_token_expired(expires_at: int) -> bool:
        """
        Check if a token has expired.
        
        Args:
            expires_at: Unix timestamp when token expires
            
        Returns:
            True if token is expired, False otherwise
        """
        if not expires_at:
            return True
        
        # Add a 5-minute buffer to refresh tokens before they expire
        buffer_seconds = 300
        current_time = int(time.time())
        
        return current_time >= (expires_at - buffer_seconds)