from rest_framework.throttling import SimpleRateThrottle
from apps.accounts.models import Tenant


class TenantRateThrottle(SimpleRateThrottle):
    """
    Limits request rates based on the active Tenant and its subscription plan.
    Free: 20 requests/minute
    Pro: 120 requests/minute
    Enterprise: 600 requests/minute
    """

    scope = "tenant"

    def get_cache_key(self, request, view):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            # Fall back to IP-based throttle if tenant context is missing
            return self.get_ident(request)
        return f"throttle_tenant_{tenant.id}"

    def get_rate(self):
        """Dynamically resolve rate limit based on tenant's plan."""
        # Check if view provides a request with an active tenant
        request = getattr(self, "request", None)
        tenant = getattr(request, "tenant", None) if request else None

        if tenant:
            plan = tenant.plan.lower()
            if plan == Tenant.Plan.PRO.lower():
                return self.THROTTLE_RATES.get("pro", "120/minute")
            elif plan == Tenant.Plan.ENTERPRISE.lower():
                return self.THROTTLE_RATES.get("enterprise", "600/minute")
            return self.THROTTLE_RATES.get("free", "20/minute")

        return self.THROTTLE_RATES.get("tenant", "60/minute")

    def allow_request(self, request, view):
        # Store request so get_rate has access to tenant
        self.request = request
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)
