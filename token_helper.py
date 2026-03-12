#!/usr/bin/env python3
"""
Get Zerodha Access Token - Browser Edition
"""

import os
import webbrowser
import requests

API_KEY = "3v3h2zkvyqhn163b"
API_SECRET = "poy85dh2wxdg7c0q4q2z3fkb1a0alt4y"

print("=" * 60)
print("ZERODHA ACCESS TOKEN GENERATOR")
print("=" * 60)

# Generate login URL
login_url = f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3"

print(f"\n1. Click/copy this URL:\n")
print(login_url)
print("\n2. Login to Zerodha in the browser")
print("\n3. After login, you will be redirected to a page")
print("   The URL will look like:")
print("   http://localhost?request_token=XXXXXXXXXXXX")
print("\n4. Tell me the request_token from that URL")
print("=" * 60)

print("\nOr try this alternative:")
alt_url = f"https://kite.zerodha.com/connect/authorize?api_key={API_KEY}&v=3"
print(alt_url)
