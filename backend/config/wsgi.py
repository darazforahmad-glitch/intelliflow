"""WSGI entry point: Gunicorn serves the API with this (Section 4.10, Figure 4.12)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
