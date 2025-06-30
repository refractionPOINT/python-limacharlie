"""
OAuth utilities for token management.
"""

import time
import requests
from typing import Dict

from .constants import FIREBASE_API_KEY


class OAuthManager:
    """Utility class for OAuth token management."""
    
    # Firebase configuration
    FIREBASE_TOKEN_URL = 'https://securetoken.googleapis.com/v1/token'
    
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
    
    @staticmethod
    def refresh_token(refresh_token: str) -> Dict[str, str]:
        """
        Refresh Firebase OAuth tokens.
        
        Args:
            refresh_token: The refresh token from Firebase
            
        Returns:
            Dictionary with new tokens and expiry
            
        Raises:
            Exception: If token refresh fails
        """
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        try:
            response = requests.post(
                f"{OAuthManager.FIREBASE_TOKEN_URL}?key={FIREBASE_API_KEY}",
                data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code != 200:
                error_data = response.json()
                raise Exception(f"Token refresh failed: {error_data.get('error', {}).get('message', 'Unknown error')}")
            
            data = response.json()
            
            # Calculate new expiry timestamp
            expires_in = int(data.get('expires_in', '3600'))
            expires_at = int(time.time()) + expires_in
            
            return {
                'id_token': data['id_token'],
                'refresh_token': data['refresh_token'],
                'expires_at': expires_at
            }
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to refresh token: {str(e)}")