#!/usr/bin/env python3
"""Get Telegram Session String - Run this, enter credentials, done."""

print("=" * 50)
print("TELEGRAM SESSION GENERATOR")
print("=" * 50)
print("""
Steps:
1. Go to https://my.telegram.org
2. Login with your phone
3. Click 'API Development tools'  
4. Create app (free):
   - App title: TradingBot
   - Short name: tradingbot
   - Platform: Desktop
5. Copy API ID and API Hash
""")

api_id = input("Enter API ID (from my.telegram.org): ").strip()
api_hash = input("Enter API Hash: ").strip()
phone = input("Enter phone (with country code, e.g., +91...): ").strip()

print("\nStarting authentication...")

from telethon import TelegramClient
import asyncio

async def main():
    client = TelegramClient(None, int(api_id), api_hash)
    
    await client.start(phone=phone)
    
    # Generate session string
    session_str = client.session.save()
    
    print("\n" + "=" * 50)
    print("SUCCESS! Copy this line to your .env file:")
    print("=" * 50)
    print(f"\nTELEGRAM_SESSION_STRING={session_str}")
    print(f"\nTELEGRAM_API_ID={api_id}")
    print(f"TELEGRAM_API_HASH={api_hash}")
    print("\n" + "=" * 50)
    
    await client.disconnect()

asyncio.run(main())
