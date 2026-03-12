#!/usr/bin/env python3
"""
Get Zerodha Access Token - with redirect handling
"""

import os
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

API_KEY = "3v3h2zkvyqhn163b"
API_SECRET = "poy85dh2wxdg7c0q4q2z3fkb1a0alt4y"

# Use a local server to capture the redirect
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.query:
            params = parse_qs(parsed.query)
            if 'request_token' in params:
                token = params['request_token'][0]
                print("\n" + "=" * 60)
                print(f"REQUEST TOKEN: {token}")
                print("=" * 60)
                print("\nNow run this to get access token:")
                print(f"python -c \"from kiteconnect import KiteConnect; k=KiteConnect('{API_KEY}'); print(k.generate_session('{token}', api_secret='{API_SECRET}')['access_token'])\"")
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Success! Check your terminal</h1>")
                return
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Waiting for authorization...</h1><p>Keep this window open</p>")

print("=" * 60)
print("ZERODHA ACCESS TOKEN")
print("=" * 60)

login_url = f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3&redirect_uri=http://localhost:7777"

print(f"\n1. Open this URL:\n{login_url}")
print("\n2. Login to Zerodha")
print("\n3. Authorize the app")
print("\n4. Wait for this page to show 'Success'")
print("\nStarting local server on port 7777...")

os.chdir('/tmp')
server = HTTPServer(('localhost', 7777), Handler)
server.handle_request()
