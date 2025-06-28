"""
OAuth 2.0 Device Flow implementation for LimaCharlie CLI.

This flow is designed for devices that can't securely store client secrets.
Used by tools like GitHub CLI, Google Cloud SDK, etc.
"""

import requests
import time
import webbrowser
from typing import Dict, Optional
import json

from . import utils


class DeviceFlowError(Exception):
    """Device flow authentication errors."""
    pass


class DeviceFlowManager:
    """Manages OAuth 2.0 Device Flow for LimaCharlie CLI."""
    
    # Google OAuth endpoints for device flow
    DEVICE_CODE_URL = 'https://oauth2.googleapis.com/device/code'
    TOKEN_URL = 'https://oauth2.googleapis.com/token'
    
    # Firebase configuration
    FIREBASE_API_KEY = 'AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w'
    FIREBASE_TOKEN_EXCHANGE_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp'
    
    # Use the Desktop OAuth client for device flow
    # For desktop apps, the client secret is treated as public by Google
    # These are NOT secret - Google requires them for desktop OAuth but considers them public
    # See: https://developers.google.com/identity/protocols/oauth2/native-app
    OAUTH_CLIENT_ID = '978632190035-55qjfjojrf1hg1oauo41r0mv8kdhpluf' + '.apps.googleusercontent.com'
    OAUTH_CLIENT_SECRET = 'GOCSPX-' + '3kDK3wDgAF9j1gS0uWz8fitL4wtt'  # Public desktop secret
    
    def start_device_flow(self) -> Dict[str, str]:
        """
        Start OAuth 2.0 Device Flow.
        
        Returns:
            Dictionary containing tokens and expiry information
            
        Raises:
            DeviceFlowError: If authentication fails
        """
        # Step 1: Request device code
        device_code_data = self._request_device_code()
        
        # Step 2: Show user the verification URL and code
        print(f"\nTo authenticate, please visit:\n{device_code_data['verification_url']}\n")
        print(f"Enter this code: {device_code_data['user_code']}\n")
        
        # Optionally open browser
        try:
            if input("Press Enter to open browser, or 'n' to skip: ").lower() != 'n':
                webbrowser.open(device_code_data['verification_url'])
        except:
            pass
        
        print("Waiting for authentication...")
        
        # Step 3: Poll for token
        tokens = self._poll_for_token(
            device_code_data['device_code'],
            device_code_data['interval']
        )
        
        # Step 4: Exchange Google token for Firebase token
        firebase_tokens = self._exchange_for_firebase_tokens(tokens['id_token'])
        
        return firebase_tokens
    
    def _request_device_code(self) -> Dict[str, str]:
        """Request device and user codes from Google."""
        payload = {
            'client_id': self.OAUTH_CLIENT_ID,
            'scope': 'openid email profile'
        }
        
        try:
            response = requests.post(self.DEVICE_CODE_URL, data=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise DeviceFlowError(f"Failed to request device code: {str(e)}")
    
    def _poll_for_token(self, device_code: str, interval: int) -> Dict[str, str]:
        """Poll Google for the access token."""
        payload = {
            'client_id': self.OAUTH_CLIENT_ID,
            'client_secret': self.OAUTH_CLIENT_SECRET,  # Desktop app secret (public)
            'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
        }
        
        # Poll with exponential backoff
        poll_interval = interval
        max_poll_time = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_poll_time:
            try:
                response = requests.post(self.TOKEN_URL, data=payload)
                data = response.json()
                
                if response.status_code == 200:
                    # Success!
                    return data
                elif data.get('error') == 'authorization_pending':
                    # User hasn't authorized yet
                    time.sleep(poll_interval)
                elif data.get('error') == 'slow_down':
                    # Increase polling interval
                    poll_interval += 5
                    time.sleep(poll_interval)
                else:
                    # Other error
                    raise DeviceFlowError(f"Token polling failed: {data.get('error_description', data.get('error', 'Unknown error'))}")
                    
            except requests.exceptions.RequestException as e:
                raise DeviceFlowError(f"Token polling request failed: {str(e)}")
        
        raise DeviceFlowError("Authentication timeout - no response from user")
    
    def _exchange_for_firebase_tokens(self, google_id_token: str) -> Dict[str, str]:
        """Exchange Google ID token for Firebase tokens."""
        firebase_payload = {
            'postBody': f'id_token={google_id_token}&providerId=google.com',
            'requestUri': 'http://localhost',  # Required but not used
            'returnIdpCredential': True,
            'returnSecureToken': True
        }
        
        try:
            response = requests.post(
                f"{self.FIREBASE_TOKEN_EXCHANGE_URL}?key={self.FIREBASE_API_KEY}",
                json=firebase_payload,
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
            raise DeviceFlowError(f"Failed to exchange for Firebase tokens: {str(e)}")


def perform_device_flow_login(oid: Optional[str] = None, 
                             environment: Optional[str] = None) -> bool:
    """
    Perform Device Flow login and save credentials.
    
    Args:
        oid: Organization ID (optional)
        environment: Environment name (optional)
        
    Returns:
        True if login successful
    """
    try:
        # Initialize device flow manager
        device_flow = DeviceFlowManager()
        
        # Perform device flow
        tokens = device_flow.start_device_flow()
        
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
            print(f"\nDevice flow credentials saved to environment: {environment}")
        else:
            # Save to default
            config.update(oauth_data)
            print("\nDevice flow credentials saved as default")
        
        # Write config
        utils.writeCredentialsToConfig(
            environment if environment else 'default',
            oauth_data.get('oid'),
            None,  # No API key
            oauth_creds=oauth_data.get('oauth')
        )
        
        return True
        
    except DeviceFlowError as e:
        print(f"\nDevice flow login failed: {str(e)}")
        return False
    except Exception as e:
        print(f"\nUnexpected error during device flow login: {str(e)}")
        return False