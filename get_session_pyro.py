#!/usr/bin/env python3
"""Get Telegram session using Pyrogram."""

from pyrogram import Client
import os

print("Telegram Session Generator (Pyrogram)")
print("=" * 40)

app = Client(
    "my_session",
    api_id=39624712,
    api_hash="468a036a590c2a7ca055a647bd58a9fd"
)

print("\nStarting... Enter phone when prompted.")
app.start()

session_string = app.export_session_string()
print(f"\nTELEGRAM_SESSION_STRING={session_string}")

app.stop()
