from rest_framework import permissions
from apps.accounts.models import Membership


class HasActiveTenant(permissions.BasePermission):
    """Ensures that the request was resolved to an active tenant context."""

    message = "No active tenant selected or access denied to the requested tenant."

    def has_permission(self, request, view):
        if not getattr(request, "tenant", None) and request.user and request.user.is_authenticated:
            header_tenant_id = request.headers.get("X-Tenant-ID") or request.META.get("HTTP_X_TENANT_ID")
            from apps.accounts.models import Membership, Tenant
            from apps.core.context import set_current_tenant
            from django.db.models import Q

            if header_tenant_id:
                m = Membership.objects.filter(user=request.user).filter(
                    Q(tenant_id=header_tenant_id) | Q(tenant__slug=header_tenant_id)
                ).select_related("tenant").first()
                if m:
                    request.tenant = m.tenant
                    set_current_tenant(m.tenant)
                elif request.user.is_superuser:
                    t = Tenant.objects.filter(Q(id=header_tenant_id) | Q(slug=header_tenant_id)).first()
                    if t:
                        request.tenant = t
                        set_current_tenant(t)
            else:
                m = Membership.objects.filter(user=request.user).select_related("tenant").first()
                if m:
                    request.tenant = m.tenant
                    set_current_tenant(m.tenant)

        return bool(request.user and request.user.is_authenticated and getattr(request, "tenant", None))


class IsTenantMember(permissions.BasePermission):
    """Allows access to any valid member of the active tenant."""

    message = "You are not a member of this tenant."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and getattr(request, "tenant", None)):
            return False
        if request.user.is_superuser:
            return True
        return Membership.objects.filter(user=request.user, tenant=request.tenant).exists()


class IsTenantEditor(permissions.BasePermission):
    """Allows write/upload operations to admins and editors of the active tenant."""

    message = "Editor or Administrator role required for this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and getattr(request, "tenant", None)):
            return False
        if request.user.is_superuser:
            return True
        membership = Membership.objects.filter(user=request.user, tenant=request.tenant).first()
        return membership is not None and membership.role in [
            Membership.Role.ADMIN,
            Membership.Role.EDITOR,
        ]


class IsTenantAdmin(permissions.BasePermission):
    """Allows sensitive operations only to tenant administrators."""

    message = "Administrator role required for this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and getattr(request, "tenant", None)):
            return False
        if request.user.is_superuser:
            return True
        membership = Membership.objects.filter(user=request.user, tenant=request.tenant).first()
        return membership is not None and membership.role == Membership.Role.ADMIN
