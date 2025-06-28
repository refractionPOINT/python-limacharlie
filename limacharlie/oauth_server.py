import http.server
import socketserver
import threading
import urllib.parse
import socket
from typing import Optional, Tuple
import time


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler for OAuth callback requests."""
    
    def __init__(self, *args, callback_result=None, **kwargs):
        self.callback_result = callback_result
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET request from OAuth provider redirect."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # Extract auth code or error
        if 'code' in params:
            self.callback_result['code'] = params['code'][0]
            self.callback_result['success'] = True
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            success_html = """
            <html>
            <head>
                <title>LimaCharlie CLI - Authentication Successful</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .success { color: #4CAF50; font-size: 24px; }
                    .message { margin-top: 20px; color: #666; }
                </style>
            </head>
            <body>
                <div class="success">✓ Authentication Successful!</div>
                <div class="message">You can now close this window and return to the CLI.</div>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())
            
        elif 'error' in params:
            self.callback_result['error'] = params.get('error_description', ['Unknown error'])[0]
            self.callback_result['success'] = False
            
            # Send error response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            error_html = f"""
            <html>
            <head>
                <title>LimaCharlie CLI - Authentication Failed</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #f44336; font-size: 24px; }}
                    .message {{ margin-top: 20px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="error">✗ Authentication Failed</div>
                <div class="message">Error: {self.callback_result['error']}</div>
                <div class="message">Please return to the CLI and try again.</div>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
        else:
            # Invalid callback
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Invalid OAuth callback")
    
    def log_message(self, format, *args):
        """Suppress log messages."""
        pass


class OAuthCallbackServer:
    """Local HTTP server for handling OAuth callbacks."""
    
    def __init__(self, timeout: int = 300):
        """
        Initialize OAuth callback server.
        
        Args:
            timeout: Maximum time to wait for callback (seconds)
        """
        self.timeout = timeout
        self.port = None
        self.server = None
        self.callback_result = {'success': False, 'code': None, 'error': None}
        self.server_thread = None
    
    def find_free_port(self) -> int:
        """Find a free port for the local server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def start(self) -> int:
        """
        Start the OAuth callback server.
        
        Returns:
            The port number the server is listening on
        """
        self.port = self.find_free_port()
        
        # Create handler with callback result reference
        handler = lambda *args, **kwargs: OAuthCallbackHandler(
            *args, 
            callback_result=self.callback_result, 
            **kwargs
        )
        
        self.server = socketserver.TCPServer(('localhost', self.port), handler)
        self.server.timeout = 1  # Check for shutdown every second
        
        # Start server in separate thread
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        return self.port
    
    def _run_server(self):
        """Run the server until callback is received or timeout."""
        start_time = time.time()
        
        while not self.callback_result['success'] and not self.callback_result['error']:
            if time.time() - start_time > self.timeout:
                self.callback_result['error'] = 'Authentication timeout'
                break
            
            self.server.handle_request()
        
        # Handle one more request to send the response
        if self.callback_result['success'] or self.callback_result['error']:
            self.server.handle_request()
    
    def wait_for_callback(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Wait for OAuth callback.
        
        Returns:
            Tuple of (success, auth_code, error_message)
        """
        if self.server_thread:
            self.server_thread.join(timeout=self.timeout + 5)
        
        return (
            self.callback_result['success'],
            self.callback_result.get('code'),
            self.callback_result.get('error')
        )
    
    def stop(self):
        """Stop the OAuth callback server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()