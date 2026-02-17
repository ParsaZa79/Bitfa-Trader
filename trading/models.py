"""Models for tracking executed trades on LBank."""

from django.db import models

from signals.models import Signal


class PositionStatus(models.TextChoices):
    PENDING = "pending", "Pending Entry"
    OPEN = "open", "Open"
    PARTIALLY_CLOSED = "partially_closed", "Partially Closed"
    CLOSED = "closed", "Closed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class OrderSide(models.TextChoices):
    OPEN_LONG = "open_long", "Open Long"
    OPEN_SHORT = "open_short", "Open Short"
    CLOSE_LONG = "close_long", "Close Long"
    CLOSE_SHORT = "close_short", "Close Short"


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    FILLED = "filled", "Filled"
    PARTIALLY_FILLED = "partially_filled", "Partially Filled"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class Position(models.Model):
    """Tracks an open/closed futures position linked to a signal."""

    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="positions")

    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=15)  # long / short
    leverage = models.IntegerField(default=8)
    margin_type = models.CharField(max_length=10, default="isolated")

    # Position details
    entry_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    remaining_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    margin_used = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    # Current SL/TP on exchange
    current_stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    current_tp = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # P&L
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)

    status = models.CharField(max_length=20, choices=PositionStatus.choices, default=PositionStatus.PENDING)

    # Timestamps
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.symbol} {self.side} x{self.leverage} ({self.status})"


class Order(models.Model):
    """Individual orders placed on LBank for a position."""

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="orders")

    # LBank order info
    lbank_order_id = models.CharField(max_length=100, blank=True, default="")
    side = models.CharField(max_length=15, choices=OrderSide.choices)
    order_type = models.CharField(max_length=20, default="limit")  # limit / market
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    filled_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.lbank_order_id or 'pending'} {self.side} {self.quantity}@{self.price}"
