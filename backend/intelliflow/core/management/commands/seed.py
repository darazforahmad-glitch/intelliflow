from typing import Any

from django.core.management.base import BaseCommand

from intelliflow.automations.seeds import seed_templates


class Command(BaseCommand):
    help = "Insert the template library (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(f"Inserted {seed_templates()} template(s).")
