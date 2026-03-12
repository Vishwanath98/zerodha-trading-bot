import asyncio
from typing import Optional, Callable
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Message
from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()


class TelegramAdapter:
    """
    Telegram signal adapter using Telethon for user client.
    This can read from public channels/groups that the user is a member of.
    """
    
    def __init__(self, callback: Callable[[str, str], None]):
        self.callback = callback
        self.client: Optional[TelegramClient] = None
        self.api_id = settings.telegram_api_id
        self.api_hash = settings.telegram_api_hash
        self.session_string = settings.telegram_session_string
        self.channel_id = settings.telegram_channel_id
    
    async def start(self):
        """Start the Telegram client."""
        if not self.api_id or not self.api_hash:
            logger.error("Telegram API credentials not configured")
            return
        
        try:
            if self.session_string:
                self.client = TelegramClient(
                    StringSession(self.session_string),
                    self.api_id,
                    self.api_hash
                )
            else:
                self.client = TelegramClient(
                    'session',
                    self.api_id,
                    self.api_hash
                )
            
            await self.client.start()
            
            if not await self.client.is_user_authorized():
                logger.error("Telegram not authorized. Please run auth flow.")
                return
            
            logger.info("Telegram client started successfully")
            
            if self.channel_id:
                await self._listen_to_channel()
            else:
                await self._listen_to_messages()
                
        except Exception as e:
            logger.error(f"Telegram startup error: {e}")
    
    async def _listen_to_channel(self):
        """Listen to specific channel."""
        try:
            entity = await self.client.get_entity(self.channel_id)
            
            @self.client.on(events.NewMessage(chats=[entity]))
            async def handle_message(event: events.NewMessage):
                message = event.message
                if message.text:
                    await self._process_message(message)
            
            logger.info(f"Listening to channel: {self.channel_id}")
            
        except Exception as e:
            logger.error(f"Error listening to channel: {e}")
    
    async def _listen_to_messages(self):
        """Listen to all messages (for authorization)."""
        
        @self.client.on(events.NewMessage)
        async def handle_message(event: events.NewMessage):
            message = event.message
            if message.text and not message.out:
                await self._process_message(message)
        
        logger.info("Listening to all messages")
    
    async def _process_message(self, message: Message):
        """Process incoming message."""
        try:
            text = message.text.strip()
            
            if not text:
                return
            
            keywords = ['BUY', 'SELL', 'LELO', 'BECHO', 'NIFTY', 'BANKNIFTY', 'FINNIFTY', 'CE', 'PE']
            
            if any(kw.lower() in text.lower() for kw in keywords):
                source = f"telegram_{message.chat_id}"
                await self.callback(source, text)
                logger.info(f"Processed signal from Telegram: {text[:50]}...")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def stop(self):
        """Stop the Telegram client."""
        if self.client:
            await self.client.stop()
            logger.info("Telegram client stopped")


class TelegramBotAdapter:
    """
    Simple Telegram bot adapter using bot API.
    Limited: can only see messages in groups where it's admin with privacy disabled.
    """
    
    def __init__(self, callback: Callable[[str, str], None]):
        self.callback = callback
        self.bot_token = settings.telegram_bot_token
    
    async def start_webhook(self, webhook_url: str):
        """Set up webhook for bot."""
        if not self.bot_token:
            logger.error("Telegram bot token not configured")
            return
        
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
        
        application = Application.builder().token(self.bot_token).build()
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            text = update.message.text
            
            keywords = ['BUY', 'SELL', 'LELO', 'BECHO', 'NIFTY', 'BANKNIFTY', 'CE', 'PE']
            if any(kw.lower() in text.lower() for kw in keywords):
                source = f"telegram_bot_{update.effective_chat.id}"
                await self.callback(source, text)
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await application.run_webhook(webhook_url)
        logger.info(f"Bot webhook started at {webhook_url}")
    
    async def send_message(self, chat_id: str, text: str):
        """Send message via bot."""
        if not self.bot_token:
            return
        
        from telegram import Bot
        bot = Bot(token=self.bot_token)
        await bot.send_message(chat_id=chat_id, text=text)


class StringSession:
    """Simple string session handler for Telethon."""
    
    def __init__(self, session_string: str):
        self.session_string = session_string
    
    def save(self):
        return self.session_string


telegram_adapter = None
