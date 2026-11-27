from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from intelliflow.accounts.models import User
from intelliflow.core.security import validate_password_strength


class Command(BaseCommand):
    help = "Create or promote a platform admin (can sign in to /admin/)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="Platform Admin")
        parser.add_argument("--password", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        validate_password_strength(options["password"])
        email = options["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email, options["password"], full_name=options["name"], email_verified=True
            )
        user.is_platform_admin = True
        user.save(update_fields=["is_platform_admin"])
        self.stdout.write(f"Platform admin ready: {user.email}")
