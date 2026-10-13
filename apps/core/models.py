import uuid
from django.db import models
from apps.core.context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    """QuerySet providing tenant-scoping helpers."""

    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantManager(models.Manager):
    """
    Manager that automatically filters querysets by the active tenant context.
    Ensures strict tenant data isolation at the ORM layer.
    """

    def get_queryset(self):
        qs = TenantQuerySet(self.model, using=self._db)
        tenant = get_current_tenant()
        if tenant is not None:
            return qs.filter(tenant=tenant)
        return qs

    def unrestricted(self):
        """Bypass tenant context filtering for administrative or background processes."""
        return TenantQuerySet(self.model, using=self._db)


class TenantAwareModel(models.Model):
    """
    Abstract base model that enforces multi-tenancy.
    All tenant-scoped resources must inherit from this model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Auto-assign tenant from current context if not explicitly set.
        Raises ValueError if attempted to save without a tenant context.
        """
        if not self.tenant_id:
            current_tenant = get_current_tenant()
            if current_tenant:
                self.tenant = current_tenant
            else:
                raise ValueError(
                    f"Cannot save {self.__class__.__name__} without an active tenant context."
                )
        super().save(*args, **kwargs)
