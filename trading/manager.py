"""Position manager — orchestrates signal execution on LBank.

This is the brain of the bot. It receives parsed signals and updates,
then decides what trades to place/modify/close.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from signals.models import Signal, SignalUpdate, SignalDirection, SignalStatus, UpdateType
from trading.models import Position, Order, PositionStatus, OrderSide, OrderStatus
from trading.lbank import LBankFuturesClient

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages the lifecycle of positions based on signals."""

    def __init__(self):
        self.client = LBankFuturesClient()

    async def close(self):
        await self.client.close()

    # ── Signal Handlers ──────────────────────────────────────

    async def handle_new_signal(self, parsed: dict, telegram_msg) -> Signal | None:
        """Process a new trading signal.

        1. Save signal to DB
        2. Calculate position size based on risk %
        3. Set leverage and margin type
        4. Place limit order at entry price
        5. Set stop loss
        """
        symbol_raw = parsed.get("symbol", "")
        direction = parsed.get("direction", "")
        entry_low = parsed.get("entry_price_low")
        entry_high = parsed.get("entry_price_high")
        stop_loss = parsed.get("stop_loss")
        take_profits = parsed.get("take_profits", [])
        risk_pct = parsed.get("risk_percent", settings.DEFAULT_RISK_PERCENT)
        leverage = parsed.get("leverage", 8)
        margin_type = parsed.get("margin_type", "isolated")

        if not all([symbol_raw, direction, entry_low, stop_loss]):
            logger.warning(f"Incomplete signal: {parsed}")
            return None

        # Normalize symbol: "ETH/USDT" → "ETHUSDT"
        symbol = symbol_raw.replace("/", "").upper()

        # Check max open positions
        open_count = await Position.objects.filter(
            status__in=[PositionStatus.OPEN, PositionStatus.PENDING]
        ).acount()
        if open_count >= settings.MAX_OPEN_POSITIONS:
            logger.warning(f"Max positions ({settings.MAX_OPEN_POSITIONS}) reached, skipping")
            return None

        # Save signal to DB
        signal = await Signal.objects.acreate(
            telegram_msg_id=telegram_msg.id,
            telegram_channel_id=telegram_msg.chat_id,
            raw_text=telegram_msg.text or "",
            symbol=symbol_raw,
            direction=SignalDirection.LONG if direction == "long" else SignalDirection.SHORT,
            entry_price_low=Decimal(str(entry_low)),
            entry_price_high=Decimal(str(entry_high)) if entry_high else None,
            stop_loss=Decimal(str(stop_loss)),
            tp1=Decimal(str(take_profits[0])) if len(take_profits) > 0 else None,
            tp2=Decimal(str(take_profits[1])) if len(take_profits) > 1 else None,
            tp3=Decimal(str(take_profits[2])) if len(take_profits) > 2 else None,
            risk_percent=Decimal(str(risk_pct)),
            leverage=leverage,
            margin_type=margin_type,
            status=SignalStatus.NEW,
            confidence=parsed.get("confidence", 0.0),
        )
        logger.info(f"Signal saved: {signal}")

        try:
            # Configure leverage and margin type on exchange
            await self.client.set_leverage(symbol, leverage)
            await self.client.set_margin_type(symbol, margin_type)

            # Calculate position size
            account = await self.client.get_account()
            balance = Decimal(str(account.get("data", {}).get("availableBalance", "0")))
            risk_amount = balance * Decimal(str(risk_pct)) / Decimal("100")

            entry_price = Decimal(str(entry_low))
            sl_price = Decimal(str(stop_loss))
            sl_distance = abs(entry_price - sl_price)

            if sl_distance == 0:
                logger.error("SL distance is 0, cannot calculate position size")
                return signal

            # Position size = risk_amount * leverage / sl_distance
            position_size = (risk_amount * Decimal(str(leverage))) / sl_distance

            # Determine order side
            if direction == "long":
                order_side = OrderSide.OPEN_LONG
            else:
                order_side = OrderSide.OPEN_SHORT

            # Place limit order at entry price
            result = await self.client.place_order(
                symbol=symbol,
                side=order_side,
                volume=str(round(position_size, 4)),
                price=str(entry_low),
                order_type="limit",
            )

            order_id = result.get("data", {}).get("orderId", "")

            # Create position record
            position = await Position.objects.acreate(
                signal=signal,
                symbol=symbol,
                side=direction,
                leverage=leverage,
                margin_type=margin_type,
                quantity=position_size,
                remaining_quantity=position_size,
                current_stop_loss=sl_price,
                status=PositionStatus.PENDING,
            )

            # Create order record
            await Order.objects.acreate(
                position=position,
                lbank_order_id=order_id,
                side=order_side,
                order_type="limit",
                price=entry_price,
                quantity=position_size,
                status=OrderStatus.SUBMITTED,
            )

            # Set stop loss on exchange
            await self.client.set_stop_loss(symbol, direction, str(stop_loss))

            signal.status = SignalStatus.ACTIVE
            await signal.asave()

            logger.info(f"Position opened: {position}, order: {order_id}")
            return signal

        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            signal.status = SignalStatus.CANCELLED
            await signal.asave()
            return signal

    async def handle_update(self, parsed: dict, telegram_msg) -> None:
        """Process a signal update (TP hit, SL move, close, etc.)."""
        msg_type = parsed.get("message_type", "")
        symbol_raw = parsed.get("symbol", "")
        symbol = symbol_raw.replace("/", "").upper() if symbol_raw else None

        # Find the related signal
        signal = await self._find_active_signal(symbol)
        if not signal:
            logger.warning(f"No active signal found for {symbol}, ignoring update")
            return

        # Map message type to handler
        handlers = {
            "entry_hit": self._handle_entry_hit,
            "tp_hit": self._handle_tp_hit,
            "risk_free": self._handle_risk_free,
            "partial_close": self._handle_partial_close,
            "full_close": self._handle_full_close,
            "position_closed": self._handle_full_close,
            "sl_modified": self._handle_sl_modified,
        }

        handler = handlers.get(msg_type)
        if handler:
            # Save update record
            update_type_map = {
                "entry_hit": UpdateType.ENTRY_HIT,
                "tp_hit": UpdateType.TP_HIT,
                "risk_free": UpdateType.RISK_FREE,
                "partial_close": UpdateType.PARTIAL_CLOSE,
                "full_close": UpdateType.FULL_CLOSE,
                "position_closed": UpdateType.POSITION_CLOSED,
                "sl_modified": UpdateType.SL_MODIFIED,
            }
            await SignalUpdate.objects.acreate(
                signal=signal,
                telegram_msg_id=telegram_msg.id,
                raw_text=telegram_msg.text or "",
                update_type=update_type_map.get(msg_type, UpdateType.INFO),
                tp_number=parsed.get("tp_number"),
                new_stop_loss=Decimal(str(parsed["new_stop_loss"])) if parsed.get("new_stop_loss") else None,
                close_percentage=parsed.get("close_percentage"),
                profit_percent=parsed.get("profit_percent"),
            )

            await handler(signal, parsed)
        else:
            logger.debug(f"No handler for update type: {msg_type}")

    # ── Update Handlers ──────────────────────────────────────

    async def _handle_entry_hit(self, signal: Signal, parsed: dict):
        """Entry point reached — position should be filling."""
        logger.info(f"Entry hit for {signal.symbol}")
        # Position status should update from order fill notifications
        # For now, just log it

    async def _handle_tp_hit(self, signal: Signal, parsed: dict):
        """Take profit reached — may need to close part of position."""
        tp_num = parsed.get("tp_number")
        logger.info(f"TP{tp_num} hit for {signal.symbol}")

        # The channel typically sends explicit close instructions
        # after TP hits, so we wait for those rather than auto-closing

    async def _handle_risk_free(self, signal: Signal, parsed: dict):
        """Move stop loss to entry (breakeven)."""
        symbol = signal.symbol.replace("/", "").upper()
        direction = signal.direction

        position = await Position.objects.filter(
            signal=signal,
            status__in=[PositionStatus.OPEN, PositionStatus.PENDING],
        ).afirst()

        if not position:
            return

        # Move SL to entry price
        new_sl = signal.entry_price_low
        try:
            await self.client.set_stop_loss(symbol, direction, str(new_sl))
            position.current_stop_loss = new_sl
            await position.asave()
            logger.info(f"SL moved to entry ({new_sl}) for {symbol}")
        except Exception as e:
            logger.error(f"Failed to move SL to entry: {e}")

    async def _handle_partial_close(self, signal: Signal, parsed: dict):
        """Close a percentage of the position."""
        close_pct = parsed.get("close_percentage", 50)
        symbol = signal.symbol.replace("/", "").upper()
        direction = signal.direction

        position = await Position.objects.filter(
            signal=signal,
            status__in=[PositionStatus.OPEN, PositionStatus.PENDING],
        ).afirst()

        if not position:
            return

        close_qty = position.remaining_quantity * Decimal(str(close_pct)) / Decimal("100")

        # Determine close side
        if direction == "long":
            close_side = OrderSide.CLOSE_LONG
        else:
            close_side = OrderSide.CLOSE_SHORT

        try:
            result = await self.client.place_order(
                symbol=symbol,
                side=close_side,
                volume=str(round(close_qty, 4)),
                order_type="market",
            )

            order_id = result.get("data", {}).get("orderId", "")
            await Order.objects.acreate(
                position=position,
                lbank_order_id=order_id,
                side=close_side,
                order_type="market",
                quantity=close_qty,
                status=OrderStatus.SUBMITTED,
            )

            position.remaining_quantity -= close_qty
            if position.remaining_quantity <= 0:
                position.status = PositionStatus.CLOSED
                position.closed_at = timezone.now()
            else:
                position.status = PositionStatus.PARTIALLY_CLOSED
            await position.asave()

            logger.info(f"Closed {close_pct}% of {symbol} ({close_qty})")
        except Exception as e:
            logger.error(f"Failed to partial close: {e}")

    async def _handle_full_close(self, signal: Signal, parsed: dict):
        """Close the entire position."""
        symbol = signal.symbol.replace("/", "").upper()
        direction = signal.direction

        position = await Position.objects.filter(
            signal=signal,
            status__in=[PositionStatus.OPEN, PositionStatus.PENDING, PositionStatus.PARTIALLY_CLOSED],
        ).afirst()

        if not position:
            return

        if direction == "long":
            close_side = OrderSide.CLOSE_LONG
        else:
            close_side = OrderSide.CLOSE_SHORT

        try:
            result = await self.client.place_order(
                symbol=symbol,
                side=close_side,
                volume=str(round(position.remaining_quantity, 4)),
                order_type="market",
            )

            order_id = result.get("data", {}).get("orderId", "")
            await Order.objects.acreate(
                position=position,
                lbank_order_id=order_id,
                side=close_side,
                order_type="market",
                quantity=position.remaining_quantity,
                status=OrderStatus.SUBMITTED,
            )

            position.remaining_quantity = Decimal("0")
            position.status = PositionStatus.CLOSED
            position.closed_at = timezone.now()
            await position.asave()

            signal.status = SignalStatus.CLOSED
            await signal.asave()

            logger.info(f"Fully closed {symbol}")
        except Exception as e:
            logger.error(f"Failed to close position: {e}")

    async def _handle_sl_modified(self, signal: Signal, parsed: dict):
        """Update stop loss to a new price."""
        new_sl = parsed.get("new_stop_loss")
        if not new_sl:
            return

        symbol = signal.symbol.replace("/", "").upper()
        direction = signal.direction

        position = await Position.objects.filter(
            signal=signal,
            status__in=[PositionStatus.OPEN, PositionStatus.PENDING],
        ).afirst()

        if not position:
            return

        try:
            await self.client.set_stop_loss(symbol, direction, str(new_sl))
            position.current_stop_loss = Decimal(str(new_sl))
            await position.asave()
            logger.info(f"SL updated to {new_sl} for {symbol}")
        except Exception as e:
            logger.error(f"Failed to update SL: {e}")

    # ── Helpers ───────────────────────────────────────────────

    async def _find_active_signal(self, symbol: str | None) -> Signal | None:
        """Find the most recent active signal for a symbol."""
        qs = Signal.objects.filter(status__in=[SignalStatus.ACTIVE, SignalStatus.NEW])
        if symbol:
            # Try exact match first, then fuzzy
            signal = await qs.filter(symbol__iexact=symbol.replace("USDT", "/USDT")).afirst()
            if not signal:
                signal = await qs.filter(symbol__icontains=symbol.replace("USDT", "")).afirst()
            return signal
        # If no symbol, return most recent active
        return await qs.order_by("-created_at").afirst()
