import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.utils.text import slugify


class Tenant(models.Model):
    """
    Represents an isolated Organization / Customer Tenant in the SaaS system.
    """

    class Plan(models.TextChoices):
        FREE = "Free", "Free Tier"
        PRO = "Pro", "Pro Tier"
        ENTERPRISE = "Enterprise", "Enterprise Tier"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    plan = models.CharField(max_length=32, choices=Plan.choices, default=Plan.FREE)
    monthly_token_limit = models.IntegerField(default=100000)
    tokens_consumed = models.IntegerField(default=0)
    storage_bytes_consumed = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"

    def __str__(self):
        return f"{self.name} ({self.plan})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.monthly_token_limit:
            if self.plan == self.Plan.PRO:
                self.monthly_token_limit = 1000000
            elif self.plan == self.Plan.ENTERPRISE:
                self.monthly_token_limit = 10000000
            else:
                self.monthly_token_limit = 100000
        super().save(*args, **kwargs)

    @property
    def token_quota_remaining(self) -> int:
        return max(0, self.monthly_token_limit - self.tokens_consumed)

    @property
    def token_quota_percent(self) -> float:
        if self.monthly_token_limit <= 0:
            return 100.0
        return min(100.0, round((self.tokens_consumed / self.monthly_token_limit) * 100, 2))

    def has_quota(self, requested_tokens: int = 1) -> bool:
        """Verify whether tenant has sufficient tokens available."""
        return (self.tokens_consumed + requested_tokens) <= self.monthly_token_limit

    def consume_tokens(self, count: int) -> int:
        """Atomically increment tokens consumed."""
        Tenant.objects.filter(id=self.id).update(
            tokens_consumed=models.F("tokens_consumed") + count
        )
        self.refresh_from_db(fields=["tokens_consumed"])
        return self.tokens_consumed


class CustomUserManager(BaseUserManager):
    """Custom user manager using email as primary identifier."""

    def create_user(self, email, password=None, full_name="", **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, full_name="", **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, full_name, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model authenticated via email.
    Associated with Tenants through Membership relations.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email


class Membership(models.Model):
    """
    Join model connecting a User to a Tenant with specific RBAC role.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "tenant")
        ordering = ["tenant", "role"]
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        return f"{self.user.email} - {self.tenant.name} ({self.role})"
