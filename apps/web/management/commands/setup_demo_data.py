import os
import uuid
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from apps.accounts.models import Tenant, CustomUser, Membership
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import DocumentExtractor, DocumentChunker, EmbeddingService
from apps.core.context import TenantContext


class Command(BaseCommand):
    help = "Seeds initial demo tenants, users, and sample documents with vectorized embeddings."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("==> Seeding Demo Tenants and Users..."))

        # 1. Tenants
        acme, created = Tenant.objects.get_or_create(
            slug="acme-corp",
            defaults={
                "name": "Acme Corporation",
                "plan": Tenant.Plan.PRO,
                "monthly_token_limit": 1000000,
                "tokens_consumed": 14200,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Tenant: {acme.name}"))

        cyberdyne, created = Tenant.objects.get_or_create(
            slug="cyberdyne-systems",
            defaults={
                "name": "CyberDyne Systems",
                "plan": Tenant.Plan.FREE,
                "monthly_token_limit": 100000,
                "tokens_consumed": 2150,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Tenant: {cyberdyne.name}"))

        # 2. Users
        admin_user = CustomUser.objects.filter(email="admin@example.com").first()
        if not admin_user:
            admin_user = CustomUser.objects.create_superuser(
                email="admin@example.com",
                password="admin123456",
                full_name="Principal Architect",
            )
            self.stdout.write(self.style.SUCCESS("Created Superuser: admin@example.com (pass: admin123456)"))

        alice = CustomUser.objects.filter(email="alice@acme.com").first()
        if not alice:
            alice = CustomUser.objects.create_user(
                email="alice@acme.com",
                password="password123",
                full_name="Alice Engineer",
            )
            self.stdout.write(self.style.SUCCESS("Created User: alice@acme.com"))

        # 3. Memberships
        Membership.objects.get_or_create(
            user=admin_user, tenant=acme, defaults={"role": Membership.Role.ADMIN}
        )
        Membership.objects.get_or_create(
            user=admin_user, tenant=cyberdyne, defaults={"role": Membership.Role.ADMIN}
        )
        Membership.objects.get_or_create(
            user=alice, tenant=acme, defaults={"role": Membership.Role.EDITOR}
        )

        # 4. Seed Documents for Acme Corporation
        self.stdout.write(self.style.NOTICE("==> Seeding and Vectorizing Sample Documents for Acme Corp..."))

        acme_doc_content_1 = """ACME CORPORATION - Q3 FINANCIAL PERFORMANCE REPORT
Confidential - For Internal Use Only

Executive Summary:
Acme Corporation recorded total gross revenue of $142.5 million for the third quarter of 2024, representing an 18.4% year-over-year expansion. Net operating margins improved to 28.2%, driven primarily by efficiencies in cloud infrastructure cost management and expanded enterprise software subscriptions.

\x0cRevenue Breakdown by Division:
1. Enterprise SaaS Solutions: $84.2 million (59% of total revenue). Customer retention rate reached 97.4%, with net revenue retention (NRR) hovering at 124%.
2. Professional Services & AI Advisory: $36.1 million (25% of total revenue). Average project delivery timeline reduced from 90 days to 42 days.
3. Hardware Integration & Edge Appliances: $22.2 million (16% of total revenue). Supply chain lead times normalized to 14 business days.

\x0cRisk Factors and Capital Allocation:
Foreign exchange fluctuations created a $2.8 million headwind due to strengthening USD against EUR and JPY. The Board has authorized a $25 million share repurchase program commencing in Q4, while capital expenditures are forecasted at $18 million focused entirely on next-generation GPU cluster deployment.

Forward Guidance:
Full-year fiscal revenue target is elevated to between $570 million and $585 million with anticipated EBITDA margin between 26% and 29%."""

        acme_doc_content_2 = """ACME CLOUD ARCHITECTURE & COMPLIANCE SPECIFICATION
Version 4.2 - Production Architecture

System Overview:
The Acme Document Intelligence Platform leverages a multi-tenant microservices architecture orchestrated via Kubernetes. All tenant workloads share scalable compute nodes while strictly maintaining physical or logical boundary isolation at the database layer.

\x0cData Storage and Security Standards:
1. Encryption at Rest: All persistent storage volumes utilize AES-256 encryption with automated monthly key rotation managed through AWS KMS or HashiCorp Vault.
2. Encryption in Transit: Strict TLS 1.3 is enforced on all external and internal mesh endpoints with mTLS (Mutual TLS) enabled between microservices.
3. PostgreSQL Vector Storage: Embeddings are generated using 1536-dimensional dense vectors and queried using pgvector HNSW indexing with Cosine Distance (<=>). Every query MUST filter by tenant_id prior to vector distance calculations.

\x0cService Level Agreement (SLA):
The platform guarantees 99.95% monthly uptime. Disaster recovery objectives dictate a Recovery Point Objective (RPO) under 5 minutes and a Recovery Time Objective (RTO) under 15 minutes."""

        cyberdyne_doc_content = """CYBERDYNE SYSTEMS - NEURAL NET CPU DESIGN SPECIFICATION
Top Secret - Skynet Research Division

Project Synopsis:
The T-800 Neural Net CPU represents a quantum leap in autonomous cybernetic decision-making. Operating at 2.4 teraflops on a specialized room-temperature superconductive substrate, the processor features real-time heuristics and adaptive neural synapses.

\x0cSubsystem Architecture:
The core instruction set incorporates custom tensor operations optimized for kinematic servos and predictive target vector tracking. Energy consumption is restricted to 15 Watts per core, sustained through a compact micro-fusion cell with a 120-year operational half-life."""

        # Seed Acme Documents
        self._seed_document(
            tenant=acme,
            user=admin_user,
            title="Acme Q3 Financial Performance Report",
            filename="acme_q3_financial_report.txt",
            content=acme_doc_content_1,
        )

        self._seed_document(
            tenant=acme,
            user=admin_user,
            title="Acme Cloud Architecture Specification",
            filename="acme_cloud_architecture_spec.txt",
            content=acme_doc_content_2,
        )

        # Seed CyberDyne Document (to prove isolation!)
        self._seed_document(
            tenant=cyberdyne,
            user=admin_user,
            title="CyberDyne Neural Net CPU Spec",
            filename="cyberdyne_neural_net_spec.txt",
            content=cyberdyne_doc_content,
        )

        self.stdout.write(self.style.SUCCESS("==> Demo data setup completed successfully!"))

    def _seed_document(self, tenant, user, title, filename, content):
        existing = Document.all_objects.filter(tenant=tenant, title=title).first()
        if existing:
            self.stdout.write(f"Document '{title}' already exists for {tenant.name}. Skipping.")
            return

        with TenantContext(tenant):
            doc = Document(
                tenant=tenant,
                uploaded_by=user,
                title=title,
                file_type=Document.FileType.TXT,
                file_size=len(content.encode("utf-8")),
                status=Document.Status.PROCESSING,
            )
            doc.file.save(filename, ContentFile(content.encode("utf-8")), save=False)
            doc.save()

            # Process and vectorize
            pages = DocumentExtractor.extract(doc.file.path, "txt")
            chunker = DocumentChunker(chunk_size=800, chunk_overlap=100)
            raw_chunks = chunker.chunk_pages(pages)

            chunk_instances = []
            for item in raw_chunks:
                emb = EmbeddingService.get_embedding(item["content"])
                chunk_instances.append(
                    DocumentChunk(
                        tenant=tenant,
                        document=doc,
                        content=item["content"],
                        page_number=item["page_number"],
                        chunk_index=item["chunk_index"],
                        token_count=item["token_count"],
                        embedding=emb,
                    )
                )

            DocumentChunk.all_objects.bulk_create(chunk_instances)

            doc.status = Document.Status.READY
            doc.total_chunks = len(chunk_instances)
            doc.total_pages = len(pages)
            doc.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Vectorized '{title}' for {tenant.name}: {len(chunk_instances)} chunks across {len(pages)} pages."
                )
            )
