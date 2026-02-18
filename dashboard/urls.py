from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/pnl-chart/", views.pnl_chart_data, name="pnl_chart_data"),
]
