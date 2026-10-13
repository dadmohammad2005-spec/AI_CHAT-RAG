from rest_framework import views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.accounts.models import Tenant, Membership
from apps.accounts.serializers import TenantSerializer, MembershipSerializer
from apps.core.permissions import HasActiveTenant


class CurrentTenantView(views.APIView):
    """
    Retrieve current tenant profile, plan details, and quota consumption.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant]

    def get(self, request):
        serializer = TenantSerializer(request.tenant)
        return Response(serializer.data)


class SwitchTenantView(views.APIView):
    """
    Switch the active tenant context for the user session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = request.data.get("tenant_id")
        if not tenant_id:
            return Response(
                {"error": "tenant_id parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if the user belongs to this tenant (or is superuser)
        has_membership = Membership.objects.filter(
            user=request.user, tenant_id=tenant_id
        ).exists()

        if not has_membership and not request.user.is_superuser:
            return Response(
                {"error": "Access denied. You do not belong to this tenant."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = Tenant.objects.filter(id=tenant_id).first()
        if not tenant:
            return Response(
                {"error": "Tenant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Update session
        request.session["active_tenant_id"] = str(tenant.id)
        request.tenant = tenant

        return Response(
            {
                "message": f"Switched to tenant: {tenant.name}",
                "tenant": TenantSerializer(tenant).data,
            }
        )


class TenantMembershipsListView(generics.ListAPIView):
    """
    List all tenants that the authenticated user belongs to.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MembershipSerializer

    def get_queryset(self):
        return Membership.objects.filter(user=self.request.user).select_related(
            "tenant", "user"
        )
