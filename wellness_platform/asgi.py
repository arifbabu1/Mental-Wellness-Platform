"""
ASGI config for wellness_platform project.

This project deploys critical features through WSGI-safe Django views and AJAX
polling, so the ASGI entrypoint stays minimal and channel-free.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wellness_platform.settings')

application = get_asgi_application()
