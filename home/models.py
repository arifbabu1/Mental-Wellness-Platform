import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
import json

from .doctor_config import (
    DEFAULT_PRIMARY_FOCUS,
    DOCTOR_PRIMARY_FOCUS_CHOICES,
    DOCTOR_SPECIALIZATION_CHOICES,
)


class User(AbstractUser):
    ROLE_CHOICES = [
        ('patient', 'Patient'),
        ('doctor', 'Doctor'),
        ('admin', 'Admin'),
    ]

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='patient')
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    profile_picture_url = models.URLField(max_length=500, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_expires = models.DateTimeField(null=True, blank=True)
    
    # OTP functionality (commented for future implementation)
    # def generate_otp(self):
    #     import random
    #     from datetime import datetime, timedelta
    #     self.otp_code = f"{random.randint(100000, 999999)}"
    #     self.otp_expires = datetime.now() + timedelta(minutes=10)
    #     self.save()
    
    def __str__(self):
        return f"{self.username} ({self.role})"


class SystemEmailConfig(models.Model):
    """Admin-managed SMTP settings for platform emails."""

    name = models.CharField(max_length=120, default='Primary website email', help_text='Admin label for this email setup.')
    email_host = models.CharField(max_length=255, help_text="SMTP host, for example smtp.gmail.com")
    email_port = models.PositiveIntegerField(default=587, validators=[MinValueValidator(1)])
    email_host_user = models.EmailField(help_text="SMTP username or Gmail address")
    email_host_password = models.CharField(
        max_length=255,
        blank=True,
        help_text="SMTP app password or provider password. Leave unchanged when editing unless rotating it.",
    )
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    default_from_email = models.EmailField(help_text="Address used as the sender for platform emails")
    receive_email = models.EmailField(blank=True, help_text='Optional mailbox used for inbound/reply handling.')
    support_email = models.EmailField(blank=True, help_text='Support contact shown in platform emails.')
    admin_notification_email = models.EmailField(blank=True, help_text='Where admin/test notifications should be sent.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', '-updated_at']
        verbose_name = 'System Email Config'
        verbose_name_plural = 'System Email Config'

    def clean(self):
        if self.use_tls and self.use_ssl:
            raise ValidationError('Use either TLS or SSL, not both.')
        if self.is_active and not self.email_host_password and not self.pk:
            raise ValidationError({'email_host_password': 'Password is required for a new active email config.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.is_active:
            SystemEmailConfig.objects.exclude(pk=self.pk).update(is_active=False)

    @classmethod
    def active(cls):
        return cls.objects.filter(is_active=True).order_by('-updated_at').first()

    @property
    def masked_password(self):
        if not self.email_host_password:
            return 'Not set'
        return 'Configured'

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f"{self.name} - {self.email_host_user} via {self.email_host} ({status})"


class PaymentReceiverAccount(models.Model):
    """Admin-managed receiving accounts for patient payments."""

    PAYMENT_METHOD_CHOICES = [
        ('card', 'Card'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('bank', 'Bank Transfer'),
    ]

    bangladesh_mobile_validator = RegexValidator(
        regex=r'^01[3-9]\d{8}$',
        message='Enter a valid Bangladesh mobile number, for example 01XXXXXXXXX.',
    )

    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50, blank=True)
    merchant_number = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    branch_name = models.CharField(max_length=150, blank=True)
    routing_number = models.CharField(max_length=30, blank=True)
    card_processor_name = models.CharField(max_length=150, blank=True)
    card_receiver_account = models.CharField(max_length=150, blank=True, help_text='Settlement account or merchant identifier for card payments.')
    # Production note: store gateway secrets in encrypted storage or environment-backed secret managers.
    api_key = models.CharField(max_length=255, blank=True, help_text="Optional provider API key. Leave unchanged unless rotating it.")
    secret_key = models.CharField(max_length=255, blank=True, help_text="Optional provider secret key. Leave unchanged unless rotating it.")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text='Use this account by default for this payment method.')
    instructions = models.TextField(blank=True, help_text='Safe public payment instructions shown to patients. Do not include secrets.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['payment_method', '-is_active', 'account_name']
        verbose_name = 'Payment Receiver Account'
        verbose_name_plural = 'Payment Receiver Accounts'

    def clean(self):
        errors = {}
        if self.payment_method in {'bkash', 'nagad'}:
            value = self.merchant_number or self.account_number
            if not value:
                errors['merchant_number'] = f'{self.get_payment_method_display()} receiver number is required.'
            else:
                self.bangladesh_mobile_validator(value)
        if self.payment_method == 'bank':
            if not self.bank_name:
                errors['bank_name'] = 'Bank name is required for bank receiving accounts.'
            if not self.account_number:
                errors['account_number'] = 'Account number is required for bank receiving accounts.'
        if self.payment_method == 'card' and not self.card_processor_name:
            errors['card_processor_name'] = 'Card processor name is required for card receiving accounts.'
        if self.is_default and not self.is_active:
            errors['is_default'] = 'A default payment receiver account must be active.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.is_default:
            self.is_active = True
        self.full_clean()
        super().save(*args, **kwargs)
        if self.is_default:
            PaymentReceiverAccount.objects.filter(
                payment_method=self.payment_method,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)

    @classmethod
    def active_for_method(cls, payment_method):
        return cls.objects.filter(payment_method=payment_method, is_active=True).order_by('-is_default', '-updated_at').first()

    @classmethod
    def default_for_method(cls, payment_method):
        return cls.active_for_method(payment_method)

    @classmethod
    def active_methods(cls):
        return list(cls.objects.filter(is_active=True).values_list('payment_method', flat=True).distinct())

    @staticmethod
    def _mask_identifier(value, prefix=3, suffix=3):
        if not value:
            return ''
        if len(value) <= prefix + suffix:
            return '*' * len(value)
        return f"{value[:prefix]}{'*' * 5}{value[-suffix:]}"

    @property
    def masked_account_number(self):
        return self._mask_identifier(self.account_number)

    @property
    def masked_merchant_number(self):
        return self._mask_identifier(self.merchant_number)

    @property
    def display_identifier(self):
        if self.payment_method in {'bkash', 'nagad'}:
            return self._mask_identifier(self.merchant_number or self.account_number)
        if self.payment_method == 'card':
            return self.card_processor_name
        return self._mask_identifier(self.account_number)

    def public_snapshot(self):
        return {
            'id': self.id,
            'payment_method': self.payment_method,
            'payment_method_display': self.get_payment_method_display(),
            'account_name': self.account_name,
            'display_identifier': self.display_identifier,
            'merchant_number_masked': self.masked_merchant_number,
            'account_number_masked': self.masked_account_number,
            'bank_name': self.bank_name,
            'branch_name': self.branch_name,
            'routing_number': self.routing_number,
            'card_processor_name': self.card_processor_name,
            'card_receiver_account': self._mask_identifier(self.card_receiver_account),
            'instructions': self.instructions,
        }

    @property
    def masked_api_key(self):
        return 'Configured' if self.api_key else 'Not set'

    @property
    def masked_secret_key(self):
        return 'Configured' if self.secret_key else 'Not set'

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f"{self.get_payment_method_display()} - {self.account_name} ({status})"


class DoctorSpecialization(models.Model):
    value = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'label']

    def __str__(self):
        return self.label


class DoctorPrimaryFocus(models.Model):
    value = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'label']
        verbose_name_plural = 'Doctor primary focuses'

    def __str__(self):
        return self.label


class Doctor(models.Model):
    SPECIALTY_CHOICES = DOCTOR_SPECIALIZATION_CHOICES
    FOCUS_CHOICES = DOCTOR_PRIMARY_FOCUS_CHOICES
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    name = models.CharField(max_length=150, default="", help_text="Doctor's full name")
    specializations = models.ManyToManyField(DoctorSpecialization, related_name='doctors')
    primary_focuses = models.ManyToManyField(DoctorPrimaryFocus, related_name='doctors')
    years_of_experience = models.IntegerField(default=0, help_text="Years of clinical experience")
    qualification = models.TextField()
    expertise_tags = models.JSONField(default=list, help_text="Clinical expertise tags (e.g., ['insomnia', 'panic-attacks'])")
    available_online = models.BooleanField(default=True, help_text="Available for online consultations")
    availability_score = models.PositiveSmallIntegerField(default=5, help_text="Availability score (0-5, 5 = available within 2 days)")
    emergency_support = models.BooleanField(default=False, help_text="Provides emergency/crisis support")
    profile_image = models.ImageField(upload_to='doctors/', null=True, blank=True)
    bio = models.TextField(default="", help_text="Professional biography")
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    clinic_name = models.CharField(max_length=255, blank=True, null=True)
    clinic_address = models.TextField(blank=True, null=True)
    license_number = models.CharField(max_length=100, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    availability_schedule = models.JSONField(default=dict, null=True, blank=True)
    
    # Enhanced tracking fields
    patients_helped = models.PositiveIntegerField(default=0, help_text="Total number of patients helped")
    success_rate = models.FloatField(default=0.0, help_text="Treatment success rate percentage")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name or f"Dr. {self.user.get_full_name()} - {self.specialty}"

    @property
    def specialization(self):
        return self.specialty

    @property
    def specialty(self):
        return ', '.join(self.specialization_labels) or 'Mental Health'

    @property
    def primary_focus(self):
        return ', '.join(self.primary_focus_labels) or DEFAULT_PRIMARY_FOCUS

    @property
    def specialization_values(self):
        if not self.pk:
            return []
        return list(self.specializations.values_list('value', flat=True))

    @property
    def specialization_labels(self):
        if not self.pk:
            return []
        return list(self.specializations.values_list('label', flat=True))

    @property
    def primary_focus_values(self):
        if not self.pk:
            return []
        return list(self.primary_focuses.values_list('value', flat=True))

    @property
    def primary_focus_labels(self):
        if not self.pk:
            return []
        return list(self.primary_focuses.values_list('label', flat=True))

    @property
    def profile_picture(self):
        return self.profile_image
    
    @property
    def match_score_data(self):
        """Calculate dynamic match score data"""
        return {
            'specialty': self.specialty,
            'specialization': self.specialization_values,
            'primary_focus': self.primary_focus_values,
            'years_of_experience': self.years_of_experience,
            'expertise_tags': self.expertise_tags,
            'patients_helped': self.patients_helped,
            'success_rate': self.success_rate,
            'availability_score': self.availability_score,
        }


class AssessmentQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('likert_scale', 'Likert Scale'),
        ('yes_no', 'Yes / No'),
        ('text', 'Text'),
    ]
    CATEGORY_CHOICES = [
        ('Depression', 'Depression'),
        ('Anxiety', 'Anxiety'),
        ('Sleep', 'Sleep'),
        ('Energy', 'Energy'),
        ('Self-esteem', 'Self-esteem'),
    ]
    
    question_text = models.TextField()
    question_text_bn = models.TextField(blank=True, default='')
    weight_value = models.IntegerField(default=1)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    track_number = models.PositiveIntegerField(default=1, help_text="Track number for calculation (1=Depression, 2=Anxiety, 3=Sleep, 4=Energy)")
    question_type = models.CharField(max_length=30, choices=QUESTION_TYPE_CHOICES, default='single_choice')
    option_choices = models.JSONField(default=list, blank=True, help_text='List of answer options with scores.')
    option_choices_bn = models.JSONField(default=list, blank=True, help_text='Bangla option labels with scores.')
    required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_core = models.BooleanField(default=False, help_text='Protected default screening question.')
    core_order = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Protected core question order from 1 to 7.')
    is_required = models.BooleanField(default=False, help_text='System-required question that should not be disabled.')
    reverse_scoring = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['core_order'],
                condition=models.Q(is_core=True),
                name='unique_core_assessment_order',
            ),
        ]
    
    def __str__(self):
        return f"{self.category}: {self.question_text[:50]}..."

    @property
    def has_bangla_translation(self):
        return bool((self.question_text_bn or '').strip())

    def get_question_text(self, lang='en'):
        if (lang or 'en').lower() == 'bn' and self.question_text_bn:
            return self.question_text_bn
        return self.question_text

    def get_option_choices(self, lang='en'):
        if (lang or 'en').lower() == 'bn' and self.option_choices_bn:
            return self.option_choices_bn
        return self.option_choices or []

    def clean(self):
        super().clean()
        if self.is_core:
            if self.core_order is None and self.track_number:
                self.core_order = self.track_number
            if self.core_order not in range(1, 8):
                raise ValidationError({'core_order': 'Core assessment question order must be between 1 and 7.'})
            duplicate_core = AssessmentQuestion.objects.filter(
                is_core=True,
                core_order=self.core_order,
            )
            if self.pk:
                duplicate_core = duplicate_core.exclude(pk=self.pk)
            if duplicate_core.exists():
                raise ValidationError({'core_order': 'Another core assessment question already uses this order.'})

    def save(self, *args, **kwargs):
        if self.is_core:
            if self.core_order is None and self.track_number:
                self.core_order = self.track_number
            self.is_active = True
            self.is_required = True
            self.required = True
            self.question_type = 'likert_scale'
            if self.core_order:
                self.track_number = self.core_order

            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {
                    'is_active',
                    'is_required',
                    'required',
                    'question_type',
                    'track_number',
                    'core_order',
                }

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_core:
            raise ValidationError('Core assessment questions cannot be deleted because they are required for patient assessment.')
        return super().delete(*args, **kwargs)
    
    @property
    def track_weight(self):
        """Get the standardized weight for this question's track"""
        track_weights = {
            'Depression': 3,
            'Anxiety': 2,
            'Sleep': 2,
            'Energy': 1,
        }
        return track_weights.get(self.category, 1)


class ClinicalAssessment(models.Model):
    """
    PHQ-9 + GAD-7 Clinical Assessment Model
    Industry-standard mental health screening tools
    """
    
    # PHQ-9 Depression Severity Levels
    DEPRESSION_SEVERITY_CHOICES = [
        ('minimal', 'Minimal'),
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('moderately_severe', 'Moderately Severe'),
        ('severe', 'Severe'),
    ]
    
    # GAD-7 Anxiety Severity Levels
    ANXIETY_SEVERITY_CHOICES = [
        ('minimal', 'Minimal'),
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('severe', 'Severe'),
    ]
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clinical_assessments')
    
    # PHQ-9 Scores (0-27)
    phq9_score = models.IntegerField(help_text="PHQ-9 depression score (0-27)")
    depression_severity = models.CharField(max_length=20, choices=DEPRESSION_SEVERITY_CHOICES)
    
    # GAD-7 Scores (0-21)
    gad7_score = models.IntegerField(help_text="GAD-7 anxiety score (0-21)")
    anxiety_severity = models.CharField(max_length=20, choices=ANXIETY_SEVERITY_CHOICES)
    
    # Primary condition determination
    primary_condition = models.CharField(max_length=20, help_text="Primary condition: Depression or Anxiety")
    
    # Emergency detection (PHQ-9 Question 9)
    emergency_risk = models.BooleanField(default=False, help_text="Suicide risk detected (Q9 >= 2)")
    suicide_risk_level = models.CharField(max_length=20, default='none', help_text="Suicide risk level")
    
    # Assessment responses (JSON storage)
    phq9_responses = models.JSONField(help_text="PHQ-9 question responses (0-3 each)")
    gad7_responses = models.JSONField(help_text="GAD-7 question responses (0-3 each)")
    
    # Metadata
    completed_at = models.DateTimeField(auto_now_add=True)
    session_duration = models.IntegerField(help_text="Time taken to complete assessment (seconds)")
    
    def __str__(self):
        return f"{self.patient.username} - PHQ-9: {self.phq9_score} ({self.depression_severity}), GAD-7: {self.gad7_score} ({self.anxiety_severity})"
    
    @property
    def requires_emergency_intervention(self):
        """Check if emergency intervention is required"""
        return self.emergency_risk or self.depression_severity == 'severe' or self.anxiety_severity == 'severe'
    
    @property
    def overall_severity_score(self):
        """Calculate overall severity score (0-100)"""
        # Normalize both scores to 0-50 scale and combine
        phq9_normalized = (self.phq9_score / 27) * 50  # PHQ-9 max is 27
        gad7_normalized = (self.gad7_score / 21) * 50  # GAD-7 max is 21
        return int(phq9_normalized + gad7_normalized)


class PatientAssessment(models.Model):
    """Legacy assessment model for backward compatibility"""
    STRESS_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
        ('severe', 'Severe'),
    ]
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='legacy_assessments')
    total_score = models.IntegerField()
    stress_level = models.CharField(max_length=10, choices=STRESS_LEVEL_CHOICES)
    recommendations = models.TextField(null=True, blank=True)
    dynamic_responses = models.JSONField(default=dict, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.patient.username} - {self.stress_level} stress (Legacy)"


class AssessmentAnswer(models.Model):
    assessment = models.ForeignKey(PatientAssessment, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE)
    answer_value = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['assessment', 'question']


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('incomplete', 'Incomplete'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    CONSULTATION_TYPE_CHOICES = [
        ('video', 'Video Consultation'),
        ('phone', 'Phone Consultation'),
        ('in_person', 'In Person'),
    ]
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='doctor_appointments')
    appointment_date = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='scheduled')
    consultation_type = models.CharField(max_length=15, choices=CONSULTATION_TYPE_CHOICES, default='video')
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(null=True, blank=True)
    meeting_id = models.CharField(max_length=255, null=True, blank=True)
    meeting_link = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.patient.username} - Dr. {self.doctor.user.get_full_name()} - {self.appointment_date}"


class Consultation(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('incomplete', 'Incomplete'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='consultation')
    room_name = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='scheduled')
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    doctor_joined_at = models.DateTimeField(null=True, blank=True)
    patient_joined_at = models.DateTimeField(null=True, blank=True)
    doctor_join_count = models.PositiveSmallIntegerField(default=0)
    patient_join_count = models.PositiveSmallIntegerField(default=0)
    doctor_last_joined_at = models.DateTimeField(null=True, blank=True)
    patient_last_joined_at = models.DateTimeField(null=True, blank=True)
    doctor_left_at = models.DateTimeField(null=True, blank=True)
    auto_complete_after_doctor_left = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    recording_url = models.URLField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Consultation for {self.appointment}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('otp_sent', 'OTP Sent'),
        ('test_paid', 'Test Paid'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    RECEIVING_ACCOUNT_CHOICES = [
        ('card', 'Card Processor'),
        ('bank', 'Bank Account'),
        ('ucb', 'UCB Bank'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('rocket', 'Rocket'),
        ('upay', 'Upay'),
        ('cash', 'Cash'),
    ]
    
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='payment')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    admin_commission = models.DecimalField(max_digits=10, decimal_places=2)
    doctor_earning = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    reference_id = models.CharField(max_length=120, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    receiving_account = models.CharField(max_length=20, choices=RECEIVING_ACCOUNT_CHOICES, null=True, blank=True, help_text="Admin account that received this payment")
    payment_receiver_account = models.ForeignKey(PaymentReceiverAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    receiver_payment_method = models.CharField(max_length=20, blank=True)
    receiver_account_snapshot = models.JSONField(default=dict, blank=True)
    wallet_number_masked = models.CharField(max_length=20, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    otp_code = models.CharField(max_length=6, blank=True)
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def calculate_commission(self, commission_rate=0.10):
        from decimal import Decimal
        commission_rate = Decimal(str(commission_rate))
        self.admin_commission = self.amount * commission_rate
        self.doctor_earning = self.amount - self.admin_commission
        self.save()

    def save(self, *args, **kwargs):
        if self.appointment_id:
            if not self.patient_id:
                self.patient_id = self.appointment.patient_id
            if not self.doctor_id:
                self.doctor_id = self.appointment.doctor_id
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Payment for {self.appointment} - {self.status}"


# Payment integration (commented for future implementation)
# class SSLCommerzPayment:
#     def __init__(self):
#         self.store_id = "your_store_id"
#         self.store_password = "your_store_password"
#         self.base_url = "https://sandbox.sslcommerz.com"
#     
#     def create_payment(self, payment):
#         # SSLCommerz integration code here
#         pass
#     
#     def verify_payment(self, transaction_id):
#         # Payment verification code here
#         pass


# Health Task and Prescription System
class HealthTaskTemplate(models.Model):
    """Predefined health tasks for doctors to use"""
    CATEGORY_CHOICES = [
        ('physical', 'Physical Activity'),
        ('diet', 'Nutrition & Diet'),
        ('medical', 'Medical Monitoring'),
        ('mental', 'Mental Wellness'),
        ('lifestyle', 'Lifestyle Habits'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    icon = models.CharField(max_length=50, default='fas fa-tasks')  # Font Awesome icon
    default_duration_days = models.IntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.title} ({self.category})"


class Prescription(models.Model):
    """Medical prescription from consultation"""
    consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name='prescription')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    patient = models.ForeignKey(User, on_delete=models.CASCADE)
    prescription_text = models.TextField()
    medications = models.JSONField(default=list)  # [{"name": "Medicine", "dosage": "500mg", "frequency": "twice daily"}]
    instructions = models.TextField()
    pdf_file = models.FileField(upload_to='prescriptions/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Prescription for {self.patient.username} - {self.created_at.date()}"


class DailyTask(models.Model):
    """Tasks assigned to patients"""
    SOURCE_CHOICES = [
        ('template', 'From Template'),
        ('custom', 'Custom Created'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    FREQUENCY_CHOICES = [
        ('once', 'Once Only'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('custom', 'Custom Days'),
    ]
    
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_tasks')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, null=True, blank=True)
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')
    
    # Task details
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20)
    icon = models.CharField(max_length=50, default='fas fa-tasks')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    
    # Duration and frequency
    start_date = models.DateField()
    end_date = models.DateField()
    duration_days = models.PositiveIntegerField(default=7)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='daily')
    recurring_days = models.JSONField(default=list)  # [1,2,3,4,5] for Mon-Fri
    
    # Completion tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(null=True, blank=True)
    
    # Reminder tracking
    reminder_times = models.JSONField(default=list)  # ["09:00", "14:00", "20:00"]
    reminders_sent = models.JSONField(default=dict)  # Track sent reminders
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} - {self.patient.username}"
    
    @property
    def is_today(self):
        from django.utils import timezone
        today = timezone.localdate()
        if self.start_date and self.end_date:
            return self.start_date <= today <= self.end_date
        return self.is_active


class TaskCompletion(models.Model):
    """Track daily completion of tasks"""
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_completions', null=True, blank=True)
    daily_task = models.ForeignKey(DailyTask, on_delete=models.CASCADE, related_name='completions')
    completion_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    patient_notes = models.TextField(null=True, blank=True)
    completion_time = models.TimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['daily_task', 'completion_date']
        verbose_name = 'Daily Task Completion'
        verbose_name_plural = 'Daily Task Completions'

    def save(self, *args, **kwargs):
        if self.daily_task_id and not self.patient_id:
            self.patient = self.daily_task.patient
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.daily_task.title} - {self.completion_date} ({'Completed' if self.is_completed else 'Incomplete'})"


class DailyTaskReminderLog(models.Model):
    """Tracks end-of-day incomplete task reminder emails."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_task_reminder_logs')
    date = models.DateField()
    email_sent_at = models.DateTimeField(auto_now_add=True)
    incomplete_tasks_count = models.PositiveIntegerField(default=0)
    incomplete_task_titles = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-date', '-email_sent_at']
        unique_together = ['user', 'date']
        verbose_name = 'Daily Task Reminder Log'
        verbose_name_plural = 'Daily Task Reminder Logs'

    def __str__(self):
        return f"{self.user.username} - {self.date} ({self.incomplete_tasks_count} incomplete)"


class Notification(models.Model):
    """System notifications for users"""
    NOTIFICATION_TYPES = [
        ('task_reminder', 'Task Reminder'),
        ('task_incomplete', 'Incomplete Task'),
        ('prescription_update', 'Prescription Update'),
        ('appointment_reminder', 'Appointment Reminder'),
        ('message', 'Message'),
        ('system', 'System Notification'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    is_actionable = models.BooleanField(default=False)
    action_url = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"


class BlogPost(models.Model):
    """Blog posts written by doctors for patients and visitors"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
    ]
    
    CATEGORY_CHOICES = [
        ('anxiety', 'Anxiety & Stress'),
        ('depression', 'Depression'),
        ('therapy', 'Therapy'),
        ('mindfulness', 'Mindfulness'),
        ('relationships', 'Relationships'),
        ('self-care', 'Self-Care'),
        ('sleep', 'Sleep Health'),
        ('workplace', 'Workplace Wellness'),
        ('mental-health', 'Mental Health Awareness'),
    ]
    
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    excerpt = models.TextField(max_length=500, help_text="Brief summary of the blog post")
    content = models.TextField(help_text="Full blog content")
    author = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='blog_posts')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='mental-health')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    
    # Media
    featured_image = models.URLField(max_length=500, blank=True, null=True, help_text="URL for featured image")
    
    # Metadata
    read_time = models.PositiveIntegerField(default=5, help_text="Estimated read time in minutes")
    views_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    
    # Publishing
    is_featured = models.BooleanField(default=False, help_text="Featured articles appear on homepage")
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-published_at', '-created_at']
        verbose_name = 'Blog Post'
        verbose_name_plural = 'Blog Posts'
    
    def __str__(self):
        return f"{self.title} by Dr. {self.author.user.get_full_name()}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while BlogPost.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        # Auto-calculate read time based on content length (average 200 words per minute)
        word_count = len(self.content.split())
        self.read_time = max(1, round(word_count / 200))
        
        super().save(*args, **kwargs)
    
    def publish(self):
        """Publish the blog post"""
        from django.utils import timezone
        self.status = 'published'
        self.published_at = timezone.now()
        self.save()
    
    def increment_views(self):
        """Increment view count"""
        self.views_count += 1
        self.save(update_fields=['views_count'])


class ChatbotKnowledgeChunk(models.Model):
    """Searchable platform knowledge used by the emergency chatbot RAG pipeline."""

    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=160)
    chunk_index = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    embedding = models.JSONField(default=list)
    embedding_model = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['source_type', 'source_id', 'chunk_index']
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['content_hash']),
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_id}#{self.chunk_index}"


class ChatSession(models.Model):
    """Session-scoped memory for the emergency AI assistant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_sessions')
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    language = models.CharField(max_length=10, default='en')
    title = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_activity_at']

    def __str__(self):
        return self.title or f"Chat session {self.pk}"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    category = models.CharField(max_length=40, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"


class EmergencyLog(models.Model):
    """Audit trail for high-risk chatbot messages."""

    RISK_CHOICES = [
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='emergency_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='emergency_logs')
    message = models.TextField()
    detected_terms = models.JSONField(default=list, blank=True)
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='high')
    recommended_action = models.CharField(max_length=255, default='Immediate professional support')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['risk_level', 'created_at']),
        ]

    def __str__(self):
        return f"{self.risk_level} emergency log at {self.created_at}"


class DoctorSchedule(models.Model):
    """Doctor availability schedule - defines when doctors are available for appointments"""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    slot_duration = models.PositiveIntegerField(default=30, help_text="Duration of each appointment slot in minutes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ['doctor', 'day_of_week', 'start_time']
        verbose_name = 'Doctor Schedule'
        verbose_name_plural = 'Doctor Schedules'
    
    def __str__(self):
        day_name = dict(self.DAY_CHOICES)[self.day_of_week]
        return f"Dr. {self.doctor.user.get_full_name()} - {day_name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time >= self.end_time:
            raise ValidationError('Start time must be before end time')
    
    def get_time_slots(self):
        """Generate available time slots based on slot_duration"""
        from datetime import datetime, timedelta
        slots = []
        current = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        
        while current + timedelta(minutes=self.slot_duration) <= end:
            slot_time = current.time()
            slots.append(slot_time.strftime('%H:%M'))
            current += timedelta(minutes=self.slot_duration)
        
        return slots


class BookedSlot(models.Model):
    """Tracks which time slots are already booked"""
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='booked_slots')
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='booked_slot')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['appointment_date', 'appointment_time']
        unique_together = ['doctor', 'appointment_date', 'appointment_time']
        verbose_name = 'Booked Slot'
        verbose_name_plural = 'Booked Slots'
    
    def __str__(self):
        return f"Dr. {self.doctor.user.get_full_name()} - {self.appointment_date} {self.appointment_time.strftime('%H:%M')}"
