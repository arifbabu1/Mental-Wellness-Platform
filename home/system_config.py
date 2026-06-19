from django.conf import settings
from django.core.mail import get_connection, send_mail
import logging

from .models import PaymentReceiverAccount, SystemEmailConfig

logger = logging.getLogger(__name__)


def get_active_email_config():
    return SystemEmailConfig.active()


def get_email_connection_kwargs(config=None):
    config = config or get_active_email_config()
    if config:
        return {
            'host': config.email_host,
            'port': config.email_port,
            'username': config.email_host_user,
            'password': config.email_host_password,
            'use_tls': config.use_tls,
            'use_ssl': config.use_ssl,
        }

    host = getattr(settings, 'EMAIL_HOST', '')
    if not host:
        return None
    return {
        'host': host,
        'port': getattr(settings, 'EMAIL_PORT', 587),
        'username': getattr(settings, 'EMAIL_HOST_USER', ''),
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', ''),
        'use_tls': getattr(settings, 'EMAIL_USE_TLS', True),
        'use_ssl': getattr(settings, 'EMAIL_USE_SSL', False),
    }


def get_default_from_email(config=None):
    config = config or get_active_email_config()
    if config:
        return config.default_from_email
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@mentalwellness.local')


def get_support_email(config=None):
    config = config or get_active_email_config()
    if config and config.support_email:
        return config.support_email
    return getattr(settings, 'SUPPORT_EMAIL', get_default_from_email(config))


def get_admin_notification_email(config=None, fallback_user=None):
    config = config or get_active_email_config()
    if config and config.admin_notification_email:
        return config.admin_notification_email
    if fallback_user and getattr(fallback_user, 'email', ''):
        return fallback_user.email
    return getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', get_default_from_email(config))


def send_platform_email(subject, message, recipient_list, html_message=None, fail_silently=True):
    """Send platform email through the active DB config, falling back to settings.py.

    Secrets are intentionally never logged. For production, prefer environment-backed
    or encrypted secret storage for SMTP passwords and gateway credentials.
    """
    recipient_list = [email for email in (recipient_list or []) if email]
    if not recipient_list:
        logger.warning("Platform email skipped because recipient list is empty: %s", subject)
        return 0

    config = get_active_email_config()
    connection_kwargs = get_email_connection_kwargs(config)
    from_email = get_default_from_email(config)

    try:
        if connection_kwargs:
            connection = get_connection(**connection_kwargs)
            return send_mail(
                subject,
                message,
                from_email,
                recipient_list,
                fail_silently=fail_silently,
                connection=connection,
                html_message=html_message,
            )

        return send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=fail_silently,
            html_message=html_message,
        )
    except Exception as exc:
        logger.warning("Platform email failed for subject %r: %s", subject, exc)
        if not fail_silently:
            raise
        return 0


def send_configured_mail(subject, message, recipient_list, fail_silently=False, html_message=None):
    return send_platform_email(
        subject,
        message,
        recipient_list,
        html_message=html_message,
        fail_silently=fail_silently,
    )


def get_active_payment_accounts():
    return PaymentReceiverAccount.objects.filter(is_active=True).order_by('payment_method', '-is_default', 'account_name')


def get_active_payment_methods():
    return PaymentReceiverAccount.active_methods()


def get_default_payment_account(payment_method):
    return PaymentReceiverAccount.default_for_method(payment_method)


def get_payment_receiver(payment_method):
    return get_default_payment_account(payment_method)


def get_payment_method_options():
    labels = dict(PaymentReceiverAccount.PAYMENT_METHOD_CHOICES)
    return [
        {
            'value': method,
            'label': labels.get(method, method.title()),
            'account': get_default_payment_account(method),
        }
        for method in get_active_payment_methods()
    ]
