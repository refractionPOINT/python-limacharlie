"""
Simplified OAuth token management for Firebase authentication.

This module handles the token lifecycle for the simplified Firebase auth flow:
- Checks token expiration with a safety buffer
- Refreshes expired tokens using Firebase's refresh endpoint
- Returns updated credentials for storage

The simplified approach means we only deal with Firebase tokens, not provider-specific
tokens, making the refresh logic much cleaner and more reliable.
"""

import time
from typing import Dict, Optional

from .oauth_firebase_simple import SimpleFirebaseAuth, FirebaseAuthError


class SimpleOAuthManager:
    """Manages OAuth tokens with automatic refresh for simplified Firebase auth."""
    
    def __init__(self):
        """Initialize the OAuth manager."""
        self.auth_client = SimpleFirebaseAuth()
    
    def ensure_valid_token(self, oauth_creds: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Ensure we have a valid (non-expired) ID token.
        
        Args:
            oauth_creds: Dictionary containing OAuth credentials
            
        Returns:
            Updated credentials with valid ID token, or None if refresh fails
        """
        if not oauth_creds:
            return None
        
        # Check if token is still valid (with 5 minute buffer)
        expires_at = oauth_creds.get('expires_at', 0)
        current_time = int(time.time())
        
        if current_time < (expires_at - 300):  # 5 minute buffer
            return oauth_creds
        
        # Token expired or about to expire, refresh it
        refresh_token = oauth_creds.get('refresh_token')
        if not refresh_token:
            print("No refresh token available")
            return None
        
        try:
            print("Refreshing expired OAuth token...")
            new_id_token, new_expires_at = self.auth_client.refresh_id_token(refresh_token)
            
            # Update credentials
            oauth_creds['id_token'] = new_id_token
            oauth_creds['expires_at'] = new_expires_at
            
            return oauth_creds
            
        except FirebaseAuthError as e:
            print(f"Failed to refresh OAuth token: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error refreshing token: {str(e)}")
            return None