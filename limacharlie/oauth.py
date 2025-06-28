import json
import webbrowser
import urllib.parse
import requests
import time
from typing import Dict, Optional, Tuple
import os
import sys

from .oauth_server import OAuthCallbackServer
from . import utils


class OAuthError(Exception):
    """OAuth-related errors."""
    pass


class OAuthManager:
    """Manages OAuth authentication flow for LimaCharlie CLI."""
    
    # Firebase configuration - these would be provided by LimaCharlie
    # Using placeholders that should be replaced with actual values
    FIREBASE_API_KEY = os.environ.get('LC_FIREBASE_API_KEY', 'YOUR_FIREBASE_WEB_API_KEY')
    FIREBASE_AUTH_DOMAIN = os.environ.get('LC_FIREBASE_AUTH_DOMAIN', 'your-project.firebaseapp.com')
    
    # OAuth endpoints
    GOOGLE_OAUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
    FIREBASE_TOKEN_EXCHANGE_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp'
    FIREBASE_REFRESH_URL = 'https://securetoken.googleapis.com/v1/token'
    
    def __init__(self):
        """Initialize OAuth manager."""
        self.callback_server = None
    
    def start_oauth_flow(self, no_browser: bool = False) -> Dict[str, str]:
        """
        Start the OAuth authentication flow.
        
        Args:
            no_browser: If True, print URL instead of opening browser
            
        Returns:
            Dictionary containing tokens and expiry information
            
        Raises:
            OAuthError: If authentication fails
        """
        # Start local callback server
        self.callback_server = OAuthCallbackServer()
        port = self.callback_server.start()
        redirect_uri = f'http://localhost:{port}'
        
        # Build OAuth URL
        auth_params = {
            'client_id': self._get_google_client_id(),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'consent'  # Ensure we get refresh token
        }
        
        auth_url = f"{self.GOOGLE_OAUTH_URL}?{urllib.parse.urlencode(auth_params)}"
        
        # Open browser or print URL
        if no_browser:
            print(f"\nPlease visit this URL to authenticate:\n{auth_url}\n")
        else:
            print(f"Opening browser for authentication...")
            if not webbrowser.open(auth_url):
                print(f"\nCould not open browser. Please visit this URL:\n{auth_url}\n")
        
        print("Waiting for authentication...")
        
        # Wait for callback
        success, auth_code, error = self.callback_server.wait_for_callback()
        self.callback_server.stop()
        
        if not success:
            raise OAuthError(f"Authentication failed: {error}")
        
        # Exchange authorization code for tokens
        tokens = self._exchange_code_for_tokens(auth_code, redirect_uri)
        
        return tokens
    
    def _get_google_client_id(self) -> str:
        """Get Google OAuth client ID from Firebase config."""
        # This would typically be fetched from Firebase config
        # For now, using environment variable or placeholder
        return os.environ.get('LC_GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com')
    
    def _exchange_code_for_tokens(self, auth_code: str, redirect_uri: str) -> Dict[str, str]:
        """
        Exchange authorization code for Firebase ID token and refresh token.
        
        Args:
            auth_code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in OAuth flow
            
        Returns:
            Dictionary with id_token, refresh_token, and expires_in
            
        Raises:
            OAuthError: If token exchange fails
        """
        # Exchange with Firebase
        payload = {
            'postBody': f'code={auth_code}&providerId=google.com&redirect_uri={redirect_uri}',
            'requestUri': redirect_uri,
            'returnIdpCredential': True,
            'returnSecureToken': True
        }
        
        try:
            response = requests.post(
                f"{self.FIREBASE_TOKEN_EXCHANGE_URL}?key={self.FIREBASE_API_KEY}",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Calculate expiry timestamp
            expires_in = int(data.get('expiresIn', '3600'))
            expires_at = int(time.time()) + expires_in
            
            return {
                'id_token': data['idToken'],
                'refresh_token': data['refreshToken'],
                'expires_at': expires_at,
                'provider': 'google'
            }
            
        except requests.exceptions.RequestException as e:
            raise OAuthError(f"Failed to exchange authorization code: {str(e)}")
        except (KeyError, ValueError) as e:
            raise OAuthError(f"Invalid response from token exchange: {str(e)}")
    
    @staticmethod
    def refresh_token(refresh_token: str) -> Dict[str, str]:
        """
        Refresh an expired ID token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            Dictionary with new id_token and expires_at
            
        Raises:
            OAuthError: If token refresh fails
        """
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        try:
            response = requests.post(
                f"{OAuthManager.FIREBASE_REFRESH_URL}?key={OAuthManager.FIREBASE_API_KEY}",
                data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Calculate new expiry
            expires_in = int(data.get('expires_in', '3600'))
            expires_at = int(time.time()) + expires_in
            
            return {
                'id_token': data['id_token'],
                'expires_at': expires_at
            }
            
        except requests.exceptions.RequestException as e:
            raise OAuthError(f"Failed to refresh token: {str(e)}")
        except (KeyError, ValueError) as e:
            raise OAuthError(f"Invalid response from token refresh: {str(e)}")
    
    @staticmethod
    def is_token_expired(expires_at: int) -> bool:
        """
        Check if a token is expired.
        
        Args:
            expires_at: Unix timestamp when token expires
            
        Returns:
            True if token is expired or will expire in next 5 minutes
        """
        # Add 5 minute buffer to refresh before actual expiry
        return int(time.time()) >= (expires_at - 300)
    
    @staticmethod
    def validate_oauth_config(config: Dict) -> bool:
        """
        Validate OAuth configuration.
        
        Args:
            config: OAuth configuration dictionary
            
        Returns:
            True if configuration is valid
        """
        required_fields = ['id_token', 'refresh_token', 'expires_at', 'provider']
        return all(field in config for field in required_fields)


def perform_oauth_login(oid: Optional[str] = None, 
                       environment: Optional[str] = None,
                       no_browser: bool = False) -> bool:
    """
    Perform OAuth login and save credentials.
    
    Args:
        oid: Organization ID (optional)
        environment: Environment name (optional)
        no_browser: If True, print URL instead of opening browser
        
    Returns:
        True if login successful
    """
    try:
        # Initialize OAuth manager
        oauth_mgr = OAuthManager()
        
        # Perform OAuth flow
        tokens = oauth_mgr.start_oauth_flow(no_browser=no_browser)
        
        # Load existing config
        config = utils.loadCredentials()
        if config is None:
            config = {}
        
        # Prepare OAuth data
        oauth_data = {
            'oauth': tokens
        }
        
        # Add OID if provided
        if oid:
            oauth_data['oid'] = oid
        
        # Save to appropriate location
        if environment:
            # Save to named environment
            if 'env' not in config:
                config['env'] = {}
            if environment not in config['env']:
                config['env'][environment] = {}
            config['env'][environment].update(oauth_data)
            print(f"\nOAuth credentials saved to environment: {environment}")
        else:
            # Save to default
            config.update(oauth_data)
            print("\nOAuth credentials saved as default")
        
        # Write config
        utils.writeCredentialsToConfig(
            config.get('oid'),
            config.get('api_key'),
            config.get('uid'),
            environment=environment,
            oauth_creds=oauth_data.get('oauth')
        )
        
        return True
        
    except OAuthError as e:
        print(f"\nOAuth login failed: {str(e)}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"\nUnexpected error during OAuth login: {str(e)}", file=sys.stderr)
        return False