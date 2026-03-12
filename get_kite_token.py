#!/usr/bin/env python3
"""
Generate Zerodha Access Token
"""

from kiteconnect import KiteConnect

API_KEY = "3v3h2zkvyqhn163b"
API_SECRET = "poy85dh2wxdg7c0q4q2z3fkb1a0alt4y"

kite = KiteConnect(api_key=API_KEY)

print("=" * 50)
print("ZERODHA ACCESS TOKEN GENERATOR")
print("=" * 50)

request_token_url = kite.login_url()
print(f"\n1. Open this URL:\n")
print(request_token_url)
print("\n2. Login with Zerodha")
print("\n3. After login, you'll see a URL with 'request_token=' in it")
print("   Copy the request_token value from the URL")
print("\n4. Paste it below")

request_token = input("\nEnter request_token: ").strip()

try:
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = data["access_token"]
    
    print("\n" + "=" * 50)
    print("SUCCESS!")
    print("=" * 50)
    print(f"\nKITE_ACCESS_TOKEN={access_token}")
    print("\nCopy this to your .env file")
    
except Exception as e:
    print(f"Error: {e}")
