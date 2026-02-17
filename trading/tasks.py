"""Celery tasks for trade monitoring and order sync."""

import asyncio
import logging

from celery import shared_task
from django.utils import timezone

from trading.models import Position, Order, PositionStatus, OrderStatus
from trading.lbank import LBankFuturesClient

logger = logging.getLogger(__name__)


@shared_task
def sync_order_status():
    """Check and sync order statuses from LBank.

    Runs periodically to update pending/submitted orders
    with their actual fill status on the exchange.
    """
    asyncio.run(_sync_orders())


async def _sync_orders():
    client = LBankFuturesClient()
    try:
        pending_orders = Order.objects.filter(
            status__in=[OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
        ).select_related("position")

        async for order in pending_orders:
            try:
                result = await client.get_order(
                    order.position.symbol,
                    order.lbank_order_id,
                )
                data = result.get("data", {})
                exchange_status = data.get("status", "")

                if exchange_status in ("filled", "completed"):
                    order.status = OrderStatus.FILLED
                    order.filled_quantity = order.quantity
                    order.filled_price = data.get("avgPrice", order.price)
                    await order.asave()

                    # Update position
                    position = order.position
                    if position.status == PositionStatus.PENDING:
                        position.status = PositionStatus.OPEN
                        position.entry_price = order.filled_price
                        position.opened_at = timezone.now()
                        await position.asave()

                    logger.info(f"Order {order.lbank_order_id} filled @ {order.filled_price}")

                elif exchange_status == "cancelled":
                    order.status = OrderStatus.CANCELLED
                    await order.asave()
                    logger.info(f"Order {order.lbank_order_id} was cancelled")

            except Exception as e:
                logger.error(f"Error syncing order {order.lbank_order_id}: {e}")

    finally:
        await client.close()


@shared_task
def sync_positions_pnl():
    """Sync unrealized PnL from exchange for open positions."""
    asyncio.run(_sync_pnl())


async def _sync_pnl():
    client = LBankFuturesClient()
    try:
        open_positions = Position.objects.filter(
            status__in=[PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]
        )

        async for position in open_positions:
            try:
                result = await client.get_positions(position.symbol)
                positions_data = result.get("data", [])

                if not positions_data:
                    continue

                for pos_data in positions_data:
                    if pos_data.get("side", "").lower() == position.side:
                        position.unrealized_pnl = pos_data.get("unrealizedPnl", 0)
                        await position.asave()
                        break

            except Exception as e:
                logger.error(f"Error syncing PnL for {position.symbol}: {e}")

    finally:
        await client.close()
