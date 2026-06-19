# Mental Wellness Platform Deployment Guide

This project is a Django application with role-based users, doctor scheduling,
appointments, payments in test mode, consultations, prescriptions, task
reminders, Google OAuth hooks, and a customized Django admin console.

## Before You Upload

Run these checks locally from the project root:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test home
```

Do not upload local secrets or development data:

- Keep `.env` private.
- Keep `db.sqlite3` private unless you intentionally want to move local data.
- Keep `__pycache__`, logs, and virtual environments out of Git.

The existing `.gitignore` already excludes those common local files.

## Upload The Project To GitHub

1. Create an empty repository on GitHub. Do not add a README, license, or
   `.gitignore` on GitHub because this project already has files locally.
2. Open PowerShell in this folder:

```powershell
cd "E:\From Documents\Project\MentalWellnessPlatform73"
```

3. Initialize Git, commit, and connect the remote:

```powershell
git init -b main
git add .
git commit -m "Initial Django project"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git remote -v
git push -u origin main
```

If Git says the branch already exists, use:

```powershell
git branch -M main
git push -u origin main
```

## PythonAnywhere Free Deployment

PythonAnywhere free accounts are good for a beginner Django deployment, but the
free tier has tight limits. Use SQLite for the first free deployment unless you
already have an external database.

### 1. Create The Web App

1. Sign in to PythonAnywhere.
2. Open a Bash console.
3. Clone the GitHub repository:

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd MentalWellnessPlatform73
```

### 2. Create A Virtual Environment

Use a Python version available on your PythonAnywhere account:

```bash
mkvirtualenv --python=/usr/bin/python3.13 mentalwellness-venv
pip install -r requirements.txt
```

If `python3.13` is unavailable, choose the newest Python version shown in your
PythonAnywhere account and use the same version when creating the web app.

### 3. Create A Production `.env`

Create `/home/YOUR_PYTHONANYWHERE_USERNAME/MentalWellnessPlatform73/.env`:

```bash
SECRET_KEY=generate-a-long-random-secret-key-here
DEBUG=False
ALLOWED_HOSTS=YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com

SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000

PAYMENT_TEST_MODE=True
PAYMENT_TEST_OTP=123456
SUPPORT_EMAIL=support@example.com
ADMIN_NOTIFICATION_EMAIL=admin@example.com
```

Generate a secret key from a PythonAnywhere Bash console:

```bash
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

Keep `PAYMENT_TEST_MODE=True` until you integrate and verify a real payment
gateway. Do not accept real money while the project is in test payment mode.

### 4. Configure The PythonAnywhere Web Tab

1. Go to the Web tab.
2. Add a new web app.
3. Choose Manual Configuration, not the new Django project wizard.
4. Select the same Python version used by your virtualenv.
5. Set Source code and Working directory to:

```text
/home/YOUR_PYTHONANYWHERE_USERNAME/MentalWellnessPlatform73
```

6. Set Virtualenv to:

```text
mentalwellness-venv
```

7. Open the WSGI configuration file from the Web tab and replace its Django
   section with:

```python
import os
import sys

path = '/home/YOUR_PYTHONANYWHERE_USERNAME/MentalWellnessPlatform73'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'wellness_platform.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

### 5. Database And Static Files

Run:

```bash
cd ~/MentalWellnessPlatform73
workon mentalwellness-venv
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

On the PythonAnywhere Web tab, add static file mappings:

```text
URL:  /static/
Path: /home/YOUR_PYTHONANYWHERE_USERNAME/MentalWellnessPlatform73/staticfiles

URL:  /media/
Path: /home/YOUR_PYTHONANYWHERE_USERNAME/MentalWellnessPlatform73/media
```

Reload the web app. Your site should open at:

```text
https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com
```

## Admin Panel Setup

### 1. Create The First Admin

On PythonAnywhere:

```bash
cd ~/MentalWellnessPlatform73
workon mentalwellness-venv
python manage.py createsuperuser
```

Then log in at:

```text
https://YOUR_PYTHONANYWHERE_USERNAME.pythonanywhere.com/admin/
```

The Django superuser can access every admin setting.

### 2. Configure System Email

In the admin panel:

1. Open `System Email Config`.
2. Add a new config.
3. Fill in SMTP host, port, username, app password, sender email, support email,
   and admin notification email.
4. Keep only one config active.
5. Use the admin action `Send test email to my admin email`.

For Gmail, use an app password, not your normal Gmail password.

### 3. Configure Payment Receiver Accounts

In the admin panel:

1. Open `Payment Receiver Accounts`.
2. Add active receiver accounts for `bKash`, `Nagad`, `Card`, or `Bank`.
3. Mark one account per payment method as default.
4. Put only public patient-facing instructions in `instructions`.
5. Do not put PINs, passwords, or private gateway secrets in instructions.

This project still uses test payment mode by default. Real payment verification
must be implemented before production payments.

### 4. Add Doctors

In the admin panel:

1. Open `Users`.
2. Add a new user with role `doctor`, or use the custom doctor creation fields
   in the admin.
3. Fill profile details: specialization, primary focus, qualification,
   experience, consultation fee, license number, clinic info, and availability.
4. Add weekly availability in `Doctor Schedules`.

### 5. Add Assessment And Task Data

From PythonAnywhere Bash:

```bash
python manage.py populate_assessment
python manage.py create_health_task_templates
```

Use the admin panel to review:

- Assessment Questions
- Doctor Specializations
- Doctor Primary Focuses
- Health Task Templates

### 6. Daily Operations

Use the admin panel to monitor:

- Users
- Doctors
- Appointments
- Payments
- Clinical Assessments
- Consultations
- Prescriptions
- Daily Tasks
- Emergency Logs

For reminder emails, the command is:

```bash
python manage.py check_task_reminders
```

On the free PythonAnywhere tier, scheduled task availability may depend on your
account age and current free-tier limits. If scheduled tasks are unavailable,
run this manually or upgrade later.

## Production Work Still Needed

- Replace payment test mode with real gateway verification.
- Replace the first-name-plus-phone password reset flow with signed token or
  email-based password reset.
- Add rate limiting for login, reset, and booking endpoints. The chatbot endpoint already includes a basic in-memory rate limit.
- Move SQLite to a production database before real users depend on the site.
- Review all mental-health emergency messaging with a qualified professional.
- Add monitoring, backups, and error reporting.
- Verify Jitsi/video consultation behavior on the final host. PythonAnywhere
  should use the project WSGI file; the consultation room uses AJAX polling and does not require ASGI WebSockets.
