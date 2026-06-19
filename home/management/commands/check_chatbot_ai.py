import json
from urllib import error, request
from urllib.parse import urlencode

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Safely check Gemini chatbot connectivity without printing secrets.'

    def handle(self, *args, **options):
        enabled = bool(getattr(settings, 'CHATBOT_AI_ENABLED', False))
        provider = (getattr(settings, 'CHATBOT_AI_PROVIDER', 'gemini') or '').lower()
        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        model = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
        timeout = getattr(settings, 'CHATBOT_TIMEOUT', 6)

        if not enabled:
            self.stdout.write(self.style.WARNING('Chatbot AI is disabled. Local fallback will be used.'))
            return
        if provider != 'gemini':
            self.stdout.write(self.style.WARNING('Unsupported chatbot provider configured. Local fallback will be used.'))
            return
        if not api_key:
            self.stdout.write(self.style.WARNING('Gemini API key is missing. Local fallback will be used.'))
            return

        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{model}:generateContent?{urlencode({"key": api_key})}'
        )
        payload = {
            'contents': [{'role': 'user', 'parts': [{'text': 'Reply with OK.'}]}],
            'generationConfig': {'maxOutputTokens': 8, 'temperature': 0},
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with request.urlopen(req, timeout=timeout) as response:
                status_code = getattr(response, 'status', 200)
            if 200 <= status_code < 300:
                self.stdout.write(self.style.SUCCESS('Gemini chatbot connectivity check succeeded.'))
            else:
                self.stdout.write(self.style.WARNING('Gemini returned a non-success response. Local fallback will be used.'))
        except (TimeoutError, error.HTTPError, error.URLError, OSError, ValueError):
            self.stdout.write(self.style.WARNING('Gemini is unavailable or rejected the test request. Local fallback will be used.'))
