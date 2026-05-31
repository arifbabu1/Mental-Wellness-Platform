from pathlib import Path
import importlib.util
import os
from urllib.parse import urlparse

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]


def _database_from_url(default_sqlite_path):
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': default_sqlite_path}
    parsed = urlparse(url)
    if parsed.scheme in {'postgres', 'postgresql'}:
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username or '',
            'PASSWORD': parsed.password or '',
            'HOST': parsed.hostname or '',
            'PORT': parsed.port or '',
        }
    if parsed.scheme == 'sqlite':
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': parsed.path}
    return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': default_sqlite_path}


_load_dotenv(BASE_DIR / '.env')

# Security settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure--o$tbvh1+2sa-4_vtpuaxmpit^f@*)gtl+g1w_x8nt&t**^4s5')
DEBUG = _env_bool('DEBUG', True)
ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', ['127.0.0.1', 'localhost', 'testserver'])

# Custom User Model
AUTH_USER_MODEL = 'home.User'
SITE_ID = int(os.environ.get('SITE_ID', '1'))

# Authentication
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/auth/redirect/'
LOGOUT_REDIRECT_URL = '/'

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

ACCOUNT_EMAIL_VERIFICATION = os.environ.get('ACCOUNT_EMAIL_VERIFICATION', 'optional')
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True

SOCIALACCOUNT_ADAPTER = 'home.adapters.MentalWellnessSocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {
            'access_type': 'online',
            'prompt': 'select_account',
        },
        'APPS': [
            {
                'client_id': GOOGLE_CLIENT_ID,
                'secret': GOOGLE_CLIENT_SECRET,
                'key': '',
            }
        ] if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET else [],
    }
}

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites',
    'django.contrib.staticfiles',
    'channels',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'home',  # Your app here
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if importlib.util.find_spec('whitenoise'):
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'wellness_platform.urls'

# Templates configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Look for templates in the base directory
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,  # Look for templates in app directories too
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wellness_platform.wsgi.application'

# Database configuration
DATABASES = {
    'default': _database_from_url(BASE_DIR / 'db.sqlite3')
}

# Password validation settings
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Localization settings
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'  # UTC+06:00 timezone
USE_I18N = True
USE_TZ = True

# Static files configuration
STATIC_URL = '/static/'  # URL for accessing static files

# This is for collecting static files in one place for production
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    BASE_DIR / 'home' / 'static',  # Add home/static to the static files search
]

STATIC_ROOT = BASE_DIR / 'staticfiles'

if importlib.util.find_spec('whitenoise'):
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

# Email configuration. Runtime mail can also be managed from the admin panel;
# these environment values remain the fallback when no active DB config exists.
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@mentalwellness.local')

# TESTING MODE: Real payment gateway charging is disabled for local/development booking.
# TODO: Enable real payment gateway verification in production by setting PAYMENT_TEST_MODE=False.
PAYMENT_TEST_MODE = _env_bool('PAYMENT_TEST_MODE', True)
PAYMENT_TEST_OTP = os.environ.get('PAYMENT_TEST_OTP', '123456')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', DEFAULT_FROM_EMAIL)
ADMIN_NOTIFICATION_EMAIL = os.environ.get('ADMIN_NOTIFICATION_EMAIL', SUPPORT_EMAIL)

# User-uploaded files, such as doctor profile images and prescription PDFs.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Security settings
SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)
CSRF_COOKIE_SECURE = _env_bool('CSRF_COOKIE_SECURE', False)
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', False)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Channels configuration
ASGI_APPLICATION = 'wellness_platform.asgi.application'

# Channels Redis configuration (for production)
# CHANNEL_LAYERS = ['channels.security.InsecureMiddleware']
# CHANNELS_REDIS = {
#     'default': {
#         'BACKEND': 'channels_redis.core.RedisChannelLayer',
#         'CONFIG': {
#             "hosts": [('127.0.0.1', 6379)],
#         },
#     }
# }

# For development, use in-memory channel layer
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Offline emergency chatbot / Ollama configuration
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
OLLAMA_CHAT_MODEL = os.environ.get('OLLAMA_CHAT_MODEL', 'llama3.2:1b')
OLLAMA_EMBED_MODEL = os.environ.get('OLLAMA_EMBED_MODEL', 'nomic-embed-text')
OLLAMA_CHAT_TIMEOUT = int(os.environ.get('OLLAMA_CHAT_TIMEOUT', '30'))
OLLAMA_EMBED_TIMEOUT = int(os.environ.get('OLLAMA_EMBED_TIMEOUT', '5'))

# WebSocket allowed origins
CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS', [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
])
