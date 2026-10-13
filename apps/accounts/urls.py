from django.urls import path
from apps.accounts.views import CurrentTenantView, SwitchTenantView, TenantMembershipsListView

app_name = "accounts"

urlpatterns = [
    path("current-tenant/", CurrentTenantView.as_view(), name="current-tenant"),
    path("switch-tenant/", SwitchTenantView.as_view(), name="switch-tenant"),
    path("memberships/", TenantMembershipsListView.as_view(), name="memberships-list"),
]
