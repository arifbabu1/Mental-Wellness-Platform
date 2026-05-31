import os
import django
from channels.routing import get_default_application
from channels.auth import AuthMiddlewareStack
from channels.security import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wellness_platform.settings')
django.setup()

application = get_default_application()

application.middleware.insert(0, AllowedHostsOriginValidator())
application.middleware.insert(1, AuthMiddlewareStack())
