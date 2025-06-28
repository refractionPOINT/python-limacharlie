import http.server
import socketserver
import threading
import urllib.parse
import socket
from typing import Optional, Tuple
import time
import queue


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler for OAuth callback requests."""
    
    def __init__(self, *args, callback_queue=None, **kwargs):
        self.callback_queue = callback_queue
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET request from OAuth provider redirect."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # Extract auth code or error
        if 'code' in params:
            if self.callback_queue:
                self.callback_queue.put({
                    'success': True,
                    'code': params['code'][0],
                    'error': None
                })
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            success_html = """
            <html>
            <head>
                <meta charset="UTF-8">
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
            self.wfile.write(success_html.encode('utf-8'))
            self.wfile.flush()
            
        elif 'error' in params:
            error_msg = params.get('error_description', ['Unknown error'])[0]
            if self.callback_queue:
                self.callback_queue.put({
                    'success': False,
                    'code': None,
                    'error': error_msg
                })
            
            # Send error response
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            error_html = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <title>LimaCharlie CLI - Authentication Failed</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #f44336; font-size: 24px; }}
                    .message {{ margin-top: 20px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="error">✗ Authentication Failed</div>
                <div class="message">Error: {error_msg}</div>
                <div class="message">Please return to the CLI and try again.</div>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode('utf-8'))
            self.wfile.flush()
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
        self.callback_queue = queue.Queue()
        self.server_thread = None
    
    def find_free_port(self) -> int:
        """Find a free port for the local server."""
        # Try preferred ports first (these should be whitelisted in Google OAuth)
        preferred_ports = [8085, 8086, 8087, 8088, 8089]
        
        for port in preferred_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    s.close()
                    return port
            except OSError:
                # Port is in use, try next one
                continue
        
        # If all preferred ports are taken, fall back to random port
        # (This will fail OAuth, but at least gives a clear error)
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
        
        # Create handler with callback queue reference
        handler = lambda *args, **kwargs: OAuthCallbackHandler(
            *args, 
            callback_queue=self.callback_queue, 
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
        
        while True:
            if time.time() - start_time > self.timeout:
                self.callback_queue.put({
                    'success': False,
                    'code': None,
                    'error': 'Authentication timeout'
                })
                break
            
            # Check if we have a callback result
            try:
                # Non-blocking check
                result = self.callback_queue.get_nowait()
                self.callback_queue.put(result)  # Put it back for wait_for_callback
                break
            except queue.Empty:
                pass
            
            # Handle one request with timeout
            self.server.handle_request()
    
    def wait_for_callback(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Wait for OAuth callback.
        
        Returns:
            Tuple of (success, auth_code, error_message)
        """
        try:
            # Wait for result with timeout
            result = self.callback_queue.get(timeout=self.timeout)
            
            # Wait a bit for the response to be sent
            time.sleep(0.5)
            
            return (
                result['success'],
                result.get('code'),
                result.get('error')
            )
        except queue.Empty:
            return (False, None, 'Authentication timeout')
    
    def stop(self):
        """Stop the OAuth callback server."""
        if self.server:
            # Set a flag to stop the server loop
            self.server.shutdown()
            self.server.server_close()
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2)