"""Telegram channel listener using Telethon.

Listens to a private signal channel and dispatches messages
for parsing and execution.
"""

import asyncio
import logging

from django.conf import settings
from telethon import TelegramClient, events

from signals.parser import SignalParser

logger = logging.getLogger(__name__)


class TelegramListener:
    """Listens to the BITFA signal channel and processes messages."""

    def __init__(self):
        self.api_id = int(settings.TELEGRAM_API_ID)
        self.api_hash = settings.TELEGRAM_API_HASH
        self.phone = settings.TELEGRAM_PHONE
        self.channel_id = int(settings.SIGNAL_CHANNEL_ID) if settings.SIGNAL_CHANNEL_ID else None
        self.parser = SignalParser(api_key=settings.GROQ_API_KEY)
        self.client: TelegramClient | None = None
        self._on_signal_callback = None
        self._on_update_callback = None

    def on_signal(self, callback):
        """Register callback for new signals: callback(parsed_data, message)."""
        self._on_signal_callback = callback

    def on_update(self, callback):
        """Register callback for signal updates: callback(parsed_data, message)."""
        self._on_update_callback = callback

    async def start(self):
        """Start the Telegram client and begin listening."""
        self.client = TelegramClient(
            "/app/bitfa_session",
            self.api_id,
            self.api_hash,
        )
        await self.client.start(phone=self.phone)
        logger.info("Telegram client started")

        # Resolve channel
        if self.channel_id:
            try:
                entity = await self.client.get_entity(self.channel_id)
                logger.info(f"Listening to channel: {entity.title}")
            except Exception as e:
                logger.error(f"Could not resolve channel {self.channel_id}: {e}")
                return

        @self.client.on(events.NewMessage(chats=self.channel_id))
        async def handler(event):
            await self._handle_message(event)

        logger.info("Listener registered, waiting for signals...")
        await self.client.run_until_disconnected()

    async def _handle_message(self, event):
        """Process an incoming channel message."""
        message = event.message
        text = message.text or ""

        if not text.strip():
            logger.debug("Empty message, skipping")
            return

        logger.info(f"New message [{message.id}]: {text[:100]}...")

        # Parse the signal
        parsed = await self.parser.parse(text)

        if not parsed:
            logger.debug(f"Message {message.id} is not a trading signal")
            return

        msg_type = parsed.get("message_type", "")
        logger.info(f"Parsed as {msg_type}: {parsed.get('symbol', 'unknown')}")

        # Dispatch based on type
        if msg_type == "new_signal" and self._on_signal_callback:
            await self._on_signal_callback(parsed, message)
        elif msg_type != "info" and self._on_update_callback:
            await self._on_update_callback(parsed, message)

    async def stop(self):
        """Disconnect the Telegram client."""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client disconnected")
