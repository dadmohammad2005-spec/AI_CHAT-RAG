from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import Tenant, CustomUser, Membership


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "plan",
        "tokens_consumed",
        "monthly_token_limit",
        "token_quota_percent",
        "created_at",
    )
    search_fields = ("name", "slug")
    list_filter = ("plan", "created_at")
    readonly_fields = ("id", "created_at", "tokens_consumed", "storage_bytes_consumed")


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "full_name")
    list_filter = ("is_staff", "is_active")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name",)}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    search_fields = ("user__email", "tenant__name")
    list_filter = ("role", "created_at")
