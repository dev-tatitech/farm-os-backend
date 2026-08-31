from pathlib import Path
import environ
import os

env = environ.Env(
    DEBUG=(bool, False),
    CORS_ALLOW_CREDENTIALS=(bool, True),
)
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(env_file=BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env.bool("DEBUG", default=True)


def _csv(name, default=""):
    return [item.strip() for item in env(name, default=default).split(",") if item.strip()]


def _allowed_hosts(raw_items):
    hosts = []
    for item in raw_items:
        host = item.replace("https://", "").replace("http://", "").split("/")[0]
        host = host.split(":")[0]
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _unique(items):
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


AUTH_USER_MODEL = "account.User"

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "ninja",
    "account",
    "common",
    "organization",
    "core",
    "admin_panel",
    "subcriptions",
    "role",
    "farms",
    "animals",
    "reproduction",
    "health",
    "feed",
    "movement_records",
    "alerts",
    "dashbaord",
    "finance",
    "pharmacy",
    "reports",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "api.urls"

# Local defaults live in settings. Public domains come from .env only.
CORS_ALLOWED_ORIGINS = _unique(
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    + _csv("CORS_ALLOWED_ORIGINS")
)
CORS_ALLOW_CREDENTIALS = env.bool("CORS_ALLOW_CREDENTIALS", default=True)
CSRF_TRUSTED_ORIGINS = _unique(
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]
    + _csv("CSRF_TRUSTED_ORIGINS")
)
ALLOWED_HOSTS = _allowed_hosts(
    _unique(
        [
            "localhost",
            "127.0.0.1",
            "[::1]",
            "localhost:3000",
            "farmos",
            "farmos_dev",
            "nginx",
            "nginx_dev",
        ]
        + _csv("ALLOWED_HOSTS")
    )
)
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "api.wsgi.application"


# Database: DATABASE_URL → DB_* Postgres → SQLite
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

_database_url = (env("DATABASE_URL", default="") or "").strip()
_db_host = (env("DB_HOST", default="") or env("LOCAL_HOSTNAME", default="") or "").strip()
if _database_url:
    DATABASES = {"default": env.db("DATABASE_URL")}
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault(
        "sslmode", env("DB_SSLMODE", default="disable")
    )
elif _db_host:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="") or env("LOCAL_DB_NAME", default=""),
            "USER": env("DB_USER", default="") or env("LOCAL_USERNAME", default=""),
            "PASSWORD": env("DB_PASSWORD", default="") or env("LOCAL_PASSWORD", default=""),
            "HOST": _db_host,
            "PORT": env("DB_PORT", default="5432"),
            "OPTIONS": {"sslmode": env("DB_SSLMODE", default="disable")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/staticfiles/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.is_dir() else []
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Media files (if applicable)
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# email config

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
