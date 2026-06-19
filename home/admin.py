from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.contrib import messages
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.contrib.admin.sites import NotRegistered
from django.utils.html import format_html
import re
from .models import (
    User, Doctor, AssessmentQuestion, PatientAssessment, 
    AssessmentAnswer, Appointment, Consultation, Payment,
    DoctorSpecialization, DoctorPrimaryFocus,
    ChatSession, ChatMessage, EmergencyLog, ChatbotKnowledgeChunk,
    SystemEmailConfig, PaymentReceiverAccount,
    BlogPost, BookedSlot, ClinicalAssessment, DailyTask, DailyTaskReminderLog,
    DoctorSchedule, HealthTaskTemplate, Notification, Prescription, TaskCompletion,
)
from .assessment_core import CORE_ASSESSMENT_WARNING
from .system_config import get_admin_notification_email, get_email_connection_kwargs

admin.site.site_header = 'Mental Wellness Platform Admin'
admin.site.site_title = 'Mental Wellness Platform Admin'
admin.site.index_title = 'Model Console'
admin.site.enable_nav_sidebar = True


def _unregister_if_registered(model):
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass


# Keep the admin sidebar focused on operational platform models. These defaults are
# still available to Django internally; they are just hidden from the care console.
_unregister_if_registered(Group)
_unregister_if_registered(Site)
try:
    from allauth.account.models import EmailAddress
    from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
    for _model in (EmailAddress, SocialAccount, SocialApp, SocialToken):
        _unregister_if_registered(_model)
except Exception:
    pass


def status_badge(label, color='blue'):
    palette = {
        'green': ('#047857', '#ecfdf5', '#bbf7d0'),
        'red': ('#b91c1c', '#fef2f2', '#fecaca'),
        'amber': ('#92400e', '#fffbeb', '#fde68a'),
        'blue': ('#0369a1', '#eff6ff', '#bfdbfe'),
        'gray': ('#475569', '#f8fafc', '#cbd5e1'),
    }
    fg, bg, border = palette.get(color, palette['blue'])
    return format_html(
        '<span class="admin-status-badge" style="color:{};background:{};border-color:{};">{}</span>',
        fg,
        bg,
        border,
        label,
    )


class OptimizedAdminMixin:
    list_per_page = 25
    save_on_top = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        select_related = getattr(self, 'list_select_related', None)
        if select_related:
            return queryset.select_related(*select_related) if isinstance(select_related, (tuple, list)) else queryset
        return queryset


class SuperuserOnlyAdminMixin:
    """Limit sensitive platform settings to superusers."""

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser


class PreserveSecretModelForm(forms.ModelForm):
    secret_field_names = ()

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk:
            for field_name in self.secret_field_names:
                if field_name in self.fields and not cleaned_data.get(field_name):
                    cleaned_data[field_name] = getattr(self.instance, field_name)
        return cleaned_data


class SystemEmailConfigAdminForm(PreserveSecretModelForm):
    secret_field_names = ('email_host_password',)

    class Meta:
        model = SystemEmailConfig
        fields = '__all__'
        widgets = {
            'email_host_password': forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        }


class PaymentReceiverAccountAdminForm(PreserveSecretModelForm):
    secret_field_names = ('api_key', 'secret_key')

    class Meta:
        model = PaymentReceiverAccount
        fields = '__all__'
        widgets = {
            'api_key': forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
            'secret_key': forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        }


@admin.register(SystemEmailConfig)
class SystemEmailConfigAdmin(SuperuserOnlyAdminMixin, OptimizedAdminMixin, admin.ModelAdmin):
    form = SystemEmailConfigAdminForm
    list_display = ('name', 'email_host_user', 'email_host', 'email_port', 'default_from_email', 'active_badge', 'security_mode', 'updated_at')
    list_filter = ('is_active', 'use_tls', 'use_ssl', 'updated_at')
    search_fields = ('name', 'email_host', 'email_host_user', 'default_from_email', 'support_email', 'admin_notification_email')
    readonly_fields = ('created_at', 'updated_at', 'masked_password')
    actions = ('activate_configs', 'send_test_email')

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'is_active')
        }),
        ('SMTP Connection', {
            'fields': ('email_host', 'email_port', 'email_host_user', 'email_host_password', 'masked_password'),
            'description': 'Use a provider app password for Gmail/SMTP. Secrets are hidden in list views and preserved when left blank on edit.',
        }),
        ('Sender and Routing', {
            'fields': ('default_from_email', 'receive_email', 'support_email', 'admin_notification_email')
        }),
        ('Security', {
            'fields': ('use_tls', 'use_ssl')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Password')
    def masked_password(self, obj):
        if not obj:
            return 'Not set'
        return obj.masked_password

    @admin.display(description='Status')
    def active_badge(self, obj):
        if obj.is_active:
            return status_badge('Active', 'green')
        return status_badge('Inactive', 'gray')

    @admin.display(description='Security')
    def security_mode(self, obj):
        if obj.use_ssl:
            return 'SSL'
        if obj.use_tls:
            return 'TLS'
        return 'None'

    @admin.action(description='Activate selected email config')
    def activate_configs(self, request, queryset):
        selected = queryset.first()
        if not selected:
            self.message_user(request, 'Select an email config to activate.', messages.WARNING)
            return
        selected.is_active = True
        selected.save()
        self.message_user(request, f'Activated email config for {selected.email_host_user}.')

    @admin.action(description='Send test email to my admin email')
    def send_test_email(self, request, queryset):
        config = queryset.first() or SystemEmailConfig.active()
        if not config:
            self.message_user(request, 'No email config is available to test.', messages.ERROR)
            return
        recipient = get_admin_notification_email(config, request.user)
        if not recipient:
            self.message_user(request, 'No admin notification email or admin account email is available for the test.', messages.ERROR)
            return
        try:
            connection = None
            kwargs = get_email_connection_kwargs(config)
            if kwargs:
                from django.core.mail import get_connection
                connection = get_connection(**kwargs)
            send_mail(
                'Mental Wellness Platform email test',
                'Your admin-managed email configuration is working.',
                config.default_from_email,
                [recipient],
                fail_silently=False,
                connection=connection,
            )
        except Exception as exc:
            self.message_user(request, f'Test email failed: {exc}', messages.ERROR)
            return
        self.message_user(request, f'Test email sent to {recipient}.')


@admin.register(PaymentReceiverAccount)
class PaymentReceiverAccountAdmin(SuperuserOnlyAdminMixin, OptimizedAdminMixin, admin.ModelAdmin):
    form = PaymentReceiverAccountAdminForm
    list_display = ('payment_method', 'account_name', 'display_identifier', 'active_badge', 'default_badge', 'masked_api_key', 'masked_secret_key', 'updated_at')
    list_filter = ('payment_method', 'is_active', 'is_default', 'updated_at')
    search_fields = ('account_name', 'account_number', 'merchant_number', 'bank_name', 'card_processor_name')
    readonly_fields = ('created_at', 'updated_at', 'masked_account_number', 'masked_merchant_number', 'masked_api_key', 'masked_secret_key')
    actions = ('activate_accounts', 'deactivate_accounts')

    fieldsets = (
        ('Basic Info', {
            'fields': ('payment_method', 'account_name')
        }),
        ('Account Details', {
            'fields': (
                'merchant_number', 'masked_merchant_number',
                'account_number', 'masked_account_number',
                'bank_name', 'branch_name', 'routing_number',
                'card_processor_name', 'card_receiver_account',
            ),
            'description': 'Enter the receiver details relevant to this method. Public pages use masked identifiers only.',
        }),
        ('Gateway/API Credentials', {
            'fields': ('api_key', 'secret_key', 'masked_api_key', 'masked_secret_key'),
            'classes': ('collapse',),
            'description': 'Optional credentials for a future gateway integration. Keep production secrets in encrypted or environment-backed storage.',
        }),
        ('Status', {
            'fields': ('is_active', 'is_default')
        }),
        ('Instructions', {
            'fields': ('instructions',),
            'description': 'Safe public payment instructions. Do not include API keys, passwords, PINs, or private credentials.',
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Status')
    def active_badge(self, obj):
        if obj.is_active:
            return status_badge('Active', 'green')
        return status_badge('Inactive', 'red')

    @admin.display(description='Default')
    def default_badge(self, obj):
        if obj.is_default:
            return status_badge('Default', 'blue')
        return status_badge('No', 'gray')

    @admin.display(description='Account number')
    def masked_account_number(self, obj):
        if not obj:
            return 'Not set'
        return obj.masked_account_number or 'Not set'

    @admin.display(description='Merchant number')
    def masked_merchant_number(self, obj):
        if not obj:
            return 'Not set'
        return obj.masked_merchant_number or 'Not set'

    @admin.display(description='API key')
    def masked_api_key(self, obj):
        if not obj:
            return 'Not set'
        return obj.masked_api_key

    @admin.display(description='Secret key')
    def masked_secret_key(self, obj):
        if not obj:
            return 'Not set'
        return obj.masked_secret_key

    @admin.action(description='Activate selected payment accounts')
    def activate_accounts(self, request, queryset):
        count = 0
        for account in queryset:
            account.is_active = True
            account.save()
            count += 1
        self.message_user(request, f'Activated {count} payment receiver account(s).')

    @admin.action(description='Deactivate selected payment accounts')
    def deactivate_accounts(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {count} payment receiver account(s).')


class DoctorInline(admin.StackedInline):
    """Inline admin for Doctor model"""
    model = Doctor
    can_delete = False
    verbose_name_plural = 'Doctor Profile'
    fields = (
        'specializations', 'primary_focuses', 'qualification', 'years_of_experience',
        'consultation_fee', 'clinic_name', 'clinic_address',
        'license_number', 'bio', 'is_available'
    )
    filter_horizontal = ('specializations', 'primary_focuses')
    
    def get_fields(self, request, obj=None):
        if obj and hasattr(obj, 'doctor_profile'):
            return self.fields
        return ()


class DoctorUserCreationForm(UserCreationForm):
    """Custom form for creating a doctor user with basic info"""
    
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'phone', 'first_name', 'last_name', 'age', 'gender', 'role')
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Choose a unique username'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email address'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Phone number'}),
            'age': forms.NumberInput(attrs={'placeholder': 'Age'}),
        }
    
    # Add doctor profile fields as form fields
    specialization = forms.ModelMultipleChoiceField(
        queryset=DoctorSpecialization.objects.filter(is_active=True),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label='Specializations'
    )
    qualification = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g., MBBS, MD (Psychiatry), FCPS'})
    )
    years_of_experience = forms.IntegerField(
        min_value=0,
        max_value=50,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': 'Years of experience'})
    )
    consultation_fee = forms.DecimalField(
        max_digits=10, 
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Consultation fee in Taka'})
    )
    clinic_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Clinic or hospital name (optional)'})
    )
    clinic_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Clinic address (optional)'})
    )
    license_number = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Medical license number (optional)'})
    )
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Brief professional summary and focus areas (optional)'})
    )
    focus_areas = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'e.g., Depression, Anxiety, Bipolar Disorder (optional)'})
    )
    primary_focus = forms.ModelMultipleChoiceField(
        queryset=DoctorPrimaryFocus.objects.filter(is_active=True),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label='Primary Focus'
    )
    languages = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Bengali, English, Hindi'})
    )
    is_available = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add placeholders for password fields
        self.fields['password1'].widget = forms.PasswordInput(attrs={'placeholder': 'Enter password'})
        self.fields['password2'].widget = forms.PasswordInput(attrs={'placeholder': 'Confirm password'})
        
        # Set role to doctor and hide it
        self.fields['role'].initial = 'doctor'
        self.fields['role'].widget = forms.HiddenInput()
        
        # Reorder fields to ensure proper order
        field_order = [
            'username', 'first_name', 'last_name', 'email', 'phone', 'age', 'gender',
            'password1', 'password2', 'role',
            'specialization', 'primary_focus', 'qualification', 'years_of_experience',
            'consultation_fee', 'clinic_name', 'clinic_address',
            'license_number', 'bio', 'focus_areas',
            'languages', 'is_available'
        ]
        self.fields = {field: self.fields[field] for field in field_order if field in self.fields}
    
    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            # Check for at least 1 numeric number
            if not re.search(r'\d', password):
                raise ValidationError("Password must contain at least 1 numeric number.")
            
            # Check for at least 1 special character (@, +, -, #, $, %)
            if not re.search(r'[@+\-#$%]', password):
                raise ValidationError("Password must contain at least 1 special character (@, +, -, #, $, %).")
        return password
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'doctor'
        user.is_verified = True  # Auto-verify doctors added by admin
        
        # Extract doctor data before saving
        doctor_data = {
            'qualification': self.cleaned_data.get('qualification'),
            'years_of_experience': self.cleaned_data.get('years_of_experience'),
            'consultation_fee': self.cleaned_data.get('consultation_fee'),
            'clinic_name': self.cleaned_data.get('clinic_name'),
            'clinic_address': self.cleaned_data.get('clinic_address'),
            'license_number': self.cleaned_data.get('license_number'),
            'bio': self.cleaned_data.get('bio', ''),
            'is_available': self.cleaned_data.get('is_available', True),
            'availability_schedule': {
                'focus_areas': self.cleaned_data.get('focus_areas', ''),
                'languages': self.cleaned_data.get('languages', '')
            }
        }
        
        if commit:
            user.save()
            # Create doctor profile
            doctor = Doctor.objects.create(user=user, **doctor_data)
            doctor.specializations.set(self.cleaned_data.get('specialization'))
            doctor.primary_focuses.set(self.cleaned_data.get('primary_focus'))
        return user


class DoctorUserAdmin(BaseUserAdmin):
    """Custom admin for creating doctor users"""
    
    add_form = DoctorUserCreationForm
    inlines = [DoctorInline]
    
    add_fieldsets = (
        ('Create Doctor Account', {
            'classes': ('wide',),
            'fields': (
                'username', 'first_name', 'last_name', 'email', 'phone',
                'password1', 'password2', 'role',
                'specialization', 'primary_focus', 'qualification', 'years_of_experience',
                'consultation_fee', 'clinic_name', 'clinic_address',
                'license_number', 'bio', 'focus_areas',
                'languages', 'is_available'
            ),
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            kwargs['form'] = DoctorUserCreationForm
        return super().get_form(request, obj, **kwargs)


def _doctor_profile_defaults_from_form(form):
    return {
        'qualification': form.cleaned_data.get('qualification'),
        'years_of_experience': form.cleaned_data.get('years_of_experience'),
        'consultation_fee': form.cleaned_data.get('consultation_fee') or 0,
        'clinic_name': form.cleaned_data.get('clinic_name'),
        'clinic_address': form.cleaned_data.get('clinic_address'),
        'license_number': form.cleaned_data.get('license_number'),
        'bio': form.cleaned_data.get('bio', ''),
        'is_available': form.cleaned_data.get('is_available', True),
        'availability_schedule': {
            'focus_areas': form.cleaned_data.get('focus_areas', ''),
            'languages': form.cleaned_data.get('languages', ''),
        },
    }


def _save_doctor_profile_from_form(user, form):
    doctor_data = _doctor_profile_defaults_from_form(form)
    doctor, created = Doctor.objects.get_or_create(user=user, defaults=doctor_data)
    if not created:
        for field, value in doctor_data.items():
            setattr(doctor, field, value)
        doctor.save()
    doctor.specializations.set(form.cleaned_data.get('specialization'))
    doctor.primary_focuses.set(form.cleaned_data.get('primary_focus'))
    return doctor


# Register User admin with doctor creation capabilities
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'phone', 'role_badge', 'age', 'gender', 'verified_badge', 'date_joined')
    list_filter = ('role', 'is_verified', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'phone', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    list_per_page = 25
    date_hierarchy = 'date_joined'
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'age', 'gender', 'profile_picture_url')}),
        ('Permissions', {'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        ('Create New User', {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email', 'phone', 'age', 'gender', 'password1', 'password2', 'role'),
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        # Use the doctor creation form when role is doctor
        if not obj and request.GET.get('role') == 'doctor':
            kwargs['form'] = DoctorUserCreationForm
        return super().get_form(request, obj, **kwargs)
    
    def get_fieldsets(self, request, obj=None):
        if not obj and request.GET.get('role') == 'doctor':
            return (
                ('Create Doctor Account', {
                    'fields': (
                        'username', 'first_name', 'last_name', 'email', 'phone', 'age', 'gender',
                        'password1', 'password2', 'role',
                        'specialization', 'primary_focus', 'qualification', 'years_of_experience',
                        'consultation_fee', 'clinic_name', 'clinic_address',
                        'license_number', 'bio', 'focus_areas',
                        'languages', 'is_available'
                    ),
                }),
            )
        # For regular user creation, show role selection
        if not obj:
            return (
                ('Create New User', {
                    'classes': ('wide',),
                    'fields': ('username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2', 'role'),
                }),
            )
        fieldsets = super().get_fieldsets(request, obj)
        if not request.user.is_superuser:
            return (
                (None, {'fields': ('username', 'password')}),
                ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'age', 'gender', 'profile_picture_url')}),
                ('Status', {'fields': ('role', 'is_verified', 'is_active')}),
                ('Important dates', {'fields': ('last_login', 'date_joined')}),
            )
        return fieldsets

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and isinstance(form, DoctorUserCreationForm):
            _save_doctor_profile_from_form(obj, form)

    @admin.display(description='Role', ordering='role')
    def role_badge(self, obj):
        colors = {'admin': 'red', 'doctor': 'blue', 'patient': 'green'}
        return status_badge(obj.get_role_display(), colors.get(obj.role, 'gray'))

    @admin.display(description='Verified', ordering='is_verified')
    def verified_badge(self, obj):
        return status_badge('Verified', 'green') if obj.is_verified else status_badge('Pending', 'amber')


@admin.register(Doctor)
class DoctorAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('doctor_name', 'specialization_list', 'primary_focus_list', 'years_of_experience', 'consultation_fee', 'clinic_name', 'availability_badge', 'created_at')
    list_filter = ('specializations', 'primary_focuses', 'is_available', 'created_at')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'specializations__label', 'primary_focuses__label', 'clinic_name')
    ordering = ('-created_at',)
    filter_horizontal = ('specializations', 'primary_focuses')
    list_select_related = ('user',)
    autocomplete_fields = ('user',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'name', 'specializations', 'primary_focuses', 'qualification', 'years_of_experience', 'license_number')
        }),
        ('Professional Details', {
            'fields': ('consultation_fee', 'clinic_name', 'clinic_address', 'bio', 'is_available', 'available_online', 'availability_score', 'emergency_support')
        }),
        ('Additional Information', {
            'fields': ('availability_schedule', 'profile_image'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at',)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing object
            return self.readonly_fields + ('user',)
        return self.readonly_fields

    def specialization_list(self, obj):
        return obj.specialty
    specialization_list.short_description = 'Specializations'

    def primary_focus_list(self, obj):
        return obj.primary_focus
    primary_focus_list.short_description = 'Primary Focus'

    @admin.display(description='Doctor', ordering='user__first_name')
    def doctor_name(self, obj):
        return obj.name or obj.user.get_full_name() or obj.user.username

    @admin.display(description='Availability', ordering='is_available')
    def availability_badge(self, obj):
        return status_badge('Available', 'green') if obj.is_available else status_badge('Unavailable', 'gray')


@admin.register(DoctorSpecialization)
class DoctorSpecializationAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('label', 'value', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label', 'value')
    ordering = ('sort_order', 'label')


@admin.register(DoctorPrimaryFocus)
class DoctorPrimaryFocusAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('label', 'value', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label', 'value')
    ordering = ('sort_order', 'label')


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('role', 'content', 'category', 'metadata', 'created_at')
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'user', 'language', 'title', 'last_activity_at', 'created_at')
    list_filter = ('language', 'created_at', 'last_activity_at')
    search_fields = ('id', 'user__username', 'title', 'session_key')
    readonly_fields = ('id', 'created_at', 'last_activity_at')
    inlines = [ChatMessageInline]
    autocomplete_fields = ('user',)


@admin.register(EmergencyLog)
class EmergencyLogAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('risk_level', 'user', 'created_at', 'recommended_action')
    list_filter = ('risk_level', 'created_at')
    search_fields = ('message', 'user__username', 'recommended_action')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user', 'session')


@admin.register(ChatbotKnowledgeChunk)
class ChatbotKnowledgeChunkAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('source_type', 'source_id', 'chunk_index', 'title', 'embedding_model', 'updated_at')
    list_filter = ('source_type', 'embedding_model', 'updated_at')
    search_fields = ('title', 'content', 'source_id')
    readonly_fields = ('updated_at',)


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('question_text', 'bangla_status_badge', 'question_group_badge', 'core_badge', 'category', 'track_number', 'core_order', 'option_count', 'weight_value', 'active_badge', 'created_at')
    list_filter = ('is_core', 'is_active', 'required', 'is_required', 'category', 'question_type', 'created_at')
    search_fields = ('question_text', 'question_text_bn', 'category')
    ordering = ('track_number', 'id')
    
    fieldsets = (
        ('Question Basic Information', {
            'fields': ('question_text', 'question_text_bn', 'category', 'question_type', 'weight_value', 'track_number', 'is_core', 'core_order')
        }),
        ('Status and Scoring Controls', {
            'fields': ('required', 'is_required', 'is_active', 'reverse_scoring')
        }),
        ('Answer Options and Scores', {
            'fields': ('option_choices', 'option_choices_bn'),
            'description': 'Store option rows as JSON using option_text, score, and option_order. Standard scoring is Never=0, Rarely=1, Sometimes=2, Often=3, Always=4.'
        }),
    )

    @admin.display(description='Group', ordering='track_number')
    def question_group_badge(self, obj):
        if obj.track_number <= 7:
            return status_badge('General', 'green')
        return status_badge('Dynamic', 'amber')

    @admin.display(description='Bangla', ordering='question_text_bn')
    def bangla_status_badge(self, obj):
        return status_badge('Translated' if obj.question_text_bn else 'Missing', 'green' if obj.question_text_bn else 'amber')

    @admin.display(description='Options')
    def option_count(self, obj):
        return len(obj.option_choices or [])

    @admin.display(description='Core', ordering='is_core')
    def core_badge(self, obj):
        return status_badge('Core' if obj.is_core else 'Editable', 'red' if obj.is_core else 'blue')

    @admin.display(description='Status', ordering='is_active')
    def active_badge(self, obj):
        return status_badge('Active' if obj.is_active else 'Inactive', 'green' if obj.is_active else 'gray')

    def save_model(self, request, obj, form, change):
        if obj.is_core and not obj.is_active:
            obj.is_active = True
            messages.warning(request, 'Core assessment questions must remain active.')
        if obj.is_core:
            obj.required = True
            obj.is_required = True
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.is_core:
            messages.warning(request, CORE_ASSESSMENT_WARNING)
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        core_count = queryset.filter(is_core=True).count()
        if core_count:
            messages.warning(request, CORE_ASSESSMENT_WARNING)
        super().delete_queryset(request, queryset.filter(is_core=False))


class AssessmentAnswerInline(admin.TabularInline):
    model = AssessmentAnswer
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(PatientAssessment)
class PatientAssessmentAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('patient', 'total_score', 'stress_badge', 'created_at')
    list_filter = ('stress_level', 'created_at')
    search_fields = ('patient__username', 'patient__email')
    ordering = ('-created_at',)
    inlines = [AssessmentAnswerInline]
    autocomplete_fields = ('patient',)
    date_hierarchy = 'created_at'
    list_select_related = ('patient',)
    
    fieldsets = (
        ('Assessment Details', {
            'fields': ('patient', 'total_score', 'stress_level', 'recommendations', 'dynamic_responses', 'result_summary')
        }),
    )
    
    readonly_fields = ('created_at',)

    @admin.display(description='Stress level', ordering='stress_level')
    def stress_badge(self, obj):
        colors = {'low': 'green', 'moderate': 'blue', 'high': 'amber', 'severe': 'red'}
        return status_badge(obj.get_stress_level_display(), colors.get(obj.stress_level, 'gray'))


@admin.register(Appointment)
class AppointmentAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'appointment_date', 'status_badge', 'consultation_fee', 'created_at')
    list_filter = ('status', 'consultation_type', 'appointment_date', 'created_at')
    search_fields = ('patient__username', 'doctor__user__username')
    ordering = ('-appointment_date',)
    list_select_related = ('patient', 'doctor__user')
    autocomplete_fields = ('patient', 'doctor')
    date_hierarchy = 'appointment_date'
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient', 'doctor', 'appointment_date', 'status', 'notes')
        }),
        ('Financial Details', {
            'fields': ('consultation_fee',)
        }),
        ('Meeting', {
            'fields': ('meeting_id', 'meeting_link'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {
            'confirmed': 'green',
            'scheduled': 'blue',
            'pending_payment': 'amber',
            'cancelled': 'red',
            'completed': 'green',
            'incomplete': 'red',
            'expired': 'gray',
        }
        return status_badge(obj.get_status_display(), colors.get(obj.status, 'gray'))


@admin.register(Consultation)
class ConsultationAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('appointment', 'room_name', 'status_badge', 'start_time', 'end_time', 'created_at')
    list_filter = ('status', 'start_time', 'created_at')
    search_fields = ('appointment__patient__username', 'appointment__doctor__user__username', 'room_name')
    ordering = ('-created_at',)
    list_select_related = ('appointment__patient', 'appointment__doctor__user')
    autocomplete_fields = ('appointment',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Consultation Details', {
            'fields': ('appointment', 'room_name', 'status', 'start_time', 'end_time')
        }),
        ('Join Tracking', {
            'fields': ('doctor_joined_at', 'patient_joined_at', 'started_at', 'completed_at', 'expired_at', 'last_activity_at'),
            'classes': ('collapse',),
        }),
        ('Additional Information', {
            'fields': ('recording_url', 'notes')
        }),
    )
    
    readonly_fields = ('created_at',)

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {'scheduled': 'blue', 'waiting': 'amber', 'in_progress': 'green', 'completed': 'green', 'expired': 'gray', 'cancelled': 'red', 'incomplete': 'red'}
        return status_badge(obj.get_status_display(), colors.get(obj.status, 'gray'))


@admin.register(Payment)
class PaymentAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('appointment', 'patient', 'doctor', 'amount', 'admin_commission', 'doctor_earning', 'status_badge', 'payment_method', 'payment_receiver_account', 'paid_at', 'created_at')
    list_filter = ('status', 'payment_method', 'receiver_payment_method', 'payment_receiver_account', 'paid_at', 'created_at')
    search_fields = (
        'appointment__patient__username',
        'patient__username',
        'doctor__user__username',
        'transaction_id',
        'reference_id',
        'payment_receiver_account__account_name',
        'wallet_number_masked',
        'card_last4',
    )
    ordering = ('-created_at',)
    list_select_related = ('appointment__patient', 'appointment__doctor__user', 'patient', 'doctor__user', 'payment_receiver_account')
    autocomplete_fields = ('appointment', 'patient', 'doctor', 'payment_receiver_account')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Payment Details', {
            'fields': (
                'appointment', 'patient', 'doctor', 'amount', 'status',
                'transaction_id', 'reference_id', 'payment_method', 'receiving_account', 'paid_at',
            )
        }),
        ('Receiver Account', {
            'fields': ('payment_receiver_account', 'receiver_payment_method', 'receiver_account_snapshot')
        }),
        ('Safe Payment Metadata', {
            'fields': ('wallet_number_masked', 'card_last4', 'otp_verified_at')
        }),
        ('Financial Breakdown', {
            'fields': ('admin_commission', 'doctor_earning')
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'otp_verified_at', 'receiver_account_snapshot')
    
    actions = ['calculate_commissions']
    
    def calculate_commissions(self, request, queryset):
        for payment in queryset:
            payment.calculate_commission()
        self.message_user(request, f"Commissions calculated for {queryset.count()} payments.")
    calculate_commissions.short_description = "Calculate commissions for selected payments"

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {'test_paid': 'green', 'completed': 'green', 'otp_sent': 'amber', 'pending': 'amber', 'failed': 'red', 'cancelled': 'red', 'refunded': 'gray'}
        return status_badge(obj.get_status_display(), colors.get(obj.status, 'gray'))


@admin.register(ClinicalAssessment)
class ClinicalAssessmentAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('patient', 'primary_condition', 'phq9_score', 'gad7_score', 'risk_badge', 'completed_at')
    list_filter = ('primary_condition', 'depression_severity', 'anxiety_severity', 'emergency_risk', 'completed_at')
    search_fields = ('patient__username', 'patient__email', 'primary_condition')
    readonly_fields = ('completed_at',)
    autocomplete_fields = ('patient',)
    list_select_related = ('patient',)
    ordering = ('-completed_at',)
    date_hierarchy = 'completed_at'

    fieldsets = (
        ('Patient and Scores', {
            'fields': ('patient', 'primary_condition', 'phq9_score', 'gad7_score', 'session_duration'),
        }),
        ('Severity', {
            'fields': ('depression_severity', 'anxiety_severity', 'emergency_risk', 'suicide_risk_level'),
        }),
        ('Responses', {
            'fields': ('phq9_responses', 'gad7_responses'),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('completed_at',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Risk', ordering='emergency_risk')
    def risk_badge(self, obj):
        if obj.emergency_risk:
            return status_badge('Emergency', 'red')
        return status_badge('Standard', 'green')


@admin.register(BlogPost)
class BlogPostAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status_badge', 'is_featured', 'published_at', 'views_count')
    list_filter = ('status', 'category', 'is_featured', 'published_at', 'created_at')
    search_fields = ('title', 'excerpt', 'content', 'author__user__username', 'author__user__email')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('author',)
    readonly_fields = ('created_at', 'updated_at', 'published_at', 'views_count', 'likes_count')
    list_select_related = ('author__user',)
    ordering = ('-published_at', '-created_at')
    date_hierarchy = 'published_at'

    fieldsets = (
        ('Article', {
            'fields': ('author', 'title', 'slug', 'excerpt', 'content', 'category', 'featured_image'),
        }),
        ('Publishing', {
            'fields': ('status', 'is_featured', 'published_at'),
        }),
        ('Metrics', {
            'fields': ('read_time', 'views_count', 'likes_count'),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {'published': 'green', 'pending': 'amber', 'draft': 'gray', 'rejected': 'red'}
        return status_badge(obj.get_status_display(), colors.get(obj.status, 'gray'))


@admin.register(Notification)
class NotificationAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'read_badge', 'is_actionable', 'created_at')
    list_filter = ('notification_type', 'is_read', 'is_actionable', 'created_at')
    search_fields = ('title', 'message', 'user__username', 'user__email')
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at',)
    list_select_related = ('user',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Read', ordering='is_read')
    def read_badge(self, obj):
        return status_badge('Read', 'gray') if obj.is_read else status_badge('Unread', 'amber')


@admin.register(HealthTaskTemplate)
class HealthTaskTemplateAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'default_duration_days', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('title', 'description', 'category')
    ordering = ('category', 'title')
    date_hierarchy = 'created_at'


@admin.register(Prescription)
class PrescriptionAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'consultation', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('patient__username', 'patient__email', 'doctor__user__username', 'prescription_text', 'instructions')
    autocomplete_fields = ('patient', 'doctor', 'consultation')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('patient', 'doctor__user', 'consultation')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Assignment', {
            'fields': ('patient', 'doctor', 'consultation', 'is_active'),
        }),
        ('Prescription', {
            'fields': ('prescription_text', 'medications', 'instructions', 'pdf_file'),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('doctor', 'day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_available')
    list_filter = ('day_of_week', 'is_available', 'slot_duration')
    search_fields = ('doctor__user__username', 'doctor__user__email', 'doctor__name')
    autocomplete_fields = ('doctor',)
    list_select_related = ('doctor__user',)
    ordering = ('doctor__user__first_name', 'day_of_week', 'start_time')


@admin.register(BookedSlot)
class BookedSlotAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('doctor', 'appointment_date', 'appointment_time', 'appointment', 'is_active', 'created_at')
    list_filter = ('appointment_date', 'is_active', 'created_at')
    search_fields = ('doctor__user__username', 'appointment__patient__username')
    autocomplete_fields = ('doctor', 'appointment')
    readonly_fields = ('created_at',)
    list_select_related = ('doctor__user', 'appointment__patient')
    ordering = ('-appointment_date', 'appointment_time')
    date_hierarchy = 'appointment_date'


@admin.register(DailyTask)
class DailyTaskAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = (
        'title', 'patient', 'doctor', 'consultation', 'is_active',
        'start_date', 'end_date', 'created_at',
    )
    list_filter = ('is_active', 'category', 'frequency', 'start_date', 'end_date', 'created_at')
    search_fields = (
        'title', 'description',
        'patient__username', 'patient__email',
        'doctor__user__username', 'doctor__user__email',
        'consultation__room_name',
    )
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    autocomplete_fields = ('patient', 'doctor', 'consultation', 'prescription')
    actions = ('activate_tasks', 'deactivate_tasks')
    ordering = ('-created_at',)
    list_select_related = ('patient', 'doctor__user', 'consultation', 'prescription')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Assignment', {
            'fields': ('patient', 'doctor', 'consultation', 'prescription', 'is_active'),
        }),
        ('Task Details', {
            'fields': ('title', 'description', 'category', 'icon', 'source'),
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date', 'frequency', 'recurring_days', 'reminder_times'),
        }),
        ('Legacy Completion Fields', {
            'fields': ('is_completed', 'completed_at', 'completion_notes', 'reminders_sent'),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.action(description='Activate selected daily tasks')
    def activate_tasks(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'Activated {count} daily task(s).')

    @admin.action(description='Deactivate selected daily tasks')
    def deactivate_tasks(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {count} daily task(s).')


@admin.register(TaskCompletion)
class TaskCompletionAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('daily_task', 'patient_display', 'completion_date', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'completion_date', 'completed_at')
    search_fields = (
        'daily_task__title',
        'patient__username', 'patient__email',
        'daily_task__patient__username', 'daily_task__patient__email',
    )
    readonly_fields = ('completed_at',)
    autocomplete_fields = ('patient', 'daily_task')
    ordering = ('-completion_date', '-completed_at')
    list_select_related = ('patient', 'daily_task__patient')

    fieldsets = (
        ('Completion', {
            'fields': ('patient', 'daily_task', 'completion_date', 'is_completed', 'completed_at', 'completion_time'),
        }),
        ('Patient Notes', {
            'fields': ('patient_notes',),
        }),
    )

    @admin.display(description='Patient')
    def patient_display(self, obj):
        return obj.patient or obj.daily_task.patient


@admin.register(DailyTaskReminderLog)
class DailyTaskReminderLogAdmin(OptimizedAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'date', 'incomplete_tasks_count', 'email_sent_at')
    list_filter = ('date', 'email_sent_at')
    search_fields = ('user__username', 'user__email', 'incomplete_task_titles')
    readonly_fields = ('user', 'date', 'email_sent_at', 'incomplete_tasks_count', 'incomplete_task_titles')
    ordering = ('-date', '-email_sent_at')
    list_select_related = ('user',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
