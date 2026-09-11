import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("AI4S_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("AI4S_DEBUG", "0") == "1"
ALLOWED_HOSTS = [x for x in os.getenv("AI4S_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x]
_default_csrf_origins = "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else ""
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("AI4S_CSRF_TRUSTED_ORIGINS", _default_csrf_origins).split(",") if x]
ROOT_URLCONF = "config.urls"
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "rest_framework", "modules.projects", "modules.execution",
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
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
}
