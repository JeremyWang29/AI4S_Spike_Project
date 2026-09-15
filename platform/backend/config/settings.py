import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from django.core.exceptions import ImproperlyConfigured
AI4S_ENV = os.getenv("AI4S_ENV", "development")
if AI4S_ENV not in ("development", "acceptance", "pilot", "production"):
    raise ImproperlyConfigured("Unknown AI4S_ENV")
SECRET_KEY = os.getenv("AI4S_SECRET_KEY", "development-only-change-me" if AI4S_ENV == "development" else "")
if AI4S_ENV != "development" and (len(SECRET_KEY) < 32 or SECRET_KEY.startswith("development")):
    raise ImproperlyConfigured("Nondevelopment requires a unique AI4S_SECRET_KEY of at least 32 characters")
DEBUG = os.getenv("AI4S_DEBUG", "0") == "1"
if AI4S_ENV != "development" and DEBUG:
    raise ImproperlyConfigured("DEBUG is forbidden outside development")
ALLOWED_HOSTS = [x for x in os.getenv("AI4S_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x]
_default_csrf_origins = "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else ""
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("AI4S_CSRF_TRUSTED_ORIGINS", _default_csrf_origins).split(",") if x]
ROOT_URLCONF = "config.urls"
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "rest_framework", "modules.projects", "modules.execution", "modules.identity", "modules.knowledge",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.errors.BusinessErrorMiddleware",
]
DATABASES = {
    "default": {
        "ENGINE": os.getenv("AI4S_DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("AI4S_DB_NAME", str(BASE_DIR / "development.sqlite3")),
        "USER": os.getenv("AI4S_DB_USER", ""), "PASSWORD": os.getenv("AI4S_DB_PASSWORD", ""),
        "HOST": os.getenv("AI4S_DB_HOST", ""), "PORT": os.getenv("AI4S_DB_PORT", ""),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_FAILURE_VIEW = "config.errors.csrf_failure"
SESSION_COOKIE_SECURE = AI4S_ENV != "development"
CSRF_COOKIE_SECURE = AI4S_ENV != "development"
SECURE_SSL_REDIRECT = AI4S_ENV != "development"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_AGE = 8 * 60 * 60
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
MEDIA_ROOT = os.getenv("AI4S_FILES_ROOT", str(BASE_DIR / "files" / AI4S_ENV))
CELERY_TASK_DEFAULT_QUEUE = "ai4s_" + AI4S_ENV
CELERY_BROKER_URL = os.getenv("AI4S_BROKER_URL", "amqp://guest:guest@localhost:5672//" if AI4S_ENV == "development" else "")
if AI4S_ENV != "development":
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", os.getenv("AI4S_BROKER_PASSWORD", "")):
        raise ImproperlyConfigured("AI4S_BROKER_PASSWORD must be a URL-safe random secret of at least 32 characters")
    for required in ("AI4S_DB_NAME", "AI4S_DB_PASSWORD", "AI4S_FILES_ROOT", "AI4S_BROKER_URL", "AI4S_ALLOWED_HOSTS"):
        if not os.getenv(required): raise ImproperlyConfigured(required + " is required outside development")
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("Nondevelopment requires PostgreSQL")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
}
