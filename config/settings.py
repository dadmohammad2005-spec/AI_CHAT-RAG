import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-prod-ready-tenant-rag-engine-change-in-production-!$94%"
)

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,web").split(",")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    "pgvector",
    # Local core & domain apps
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.documents.apps.DocumentsConfig",
    "apps.rag.apps.RagConfig",
    "apps.web.apps.WebConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Multi-tenant isolation middleware (enforces tenant context)
    "apps.core.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Context processor injecting active tenant into templates
                "apps.core.context.tenant_context_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database Configuration
# Uses PostgreSQL with pgvector in containerized/production setups
USE_SQLITE = os.environ.get("USE_SQLITE", "False").lower() in ("true", "1", "yes")
DB_ENGINE = os.environ.get(
    "DB_ENGINE", "django.db.backends.sqlite3" if USE_SQLITE else "django.db.backends.postgresql"
)
DB_NAME = os.environ.get("DB_NAME", "ai_rag_db")
DB_USER = os.environ.get("DB_USER", "rag_admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "rag_secure_password")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

if "sqlite3" in DB_ENGINE or USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": DB_NAME,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": DB_HOST,
            "PORT": DB_PORT,
        }
    }

# Custom User Model
AUTH_USER_MODEL = "accounts.CustomUser"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files (Uploaded tenant documents)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# File Upload Limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB

# Redis & Caching
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
if "sqlite3" in DB_ENGINE or USE_SQLITE:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-rag-dev-cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

# Celery Configuration
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_ALWAYS_EAGER = os.environ.get(
    "CELERY_TASK_ALWAYS_EAGER", "True" if (USE_SQLITE or "sqlite3" in DB_ENGINE) else "False"
).lower() in ("true", "1", "yes")
CELERY_TASK_EAGER_PROPAGATES = True

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.core.throttling.TenantRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "tenant": "60/minute",
        "free": "20/minute",
        "pro": "120/minute",
        "enterprise": "600/minute",
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# CORS configuration
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant-id",  # Custom header for tenant context
]

# AI & RAG Configuration
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
AI_EMBEDDING_DIMENSION = int(os.environ.get("AI_EMBEDDING_DIMENSION", "1536"))
AI_FALLBACK_TO_MOCK = os.environ.get("AI_FALLBACK_TO_MOCK", "True").lower() in ("true", "1", "yes")

RAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "800"))
RAG_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "100"))
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "4"))
RAG_SIMILARITY_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.35"))

DEFAULT_FREE_TOKEN_LIMIT = int(os.environ.get("DEFAULT_FREE_TOKEN_LIMIT", "100000"))
DEFAULT_PRO_TOKEN_LIMIT = int(os.environ.get("DEFAULT_PRO_TOKEN_LIMIT", "1000000"))
DEFAULT_ENTERPRISE_TOKEN_LIMIT = int(os.environ.get("DEFAULT_ENTERPRISE_TOKEN_LIMIT", "10000000"))
