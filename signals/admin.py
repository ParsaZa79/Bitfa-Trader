"""Admin configuration for signals app."""

from django.contrib import admin

from signals.models import Signal, SignalUpdate


class SignalUpdateInline(admin.TabularInline):
    model = SignalUpdate
    extra = 0
    readonly_fields = ("telegram_msg_id", "update_type", "raw_text", "created_at")


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "direction",
        "entry_price_low",
        "stop_loss",
        "leverage",
        "risk_percent",
        "status",
        "confidence",
        "created_at",
    )
    list_filter = ("status", "direction", "symbol", "created_at")
    search_fields = ("symbol", "raw_text")
    readonly_fields = ("telegram_msg_id", "telegram_channel_id", "created_at", "updated_at")
    inlines = [SignalUpdateInline]

    fieldsets = (
        ("Signal", {
            "fields": ("symbol", "direction", "status", "confidence"),
        }),
        ("Prices", {
            "fields": ("entry_price_low", "entry_price_high", "stop_loss", "tp1", "tp2", "tp3"),
        }),
        ("Risk", {
            "fields": ("risk_percent", "leverage", "margin_type"),
        }),
        ("Telegram", {
            "fields": ("telegram_msg_id", "telegram_channel_id", "raw_text"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("signal_time", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(SignalUpdate)
class SignalUpdateAdmin(admin.ModelAdmin):
    list_display = ("signal", "update_type", "tp_number", "profit_percent", "created_at")
    list_filter = ("update_type", "created_at")
    search_fields = ("raw_text",)
