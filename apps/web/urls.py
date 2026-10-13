from django.urls import path
from apps.web.views import (
    dashboard_view,
    documents_view,
    documents_table_partial,
    chat_view,
    switch_tenant_view,
)

app_name = "web"

urlpatterns = [
    path("", dashboard_view, name="index"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("documents/", documents_view, name="documents"),
    path("documents/table-partial/", documents_table_partial, name="documents-table-partial"),
    path("chat/", chat_view, name="chat"),
    path("switch-tenant/<uuid:tenant_id>/", switch_tenant_view, name="switch-tenant"),
]
