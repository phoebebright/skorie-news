import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-example-app-secret-key'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.flatpages',
        'rest_framework',
    "rest_framework_api_key",
    'skorie_news',
    'web',
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

AUTH_USER_MODEL = 'users.CustomUser'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SITE_ID = 1

# Skorie News Settings
NEWSLETTER_GENERAL_SLUG = 'general'

# Hetzner / S3 Settings (Dummy values for example)
HETZNER_AWS_STORAGE_BUCKET_NAME = 'dummy-bucket'
HETZNER_AWS_STORAGE_PUBLIC_BUCKET = 'dummy-public-bucket'
HETZNER_AWS_S3_ENDPOINT_URL = 'https://s3.example.com'
HETZNER_AWS_S3_REGION_NAME = 'us-east-1'
HETZNER_AWS_ACCESS_KEY_ID = 'dummy-key'
HETZNER_AWS_SECRET_ACCESS_KEY = 'dummy-secret'
HETZNER_AWS_S3_ADDRESSING_STYLE = 'virtual'
HETZNER_AWS_S3_SIGNATURE_VERSION = 's3v4'
HETZNER_AWS_S3_LOCATION = 'ride'
HETZNER_AWS_S3_FILE_OVERWRITE = False

MODEL_ROLES_PATH = 'web.roles_and_disciplines.ModelRoles'
DISCIPLINES_PATH = 'web.roles_and_disciplines.Disciplines'

USE_KEYCLOAK = False
