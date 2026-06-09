# PythonAnywhere Deployment Guide

This project is configured for a university demo deployment. Payment remains demo/test only; do not add real bKash, Nagad, or card gateway credentials unless the payment system is redesigned and audited.

## 1. Prepare The GitHub Repo

Do not commit local-only files:

- `.env`
- `db.sqlite3` or any `*.sqlite3`
- `staticfiles/`
- `media/private/`, temporary media, or generated PDFs
- `__pycache__/`, `*.pyc`
- logs, backups, IDE files, or secrets

Push only source code, templates, static source files, migrations, docs, and safe config examples.

## 2. Create PythonAnywhere App

In a PythonAnywhere Bash console:

```bash
git clone https://github.com/YOUR_USERNAME/Mental-Wellness-Platform.git
cd Mental-Wellness-Platform
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Django 5.2 LTS supports Python 3.10 through 3.14. Choose the newest supported Python runtime available in your PythonAnywhere account.

## 3. Create `.env`

Copy `.env.example` to `.env` on PythonAnywhere and fill production values:

```bash
cp .env.example .env
nano .env
```

Recommended production values:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=yourusername.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com
SITE_DOMAIN=yourusername.pythonanywhere.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
PAYMENT_TEST_MODE=True
```

If Google login is not configured, leave `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` empty. The Google button will be hidden.

## 4. Google Login Setup

In Google Cloud Console create an OAuth 2.0 Web application client.

Use these values for PythonAnywhere:

- Authorized JavaScript origin: `https://yourusername.pythonanywhere.com`
- Authorized redirect URI: `https://yourusername.pythonanywhere.com/accounts/google/login/callback/`

Then set these in `.env`:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
SITE_DOMAIN=yourusername.pythonanywhere.com
SITE_ID=1
```

After migrations, run:

```bash
python manage.py configure_site_domain
```

Google login uses a POST form because `SOCIALACCOUNT_LOGIN_ON_GET=False`. After Google authentication the app routes through `/auth/redirect/`; incomplete patient profiles are sent to the profile completion page before the dashboard.

## 5. Database And Static Files

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py configure_site_domain
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check
```

SQLite can work for a small demo. For heavier use, set `DATABASE_URL` to a hosted PostgreSQL database and run migrations again.

## 6. PythonAnywhere WSGI

In the PythonAnywhere Web tab, set:

- Source code: `/home/yourusername/Mental-Wellness-Platform`
- Working directory: `/home/yourusername/Mental-Wellness-Platform`
- Virtualenv: `/home/yourusername/Mental-Wellness-Platform/.venv`

Edit the WSGI file:

```python
import os
import sys

project_home = '/home/yourusername/Mental-Wellness-Platform'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wellness_platform.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## 7. Static And Media Mapping

In the Web tab static files section:

- URL: `/static/`
- Directory: `/home/yourusername/Mental-Wellness-Platform/staticfiles`

For uploaded media in a demo:

- URL: `/media/`
- Directory: `/home/yourusername/Mental-Wellness-Platform/media`

## 8. Daily Task Reminder Scheduled Task

Add a PythonAnywhere scheduled task, for example daily at 7:05 PM Asia/Dhaka:

```bash
cd /home/yourusername/Mental-Wellness-Platform && source .venv/bin/activate && python manage.py check_task_reminders
```

Use `--force` only for manual testing.

## 9. Consultation Rooms

Video consultations use Jitsi (`meet.jit.si`). No custom WebRTC/WebSocket dependency is required for the consultation room. The room status uses safe backend polling, so WSGI deployment works.

Current timing rules:

- Room opens 10 minutes before the appointment.
- Before scheduled time, patient and doctor enter a waiting room.
- Doctor starts the video at or after scheduled time.
- Room expires 30 minutes after scheduled time if not completed.
- Doctor can explicitly complete the consultation.
- If the doctor leaves after the session starts and does not rejoin within 3 minutes, the backend marks it completed.

## 10. Common Troubleshooting

- `SECRET_KEY must be set when DEBUG=False`: create `.env` and set `SECRET_KEY`.
- `DisallowedHost`: add your PythonAnywhere domain to `ALLOWED_HOSTS`.
- CSRF errors after login/form submit: add `https://yourusername.pythonanywhere.com` to `CSRF_TRUSTED_ORIGINS`.
- Static files missing: run `collectstatic --noinput` and confirm the `/static/` mapping.
- Password reset emails not sending: configure SMTP environment variables or the admin-managed email config.
- Google callback mismatch: confirm the redirect URI is exactly `https://yourusername.pythonanywhere.com/accounts/google/login/callback/` and run `python manage.py configure_site_domain`.
- Chatbot unavailable: Ollama is optional. On PythonAnywhere free hosting it usually will not run, and the app falls back gracefully.
