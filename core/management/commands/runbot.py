"""Django management command to run the Telegram signal bot."""

import asyncio
import logging

from django.core.management.base import BaseCommand

from signals.listener import TelegramListener
from trading.manager import PositionManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start the Telegram signal listener and trade executor"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse signals but don't execute trades",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY RUN mode — no trades will be executed"))

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

        asyncio.run(self._run(dry_run))

    async def _run(self, dry_run: bool):
        listener = TelegramListener()
        manager = PositionManager()

        async def on_signal(parsed, message):
            logger.info(f"📊 New signal: {parsed.get('symbol')} {parsed.get('direction')}")
            if dry_run:
                logger.info(f"[DRY RUN] Would execute: {parsed}")
                return
            await manager.handle_new_signal(parsed, message)

        async def on_update(parsed, message):
            logger.info(f"📝 Signal update: {parsed.get('message_type')} for {parsed.get('symbol')}")
            if dry_run:
                logger.info(f"[DRY RUN] Would handle update: {parsed}")
                return
            await manager.handle_update(parsed, message)

        listener.on_signal(on_signal)
        listener.on_update(on_update)

        try:
            self.stdout.write(self.style.SUCCESS("🚀 Bitfa Trader bot starting..."))
            await listener.start()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹ Shutting down..."))
        finally:
            await listener.stop()
            await manager.close()
