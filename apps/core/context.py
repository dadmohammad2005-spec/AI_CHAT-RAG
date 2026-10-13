import contextvars
from typing import Optional, Any

# Thread-safe and async-safe context variable for tenant isolation
_current_tenant_var: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "current_tenant", default=None
)


def get_current_tenant() -> Optional[Any]:
    """Retrieve the current active tenant from context."""
    return _current_tenant_var.get()


def set_current_tenant(tenant: Any):
    """Set the active tenant in context and return the token."""
    return _current_tenant_var.set(tenant)


def reset_current_tenant(token) -> None:
    """Reset the tenant context back to its previous state."""
    _current_tenant_var.reset(token)


class TenantContext:
    """
    Context manager to safely execute a code block under a specific tenant context.
    Useful for Celery workers, background jobs, management commands, and unit tests.
    """

    def __init__(self, tenant: Any):
        self.tenant = tenant
        self.token = None

    def __enter__(self):
        self.token = set_current_tenant(self.tenant)
        return self.tenant

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token is not None:
            reset_current_tenant(self.token)


def tenant_context_processor(request):
    """
    Django template context processor that injects the active tenant
    and the user's available tenants into all rendered templates.
    """
    return {
        "active_tenant": getattr(request, "tenant", None),
        "user_tenants": getattr(request, "user_tenants", []),
    }
