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
        
        # Validate CSRF state parameter if expected
        if hasattr(self.server, 'expected_state') and self.server.expected_state:
            if 'state' not in params:
                # Missing state parameter
                self.send_error_response("Missing state parameter - possible CSRF attack")
                if self.callback_queue:
                    self.callback_queue.put({
                        'success': False,
                        'path': self.path,
                        'error': 'Missing state parameter - possible CSRF attack'
                    })
                return
            
            received_state = params['state'][0] if params['state'] else None
            if received_state != self.server.expected_state:
                # Invalid state parameter
                self.send_error_response("Invalid state parameter - possible CSRF attack")
                if self.callback_queue:
                    self.callback_queue.put({
                        'success': False,
                        'path': self.path,
                        'error': 'Invalid state parameter - possible CSRF attack'
                    })
                return
        
        # Extract auth code or error
        if 'code' in params:
            if self.callback_queue:
                self.callback_queue.put({
                    'success': True,
                    'path': self.path,  # Return full path for parsing
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
                <title>LimaCharlie - Authentication Successful</title>
                <link rel="icon" type="image/png" href="data:image/png;base64,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">
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
                    
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }
                    
                    body {
                        font-family: 'Rubik', -apple-system, BlinkMacSystemFont, sans-serif;
                        background: #00030C;
                        color: #ffffff;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        background-image:
                            radial-gradient(circle at 20% 50%, rgba(74, 144, 226, 0.1) 0%, transparent 50%),
                            radial-gradient(circle at 80% 80%, rgba(226, 74, 144, 0.08) 0%, transparent 50%);
                    }
                    
                    .container {
                        text-align: center;
                        padding: 60px 40px;
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 16px;
                        backdrop-filter: blur(24px);
                        -webkit-backdrop-filter: blur(24px);
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                        max-width: 500px;
                        width: 90%;
                    }
                    
                    .logo {
                        max-width: 180px;
                        height: auto;
                        margin: 0 auto 40px;
                        display: block;
                        filter: drop-shadow(0 4px 12px rgba(74, 144, 226, 0.3));
                    }
                    
                    .success-icon {
                        width: 80px;
                        height: 80px;
                        margin: 0 auto 30px;
                        background: linear-gradient(135deg, #4A90E2 0%, #A74AE2 100%);
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 40px;
                        color: #ffffff;
                        font-weight: bold;
                        box-shadow: 0 4px 20px rgba(74, 144, 226, 0.4);
                    }
                    
                    .title {
                        font-size: 28px;
                        font-weight: 500;
                        margin-bottom: 16px;
                        color: #ffffff;
                    }
                    
                    .message {
                        font-size: 16px;
                        color: rgba(255, 255, 255, 0.7);
                        line-height: 1.6;
                        margin-bottom: 40px;
                    }
                    
                    .action {
                        display: inline-block;
                        padding: 12px 32px;
                        background: linear-gradient(135deg, #4A90E2 0%, #A74AE2 100%);
                        color: #ffffff;
                        text-decoration: none;
                        font-weight: 500;
                        font-size: 14px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        border-radius: 12px;
                        position: relative;
                        overflow: hidden;
                        transition: all 0.3s ease;
                    }

                    .action:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 6px 24px rgba(74, 144, 226, 0.5);
                    }
                    
                    .cli-hint {
                        margin-top: 40px;
                        padding: 16px;
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 8px;
                        font-family: 'IBM Plex Mono', 'Courier New', monospace;
                        font-size: 14px;
                        color: #4A90E2;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAiCAYAAAAZHFoXAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAALMSURBVHgBzZdNbtNAFMffcy0oElJ7hFgKC3Zhh0IiJSeAbqjChvQEbU9AOQHpCRoWKGk3wAkSqaHqrtkhFUJyhJYFCMn2MC/OQGpsz5sJdfKTLPljxv79PV82wIJUu6OjJ8fjl2BB+eSyVOl+69WOLjbBEgRL6KH+vY2e3C3RsUBsftr23nLrk7wj3B4IIPmh+/O63t95dAWGWAWIyyu4IWLyCqsQxgHS5BW6ECnyCuMQRgF08oq0EBp5hVEIdgCuvCIegimvYIdwgIGpPIGh76l9Q3miRM/jzE7aFrCRBxG8HjQeHNCuhfw82pbIDLBkeUVmiNQAKyKvSA2RGGDF5BWJIf4ZxHnIC4CJALHvC/Rok1NWHQXoFsDEgY15y0MYHg5eFPeSLtU640KAoicDFiCdGy2Bucojfhhse1tZt6QQviMuuIsd5iYvoe5y3vAmoKHSHbVk2l1NsWkIN8cBO+TIE65wWgEEQ105f32z5Er592CywgK2Tmfytc7ngs+dbUR4DUz6UdA2p6wTOrgvrdhffyGIZ4+lePSghxMMw4+siuhswC0wHQPlk7HsBoI9b9M0GIhf9XMZgI6rna9tgY7ur+xK9lmP84Em79eUgV/pygkR7EzXgbPn3jBErHNbQqYurOHdnmqJ00axiSLUzeOb/vr9PeAg5WkqzdoCEdI47P9ZyHIJgWu75XeXmeOtejx6k7kOSD/ZbbfOGsV2dBgjl+6E4sD98f1wvjtVOl9qMiB1mxpkyNNLppf991QCOY0Joj+TKGhW30T5Wd1kcgyhJ0U+upTBSoTIkI8ua1hqCI18VITBUkIw5AnWT73NFOvCnaY6Zq4T8zdgyUdFDeC2BMmSdPw8b4rly0fFDdGFSJNXZIYwlI+qWJAWQievSAxhIR9VsyQegiuvuBHCUj6qugAqBH1Sm8grpiEc56mt/H+B/mFhARat/xtQb49hx469swAAAABJRU5ErkJggg==" alt="LimaCharlie" class="logo">
                    <div class="success-icon">✓</div>
                    <h1 class="title">Authentication Successful</h1>
                    <p class="message">
                        You've been successfully authenticated with LimaCharlie CLI.<br>
                        Your credentials have been securely stored.
                    </p>
                    <div class="message" style="margin-bottom: 20px;">
                        You can safely close this browser window/tab.
                    </div>
                    <div class="cli-hint">Return to your terminal to continue</div>
                </div>
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
                    'path': self.path,
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
                <title>LimaCharlie - Authentication Error</title>
                <link rel="icon" type="image/png" href="data:image/png;base64,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">
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
                    
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    
                    body {{
                        font-family: 'Rubik', -apple-system, BlinkMacSystemFont, sans-serif;
                        background: #00030C;
                        color: #ffffff;
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        background-image:
                            radial-gradient(circle at 20% 50%, rgba(226, 74, 74, 0.1) 0%, transparent 50%),
                            radial-gradient(circle at 80% 80%, rgba(226, 74, 74, 0.08) 0%, transparent 50%);
                    }}

                    .container {{
                        text-align: center;
                        padding: 60px 40px;
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 16px;
                        backdrop-filter: blur(24px);
                        -webkit-backdrop-filter: blur(24px);
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                        max-width: 500px;
                        width: 90%;
                    }}

                    .logo {{
                        max-width: 150px;
                        height: auto;
                        margin: 0 auto 40px;
                        display: block;
                        filter: drop-shadow(0 4px 12px rgba(74, 144, 226, 0.3));
                    }}
                    
                    .error-icon {{
                        width: 80px;
                        height: 80px;
                        margin: 0 auto 30px;
                        background: linear-gradient(135deg, #E24A4A 0%, #F02463 100%);
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 40px;
                        color: #ffffff;
                        font-weight: bold;
                        box-shadow: 0 4px 20px rgba(226, 74, 74, 0.4);
                    }}
                    
                    .title {{
                        font-size: 28px;
                        font-weight: 500;
                        margin-bottom: 16px;
                        color: #ffffff;
                    }}
                    
                    .error-message {{
                        font-size: 16px;
                        color: #E24A4A;
                        margin-bottom: 16px;
                        padding: 12px 20px;
                        background: rgba(226, 74, 74, 0.1);
                        border: 1px solid rgba(226, 74, 74, 0.2);
                        border-radius: 8px;
                        font-family: 'IBM Plex Mono', 'Courier New', monospace;
                    }}
                    
                    .message {{
                        font-size: 16px;
                        color: rgba(255, 255, 255, 0.7);
                        line-height: 1.6;
                        margin-bottom: 40px;
                    }}
                    
                    .action {{
                        display: inline-block;
                        padding: 12px 32px;
                        background: rgba(255, 255, 255, 0.1);
                        color: #ffffff;
                        text-decoration: none;
                        font-weight: 500;
                        font-size: 14px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        border-radius: 4px;
                        transition: all 0.3s ease;
                    }}
                    
                    .action:hover {{
                        background: rgba(255, 255, 255, 0.15);
                        border-color: rgba(255, 255, 255, 0.3);
                        transform: translateY(-2px);
                    }}
                    
                    .cli-hint {{
                        margin-top: 40px;
                        padding: 16px;
                        background: rgba(255, 255, 255, 0.05);
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        border-radius: 8px;
                        font-family: 'IBM Plex Mono', 'Courier New', monospace;
                        font-size: 14px;
                        color: #4A90E2;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAiCAYAAAAZHFoXAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAALMSURBVHgBzZdNbtNAFMffcy0oElJ7hFgKC3Zhh0IiJSeAbqjChvQEbU9AOQHpCRoWKGk3wAkSqaHqrtkhFUJyhJYFCMn2MC/OQGpsz5sJdfKTLPljxv79PV82wIJUu6OjJ8fjl2BB+eSyVOl+69WOLjbBEgRL6KH+vY2e3C3RsUBsftr23nLrk7wj3B4IIPmh+/O63t95dAWGWAWIyyu4IWLyCqsQxgHS5BW6ECnyCuMQRgF08oq0EBp5hVEIdgCuvCIegimvYIdwgIGpPIGh76l9Q3miRM/jzE7aFrCRBxG8HjQeHNCuhfw82pbIDLBkeUVmiNQAKyKvSA2RGGDF5BWJIf4ZxHnIC4CJALHvC/Rok1NWHQXoFsDEgY15y0MYHg5eFPeSLtU640KAoicDFiCdGy2Bucojfhhse1tZt6QQviMuuIsd5iYvoe5y3vAmoKHSHbVk2l1NsWkIN8cBO+TIE65wWgEEQ105f32z5Er592CywgK2Tmfytc7ngs+dbUR4DUz6UdA2p6wTOrgvrdhffyGIZ4+lePSghxMMw4+siuhswC0wHQPlk7HsBoI9b9M0GIhf9XMZgI6rna9tgY7ur+xK9lmP84Em79eUgV/pygkR7EzXgbPn3jBErHNbQqYurOHdnmqJ00axiSLUzeOb/vr9PeAg5WkqzdoCEdI47P9ZyHIJgWu75XeXmeOtejx6k7kOSD/ZbbfOGsV2dBgjl+6E4sD98f1wvjtVOl9qMiB1mxpkyNNLppf991QCOY0Joj+TKGhW30T5Wd1kcgyhJ0U+upTBSoTIkI8ua1hqCI18VITBUkIw5AnWT73NFOvCnaY6Zq4T8zdgyUdFDeC2BMmSdPw8b4rly0fFDdGFSJNXZIYwlI+qWJAWQievSAxhIR9VsyQegiuvuBHCUj6qugAqBH1Sm8grpiEc56mt/H+B/mFhARat/xtQb49hx469swAAAABJRU5ErkJggg==" alt="LimaCharlie" class="logo">
                    <div class="error-icon">✕</div>
                    <h1 class="title">Authentication Failed</h1>
                    <div class="error-message">{error_msg}</div>
                    <p class="message">
                        The authentication process encountered an error.<br>
                        Please return to your terminal and try again.
                    </p>
                    <div class="message" style="margin-bottom: 20px;">
                        You can close this browser window/tab.
                    </div>
                    <div class="cli-hint">Run 'limacharlie login --oauth' to retry</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode('utf-8'))
            self.wfile.flush()
        else:
            # Handle other requests (like favicon.ico)
            if self.path == '/favicon.ico':
                self.send_response(204)  # No Content
                self.end_headers()
            else:
                # Invalid callback
                self.send_response(400)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Invalid OAuth callback")
    
    def send_error_response(self, error_msg: str):
        """Send an error response with the given message."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        error_html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>LimaCharlie - Security Error</title>
            <link rel="icon" type="image/png" href="data:image/png;base64,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">
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}

                body {{
                    font-family: 'Rubik', -apple-system, BlinkMacSystemFont, sans-serif;
                    background: #00030C;
                    color: #ffffff;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background-image:
                        radial-gradient(circle at 20% 50%, rgba(226, 74, 74, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 80%, rgba(226, 74, 74, 0.08) 0%, transparent 50%);
                }}

                .container {{
                    text-align: center;
                    padding: 60px 40px;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 16px;
                    backdrop-filter: blur(24px);
                    -webkit-backdrop-filter: blur(24px);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                    max-width: 500px;
                    width: 90%;
                }}

                .logo {{
                    max-width: 150px;
                    height: auto;
                    margin: 0 auto 40px;
                    display: block;
                    filter: drop-shadow(0 4px 12px rgba(74, 144, 226, 0.3));
                }}

                .error-icon {{
                    width: 80px;
                    height: 80px;
                    margin: 0 auto 30px;
                    background: linear-gradient(135deg, #E24A4A 0%, #F02463 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 40px;
                    color: #ffffff;
                    font-weight: bold;
                    box-shadow: 0 4px 20px rgba(240, 36, 99, 0.4);
                }}
                
                .title {{
                    font-size: 28px;
                    font-weight: 500;
                    margin-bottom: 16px;
                    color: #ffffff;
                }}
                
                .error-message {{
                    font-size: 16px;
                    color: #F02463;
                    margin-bottom: 16px;
                    padding: 12px 20px;
                    background: rgba(240, 36, 99, 0.1);
                    border: 1px solid rgba(240, 36, 99, 0.2);
                    border-radius: 8px;
                    font-family: 'Courier New', monospace;
                }}
                
                .message {{
                    font-size: 16px;
                    color: rgba(255, 255, 255, 0.7);
                    line-height: 1.6;
                    margin-bottom: 40px;
                }}
                
                .cli-hint {{
                    margin-top: 40px;
                    padding: 16px;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    font-family: 'IBM Plex Mono', 'Courier New', monospace;
                    font-size: 14px;
                    color: #4A90E2;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAiCAYAAAAZHFoXAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAALMSURBVHgBzZdNbtNAFMffcy0oElJ7hFgKC3Zhh0IiJSeAbqjChvQEbU9AOQHpCRoWKGk3wAkSqaHqrtkhFUJyhJYFCMn2MC/OQGpsz5sJdfKTLPljxv79PV82wIJUu6OjJ8fjl2BB+eSyVOl+69WOLjbBEgRL6KH+vY2e3C3RsUBsftr23nLrk7wj3B4IIPmh+/O63t95dAWGWAWIyyu4IWLyCqsQxgHS5BW6ECnyCuMQRgF08oq0EBp5hVEIdgCuvCIegimvYIdwgIGpPIGh76l9Q3miRM/jzE7aFrCRBxG8HjQeHNCuhfw82pbIDLBkeUVmiNQAKyKvSA2RGGDF5BWJIf4ZxHnIC4CJALHvC/Rok1NWHQXoFsDEgY15y0MYHg5eFPeSLtU640KAoicDFiCdGy2Bucojfhhse1tZt6QQviMuuIsd5iYvoe5y3vAmoKHSHbVk2l1NsWkIN8cBO+TIE65wWgEEQ105f32z5Er592CywgK2Tmfytc7ngs+dbUR4DUz6UdA2p6wTOrgvrdhffyGIZ4+lePSghxMMw4+siuhswC0wHQPlk7HsBoI9b9M0GIhf9XMZgI6rna9tgY7ur+xK9lmP84Em79eUgV/pygkR7EzXgbPn3jBErHNbQqYurOHdnmqJ00axiSLUzeOb/vr9PeAg5WkqzdoCEdI47P9ZyHIJgWu75XeXmeOtejx6k7kOSD/ZbbfOGsV2dBgjl+6E4sD98f1wvjtVOl9qMiB1mxpkyNNLppf991QCOY0Joj+TKGhW30T5Wd1kcgyhJ0U+upTBSoTIkI8ua1hqCI18VITBUkIw5AnWT73NFOvCnaY6Zq4T8zdgyUdFDeC2BMmSdPw8b4rly0fFDdGFSJNXZIYwlI+qWJAWQievSAxhIR9VsyQegiuvuBHCUj6qugAqBH1Sm8grpiEc56mt/H+B/mFhARat/xtQb49hx469swAAAABJRU5ErkJggg==" alt="LimaCharlie" class="logo">
                <div class="error-icon">✕</div>
                <h1 class="title">Authentication Failed</h1>
                <div class="error-message">{error_msg}</div>
                <p class="message">
                    The authentication process encountered an error.<br>
                    Please return to your terminal and try again.
                </p>
                <div class="message" style="margin-bottom: 20px;">
                    You can close this browser window/tab.
                </div>
                <div class="cli-hint">Run 'limacharlie login --oauth' to retry</div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(error_html.encode('utf-8'))
        self.wfile.flush()
    
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
        self.expected_state = None  # For CSRF validation
    
    def find_free_port(self) -> int:
        """Find a free port for the local server."""
        # Try preferred ports - kept to minimal set for easier OAuth configuration
        # These ports should be whitelisted in Microsoft OAuth app settings
        preferred_ports = [
            8085, 8086, 8087, 8088, 8089  # 5 ports only
        ]

        for port in preferred_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    s.close()
                    return port
            except OSError:
                # Port is in use, try next one
                continue

        # If all preferred ports are taken, provide helpful error
        raise RuntimeError(
            "All OAuth callback ports (8085-8089) are currently in use.\n"
            "Please free up one of these ports or close applications using them:\n"
            "  - Check with: lsof -i :8085-8089 (macOS/Linux) or netstat -ano | findstr \"808[5-9]\" (Windows)\n"
            "  - Then try the OAuth login again."
        )
    
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
        
        # Pass expected_state to the server if set
        if self.expected_state:
            self.server.expected_state = self.expected_state
        
        # Start server in separate thread
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        return self.port
    
    def _run_server(self):
        """Run the server until callback is received or timeout."""
        start_time = time.time()
        got_result = False
        
        while not got_result and self.server:
            if time.time() - start_time > self.timeout:
                self.callback_queue.put({
                    'success': False,
                    'path': None,
                    'error': 'Authentication timeout'
                })
                break
            
            # Check if we have a callback result
            try:
                # Non-blocking check
                result = self.callback_queue.get_nowait()
                self.callback_queue.put(result)  # Put it back for wait_for_callback
                got_result = True
                # Continue to handle a few more requests (like favicon)
                for _ in range(3):
                    try:
                        if self.server and self.server.handle_request() is False:
                            break
                    except:
                        break
                break
            except queue.Empty:
                pass
            
            # Handle one request with timeout
            try:
                if self.server:
                    self.server.handle_request()
            except:
                # Server was shut down
                break
        
    
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
                result.get('path'),  # Return path instead of code
                result.get('error')
            )
        except queue.Empty:
            return (False, None, 'Authentication timeout')
    
    def stop(self):
        """Stop the OAuth callback server."""
        if self.server:
            # Set server to None to signal the thread to stop
            server = self.server
            self.server = None
            
            # Shutdown must be called from a different thread
            shutdown_thread = threading.Thread(target=server.shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()
            shutdown_thread.join(timeout=1)
            
            try:
                server.server_close()
            except:
                pass
                
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=1)