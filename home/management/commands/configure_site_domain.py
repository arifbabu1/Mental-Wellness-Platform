from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Set the Django Sites domain/name from SITE_DOMAIN.'

    def handle(self, *args, **options):
        site_domain = getattr(settings, 'SITE_DOMAIN', '') or ''
        if not site_domain:
            self.stdout.write(self.style.WARNING('SITE_DOMAIN is not set. Nothing to update.'))
            return

        site, _created = Site.objects.update_or_create(
            id=getattr(settings, 'SITE_ID', 1),
            defaults={
                'domain': site_domain,
                'name': site_domain,
            },
        )
        self.stdout.write(self.style.SUCCESS(f'Configured Django site: {site.domain}'))
