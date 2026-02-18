"""Dashboard views."""

import asyncio
import json
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Q

from signals.models import Signal, SignalUpdate
from trading.models import Position, Order
from trading.lbank.client import LBankFuturesClient


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def index(request):
    """Main dashboard view."""
    # Overview stats
    total_signals = Signal.objects.count()
    open_positions = Position.objects.filter(status__in=["open", "partially_closed"]).count()
    closed_positions = Position.objects.filter(status="closed").count()

    total_pnl = Position.objects.filter(status="closed").aggregate(
        total=Sum("realized_pnl")
    )["total"] or Decimal("0")

    winning = Position.objects.filter(status="closed", realized_pnl__gt=0).count()
    win_rate = (winning / closed_positions * 100) if closed_positions > 0 else 0

    unrealized_pnl = Position.objects.filter(
        status__in=["open", "partially_closed"]
    ).aggregate(total=Sum("unrealized_pnl"))["total"] or Decimal("0")

    # Signals list
    signals = Signal.objects.all()[:50]

    # Positions
    positions = Position.objects.select_related("signal").all()[:50]

    # Activity feed - combine signal updates and recent orders
    recent_updates = SignalUpdate.objects.select_related("signal").order_by("-created_at")[:20]
    recent_orders = Order.objects.select_related("position").filter(
        status="filled"
    ).order_by("-created_at")[:20]

    # Build activity feed
    activities = []
    for u in recent_updates:
        activities.append({
            "time": u.created_at,
            "type": u.get_update_type_display(),
            "symbol": u.signal.symbol,
            "detail": u.raw_text[:120] if u.raw_text else "",
            "icon": _update_icon(u.update_type),
            "color": _update_color(u.update_type),
        })
    for o in recent_orders:
        activities.append({
            "time": o.created_at,
            "type": f"Order {o.get_side_display()}",
            "symbol": o.position.symbol,
            "detail": f"{o.quantity}@{o.filled_price or o.price}",
            "icon": "📋",
            "color": "text-blue-400",
        })
    activities.sort(key=lambda x: x["time"], reverse=True)
    activities = activities[:25]

    ctx = {
        "total_signals": total_signals,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "total_pnl": total_pnl,
        "unrealized_pnl": unrealized_pnl,
        "win_rate": round(win_rate, 1),
        "winning": winning,
        "signals": signals,
        "positions": positions,
        "activities": activities,
    }
    return render(request, "dashboard/index.html", ctx)


def pnl_chart_data(request):
    """Return cumulative PnL data for Chart.js."""
    closed = Position.objects.filter(
        status="closed", closed_at__isnull=False
    ).order_by("closed_at").values_list("closed_at", "realized_pnl")

    labels = []
    data = []
    cumulative = Decimal("0")
    for closed_at, pnl in closed:
        cumulative += pnl or Decimal("0")
        labels.append(closed_at.strftime("%b %d %H:%M"))
        data.append(float(cumulative))

    return JsonResponse({"labels": labels, "data": data})


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=10)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _fetch_exchange_data():
    """Fetch positions, open orders and account from LBank."""
    client = LBankFuturesClient()
    try:
        positions = await client.get_positions()
        open_orders = await client.get_open_orders()
        account = await client.get_account()
        return {
            "positions": positions.get("data", []) if isinstance(positions, dict) else [],
            "open_orders": open_orders.get("data", []) if isinstance(open_orders, dict) else [],
            "account": account.get("data", {}) if isinstance(account, dict) else {},
        }
    except Exception as e:
        return {"positions": [], "open_orders": [], "account": {}, "error": str(e)}
    finally:
        await client.close()


def exchange_data(request):
    """API endpoint: live exchange data from LBank."""
    data = _run_async(_fetch_exchange_data())
    return JsonResponse(data)


def _update_icon(update_type):
    icons = {
        "entry_hit": "🎯",
        "tp_hit": "✅",
        "sl_modified": "🔄",
        "partial_close": "📊",
        "full_close": "🏁",
        "risk_free": "🛡️",
        "position_closed": "🔒",
        "info": "ℹ️",
    }
    return icons.get(update_type, "📌")


def _update_color(update_type):
    colors = {
        "entry_hit": "text-yellow-400",
        "tp_hit": "text-green-400",
        "sl_modified": "text-orange-400",
        "partial_close": "text-blue-400",
        "full_close": "text-green-400",
        "risk_free": "text-cyan-400",
        "position_closed": "text-gray-400",
        "info": "text-gray-500",
    }
    return colors.get(update_type, "text-gray-400")
