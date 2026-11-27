import secrets
from typing import Any

from django.core.management.base import BaseCommand

from intelliflow.core.crypto import generate_key


class Command(BaseCommand):
    help = "Print fresh SECRET_KEY and ENCRYPTION_KEYS values for a new environment."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(f"SECRET_KEY={secrets.token_urlsafe(48)}")
        self.stdout.write(f"ENCRYPTION_KEYS=k{secrets.token_hex(2)}:{generate_key()}")
