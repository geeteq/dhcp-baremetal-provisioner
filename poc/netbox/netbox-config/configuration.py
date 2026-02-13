"""
NetBox Configuration for Testing Environment
Version: 3.7.3
"""

import os
from pathlib import Path

# Read secret from Docker environment
SECRET_KEY = os.environ.get('SECRET_KEY', '1q2w3e4r')

# Database configuration
DATABASE = {
    'NAME': os.environ.get('DB_NAME', 'netbox'),
    'USER': os.environ.get('DB_USER', 'netbox'),
    'PASSWORD': os.environ.get('DB_PASSWORD', 'netbox_password'),
    'HOST': os.environ.get('DB_HOST', 'netbox-postgres'),
    'PORT': os.environ.get('DB_PORT', '5432'),
    'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '300')),
}

# Redis configuration for caching
REDIS = {
    'tasks': {
        'HOST': os.environ.get('REDIS_HOST', 'netbox-redis'),
        'PORT': int(os.environ.get('REDIS_PORT', '6379')),
        'PASSWORD': os.environ.get('REDIS_PASSWORD', ''),
        'DATABASE': int(os.environ.get('REDIS_DATABASE', '0')),
        'SSL': os.environ.get('REDIS_SSL', 'False').lower() == 'true',
    },
    'caching': {
        'HOST': os.environ.get('REDIS_CACHE_HOST', 'netbox-redis-cache'),
        'PORT': int(os.environ.get('REDIS_CACHE_PORT', '6379')),
        'PASSWORD': os.environ.get('REDIS_CACHE_PASSWORD', ''),
        'DATABASE': int(os.environ.get('REDIS_CACHE_DATABASE', '1')),
        'SSL': os.environ.get('REDIS_CACHE_SSL', 'False').lower() == 'true',
    }
}

# Base URL path if behind a reverse proxy
BASE_PATH = os.environ.get('BASE_PATH', '')

# Allowed hostnames
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split()

# Time zone
TIME_ZONE = os.environ.get('TIME_ZONE', 'UTC')

# Email configuration (for testing)
EMAIL = {
    'SERVER': os.environ.get('EMAIL_SERVER', 'localhost'),
    'PORT': int(os.environ.get('EMAIL_PORT', '25')),
    'USERNAME': os.environ.get('EMAIL_USERNAME', ''),
    'PASSWORD': os.environ.get('EMAIL_PASSWORD', ''),
    'USE_SSL': os.environ.get('EMAIL_USE_SSL', 'False').lower() == 'true',
    'USE_TLS': os.environ.get('EMAIL_USE_TLS', 'False').lower() == 'true',
    'TIMEOUT': int(os.environ.get('EMAIL_TIMEOUT', '10')),
    'FROM_EMAIL': os.environ.get('EMAIL_FROM', 'netbox@example.com'),
}

# CORS settings (for API access)
CORS_ORIGIN_ALLOW_ALL = os.environ.get('CORS_ORIGIN_ALLOW_ALL', 'True').lower() == 'true'
CORS_ORIGIN_WHITELIST = [
    'http://localhost',
    'http://localhost:8000',
]
CORS_ORIGIN_REGEX_WHITELIST = []

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
}

# Debug mode (DO NOT enable in production)
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# Developer options
DEVELOPER = DEBUG

# Plugins configuration
PLUGINS = []

# Plugins configuration settings
PLUGINS_CONFIG = {}

# Remote authentication (disabled for testing)
REMOTE_AUTH_ENABLED = False
REMOTE_AUTH_BACKEND = 'netbox.authentication.RemoteUserBackend'
REMOTE_AUTH_HEADER = 'HTTP_REMOTE_USER'
REMOTE_AUTH_AUTO_CREATE_USER = True
REMOTE_AUTH_DEFAULT_GROUPS = []
REMOTE_AUTH_DEFAULT_PERMISSIONS = {}

# Custom fields for baremetal lifecycle tracking
# These will be created via the initialization script

# Webhooks configuration
WEBHOOKS_ENABLED = os.environ.get('WEBHOOKS_ENABLED', 'True').lower() == 'true'

# Pagination
PAGINATE_COUNT = 50
MAX_PAGE_SIZE = 1000

# Prefer IPv4
PREFER_IPV4 = True

# Change logging
CHANGELOG_RETENTION = 90

# Job result retention
JOBRESULT_RETENTION = 90

# Maintenance mode
MAINTENANCE_MODE = False

# GraphQL
GRAPHQL_ENABLED = True

# Banner (for testing environment)
BANNER_TOP = os.environ.get('BANNER_TOP', 'NetBox Test Environment v3.7.3')
BANNER_BOTTOM = os.environ.get('BANNER_BOTTOM', '')
BANNER_LOGIN = 'Baremetal Provisioning Test Environment'

# Session timeout (1 week for testing)
SESSION_COOKIE_AGE = 604800

# Storage backends
STORAGE_BACKEND = None
STORAGE_CONFIG = {}
