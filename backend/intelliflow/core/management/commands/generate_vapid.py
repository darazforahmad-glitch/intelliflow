import base64
from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print a VAPID key pair for Web Push."

    def handle(self, *args: Any, **options: Any) -> None:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid02

        vapid = Vapid02()
        vapid.generate_keys()
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        self.stdout.write(
            f"VAPID_PUBLIC_KEY={base64.urlsafe_b64encode(public).decode().rstrip('=')}"
        )
        self.stdout.write(
            f"VAPID_PRIVATE_KEY={base64.urlsafe_b64encode(private).decode().rstrip('=')}"
        )
