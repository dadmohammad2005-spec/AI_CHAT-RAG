from rest_framework import serializers
from apps.accounts.models import Tenant, CustomUser, Membership


class TenantSerializer(serializers.ModelSerializer):
    token_quota_remaining = serializers.IntegerField(read_only=True)
    token_quota_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "plan",
            "monthly_token_limit",
            "tokens_consumed",
            "storage_bytes_consumed",
            "token_quota_remaining",
            "token_quota_percent",
            "created_at",
        ]
        read_only_fields = ["id", "tokens_consumed", "storage_bytes_consumed", "created_at"]


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "email", "full_name", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class MembershipSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "tenant", "tenant_name", "role", "created_at"]
        read_only_fields = ["id", "created_at"]
