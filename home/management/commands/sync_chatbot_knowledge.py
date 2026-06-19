from django.core.management.base import BaseCommand

from home.rag_chatbot import sync_knowledge_base


class Command(BaseCommand):
    help = 'Sync chatbot platform knowledge chunks idempotently.'

    def handle(self, *args, **options):
        summary = sync_knowledge_base()
        self.stdout.write(
            self.style.SUCCESS(
                "Chatbot knowledge sync complete: "
                f"created={summary['created']}, "
                f"updated={summary['updated']}, "
                f"deleted={summary['deleted']}, "
                f"unchanged={summary['unchanged']}"
            )
        )
