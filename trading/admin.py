"""Admin configuration for trading app."""

from django.contrib import admin

from trading.models import Position, Order


class OrderInline(admin.TabularInline):
    model = Order
    extra = 0
    readonly_fields = ("lbank_order_id", "side", "order_type", "price", "quantity", "filled_quantity", "status", "created_at")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "side",
        "leverage",
        "quantity",
        "remaining_quantity",
        "entry_price",
        "current_stop_loss",
        "realized_pnl",
        "status",
        "opened_at",
    )
    list_filter = ("status", "side", "symbol", "created_at")
    search_fields = ("symbol",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [OrderInline]

    fieldsets = (
        ("Position", {
            "fields": ("signal", "symbol", "side", "leverage", "margin_type", "status"),
        }),
        ("Size", {
            "fields": ("quantity", "remaining_quantity", "margin_used", "entry_price"),
        }),
        ("SL/TP", {
            "fields": ("current_stop_loss", "current_tp"),
        }),
        ("P&L", {
            "fields": ("realized_pnl", "unrealized_pnl"),
        }),
        ("Timestamps", {
            "fields": ("opened_at", "closed_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "lbank_order_id",
        "position",
        "side",
        "order_type",
        "price",
        "quantity",
        "filled_quantity",
        "status",
        "created_at",
    )
    list_filter = ("status", "side", "order_type", "created_at")
    search_fields = ("lbank_order_id",)
