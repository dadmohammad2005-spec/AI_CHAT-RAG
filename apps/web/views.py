from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib import messages
from apps.accounts.models import Tenant, CustomUser, Membership
from apps.documents.models import Document, DocumentChunk
from apps.rag.models import QueryLog


def get_or_set_default_tenant(request):
    """
    Ensure a valid tenant is assigned to the session for interactive browsing.
    If no user is logged in, auto-log in the demo administrator.
    """
    if not request.user.is_authenticated:
        # Auto-authenticate default demo user for seamless local inspection
        demo_user = CustomUser.objects.filter(email="admin@example.com").first()
        if demo_user:
            login(request, demo_user)

    tenant = getattr(request, "tenant", None)
    if not tenant:
        # Fall back to first available tenant
        tenant = Tenant.objects.first()
        if tenant:
            request.session["active_tenant_id"] = str(tenant.id)
            request.tenant = tenant
    return tenant


def dashboard_view(request):
    tenant = get_or_set_default_tenant(request)
    if not tenant:
        return render(request, "dashboard.html", {"tenant": None, "empty_state": True})

    documents_qs = Document.objects.filter(tenant=tenant)
    total_docs = documents_qs.count()
    ready_docs = documents_qs.filter(status=Document.Status.READY).count()
    processing_docs = documents_qs.filter(status=Document.Status.PROCESSING).count()
    total_chunks = DocumentChunk.objects.filter(tenant=tenant).count()

    queries_qs = QueryLog.objects.filter(tenant=tenant)
    total_queries = queries_qs.count()
    recent_queries = queries_qs.order_by("-created_at")[:6]

    recent_documents = documents_qs.order_by("-created_at")[:5]

    context = {
        "tenant": tenant,
        "total_docs": total_docs,
        "ready_docs": ready_docs,
        "processing_docs": processing_docs,
        "total_chunks": total_chunks,
        "total_queries": total_queries,
        "recent_queries": recent_queries,
        "recent_documents": recent_documents,
        "tokens_consumed": tenant.tokens_consumed,
        "monthly_limit": tenant.monthly_token_limit,
        "token_percent": tenant.token_quota_percent,
        "all_tenants": Tenant.objects.all(),
    }
    return render(request, "dashboard.html", context)


def documents_view(request):
    tenant = get_or_set_default_tenant(request)
    documents = (
        Document.objects.filter(tenant=tenant).order_by("-created_at")
        if tenant
        else Document.objects.none()
    )
    has_active_processing = documents.filter(
        status__in=[Document.Status.PENDING, Document.Status.PROCESSING]
    ).exists()

    context = {
        "tenant": tenant,
        "documents": documents,
        "has_active_processing": has_active_processing,
        "all_tenants": Tenant.objects.all(),
    }
    return render(request, "documents.html", context)


def documents_table_partial(request):
    """HTMX endpoint for polling document status updates."""
    tenant = getattr(request, "tenant", None) or Tenant.objects.first()
    documents = (
        Document.objects.filter(tenant=tenant).order_by("-created_at")
        if tenant
        else Document.objects.none()
    )
    has_active_processing = documents.filter(
        status__in=[Document.Status.PENDING, Document.Status.PROCESSING]
    ).exists()

    context = {
        "documents": documents,
        "has_active_processing": has_active_processing,
    }
    return render(request, "partials/documents_list.html", context)


def chat_view(request):
    tenant = get_or_set_default_tenant(request)
    ready_docs = (
        Document.objects.filter(tenant=tenant, status=Document.Status.READY).order_by("title")
        if tenant
        else Document.objects.none()
    )
    recent_queries = (
        QueryLog.objects.filter(tenant=tenant).order_by("-created_at")[:10]
        if tenant
        else QueryLog.objects.none()
    )

    context = {
        "tenant": tenant,
        "ready_docs": ready_docs,
        "recent_queries": recent_queries,
        "all_tenants": Tenant.objects.all(),
    }
    return render(request, "chat.html", context)


def switch_tenant_view(request, tenant_id):
    """Switch active tenant from top navigation."""
    tenant = get_object_or_404(Tenant, id=tenant_id)
    request.session["active_tenant_id"] = str(tenant.id)
    messages.success(request, f"Switched context to tenant: {tenant.name}")
    redirect_url = request.META.get("HTTP_REFERER", "/")
    return redirect(redirect_url)
