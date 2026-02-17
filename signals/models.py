"""Models for parsed trading signals and their updates."""

from django.db import models


class SignalDirection(models.TextChoices):
    LONG = "long", "Long"
    SHORT = "short", "Short"


class SignalStatus(models.TextChoices):
    NEW = "new", "New"
    ACTIVE = "active", "Active"
    PARTIALLY_CLOSED = "partially_closed", "Partially Closed"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class UpdateType(models.TextChoices):
    ENTRY_HIT = "entry_hit", "Entry Hit"
    TP_HIT = "tp_hit", "Take Profit Hit"
    SL_MODIFIED = "sl_modified", "Stop Loss Modified"
    PARTIAL_CLOSE = "partial_close", "Partial Close"
    FULL_CLOSE = "full_close", "Full Close"
    RISK_FREE = "risk_free", "Risk Free (Move SL to Entry)"
    POSITION_CLOSED = "position_closed", "Position Fully Closed"
    INFO = "info", "Informational"


class Signal(models.Model):
    """A trading signal parsed from the Telegram channel."""

    telegram_msg_id = models.BigIntegerField(unique=True)
    telegram_channel_id = models.BigIntegerField()
    raw_text = models.TextField(blank=True, default="")
    raw_image_path = models.CharField(max_length=500, blank=True, default="")

    # Parsed signal data
    symbol = models.CharField(max_length=20)  # e.g. ETH/USDT
    direction = models.CharField(max_length=5, choices=SignalDirection.choices)
    entry_price_low = models.DecimalField(max_digits=20, decimal_places=8)
    entry_price_high = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8)
    tp1 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    tp2 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    tp3 = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Risk management from signal
    risk_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    leverage = models.IntegerField(default=8)
    margin_type = models.CharField(max_length=10, default="isolated")  # isolated / cross

    # Status tracking
    status = models.CharField(max_length=20, choices=SignalStatus.choices, default=SignalStatus.NEW)
    confidence = models.FloatField(default=0.0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signal_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.symbol} {self.direction} @ {self.entry_price_low} ({self.status})"


class SignalUpdate(models.Model):
    """An update/follow-up message related to a signal."""

    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="updates")
    telegram_msg_id = models.BigIntegerField(unique=True)
    raw_text = models.TextField(blank=True, default="")

    update_type = models.CharField(max_length=20, choices=UpdateType.choices)

    # Optional fields depending on update type
    tp_number = models.IntegerField(null=True, blank=True)
    new_stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    close_percentage = models.IntegerField(null=True, blank=True)
    profit_percent = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Update for {self.signal.symbol}: {self.update_type}"
