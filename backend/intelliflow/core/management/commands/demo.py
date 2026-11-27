from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from intelliflow.core.demo import build_demo


class Command(BaseCommand):
    help = "Build the demo workspace through the real code paths (idempotent)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default="demo@intelliflow.pk")
        parser.add_argument("--password", default="Demo12345")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        if not build_demo(email, options["password"]):
            self.stdout.write(f"Demo user {email} already exists; nothing to do.")
            return
        self.stdout.write("Demo workspace ready.")
        self.stdout.write(
            f"  Sign in at {settings.FRONTEND_URL}/login with {email} / {options['password']}"
        )
