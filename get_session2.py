#!/usr/bin/env python3
"""Simple script to get your Telegram session string."""

from telethon import TelegramClient
import asyncio

print("Telegram Session Generator")
print("=" * 40)
print("Enter your details when prompted...")
print()

api_id = 39624712
api_hash = "468a036a590c2a7ca055a647bd58a9fd"

async def main():
    client = TelegramClient("session_file", api_id, api_hash)
    await client.start()
    
    # Get session string
    session = client.session.save()
    print(f"\nTELEGRAM_SESSION_STRING={session}")
    
    await client.disconnect()

asyncio.run(main())
