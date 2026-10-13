import uuid
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from apps.core.context import set_current_tenant, reset_current_tenant


class TenantContextMiddleware(MiddlewareMixin):
    """
    Middleware that identifies the active tenant per request and binds it
    to the thread-safe/async context and request object.

    Resolution Strategy:
    1. HTTP Header: 'X-Tenant-ID' (UUID or Slug)
    2. Session value: 'active_tenant_id'
    3. User's primary membership tenant
    """

    def process_request(self, request):
        request.tenant = None
        request.user_tenants = []
        request._tenant_context_token = None

        if not hasattr(request, "user") or not request.user.is_authenticated:
            # For unauthenticated requests, no user-based tenant scoping
            return None

        from apps.accounts.models import Tenant, Membership

        # Collect all active memberships for this user
        memberships = Membership.objects.filter(user=request.user).select_related("tenant")
        user_tenants = [m.tenant for m in memberships]
        request.user_tenants = user_tenants

        if not user_tenants and not request.user.is_staff:
            return None

        # 1. Check HTTP header 'X-Tenant-ID'
        header_tenant_id = request.headers.get("X-Tenant-ID")
        selected_tenant = None

        if header_tenant_id:
            # Find in user's permitted tenants by ID or slug
            for t in user_tenants:
                if str(t.id) == header_tenant_id or t.slug == header_tenant_id:
                    selected_tenant = t
                    break
            
            # Superusers can access any tenant via header
            if not selected_tenant and request.user.is_superuser:
                try:
                    if self._is_valid_uuid(header_tenant_id):
                        selected_tenant = Tenant.objects.filter(id=header_tenant_id).first()
                    else:
                        selected_tenant = Tenant.objects.filter(slug=header_tenant_id).first()
                except Exception:
                    pass

        # 2. Check Session
        if not selected_tenant:
            session_tenant_id = request.session.get("active_tenant_id")
            if session_tenant_id:
                for t in user_tenants:
                    if str(t.id) == str(session_tenant_id):
                        selected_tenant = t
                        break

        # 3. Default to user's first tenant membership
        if not selected_tenant and user_tenants:
            selected_tenant = user_tenants[0]
            # Store in session for consistent browsing
            request.session["active_tenant_id"] = str(selected_tenant.id)

        if selected_tenant:
            request.tenant = selected_tenant
            request._tenant_context_token = set_current_tenant(selected_tenant)

        return None

    def process_response(self, request, response):
        """Cleanup context variable when the request cycle completes."""
        token = getattr(request, "_tenant_context_token", None)
        if token is not None:
            reset_current_tenant(token)
        return response

    def process_exception(self, request, exception):
        """Ensure cleanup even on unhandled exceptions."""
        token = getattr(request, "_tenant_context_token", None)
        if token is not None:
            reset_current_tenant(token)
        return None

    @staticmethod
    def _is_valid_uuid(val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except ValueError:
            return False
