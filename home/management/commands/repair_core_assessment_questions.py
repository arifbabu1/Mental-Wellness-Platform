from django.core.management.base import BaseCommand

from home.assessment_core import ensure_core_assessment_questions


class Command(BaseCommand):
    help = 'Repair the protected 7 core assessment questions.'

    def handle(self, *args, **options):
        summary = ensure_core_assessment_questions()
        self.stdout.write(
            self.style.SUCCESS(
                "Core assessment repair complete: "
                f"created={summary['created']}, "
                f"repaired={summary['repaired']}, "
                f"already_ok={summary['already_ok']}"
            )
        )
