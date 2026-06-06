from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect


class MentalWellnessSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google OAuth behavior tailored for the platform's custom User model."""

    patient_only_message = 'Google login is only available for patient accounts.'

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)

        email = self._get_email(sociallogin)
        email_verified = self._is_email_verified(sociallogin)
        if not email:
            messages.error(request, 'Google did not return an email address. Please use manual login or another Google account.')
            raise ImmediateHttpResponse(redirect('login'))

        if sociallogin.is_existing:
            self._block_non_patient(request, sociallogin.user)
            self._sync_user_from_google(sociallogin.user, sociallogin, email_verified)
            return

        existing_user = get_user_model().objects.filter(email__iexact=email).first()
        if existing_user:
            self._block_non_patient(request, existing_user)
            if email_verified:
                sociallogin.user = existing_user
                self._sync_user_from_google(existing_user, sociallogin, email_verified)
                return
            messages.error(
                request,
                'An account already exists with this email address. Please sign in manually before using Google login.',
            )
            raise ImmediateHttpResponse(redirect('login'))

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        error_text = str(error or '').lower()
        if 'cancel' in error_text:
            message = 'Google sign-in was cancelled. You can continue with your email and password.'
        elif exception:
            message = 'Google sign-in is not configured correctly yet. Please check the OAuth client settings.'
        else:
            message = 'Google sign-in could not be completed. Please try again.'
        messages.error(request, message)
        raise ImmediateHttpResponse(redirect('login'))

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.role = 'patient'
        self._apply_google_profile(user, sociallogin)
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        self._sync_user_from_google(user, sociallogin, self._is_email_verified(sociallogin))
        return user

    def _sync_user_from_google(self, user, sociallogin, email_verified):
        self._block_non_patient(None, user)
        self._apply_google_profile(user, sociallogin)
        user.role = 'patient'
        if email_verified and hasattr(user, 'is_verified'):
            user.is_verified = True
        update_fields = ['first_name', 'last_name', 'role']
        if hasattr(user, 'profile_picture_url'):
            update_fields.append('profile_picture_url')
        if hasattr(user, 'is_verified'):
            update_fields.append('is_verified')
        user.save(update_fields=update_fields)
        self._sync_email_address(user, self._get_email(sociallogin), email_verified)

    def _apply_google_profile(self, user, sociallogin):
        extra_data = sociallogin.account.extra_data or {}
        name = extra_data.get('name') or ''
        if not user.first_name:
            user.first_name = extra_data.get('given_name') or name.partition(' ')[0]
        if not user.last_name:
            user.last_name = extra_data.get('family_name') or name.partition(' ')[2]
        picture = extra_data.get('picture')
        if picture and hasattr(user, 'profile_picture_url'):
            user.profile_picture_url = picture

    def _sync_email_address(self, user, email, email_verified):
        if not email:
            return
        EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={
                'primary': True,
                'verified': bool(email_verified),
            },
        )

    def _block_non_patient(self, request, user):
        if not user:
            return
        is_blocked = (
            getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) != 'patient'
        )
        if is_blocked:
            if request is not None:
                messages.error(request, self.patient_only_message)
            raise ImmediateHttpResponse(redirect('login'))

    def _get_email(self, sociallogin):
        for email_address in sociallogin.email_addresses:
            if email_address.email:
                return email_address.email
        return (sociallogin.account.extra_data or {}).get('email') or getattr(sociallogin.user, 'email', '')

    def _is_email_verified(self, sociallogin):
        if any(email_address.verified for email_address in sociallogin.email_addresses):
            return True
        value = (sociallogin.account.extra_data or {}).get('email_verified')
        return value is True or str(value).lower() == 'true'


CustomSocialAccountAdapter = MentalWellnessSocialAccountAdapter
