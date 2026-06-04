from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404

from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.password_validation import validate_password

from django.contrib.auth.decorators import login_required

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.http import url_has_allowed_host_and_scheme

from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.http.request import RawPostDataException
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from django.utils import timezone

from django.db import IntegrityError, transaction

from django.db.models import Q

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import json
import logging

import random
import re

import string

logger = logging.getLogger(__name__)


def _add_password_validation_errors(request, password, user=None):
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return False
    return True


def _request_is_json(request):
    return (request.content_type or '').split(';')[0].strip().lower() == 'application/json'


def _parse_json_value(value, fallback):
    if value in (None, ''):
        return fallback
    if isinstance(value, str):
        return json.loads(value)
    return value


def _load_consultation_save_payload(request):
    if _request_is_json(request):
        payload = json.loads(request.body.decode('utf-8') or '{}')
        daily_tasks_raw = (
            payload.get('daily_tasks')
            if 'daily_tasks' in payload
            else payload.get('tasks', payload.get('daily_tasks_json', []))
        )
    else:
        payload = request.POST
        daily_tasks_raw = request.POST.get('daily_tasks_json', '[]')

    daily_tasks = _parse_json_value(daily_tasks_raw, [])
    if isinstance(daily_tasks, dict):
        daily_tasks = [daily_tasks]
    if not isinstance(daily_tasks, list):
        daily_tasks = []
    return payload, daily_tasks_raw, daily_tasks


def _safe_request_body(request):
    try:
        return request.body
    except RawPostDataException:
        return b'<already read by request.POST>'


CONSULTATION_JOIN_STATUSES = {'scheduled', 'confirmed', 'waiting', 'in_progress'}
CONSULTATION_TERMINAL_STATUSES = {'completed', 'cancelled', 'incomplete', 'expired'}


def _consultation_window(appointment):
    scheduled_at = timezone.localtime(appointment.appointment_date)
    return {
        'scheduled_at': scheduled_at,
        'opens_at': scheduled_at - timedelta(minutes=20),
        'expires_at': scheduled_at + timedelta(hours=2),
    }


def _get_or_create_consultation_for_appointment(appointment):
    try:
        consultation = appointment.consultation
    except Consultation.DoesNotExist:
        consultation = None

    if consultation:
        update_fields = []
        if not appointment.meeting_id:
            appointment.meeting_id = consultation.room_name
            update_fields.append('meeting_id')
        if not appointment.meeting_link:
            appointment.meeting_link = f"/consultation/{appointment.id}/"
            update_fields.append('meeting_link')
        if update_fields:
            update_fields.append('updated_at')
            appointment.save(update_fields=update_fields)
        return consultation

    if not appointment.meeting_id:
        appointment.meeting_id = f"room_{appointment.id}"
        appointment.meeting_link = appointment.meeting_link or f"/consultation/{appointment.id}/"
        appointment.save(update_fields=['meeting_id', 'meeting_link', 'updated_at'])

    room_name = appointment.meeting_id
    if Consultation.objects.filter(room_name=room_name).exists():
        room_name = f"room_{appointment.id}"
        suffix = 1
        while Consultation.objects.filter(room_name=room_name).exists():
            suffix += 1
            room_name = f"room_{appointment.id}_{suffix}"
        appointment.meeting_id = room_name
        appointment.meeting_link = f"/consultation/{appointment.id}/"
        appointment.save(update_fields=['meeting_id', 'meeting_link', 'updated_at'])

    return Consultation.objects.create(
        appointment=appointment,
        room_name=room_name,
        status='scheduled',
    )


def _is_platform_admin(user):
    return bool(
        getattr(user, 'is_superuser', False)
        or getattr(user, 'is_staff', False)
        or getattr(user, 'role', None) == 'admin'
    )


def _consultation_participant_role(user, appointment):
    if appointment.patient_id == user.id:
        return 'patient'
    doctor_user_id = getattr(getattr(appointment, 'doctor', None), 'user_id', None)
    if doctor_user_id == user.id:
        return 'doctor'
    if _is_platform_admin(user):
        return 'admin'
    return None


def _can_access_consultation(user, appointment):
    return _consultation_participant_role(user, appointment) is not None


def _consultation_forbidden(message='You are not allowed to join this consultation.'):
    return HttpResponseForbidden(message)


def _safe_user_name(user):
    if not user:
        return 'Unknown user'
    return user.get_full_name() or user.username or f'User #{user.pk}'


def _consultation_redirect_name(user):
    if getattr(user, 'role', None) == 'doctor':
        return 'doctor_appointments'
    if _is_platform_admin(user):
        return 'admin_appointments'
    return 'patient_appointments'


def _expire_consultation_if_needed(appointment, now=None):
    now = now or timezone.localtime()
    window = _consultation_window(appointment)
    if now <= window['expires_at'] or appointment.status in CONSULTATION_TERMINAL_STATUSES or appointment.status == 'pending_payment':
        return None

    try:
        consultation = appointment.consultation
    except Consultation.DoesNotExist:
        consultation = _get_or_create_consultation_for_appointment(appointment)
    if consultation:
        consultation.status = 'expired'
        consultation.expired_at = consultation.expired_at or timezone.now()
        consultation.last_activity_at = timezone.now()
        consultation.save(update_fields=['status', 'expired_at', 'last_activity_at'])

    appointment.status = 'incomplete'
    appointment.save(update_fields=['status', 'updated_at'])
    return consultation


def _appointment_access_state(appointment, now=None):
    now = now or timezone.localtime()
    _expire_consultation_if_needed(appointment, now)
    window = _consultation_window(appointment)

    can_join = False
    message = ''
    state = appointment.status

    if appointment.status == 'pending_payment':
        message = 'Payment is required before joining this consultation.'
    elif appointment.status in {'completed', 'cancelled'}:
        message = f'Consultation is {appointment.get_status_display().lower()}.'
    elif appointment.status in {'incomplete', 'expired'}:
        message = 'Consultation room has expired.'
        state = 'expired'
    elif now < window['opens_at']:
        message = 'Consultation room will open 20 minutes before scheduled time.'
        state = 'scheduled'
    elif now > window['expires_at']:
        message = 'Consultation room has expired.'
        state = 'expired'
    elif appointment.status in CONSULTATION_JOIN_STATUSES:
        can_join = True
        message = 'Consultation room is open.'
        state = appointment.status if appointment.status in {'waiting', 'in_progress'} else 'open'
    else:
        message = 'Consultation room is not available.'

    return {
        'can_join': can_join,
        'state': state,
        'message': message,
        'opens_at': window['opens_at'],
        'expires_at': window['expires_at'],
    }


def _annotate_consultation_access(appointments):
    annotated = list(appointments)
    for appointment in annotated:
        access = _appointment_access_state(appointment)
        appointment.can_join_consultation = access['can_join']
        appointment.consultation_access_state = access['state']
        appointment.consultation_access_message = access['message']
        appointment.consultation_opens_at = access['opens_at']
        appointment.consultation_expires_at = access['expires_at']
    return annotated


def _mark_participant_joined(consultation, user):
    now = timezone.now()
    update_fields = ['last_activity_at']
    consultation.last_activity_at = now

    if user.role == 'doctor' and not consultation.doctor_joined_at:
        consultation.doctor_joined_at = now
        update_fields.append('doctor_joined_at')
    elif user.role == 'patient' and not consultation.patient_joined_at:
        consultation.patient_joined_at = now
        update_fields.append('patient_joined_at')

    both_joined = consultation.doctor_joined_at and consultation.patient_joined_at
    if both_joined:
        consultation.status = 'in_progress'
        if not consultation.started_at:
            consultation.started_at = now
            update_fields.append('started_at')
        consultation.appointment.status = 'in_progress'
    else:
        consultation.status = 'waiting'
        consultation.appointment.status = 'waiting'

    update_fields.append('status')
    consultation.save(update_fields=list(dict.fromkeys(update_fields)))
    consultation.appointment.save(update_fields=['status', 'updated_at'])


def _google_oauth_enabled():
    return bool(getattr(settings, 'GOOGLE_CLIENT_ID', '') and getattr(settings, 'GOOGLE_CLIENT_SECRET', ''))


def _auth_template_context():
    return {'google_oauth_enabled': _google_oauth_enabled()}


def _role_redirect_name(user):
    if not getattr(user, 'role', None):
        return 'complete_social_profile'
    if user.role == 'admin':
        return 'admin_dashboard'
    if user.role == 'doctor':
        return 'doctor_dashboard'
    return 'patient_dashboard'


def _safe_next_url(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None



# Import admin views

from . import admin_views



# Import admin payment view directly

from .admin_views import admin_payments



from .models import (

    User, Doctor, AssessmentQuestion, PatientAssessment, 

    AssessmentAnswer, Appointment, Consultation, Payment,

    HealthTaskTemplate, Prescription, DailyTask, TaskCompletion, Notification, BlogPost,

    DoctorSchedule, BookedSlot, DoctorSpecialization, DoctorPrimaryFocus

)
from .system_config import (
    get_active_payment_methods,
    get_default_payment_account,
    get_payment_method_options,
    get_payment_receiver,
    get_support_email,
    send_configured_mail,
)
from .task_services import get_today_task_items, mark_task_completed, replace_active_daily_tasks

from .recommendation_engine import (
    DYNAMIC_QUESTION_GROUPS,
    build_assessment_profile,
    get_dynamic_response_payload,
    recommend_doctors,
)
from .doctor_config import (
    DEFAULT_PRIMARY_FOCUS,
    DOCTOR_PRIMARY_FOCUS_CHOICES,
    DOCTOR_PRIMARY_FOCUS_VALUES,
    DOCTOR_SPECIALIZATION_CHOICES,
    DOCTOR_SPECIALIZATION_VALUES,
)
from .rag_chatbot import (
    chatbot_reply,
    detect_emergency_payload,
    extract_symptoms_from_history,
    get_chat_history,
    recommend_doctors_for_symptoms,
)


def _doctor_availability_text(value):
    if isinstance(value, dict):
        if 'notes' in value:
            return value.get('notes') or ''
        return json.dumps(value) if value else ''
    return value or ''


def _doctor_form_context(request, doctor=None, is_edit=False):
    selected_specializations = getattr(doctor, 'specialization_values', [])
    selected_primary_focuses = getattr(doctor, 'primary_focus_values', [])
    if request.method == 'POST':
        selected_specializations = request.POST.getlist('specialization') or request.POST.getlist('specializations')
        selected_primary_focuses = request.POST.getlist('primary_focus') or request.POST.getlist('primary_focuses')

    return {
        'doctor': doctor,
        'user': request.user,
        'is_edit': is_edit,
        'specialization_choices': DOCTOR_SPECIALIZATION_CHOICES,
        'primary_focus_choices': DOCTOR_PRIMARY_FOCUS_CHOICES,
        'selected_specializations': selected_specializations,
        'selected_primary_focuses': selected_primary_focuses,
        'availability_schedule_text': _doctor_availability_text(getattr(doctor, 'availability_schedule', '')),
    }


def _parse_non_negative_int(value, field_label, required=True, max_value=50):
    if value in (None, ''):
        if required:
            raise ValueError(f'{field_label} is required.')
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field_label} must be a valid number.')
    if parsed < 0 or parsed > max_value:
        raise ValueError(f'{field_label} must be between 0 and {max_value}.')
    return parsed


def _parse_consultation_fee(value):
    if value in (None, ''):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Consultation fee must be a valid amount.')
    if parsed < 0:
        raise ValueError('Consultation fee cannot be negative.')
    return parsed


def _validate_doctor_profile_payload(request):
    post = request.POST
    required_fields = {
        'first_name': 'First name',
        'last_name': 'Last name',
        'email': 'Email address',
        'phone': 'Phone number',
        'qualification': 'Qualification',
        'years_of_experience': 'Years of experience',
        'license_number': 'License number',
    }

    data = {}
    for field, label in required_fields.items():
        data[field] = (post.get(field) or '').strip()
        if not data[field]:
            raise ValueError(f'{label} is required.')

    specializations = [value.strip() for value in post.getlist('specialization') if value.strip()]
    if not specializations:
        specializations = [value.strip() for value in post.getlist('specializations') if value.strip()]
    if not specializations and post.get('specialty'):
        specializations = [(post.get('specialty') or '').strip()]
    if not specializations:
        raise ValueError('Please choose at least one specialization.')
    invalid_specializations = [value for value in specializations if value not in DOCTOR_SPECIALIZATION_VALUES]
    if invalid_specializations:
        raise ValueError('Please choose valid specializations only.')
    data['specialization'] = list(dict.fromkeys(specializations))

    primary_focuses = [value.strip() for value in post.getlist('primary_focus') if value.strip()]
    if not primary_focuses:
        primary_focuses = [value.strip() for value in post.getlist('primary_focuses') if value.strip()]
    if not primary_focuses:
        raise ValueError('Please choose at least one primary focus.')
    invalid_focuses = [value for value in primary_focuses if value not in DOCTOR_PRIMARY_FOCUS_VALUES]
    if invalid_focuses:
        raise ValueError('Please choose valid primary focus areas only.')
    data['primary_focus'] = list(dict.fromkeys(primary_focuses))

    data['years_of_experience'] = _parse_non_negative_int(data['years_of_experience'], 'Years of experience')
    data['consultation_fee'] = _parse_consultation_fee((post.get('consultation_fee') or '').strip())
    data['clinic_name'] = (post.get('clinic_name') or '').strip()
    data['clinic_address'] = (post.get('clinic_address') or '').strip()
    data['bio'] = (post.get('bio') or '').strip()
    availability_notes = (post.get('availability_schedule') or '').strip()
    data['availability_schedule'] = {'notes': availability_notes} if availability_notes else {}

    duplicate_email = User.objects.filter(email=data['email']).exclude(pk=request.user.pk).exists()
    if duplicate_email:
        raise ValueError('This email address is already in use.')

    return data


def _save_doctor_profile(request, doctor, data):
    request.user.first_name = data['first_name']
    request.user.last_name = data['last_name']
    request.user.email = data['email']
    request.user.phone = data['phone']
    request.user.save(update_fields=['first_name', 'last_name', 'email', 'phone'])

    doctor.name = request.user.get_full_name()
    doctor.qualification = data['qualification']
    doctor.years_of_experience = data['years_of_experience']
    doctor.consultation_fee = data['consultation_fee']
    doctor.clinic_name = data['clinic_name']
    doctor.clinic_address = data['clinic_address']
    doctor.license_number = data['license_number']
    doctor.bio = data['bio']
    doctor.availability_schedule = data['availability_schedule']

    profile_picture = request.FILES.get('profile_picture')
    if profile_picture:
        doctor.profile_image = profile_picture

    doctor.save()

    specialization_options = DoctorSpecialization.objects.filter(value__in=data['specialization'], is_active=True)
    focus_options = DoctorPrimaryFocus.objects.filter(value__in=data['primary_focus'], is_active=True)
    doctor.specializations.set(specialization_options)
    doctor.primary_focuses.set(focus_options)


def _doctor_specialization_values(doctor):
    values = getattr(doctor, 'specialization_values', None)
    if values is not None:
        return set(values)
    value = getattr(doctor, 'specialty', None)
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value} if value else set()


def _doctor_primary_focus_values(doctor):
    values = getattr(doctor, 'primary_focus_values', None)
    if values is not None:
        return set(values)
    value = getattr(doctor, 'primary_focus', None)
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value} if value else set()


def _available_doctors_matching_specializations(specializations, focus_values=None):
    match_filter = Q(specializations__value__in=specializations)
    if focus_values:
        match_filter |= Q(primary_focuses__value__in=focus_values)
    return Doctor.objects.filter(
        match_filter,
        is_available=True,
    ).distinct().select_related('user').prefetch_related('specializations', 'primary_focuses')





def home(request):

    """Landing page"""

    return render(request, 'home/homepage.html')





@ensure_csrf_cookie
def emergency(request):

    """Emergency help page"""

    return render(request, 'home/emergency.html')


@require_POST
def emergency_chat(request):
    """Offline RAG/Ollama chatbot endpoint for the emergency page."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    message = (payload.get('message') or '').strip()
    session_id = (payload.get('session_id') or '').strip()
    user = request.user if request.user.is_authenticated else None
    if not request.session.session_key:
        request.session.save()
    return JsonResponse(chatbot_reply(message, user, session_id, request.session.session_key))


def emergency_chat_history(request):
    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id:
        return JsonResponse({'error': 'session_id is required.'}, status=400)
    user = request.user if request.user.is_authenticated else None
    history = get_chat_history(session_id, user)
    if history is None:
        return JsonResponse({'error': 'Chat session not found.'}, status=404)
    return JsonResponse(history)


@require_POST
def emergency_doctor_recommendations(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
    message = (payload.get('message') or '').strip()
    symptoms = payload.get('symptoms') or extract_symptoms_from_history(message)
    crisis = bool(payload.get('crisis'))
    doctors = recommend_doctors_for_symptoms(symptoms, crisis=crisis, limit=5)
    return JsonResponse({'symptoms': symptoms, 'doctors': doctors})


@require_POST
def emergency_detect(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
    message = (payload.get('message') or '').strip()
    return JsonResponse(detect_emergency_payload(message))





def about(request):

    """About page"""

    return render(request, 'home/about.html')





def blogs(request):

    """

    Render the blogs page with mental health articles and resources.

    Public access for visitors showing general blog content.

    """

    # Get user's last assessment result (only for logged-in patients)

    last_assessment = None

    stress_level = None

    

    # If user is authenticated and is a patient, get their assessment

    if request.user.is_authenticated and request.user.role == 'patient':

        try:

            last_assessment = PatientAssessment.objects.filter(

                patient=request.user

            ).order_by('-created_at').first()

            

            if last_assessment:

                stress_level = last_assessment.stress_level

        except:

            pass

    

    # Get published blogs from database

    published_blogs = BlogPost.objects.filter(status='published').order_by('-published_at')

    

    # Get featured blog

    featured_blog = published_blogs.filter(is_featured=True).first()

    if not featured_blog:

        featured_blog = published_blogs.first()

    

    # Get all other blogs for the general section

    all_blogs = published_blogs.exclude(id=featured_blog.id) if featured_blog else published_blogs

    

    # Get blogs by category

    categories = BlogPost.CATEGORY_CHOICES

    category_blogs = {}

    for cat_key, cat_name in categories:

        category_blogs[cat_key] = published_blogs.filter(category=cat_key)[:3]

    

    # Check if a specific category is requested (from assessment results)

    selected_category = None

    selected_category_blogs = []

    selected_category_name = ''

    

    # Get category from GET parameter (for direct links)

    category_param = request.GET.get('category')

    if category_param and category_param in dict(categories).keys():

        selected_category = category_param

        selected_category_blogs = published_blogs.filter(category=selected_category)

        selected_category_name = dict(categories).get(selected_category, '')

    

    context = {

        'user': request.user,

        'last_assessment': last_assessment,

        'stress_level': stress_level,

        'featured_blog': featured_blog,

        'all_blogs': all_blogs,

        'category_blogs': category_blogs,

        'categories': categories,

        'selected_category': selected_category,

        'selected_category_blogs': selected_category_blogs,

        'selected_category_name': selected_category_name,

    }

    return render(request, 'patient/blogs.html', context)





def services(request):

    """Services page"""

    return render(request, 'home/services.html')





def contact(request):

    """Contact page"""

    return render(request, 'home/contact.html')





def register(request):

    """User registration page"""

    if request.method == 'POST':

        # Get form data

        username = request.POST.get('username')

        email = request.POST.get('email')

        phone = request.POST.get('phone')

        password = request.POST.get('password1')

        confirm_password = request.POST.get('password2')

        role = 'patient'  # All public registrations are patients

        

        # New fields

        first_name = request.POST.get('first_name', '')

        last_name = request.POST.get('last_name', '')

        age = request.POST.get('age', '')

        gender = request.POST.get('gender', '')

        previous_treatment = request.POST.get('previous_mental_health_treatment', '')

        concerns = request.POST.getlist('concerns')

        medications = request.POST.get('medications', '')

        

        # Validation

        if password != confirm_password:

            messages.error(request, 'Passwords do not match')

            return render(request, 'auth/register.html', _auth_template_context())

        password_probe = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        if not _add_password_validation_errors(request, password, password_probe):

            return render(request, 'auth/register.html', _auth_template_context())

        

        if User.objects.filter(username=username).exists():

            messages.error(request, 'Username already exists')

            return render(request, 'auth/register.html', _auth_template_context())

        

        if User.objects.filter(email=email).exists():

            messages.error(request, 'Email already exists')

            return render(request, 'auth/register.html', _auth_template_context())

        

        # if User.objects.filter(phone=phone).exists():

        #     messages.error(request, 'Phone number already exists')

        #     return render(request, 'auth/register.html')

        

        # Create user

        user_age = None
        if age:
            try:
                user_age = int(age)
            except (TypeError, ValueError):
                user_age = None

        user = User.objects.create_user(

            username=username,

            email=email,

            phone=phone,

            password=password,

            role=role,

            first_name=first_name,

            last_name=last_name,

            age=user_age,

            gender=gender or None

        )

        

        # Store additional patient information in session for later use

        if role == 'patient':

            request.session['patient_info'] = {

                'age': age,

                'gender': gender,

                'previous_treatment': previous_treatment,

                'concerns': concerns,

                'medications': medications

            }

        

        # If doctor, create doctor profile

        if role == 'doctor':

            return redirect('complete_doctor_profile', user_id=user.id)

        

        messages.success(request, 'Registration successful! Please login.')

        return redirect('login')

    

    return render(request, 'auth/register.html', _auth_template_context())





def login_view(request):

    """User login page"""

    if request.method == 'POST':

        username = request.POST.get('username')

        password = request.POST.get('password')

        

        user = authenticate(request, username=username, password=password)

        if user is not None:

            login(request, user)
            next_url = _safe_next_url(request)
            if next_url:
                return redirect(next_url)
            return redirect(_role_redirect_name(user))

        else:

            messages.error(request, 'Invalid credentials')

    

    return render(request, 'auth/login.html', _auth_template_context())


def google_oauth_login(request):
    """Start Google OAuth with a friendly configuration guard."""

    if not _google_oauth_enabled():
        messages.error(request, 'Google sign-in is not configured yet. Please add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.')
        referer = request.META.get('HTTP_REFERER', '')
        return redirect('register' if 'register' in referer else 'login')

    if request.method != 'POST':
        return redirect('login')

    from allauth.socialaccount.providers.google.views import oauth2_login

    return oauth2_login(request)


@login_required
def auth_redirect(request):
    next_url = _safe_next_url(request)
    if next_url:
        return redirect(next_url)
    return redirect(_role_redirect_name(request.user))


@login_required
def complete_social_profile(request):
    """Fallback profile completion for OAuth users missing platform role details."""

    if request.method == 'POST':
        selected_role = request.POST.get('role') or 'patient'
        if selected_role not in {'patient', 'doctor'}:
            messages.error(request, 'Please choose a valid account type.')
            return render(request, 'auth/complete_social_profile.html')

        request.user.role = selected_role
        phone = request.POST.get('phone', '').strip()
        age = request.POST.get('age', '').strip()
        gender = request.POST.get('gender', '').strip()
        if phone:
            request.user.phone = phone
        if age:
            try:
                request.user.age = int(age)
            except (TypeError, ValueError):
                messages.error(request, 'Please enter a valid age.')
                return render(request, 'auth/complete_social_profile.html')
        if gender:
            request.user.gender = gender
        request.user.save(update_fields=['role', 'phone', 'age', 'gender'])

        if selected_role == 'doctor':
            return redirect('complete_doctor_profile', user_id=request.user.id)
        return redirect('patient_dashboard')

    if request.user.role:
        return redirect(_role_redirect_name(request.user))

    return render(request, 'auth/complete_social_profile.html')





def logout_view(request):

    """User logout"""

    logout(request)

    return redirect('home')





def forgot_password(request):

    """Step 1: Show form to enter first name and mobile number"""

    return render(request, 'auth/forgot_password.html')





def forgot_password_verify(request):

    """Step 2: Verify first name and mobile number, then allow password reset"""

    if request.method == 'POST':

        first_name = request.POST.get('first_name', '').strip()

        phone = request.POST.get('phone', '').strip()



        if not first_name or not phone:

            messages.error(request, 'Please enter both first name and mobile number.')

            return render(request, 'auth/forgot_password.html')



        # Normalize phone number to handle different formats

        normalized_phone = phone

        

        # Remove any spaces, dashes, or parentheses

        normalized_phone = normalized_phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

        

        # If phone starts with +880, keep it as is

        # If phone starts with 01, add +880 prefix

        if normalized_phone.startswith('+880'):

            normalized_phone = normalized_phone

        elif normalized_phone.startswith('01'):

            normalized_phone = '+880' + normalized_phone

        # If phone starts with 880 (without +), add +

        elif normalized_phone.startswith('880') and len(normalized_phone) >= 11:

            normalized_phone = '+' + normalized_phone



        try:

            # Try with normalized phone first

            user = User.objects.get(first_name__iexact=first_name, phone=normalized_phone)

            # Store verified user id in session

            request.session['reset_user_id'] = user.id

            return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})

        except User.DoesNotExist:

            # If normalized phone doesn't work, try the original input

            try:

                user = User.objects.get(first_name__iexact=first_name, phone=phone)

                request.session['reset_user_id'] = user.id

                return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})

            except User.DoesNotExist:

                messages.error(request, 'No account found with that first name and mobile number combination.')

                return render(request, 'auth/forgot_password.html')



    return redirect('forgot_password')





def forgot_password_reset(request):

    """Step 3: Set new password after identity verification"""

    reset_user_id = request.session.get('reset_user_id')



    if not reset_user_id:

        messages.error(request, 'Please verify your identity first.')

        return redirect('forgot_password')



    try:

        user = User.objects.get(id=reset_user_id)

    except User.DoesNotExist:

        messages.error(request, 'User not found. Please try again.')

        return redirect('forgot_password')



    if request.method == 'POST':

        new_password = request.POST.get('new_password', '').strip()

        confirm_password = request.POST.get('confirm_password', '').strip()



        if not new_password or not confirm_password:

            messages.error(request, 'Please fill in both password fields.')

            return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})



        if new_password != confirm_password:

            messages.error(request, 'Passwords do not match.')

            return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})

        if not _add_password_validation_errors(request, new_password, user):

            return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})



        user.set_password(new_password)

        user.save()

        # Clear session

        if 'reset_user_id' in request.session:

            del request.session['reset_user_id']



        messages.success(request, 'Password reset successful! You can now log in with your new password.')

        return redirect('login')



    return render(request, 'auth/forgot_password_reset.html', {'reset_user': user})





@login_required

def edit_doctor_profile(request):

    """Edit existing doctor profile"""

    if request.user.role != 'doctor':

        return redirect('home')

    

    try:

        doctor = request.user.doctor_profile

    except Doctor.DoesNotExist:

        return redirect('complete_doctor_profile', user_id=request.user.id)

    

    if request.method == 'POST':
        try:
            data = _validate_doctor_profile_payload(request)
            _save_doctor_profile(request, doctor, data)
            messages.success(request, 'Profile updated successfully!')
            return redirect('doctor_dashboard')
        except ValueError as error:
            messages.error(request, str(error))
        except Exception:
            messages.error(request, 'Unable to update your profile. Please try again.')

    return render(request, 'doctor/complete_profile.html', _doctor_form_context(request, doctor, is_edit=True))





@login_required

def complete_doctor_profile(request, user_id):

    """Complete doctor profile after registration"""

    if request.user.id != user_id or request.user.role != 'doctor':

        return redirect('home')

    

    # Check if doctor profile already exists

    try:

        doctor_profile = request.user.doctor_profile

        messages.info(request, 'Your profile is already complete!')

        return redirect('doctor_dashboard')

    except Doctor.DoesNotExist:

        pass  # Profile doesn't exist, continue with creation

    

    if request.method == 'POST':
        try:
            data = _validate_doctor_profile_payload(request)
            doctor = Doctor(user=request.user)
            _save_doctor_profile(request, doctor, data)
            messages.success(request, 'Doctor profile completed successfully!')
            return redirect('doctor_dashboard')
        except ValueError as error:
            messages.error(request, str(error))
        except IntegrityError:
            messages.error(request, 'A doctor profile already exists for this account.')
        except Exception:
            messages.error(request, 'Unable to complete your profile. Please try again.')

    return render(request, 'doctor/complete_profile.html', _doctor_form_context(request))





@login_required

def patient_dashboard(request):

    """Patient dashboard"""

    if request.user.role != 'patient':

        return redirect('home')

    

    recent_assessments = PatientAssessment.objects.filter(

        patient=request.user

    ).order_by('-created_at')[:5]

    

    upcoming_appointments = _annotate_consultation_access(Appointment.objects.filter(

        patient=request.user,

        appointment_date__gte=timezone.now() - timedelta(hours=2),

        status__in=['scheduled', 'confirmed', 'waiting', 'in_progress']

    ).order_by('appointment_date')[:5])

    

    active_today_tasks = get_today_task_items(request.user)

    # Get unread notifications

    unread_notifications = Notification.objects.filter(

        user=request.user,

        is_read=False

    )[:5]

    

    # Get recent prescriptions - SIMPLIFIED VERSION

    recent_prescriptions = Prescription.objects.filter(

        patient=request.user

    ).order_by('-created_at')[:5]

    

    completed_count = len([t for t in active_today_tasks if t['completion'] and t['completion'].is_completed])
    total_tasks = len(active_today_tasks)

    context = {

        'recent_assessments': recent_assessments,

        'upcoming_appointments': upcoming_appointments,

        'today_tasks': active_today_tasks,

        'task_items': active_today_tasks,

        'unread_notifications': unread_notifications,

        'recent_prescriptions': recent_prescriptions,

        'total_tasks': total_tasks,

        'completed_tasks': completed_count,

        'completed_count': completed_count,

    }

    return render(request, 'patient/dashboard.html', context)





@login_required

def test_patient_data(request):

    """Test endpoint to check patient data"""

    if request.user.role != 'patient':

        return JsonResponse({'error': 'Not a patient'}, status=403)

    

    from datetime import date

    

    # Get all data for this patient

    prescriptions = Prescription.objects.filter(patient=request.user).values('id', 'prescription_text', 'created_at', 'medications')

    tasks = DailyTask.objects.filter(patient=request.user, is_active=True).values('id', 'title', 'description', 'created_at', 'start_date', 'end_date')

    

    return JsonResponse({

        'success': True,

        'prescriptions': list(prescriptions),

        'tasks': list(tasks),

        'prescriptions_count': prescriptions.count(),

        'tasks_count': tasks.count()

    })





@login_required

def send_message(request):

    """API endpoint for sending messages to patients"""

    if request.user.role != 'doctor':

        return JsonResponse({'error': 'Unauthorized'}, status=401)

    

    if request.method != 'POST':

        return JsonResponse({'error': 'Method not allowed'}, status=405)

    

    try:

        data = json.loads(request.body)

        patient_id = data.get('patient_id')

        message_text = data.get('message')

        

        if not patient_id or not message_text:

            return JsonResponse({'error': 'Patient ID and message are required'}, status=400)

        

        # Get patient

        patient = get_object_or_404(User, id=patient_id, role='patient')

        

        # In a real implementation, you would:

        # 1. Save the message to a Message model

        # 2. Send notification to patient

        # 3. Create notification record

        

        # For now, we'll just simulate success

        # You could create a Notification model entry here

        

        # Create notification for patient

        try:

            from .models import Notification

            Notification.objects.create(

                user=patient,

                title='New message from Dr. ' + request.user.get_full_name(),

                message=message_text,

                notification_type='message'

            )

        except:

            pass  # Notification model might not exist or have different fields

        

        return JsonResponse({'success': True, 'message': 'Message sent successfully'})

        

    except json.JSONDecodeError:

        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    except Exception as e:

        return JsonResponse({'error': str(e)}, status=500)





@login_required

def analytics(request):

    """API endpoint for doctor analytics"""

    if request.user.role != 'doctor':

        return JsonResponse({'error': 'Unauthorized'}, status=401)

    

    try:

        doctor = request.user.doctor_profile

        

        # Get all appointments for this doctor

        appointments = Appointment.objects.filter(doctor=doctor)

        

        # Calculate metrics

        total_patients = appointments.values('patient').distinct().count()

        completed_sessions = appointments.filter(status='completed').count()

        

        # Calculate total earnings

        total_earnings = 0

        for payment in Payment.objects.filter(appointment__doctor=doctor, status='completed'):

            total_earnings += payment.doctor_earning or 0

        

        data = {

            'total_patients': total_patients,

            'completed_sessions': completed_sessions,

            'total_earnings': int(total_earnings),

        }

        

        return JsonResponse(data)

    

    except Exception as e:

        return JsonResponse({'error': str(e)}, status=500)





@login_required

def appointment_details(request, appointment_id):

    """API endpoint for appointment details"""

    if request.user.role != 'doctor':

        return JsonResponse({'error': 'Unauthorized'}, status=401)

    

    try:

        appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)

        

        data = {

            'patient_name': appointment.patient.get_full_name() or appointment.patient.username,

            'date': appointment.appointment_date.strftime('%B %d, %Y'),

            'time': appointment.appointment_date.strftime('%I:%M %p'),

            'status': appointment.get_status_display(),

            'consultation_type': 'Video Consultation',

            'fee': str(appointment.consultation_fee) if appointment.consultation_fee else 'Not Set',

            'notes': appointment.notes or ''

        }

        

        return JsonResponse(data)

    

    except Exception as e:

        return JsonResponse({'error': str(e)}, status=500)





@login_required

def doctor_dashboard(request):

    """Doctor dashboard"""

    if request.user.role != 'doctor':

        return redirect('home')

    

    try:

        doctor = request.user.doctor_profile

    except Doctor.DoesNotExist:

        return redirect('complete_doctor_profile', user_id=request.user.id)

    

    # Get current date in the correct timezone

    from django.utils import timezone

    

    # Django automatically uses the timezone from settings.py (Asia/Dhaka)

    now = timezone.now()

    today = now.date()

    

    # Filter today's appointments using Django's timezone-aware date filtering

    today_appointments = _annotate_consultation_access(Appointment.objects.filter(

        doctor=doctor,

        appointment_date__date=today,

        status__in=['scheduled', 'confirmed', 'waiting', 'in_progress']

    ).select_related('patient').order_by('appointment_date'))

    

    upcoming_appointments = _annotate_consultation_access(Appointment.objects.filter(

        doctor=doctor,

        appointment_date__gt=now,

        status__in=['scheduled', 'confirmed', 'waiting', 'in_progress']

    ).select_related('patient').order_by('appointment_date')[:10])

    

    context = {

        'doctor': doctor,

        'today_appointments': today_appointments,

        'upcoming_appointments': upcoming_appointments,

        'today_date': today.strftime('%B %d, %Y'),

    }

    return render(request, 'doctor/dashboard.html', context)





@login_required

def admin_dashboard(request):

    """Admin dashboard"""

    if request.user.role != 'admin':

        return redirect('home')

    

    total_users = User.objects.count()

    total_patients = User.objects.filter(role='patient').count()

    total_doctors = User.objects.filter(role='doctor').count()

    total_appointments = Appointment.objects.count()

    

    recent_appointments = Appointment.objects.all().order_by('-created_at')[:10]

    

    context = {

        'total_users': total_users,

        'total_patients': total_patients,

        'total_doctors': total_doctors,

        'total_appointments': total_appointments,

        'recent_appointments': recent_appointments,

    }

    return render(request, 'admin/dashboard.html', context)





@login_required

def assessment(request):

    """Rule-based weighted mental health assessment"""

    if request.user.role != 'patient':

        return redirect('home')

    

    questions = list(AssessmentQuestion.objects.all().order_by('track_number', 'id')[:7])

    if request.method == 'POST':

        total_score = 0

        answers = []
        core_answers = []

        

        for question in questions:

            answer_value = int(request.POST.get(f'question_{question.id}', 0))
            answer_value = max(0, min(4, answer_value))

            total_score += answer_value * question.weight_value
            core_answers.append(answer_value)

            answers.append({

                'question_id': question.id,

                'answer_value': answer_value

            })

        

        initial_profile = build_assessment_profile(core_answers, request.user)
        dynamic_responses = get_dynamic_response_payload(request.POST, initial_profile['triggered_modules'])
        result_profile = build_assessment_profile(core_answers, request.user, dynamic_responses)
        stress_level = result_profile['severity_level'].lower()

        

        # Create assessment record

        assessment = PatientAssessment.objects.create(

            patient=request.user,

            total_score=total_score,

            stress_level=stress_level,

            recommendations=(
                f"Primary concern: {result_profile['primary_condition']}. "
                f"Severity: {result_profile['severity_level']}. "
                "Consider consulting with one of the recommended mental health professionals."
            ),

            dynamic_responses=dynamic_responses,

            result_summary=result_profile

        )

        

        # Save answers

        for answer_data in answers:

            AssessmentAnswer.objects.create(

                assessment=assessment,

                question_id=answer_data['question_id'],

                answer_value=answer_data['answer_value']

            )

        

        return redirect('assessment_results', assessment_id=assessment.id)

    

    context = {
        'questions': questions,
        'dynamic_question_groups': DYNAMIC_QUESTION_GROUPS,
        'profile_age': request.user.age,
    }

    return render(request, 'patient/assessment.html', context)





@login_required

def assessment_results(request, assessment_id):

    """Assessment results page"""

    if request.user.role != 'patient':

        return redirect('home')

    

    assessment = get_object_or_404(PatientAssessment, id=assessment_id, patient=request.user)

    answers = assessment.answers.select_related('question').order_by('question__track_number', 'question__id')
    core_answers = [answer.answer_value for answer in answers[:7]]
    if assessment.result_summary:
        result_profile = assessment.result_summary
    else:
        result_profile = build_assessment_profile(core_answers, request.user, assessment.dynamic_responses)

    

    # Calculate category scores

    category_scores = {}

    for answer in answers:

        category = answer.question.category

        if category not in category_scores:

            category_scores[category] = 0

        category_scores[category] += answer.answer_value * answer.question.weight_value

    

    # Generate personalized recommendations based on scores and stress level

    recommendations = generate_personalized_recommendations(assessment.stress_level, category_scores)

    

    # Get blog recommendations based on stress level

    recommended_blog_categories = []

    if assessment.stress_level:

        stress_level_mapping = {

            'low': ['mindfulness', 'self-care', 'sleep'],

            'moderate': ['anxiety', 'workplace', 'self-care'],

            'high': ['depression', 'therapy', 'relationships'],

            'severe': ['therapy', 'depression', 'anxiety']

        }

        recommended_blog_categories = stress_level_mapping.get(

            assessment.stress_level, 

            ['mindfulness', 'self-care']

        )

    

    # Get actual blogs from database

    recommended_blogs = []

    if recommended_blog_categories:

        published_blogs = BlogPost.objects.filter(status='published')

        recommended_blogs = published_blogs.filter(

            category__in=recommended_blog_categories

        )[:4]  # Show up to 4 recommended blogs

    

    # 🚀 Get advanced doctor recommendations based on assessment
    candidate_doctors = Doctor.objects.filter(is_available=True).select_related('user').prefetch_related('specializations', 'primary_focuses')
    recommended_doctors = recommend_doctors(candidate_doctors, result_profile, limit=5)

    for doctor_rec in recommended_doctors:
        doctor_rec['actual_patients_helped'] = Appointment.objects.filter(
            doctor=doctor_rec['doctor'],
            status='completed'
        ).values('patient').distinct().count()

    # Calculate PHQ-9 and GAD-7 scores for display
    phq9_score = category_scores.get('Depression', 0)
    gad7_score = category_scores.get('Anxiety', 0)

    # Get severity levels
    depression_severity = get_depression_severity(phq9_score)
    anxiety_severity = get_anxiety_severity(gad7_score)

    # Detect emergency
    emergency = result_profile['emotional_risk_level'] == 'High'

    # Determine primary condition
    primary_condition = result_profile['primary_condition']


    context = {

        'assessment': assessment,

        'answers': answers,

        'category_scores': category_scores,

        'score_breakdown': result_profile['category_scores'],

        'dynamic_questions_triggered': result_profile['triggered_modules'],

        'dynamic_scores': result_profile.get('dynamic_scores', {}),

        'recommendations': recommendations,

        'recommended_blog_categories': recommended_blog_categories,

        'recommended_blogs': recommended_blogs,

        'categories': BlogPost.CATEGORY_CHOICES,

        'recommended_doctors': recommended_doctors,

        'phq9_score': phq9_score,

        'gad7_score': gad7_score,

        'depression_severity': depression_severity,

        'anxiety_severity': anxiety_severity,

        'emergency': emergency,

        'primary_condition': primary_condition,

        'secondary_condition': result_profile['secondary_condition'],

        'severity_level': result_profile['severity_level'],

        'emotional_risk_level': result_profile['emotional_risk_level'],

    }

    return render(request, 'patient/assessment_results.html', context)





def get_recommended_doctors_advanced(stress_level, category_scores):
    """
    🚀 UPDATED DOCTOR RECOMMENDATION ENGINE
    Based on PHQ-9 and GAD-7 clinical scoring system
    """
    from home.models import Doctor

    # 🧮 STEP 1: Calculate PHQ-9 and GAD-7 scores
    phq9_score = category_scores.get('Depression', 0)
    gad7_score = category_scores.get('Anxiety', 0)

    # 🧠 STEP 2: Detect severity
    depression_severity = get_depression_severity(phq9_score)
    anxiety_severity = get_anxiety_severity(gad7_score)

    # 🚨 STEP 3: Emergency detection (check for suicide risk)
    # In PHQ-9, question 9 is about self-harm thoughts
    # We'll check if depression score is very high as a proxy
    emergency = phq9_score >= 15  # Moderately severe to severe depression

    # 🧠 STEP 4: Detect primary condition
    if phq9_score >= gad7_score:
        primary_condition = "Depression"
        severity = depression_severity
    else:
        primary_condition = "Anxiety"
        severity = anxiety_severity

    # 🏥 STEP 5: Filter suitable doctors based on severity
    allowed_specialties = get_allowed_specialties(severity, emergency)

    # Get candidate doctors
    candidate_doctors = _available_doctors_matching_specializations(allowed_specialties, [primary_condition])

    # 🧠 STEP 6: Calculate match scores for each doctor
    doctor_results = []
    for doctor in candidate_doctors:
        score = calculate_doctor_match_score(
            doctor,
            primary_condition,
            severity,
            emergency
        )
        doctor_results.append({
            'doctor': doctor,
            'total_score': score,
            'match_percentage': score
        })

    # 🏆 STEP 7: Sort and return top 3
    doctor_results.sort(key=lambda x: x['total_score'], reverse=True)
    return doctor_results[:3]


def get_depression_severity(score):
    """Detect depression severity based on PHQ-9 score"""
    if score <= 4:
        return "Minimal"
    elif score <= 9:
        return "Mild"
    elif score <= 14:
        return "Moderate"
    elif score <= 19:
        return "Moderately Severe"
    return "Severe"


def get_anxiety_severity(score):
    """Detect anxiety severity based on GAD-7 score"""
    if score <= 4:
        return "Minimal"
    elif score <= 9:
        return "Mild"
    elif score <= 14:
        return "Moderate"
    return "Severe"


def get_allowed_specialties(severity, emergency):
    """Get allowed specialties based on severity and emergency status"""
    # Severe cases or emergency
    if severity in ['Severe', 'Moderately Severe'] or emergency:
        return ['Psychiatrist', 'Clinical Psychologist']

    # Moderate cases
    elif severity == 'Moderate':
        return ['Clinical Psychologist', 'Therapist']

    # Mild cases
    else:
        return ['Counselor', 'Therapist', 'Clinical Psychologist']


def calculate_doctor_match_score(doctor, primary_condition, severity, emergency):
    """
    🧠 NEW MATCHING FORMULA
    Factor | Weight
    Specialty Match | 45
    Severity Suitability | 25
    Expertise Tags | 15
    Experience | 10
    Availability | 5
    TOTAL = 100
    """
    score = 0
    specializations = _doctor_specialization_values(doctor)
    focus_areas = _doctor_primary_focus_values(doctor)

    # SPECIALTY MATCH (45 points)
    if severity in ['Severe', 'Moderately Severe']:
        if 'Psychiatrist' in specializations:
            score += 45
        elif 'Clinical Psychologist' in specializations:
            score += 40
    else:
        if 'Clinical Psychologist' in specializations:
            score += 45
        elif 'Therapist' in specializations:
            score += 40
        elif 'Counselor' in specializations:
            score += 35

    # PRIMARY FOCUS MATCH (25 points)
    if primary_condition in focus_areas:
        score += 25
    elif primary_condition == 'Depression' and focus_areas & {'Stress', 'Sleep'}:
        score += 15
    elif primary_condition == 'Anxiety' and 'Stress' in focus_areas:
        score += 15

    # EXPERTISE TAGS (15 points)
    if doctor.expertise_tags:
        # Check if primary condition or related terms are in expertise tags
        condition_keywords = {
            'Depression': ['depression', 'mood', 'sadness', 'hopeless'],
            'Anxiety': ['anxiety', 'worry', 'panic', 'fear', 'nervous']
        }
        keywords = condition_keywords.get(primary_condition, [])

        for tag in doctor.expertise_tags:
            tag_lower = tag.lower()
            if any(keyword in tag_lower for keyword in keywords):
                score += 15
                break

    # EXPERIENCE (10 points)
    if doctor.years_of_experience >= 10:
        score += 10
    elif doctor.years_of_experience >= 5:
        score += 7
    elif doctor.years_of_experience >= 2:
        score += 4
    else:
        score += 2

    # AVAILABILITY (5 points)
    if doctor.available_online:
        score += 5

    # EMERGENCY BONUS (extra 10 points if emergency and doctor supports it)
    if emergency and doctor.emergency_support:
        score += 10

    return min(score, 100)





def calculate_normalized_tracks(category_scores):

    """

    🧮 Calculate normalized scores for each track (0.0-1.0 scale)

    Prevents question count bias

    """

    # Track maximum possible scores

    track_max_scores = {

        'Depression': 36,    # (Q1*3) + (Q2*3) + (Q7*3) = 12*3

        'Anxiety': 16,       # (Q3*2) + (Q4*2) = 8*2

        'Sleep': 8,          # Q5*2 = 4*2

        'Energy': 4           # Q6*1 = 4*1

    }

    

    normalized_scores = {}

    for category, raw_score in category_scores.items():

        max_score = track_max_scores.get(category, 1)

        normalized_scores[category] = raw_score / max_score if max_score > 0 else 0

    

    return normalized_scores





def identify_primary_condition(track_scores):

    """

    🎯 Identify patient's dominant medical concern

    """

    if not track_scores:

        return 'Stress', 0.0

    

    primary_condition = max(track_scores.items(), key=lambda x: x[1])[0]

    primary_severity = track_scores[primary_condition]

    

    return primary_condition, primary_severity





def apply_clinical_triage(primary_condition, primary_severity):

    """

    🛡️ Clinical triage filtering for patient safety

    """

    from home.models import Doctor

    

    # Scenario A: High Severity (>= 0.50) - Specialists only

    if primary_severity >= 0.50:

        if primary_condition in ['Depression', 'Anxiety']:

            return _available_doctors_matching_specializations(['Psychiatrist', 'Clinical Psychologist'], [primary_condition])

        else:

            return _available_doctors_matching_specializations(['Psychiatrist', 'Therapist'], [primary_condition])

    

    # Scenario B: Mild to Moderate (< 0.50) - General practitioners

    else:

        if primary_condition in ['Sleep', 'Energy']:

            return _available_doctors_matching_specializations(['Psychiatrist', 'Therapist'], [primary_condition])

        else:

            return _available_doctors_matching_specializations(['Clinical Psychologist', 'Therapist', 'Counselor'], [primary_condition])





def score_doctors_advanced(doctors, primary_condition, primary_severity, track_scores):

    """

    📊 Advanced 100-point scoring system

    """

    from home.models import Appointment

    

    scored_doctors = []

    

    for doctor in doctors:

        # 🎯 Focus Alignment (40 Points Max)

        focus_score = 0

        focus_areas = _doctor_primary_focus_values(doctor)

        if primary_condition in focus_areas:

            focus_score = 40

        elif focus_areas & set(track_scores.keys()):

            focus_score = 20

        

        # 🔍 Sub-Symptom Keyword Alignment (40 Points Max)

        keyword_score = 0

        if doctor.expertise_tags:

            # Check for secondary elevated concerns

            for category, severity in track_scores.items():

                if severity >= 0.50 and category != primary_condition:

                    if any(tag.lower() in [expertise.lower() for expertise in doctor.expertise_tags] 

                          for tag in get_category_keywords(category)):

                        keyword_score = 30

                        break

            else:

                keyword_score = 10

        

        # 💪 Professional Longevity (20 Points Max)

        experience_score = 0

        if doctor.years_of_experience >= 10:

            experience_score = 20

        elif doctor.years_of_experience >= 5:

            experience_score = 10

        elif doctor.years_of_experience >= 2:

            experience_score = 5

        

        quality_score = 0

        if hasattr(doctor, 'success_rate') and doctor.success_rate >= 80:

            quality_score += 5

        

        # 📈 Calculate total score and percentage

        total_score = focus_score + keyword_score + experience_score + quality_score

        match_percentage = min(99, int((total_score / 100) * 100))

        

        # 📊 Get actual patients helped

        actual_patients_helped = Appointment.objects.filter(

            doctor=doctor,

            status='completed'

        ).values('patient').distinct().count()

        

        # 🎯 Generate personalized match reason

        match_reason = generate_advanced_match_reason(

            doctor, primary_condition, primary_severity, 

            focus_score, keyword_score, experience_score

        )

        

        scored_doctors.append({

            'doctor': doctor,

            'total_score': total_score,

            'match_percentage': match_percentage,

            'match_reason': match_reason,

            'actual_patients_helped': actual_patients_helped,

            'score_breakdown': {

                'focus_alignment': focus_score,

                'keyword_match': keyword_score,

                'experience': experience_score,

                'quality_bonus': quality_score

            },

            'clinical_triage': {

                'primary_condition': primary_condition,

                'severity_level': primary_severity,

                'triage_level': 'high' if primary_severity >= 0.50 else 'moderate'

            }

        })

    

    return scored_doctors





def get_category_keywords(category):

    """

    🔍 Get symptom keywords for each category

    """

    keyword_mapping = {

        'Depression': ['depression', 'sadness', 'hopeless', 'worthless', 'guilt', 'fatigue'],

        'Anxiety': ['anxiety', 'panic', 'worry', 'fear', 'nervous', 'stress'],

        'Sleep': ['insomnia', 'sleep', 'tired', 'exhausted', 'fatigue', 'restless'],

        'Energy': ['energy', 'tired', 'exhausted', 'low-energy', 'fatigue', 'lethargic']

    }

    return keyword_mapping.get(category, [])





def generate_advanced_match_reason(doctor, primary_condition, severity, focus_score, keyword_score, experience_score):

    """

    🎯 Generate personalized match reason with clinical context

    """

    severity_level = 'severe' if severity >= 0.50 else 'moderate'

    

    reasons = {

        'Psychiatrist': f"🧠 Advanced psychiatric care for {severity_level} {primary_condition.lower()}. Can provide medication management and comprehensive treatment plans.",

        'Clinical Psychologist': f"🎓 Clinical psychology specialist for {severity_level} {primary_condition.lower()}. Expert in evidence-based therapeutic interventions.",

        'Therapist': f"💊 Specialized therapeutic interventions for your {primary_condition.lower()} symptoms. Uses evidence-based treatment modalities.",

        'Counselor': f"💪 Expert counseling and coping strategies for {severity_level} {primary_condition.lower()}. Focus on practical emotional support."

    }

    

    base_reason = reasons.get(doctor.specialty, f"🏥 Experienced in treating {severity_level} {primary_condition.lower()} conditions")

    

    # Add scoring context

    if focus_score == 40:

        base_reason += f" ✅ Perfect specialty match for your {primary_condition} concerns."

    elif keyword_score >= 30:

        base_reason += f" 🔍 Expertise in your specific symptom patterns."

    elif experience_score >= 20:

        base_reason += f" 💪 Extensive clinical experience ({doctor.years_of_experience}+ years)."

    

    return base_reason





def get_match_reason(doctor_specialty, stress_level, category_scores):

    """Generate reason why this doctor is recommended"""

    

    # Find the highest scoring category

    highest_category = max(category_scores.items(), key=lambda x: x[1])[0] if category_scores else 'general'

    

    reasons = {

        'Psychiatrist': f"Can provide medication management and comprehensive care for {stress_level} mental health conditions",

        'Counselor': f"Expert in counseling and coping strategies for {stress_level} stress and emotional challenges",

        'Therapist': f"Provides specialized therapeutic interventions for your specific needs",

        'Clinical Psychologist': f"Highly qualified to treat complex {stress_level} mental health conditions"

    }

    

    return reasons.get(doctor_specialty, f"Experienced in treating patients with similar assessment profiles")





def generate_personalized_recommendations(stress_level, category_scores):

    """Generate personalized recommendations based on assessment results"""

    recommendations = []
    stress_level = (stress_level or '').lower()

    

    # Base recommendations by stress level

    if stress_level == 'low':

        recommendations.append({

            'icon': '✅',

            'title': 'Continue Your Wellness Journey',

            'description': 'Your mental health appears to be in good shape. Continue practicing self-care, maintaining healthy habits, and regular check-ins to sustain your wellbeing.',

            'priority': 'low',

            'actionable_steps': [

                'Maintain regular sleep schedule (7-9 hours)',

                'Continue physical activity (30 mins daily)',

                'Practice mindfulness or meditation 10-15 minutes daily',

                'Stay connected with supportive friends and family',

                'Engage in hobbies and activities you enjoy'

            ]

        })

    elif stress_level == 'moderate':

        recommendations.append({

            'icon': '💡',

            'title': 'Consider Professional Support',

            'description': 'Your results suggest moderate stress levels. Speaking with a mental health professional can provide valuable tools and strategies for managing stress effectively.',

            'priority': 'medium',

            'actionable_steps': [

                'Schedule consultation with a mental health professional',

                'Practice stress management techniques (deep breathing, progressive muscle relaxation)',

                'Establish healthy boundaries in work and personal life',

                'Consider cognitive behavioral therapy techniques',

                'Join support groups or wellness communities'

            ]

        })

    elif stress_level == 'high':

        recommendations.append({

            'icon': '🎯',

            'title': 'Professional Help Recommended',

            'description': 'We strongly recommend connecting with a mental health professional for personalized support and guidance. Your symptoms may benefit from professional intervention.',

            'priority': 'high',

            'actionable_steps': [

                'Seek immediate consultation with a mental health professional',

                'Consider therapy or counseling sessions',

                'Practice daily stress reduction techniques',

                'Inform trusted family members or friends about your situation',

                'Create a structured daily routine for stability'

            ]

        })

    elif stress_level == 'severe':

        recommendations.append({

            'icon': '🚨',

            'title': 'Immediate Support Available',

            'description': 'Your results suggest significant distress. Please don\'t hesitate to reach out for immediate professional support. Help is available and you don\'t have to face this alone.',

            'priority': 'urgent',

            'actionable_steps': [

                'Contact mental health professional immediately',

                'Call emergency hotline: 16101',

                'Reach out to trusted family or friends',

                'Consider crisis intervention services',

                'Remove yourself from overwhelming situations if possible'

            ]

        })

    

    # Category-specific recommendations with detailed analysis

    for category, score in category_scores.items():

        if score >= 15:  # High score in category indicates concern

            if category == 'Depression':

                recommendations.append({

                    'icon': '🌧️',

                    'title': 'Focus on Mood Management',

                    'description': 'Your responses indicate symptoms of depression. Focus on activities that boost mood and consider professional support for comprehensive care.',

                    'priority': 'high',

                    'actionable_steps': [

                        'Engage in regular physical exercise (releases endorphins)',

                        'Get sunlight exposure daily (15-30 minutes)',

                        'Practice gratitude journaling (3 things daily)',

                        'Connect with supportive people regularly',

                        'Consider antidepressant medications with professional guidance',

                        'Establish a consistent daily routine',

                        'Limit alcohol and avoid recreational drugs',

                        'Practice self-compassion and positive self-talk'

                    ]

                })

            elif category == 'Anxiety':

                recommendations.append({

                    'icon': '🧘',

                    'title': 'Practice Anxiety Management',

                    'description': 'Your anxiety levels appear elevated. Learning relaxation techniques and coping strategies can significantly help manage anxiety symptoms.',

                    'priority': 'high',

                    'actionable_steps': [

                        'Practice 4-7-8 breathing technique (inhale 4, hold 7, exhale 8)',

                        'Try progressive muscle relaxation daily',

                        'Limit caffeine and stimulant intake',

                        'Practice mindfulness meditation (10-20 minutes daily)',

                        'Challenge anxious thoughts with cognitive restructuring',

                        'Create a worry time limit (15-20 minutes daily)',

                        'Use grounding techniques (5-4-3-2-1 method)',

                        'Consider anti-anxiety medications if prescribed'

                    ]

                })

            elif category == 'Sleep':

                recommendations.append({

                    'icon': '😴',

                    'title': 'Improve Sleep Hygiene',

                    'description': 'Quality sleep is crucial for mental health. Establishing proper sleep habits can significantly improve your overall wellbeing.',

                    'priority': 'medium',

                    'actionable_steps': [

                        'Maintain consistent sleep schedule (same bedtime/wake time)',

                        'Avoid screens 1 hour before bed (blue light affects melatonin)',

                        'Create relaxing bedtime routine (reading, gentle music)',

                        'Keep bedroom cool, dark, and quiet',

                        'Avoid caffeine after 2 PM',

                        'Exercise regularly but not within 3 hours of bedtime',

                        'Consider natural sleep aids (melatonin, valerian root)',

                        'Limit fluids 2 hours before bedtime'

                    ]

                })

            elif category == 'Energy':

                recommendations.append({

                    'icon': '⚡',

                    'title': 'Boost Energy Levels Naturally',

                    'description': 'Low energy can impact daily functioning. Focus on nutrition, exercise, and lifestyle changes to improve your energy levels.',

                    'priority': 'medium',

                    'actionable_steps': [

                        'Eat balanced meals with protein, complex carbs, healthy fats',

                        'Stay hydrated (8 glasses of water daily)',

                        'Take short walks every 2 hours',

                        'Practice good posture to improve energy flow',

                        'Consider vitamin B12 and D supplements',

                        'Limit processed foods and sugar',

                        'Take power naps (10-20 minutes) if needed',

                        'Practice stress management to conserve energy'

                    ]

                })

            elif category == 'Self-esteem':

                recommendations.append({

                    'icon': '💪',

                    'title': 'Build Self-Confidence',

                    'description': 'Working on self-esteem can improve overall mental health. Focus on self-acceptance and personal growth strategies.',

                    'priority': 'medium',

                    'actionable_steps': [

                        'Practice positive affirmations daily',

                        'Set and achieve small, realistic goals',

                        'Keep a success journal (document achievements)',

                        'Challenge negative self-talk with evidence',

                        'Learn new skills or hobbies to build competence',

                        'Surround yourself with supportive people',

                        'Practice self-care without guilt',

                        'Consider therapy to work on self-worth issues'

                    ]

                })

    

    # Add lifestyle recommendations based on overall pattern

    if len([s for s in category_scores.values() if s >= 15]) >= 3:

        recommendations.append({

            'icon': '🌟',

            'title': 'Comprehensive Lifestyle Reset',

            'description': 'Multiple areas show elevated concern. A holistic approach to lifestyle changes can create significant improvement across all areas.',

            'priority': 'high',

            'actionable_steps': [

                'Create a structured daily schedule',

                'Implement morning routine (exercise, meditation, healthy breakfast)',

                'Practice digital detox (limit screen time)',

                'Establish work-life boundaries',

                'Join group activities or classes',

                'Consider nutritional counseling',

                'Practice time management techniques',

                'Build a strong support network'

            ]

        })

    

    # Add positive reinforcement for areas doing well

    good_categories = [cat for cat, score in category_scores.items() if score < 10]

    if good_categories:

        recommendations.append({

            'icon': '🌈',

            'title': 'Build on Your Strengths',

            'description': f'You\'re showing good progress in: {", ".join(good_categories)}. Continue these positive practices while working on other areas.',

            'priority': 'low',

            'actionable_steps': [

                'Continue what\'s working well in these areas',

                'Share your successful strategies with others',

                'Use these strengths as motivation for other areas',

                'Teach or mentor others in your strong areas',

                'Document your successful techniques',

                'Celebrate your progress regularly'

            ]

        })

    

    return recommendations





@login_required

def doctors_list(request):

    """List of available doctors"""

    if request.user.role != 'patient':

        return redirect('home')

    

    doctors = Doctor.objects.filter(is_available=True).select_related('user').prefetch_related('specializations', 'primary_focuses')

    

    context = {'doctors': doctors}

    return render(request, 'patient/doctors.html', context)





BOOKING_PAYMENT_METHODS = {'card', 'bkash', 'nagad'}
BOOKING_PAYMENT_METHOD_LABELS = {
    'card': 'Card',
    'bkash': 'bKash',
    'nagad': 'Nagad',
}
BANGLADESH_MOBILE_RE = re.compile(r'^01[3-9]\d{8}$')
CARD_NUMBER_RE = re.compile(r'^\d{13,19}$')
CVV_RE = re.compile(r'^\d{3,4}$')


def _format_slot_time(slot_time):
    hour = slot_time.hour
    minute = slot_time.minute
    if hour < 12:
        period = 'AM'
        display_hour = hour if hour else 12
    else:
        period = 'PM'
        display_hour = hour - 12 if hour != 12 else 12
    return f'{display_hour}:{minute:02d} {period}'


def _get_booking_payment_options():
    return [
        option for option in get_payment_method_options()
        if option['value'] in BOOKING_PAYMENT_METHODS
    ]


def _get_selected_booking_date(request, available_dates):
    selected_date = request.POST.get('appointment_date') or request.GET.get('date')
    valid_dates = {item['date'] for item in available_dates}
    if selected_date in valid_dates:
        return selected_date
    return available_dates[0]['date'] if available_dates else None


def _build_booking_context(request, doctor, selected_date_str=None, form_data=None):
    doctor_schedules = DoctorSchedule.objects.filter(doctor=doctor, is_available=True)
    available_weekdays = set(doctor_schedules.values_list('day_of_week', flat=True))
    today = timezone.localdate()
    now_time = timezone.localtime().time()
    available_dates = []

    for offset in range(14):
        candidate = today + timedelta(days=offset)
        if candidate.weekday() in available_weekdays:
            available_dates.append({
                'date': candidate.isoformat(),
                'day_name': candidate.strftime('%A'),
                'formatted_date': candidate.strftime('%b %d'),
                'is_today': offset == 0,
            })

    selected_date_str = selected_date_str or _get_selected_booking_date(request, available_dates)
    selected_time_slots = []
    selected_date_obj = None

    if selected_date_str:
        try:
            selected_date_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date_obj = None

    if selected_date_obj:
        booked_slots = set(
            BookedSlot.objects.filter(
                doctor=doctor,
                appointment_date=selected_date_obj,
                is_active=True,
            ).values_list('appointment_time', flat=True)
        )
        day_schedules = doctor_schedules.filter(day_of_week=selected_date_obj.weekday())
        for schedule in day_schedules:
            for slot_time_str in schedule.get_time_slots():
                slot_time = datetime.strptime(slot_time_str, '%H:%M').time()
                is_booked = slot_time in booked_slots
                is_past = selected_date_obj == today and slot_time <= now_time
                selected_time_slots.append({
                    'time': _format_slot_time(slot_time),
                    'time_24h': slot_time_str,
                    'available': not is_booked and not is_past,
                    'is_booked': is_booked,
                    'is_past': is_past,
                })

    payment_options = _get_booking_payment_options()
    active_payment_methods = [option['value'] for option in payment_options]
    return {
        'doctor': doctor,
        'patient': request.user,
        'available_dates': available_dates,
        'time_slots': selected_time_slots,
        'selected_date': selected_date_str,
        'selected_time': (form_data or {}).get('appointment_time', ''),
        'consultation_fee': doctor.consultation_fee or 0,
        'payment_options': payment_options,
        'active_payment_methods': active_payment_methods,
        'form_data': form_data or {},
        'payment_test_mode': getattr(settings, 'PAYMENT_TEST_MODE', True),
    }


def _parse_booking_datetime(date_value, time_value):
    selected_date = datetime.strptime(date_value, '%Y-%m-%d').date()
    selected_time = None
    for time_format in ('%I:%M %p', '%H:%M'):
        try:
            selected_time = datetime.strptime(time_value, time_format).time()
            break
        except ValueError:
            continue
    if selected_time is None:
        raise ValueError('Invalid appointment time format')

    appointment_datetime = datetime.combine(selected_date, selected_time)
    appointment_datetime = timezone.make_aware(appointment_datetime, timezone.get_current_timezone())
    return selected_date, selected_time, appointment_datetime


def _slot_is_on_schedule(doctor, selected_date, selected_time):
    schedules = DoctorSchedule.objects.filter(
        doctor=doctor,
        day_of_week=selected_date.weekday(),
        is_available=True,
    )
    selected_time_24h = selected_time.strftime('%H:%M')
    return any(selected_time_24h in schedule.get_time_slots() for schedule in schedules)


def _set_payment_commission(payment):
    commission_rate = Decimal('0.10')
    payment.admin_commission = payment.amount * commission_rate
    payment.doctor_earning = payment.amount - payment.admin_commission


def _digits_only(value):
    return re.sub(r'\D', '', value or '')


def _mask_wallet_number(number):
    return f'{number[:3]}*****{number[-3:]}'


def _generate_test_otp():
    return f'{random.SystemRandom().randint(100000, 999999)}'


def _clean_payment_reference(value):
    return re.sub(r'[<>]', '', (value or '').strip())[:120]


def _payment_method_label(payment_method):
    return BOOKING_PAYMENT_METHOD_LABELS.get(payment_method, (payment_method or 'Payment').title())


def _receiver_account_snapshot(receiver_account):
    if not receiver_account:
        return {}
    return receiver_account.public_snapshot()


def _get_receiver_account_or_error(payment_method):
    receiver_account = get_default_payment_account(payment_method)
    if not receiver_account:
        raise ValueError(f'{_payment_method_label(payment_method)} is not available right now. Please choose another payment method or contact support.')
    return receiver_account


def _validate_payment_details(payment_method, post_data):
    details = {
        'wallet_number_masked': '',
        'card_last4': '',
        'reference_id': _clean_payment_reference(post_data.get('reference_id') or post_data.get('wallet_reference')),
    }

    if payment_method in {'bkash', 'nagad'}:
        wallet_number = _digits_only(post_data.get('wallet_number') or post_data.get('mobile_number'))
        if not wallet_number:
            raise ValueError(f'Please enter your {_payment_method_label(payment_method)} wallet number.')
        if not BANGLADESH_MOBILE_RE.match(wallet_number):
            raise ValueError('Please enter a valid Bangladesh mobile number, for example 01XXXXXXXXX.')
        details['wallet_number_masked'] = _mask_wallet_number(wallet_number)
        return details

    if payment_method == 'card':
        cardholder_name = (post_data.get('cardholder_name') or post_data.get('card_name') or '').strip()
        card_number = _digits_only(post_data.get('card_number'))
        expiry_month = _digits_only(post_data.get('expiry_month'))
        expiry_year = _digits_only(post_data.get('expiry_year'))
        legacy_expiry = (post_data.get('card_expiry') or '').strip()
        cvv = _digits_only(post_data.get('cvv') or post_data.get('card_cvv'))

        if legacy_expiry and (not expiry_month or not expiry_year):
            expiry_parts = legacy_expiry.split('/')
            if len(expiry_parts) == 2:
                expiry_month = _digits_only(expiry_parts[0])
                expiry_year = _digits_only(expiry_parts[1])

        if not cardholder_name:
            raise ValueError('Please enter the cardholder name.')
        if not CARD_NUMBER_RE.match(card_number):
            raise ValueError('Please enter a valid test card number with 13 to 19 digits.')
        if not expiry_month or not expiry_year:
            raise ValueError('Please enter the card expiry month and year.')
        try:
            month = int(expiry_month)
            year = int(expiry_year)
        except ValueError:
            raise ValueError('Please enter a valid card expiry month and year.')
        if year < 100:
            year += 2000
        if month < 1 or month > 12:
            raise ValueError('Please enter a valid card expiry month.')
        today = timezone.localdate()
        if (year, month) < (today.year, today.month):
            raise ValueError('Please enter a card expiry date that has not passed.')
        if not CVV_RE.match(cvv):
            raise ValueError('Please enter a valid CVV in testing format.')
        details['card_last4'] = card_number[-4:]
        return details

    raise ValueError('Please choose a supported payment method.')


def _create_booking_payment(appointment, payment_method, payment_details=None, status='otp_sent'):
    payment_details = payment_details or {}
    receiver_account = _get_receiver_account_or_error(payment_method)
    payment = Payment(
        appointment=appointment,
        patient=appointment.patient,
        doctor=appointment.doctor,
        amount=appointment.consultation_fee,
        admin_commission=0,
        doctor_earning=0,
        status=status,
        payment_method=payment_method,
        receiving_account=payment_method,
        payment_receiver_account=receiver_account,
        receiver_payment_method=receiver_account.payment_method,
        receiver_account_snapshot=_receiver_account_snapshot(receiver_account),
        reference_id=payment_details.get('reference_id', ''),
        wallet_number_masked=payment_details.get('wallet_number_masked', ''),
        card_last4=payment_details.get('card_last4', ''),
        otp_code=_generate_test_otp() if getattr(settings, 'PAYMENT_TEST_MODE', True) else '',
    )
    _set_payment_commission(payment)
    payment.save()
    if getattr(settings, 'PAYMENT_TEST_MODE', True):
        logger.info("TESTING MODE: generated payment OTP for payment %s is %s", payment.id, payment.otp_code)
    return payment


def _refresh_payment_for_retry(payment, payment_details):
    receiver_account = _get_receiver_account_or_error(payment.payment_method)
    payment.receiving_account = payment.payment_method
    payment.payment_receiver_account = receiver_account
    payment.receiver_payment_method = receiver_account.payment_method
    payment.receiver_account_snapshot = _receiver_account_snapshot(receiver_account)
    payment.reference_id = payment_details.get('reference_id', '')
    payment.wallet_number_masked = payment_details.get('wallet_number_masked', '')
    payment.card_last4 = payment_details.get('card_last4', '')
    payment.otp_code = _generate_test_otp() if getattr(settings, 'PAYMENT_TEST_MODE', True) else ''
    payment.status = 'otp_sent'
    payment.otp_verified_at = None
    payment.paid_at = None
    payment.transaction_id = None
    _set_payment_commission(payment)
    payment.save(update_fields=[
        'payment_method', 'amount', 'receiving_account', 'payment_receiver_account',
        'receiver_payment_method', 'receiver_account_snapshot',
        'reference_id', 'wallet_number_masked', 'card_last4', 'otp_code',
        'status', 'otp_verified_at', 'paid_at', 'transaction_id',
        'admin_commission', 'doctor_earning', 'updated_at',
    ])
    if getattr(settings, 'PAYMENT_TEST_MODE', True):
        logger.info("TESTING MODE: refreshed payment OTP for payment %s is %s", payment.id, payment.otp_code)
    return payment


def _complete_booking_payment(request, appointment, payment, transaction_prefix):
    meeting_link = generate_meeting_link(appointment, request=request)
    appointment.status = 'confirmed'
    appointment.meeting_link = meeting_link
    appointment.save(update_fields=['status', 'meeting_id', 'meeting_link', 'updated_at'])

    payment.status = 'test_paid'
    payment.transaction_id = f'{transaction_prefix}-{payment.payment_method.upper()}-{payment.id}-{timezone.now().strftime("%Y%m%d%H%M%S")}'
    payment.receiving_account = payment.payment_method
    payment.paid_at = timezone.now()
    payment.otp_verified_at = timezone.now()
    _set_payment_commission(payment)
    payment.save(update_fields=[
        'status', 'transaction_id', 'receiving_account', 'paid_at', 'otp_verified_at',
        'admin_commission', 'doctor_earning', 'updated_at',
    ])

    send_booking_confirmation_email(appointment, payment, meeting_link)
    return meeting_link


def _confirm_payment_with_slot(request, payment_id, status='test_paid', transaction_id=None, transaction_prefix='TEST'):
    now = timezone.now()
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related(
            'appointment__patient',
            'appointment__doctor__user',
            'payment_receiver_account',
        ).get(id=payment_id, appointment__patient=request.user)
        appointment = payment.appointment
        selected_local = timezone.localtime(appointment.appointment_date)
        selected_date = selected_local.date()
        selected_time = selected_local.time()

        if payment.status in {'test_paid', 'completed'} and appointment.status == 'confirmed':
            return appointment, payment, appointment.meeting_link, False

        existing_slot = BookedSlot.objects.select_for_update().filter(
            doctor=appointment.doctor,
            appointment_date=selected_date,
            appointment_time=selected_time,
            is_active=True,
        ).first()
        if existing_slot and existing_slot.appointment_id != appointment.id:
            payment.status = 'failed'
            payment.save(update_fields=['status', 'updated_at'])
            appointment.status = 'cancelled'
            appointment.save(update_fields=['status', 'updated_at'])
            raise ValueError('This appointment slot is no longer available. Your payment was not completed.')

        meeting_link = generate_meeting_link(appointment, request=request)
        appointment.status = 'confirmed'
        appointment.meeting_link = meeting_link
        appointment.save(update_fields=['status', 'meeting_id', 'meeting_link', 'updated_at'])

        BookedSlot.objects.get_or_create(
            doctor=appointment.doctor,
            appointment_date=selected_date,
            appointment_time=selected_time,
            defaults={
                'appointment': appointment,
                'is_active': True,
            },
        )

        payment.status = status
        payment.transaction_id = transaction_id or f'{transaction_prefix}-{payment.payment_method.upper()}-{payment.id}-{now.strftime("%Y%m%d%H%M%S")}'
        payment.receiving_account = payment.payment_method
        payment.paid_at = now
        payment.otp_verified_at = now
        _set_payment_commission(payment)
        payment.save(update_fields=[
            'status', 'transaction_id', 'receiving_account', 'paid_at', 'otp_verified_at',
            'admin_commission', 'doctor_earning', 'updated_at',
        ])

    send_booking_confirmation_email(appointment, payment, meeting_link)
    logger.info("SMS SIMULATION: Payment Successful! Your Appointment ID is %s.", appointment.id)
    return appointment, payment, meeting_link, True


def _verify_real_payment(payment, request):
    # TODO: Enable real payment verification in production.
    # Real gateway code should verify transaction ownership, amount, status,
    # provider signature/webhook authenticity, and idempotency before returning success.
    return {
        'success': False,
        'message': 'Real payment verification is not configured yet.',
        'transaction_id': '',
    }


@login_required

def book_appointment(request, doctor_id):

    """Collect schedule and payment details, then start a test checkout intent."""

    if request.user.role != 'patient':

        messages.error(request, 'Only patient accounts can book appointments.')

        return redirect('home')

    doctor = get_object_or_404(
        Doctor.objects.select_related('user').prefetch_related('specializations', 'primary_focuses'),
        id=doctor_id,
        is_available=True,
    )

    context = _build_booking_context(request, doctor)

    if request.method == 'POST':

        appointment_date = request.POST.get('appointment_date', '').strip()

        appointment_time = request.POST.get('appointment_time', '').strip()

        consultation_type = request.POST.get('consultation_type', 'video')

        payment_method = request.POST.get('payment_method', '').strip()

        notes = request.POST.get('notes', '').strip()

        context = _build_booking_context(request, doctor, appointment_date, request.POST)

        active_payment_methods = context['active_payment_methods']

        if not active_payment_methods:

            messages.error(request, 'No payment methods are active right now. Please contact support.')

            return render(request, 'patient/book_appointment.html', context)

        if payment_method not in active_payment_methods:

            messages.error(request, 'Please select an active payment method.')

            return render(request, 'patient/book_appointment.html', context)

        if not appointment_date or not appointment_time:

            messages.error(request, 'Please select both date and time for your appointment.')

            return render(request, 'patient/book_appointment.html', context)

        if consultation_type not in {'video', 'phone', 'in_person'}:

            messages.error(request, 'Please choose a valid consultation type.')

            return render(request, 'patient/book_appointment.html', context)

        if not doctor.consultation_fee:

            messages.error(request, 'This doctor does not have a consultation fee set. Please contact support.')

            return render(request, 'patient/book_appointment.html', context)

        try:

            selected_date, selected_time, appointment_datetime = _parse_booking_datetime(appointment_date, appointment_time)

        except ValueError:

            messages.error(request, 'Invalid appointment date or time format.')

            return render(request, 'patient/book_appointment.html', context)

        if appointment_datetime <= timezone.now():

            messages.error(request, 'Please select a future appointment date and time.')

            return render(request, 'patient/book_appointment.html', context)

        if not _slot_is_on_schedule(doctor, selected_date, selected_time):

            messages.error(request, 'The selected time is not in this doctor schedule. Please choose another slot.')

            return render(request, 'patient/book_appointment.html', context)

        try:

            with transaction.atomic():

                if BookedSlot.objects.select_for_update().filter(
                    doctor=doctor,
                    appointment_date=selected_date,
                    appointment_time=selected_time,
                    is_active=True,
                ).exists():

                    messages.error(request, 'This time slot has just been booked by another patient. Please select a different time.')

                    return render(request, 'patient/book_appointment.html', context)

                payment_details = _validate_payment_details(payment_method, request.POST)

                appointment = Appointment.objects.select_for_update().filter(
                    patient=request.user,
                    doctor=doctor,
                    appointment_date=appointment_datetime,
                    status='pending_payment',
                ).order_by('-created_at').first()

                if appointment:
                    appointment.consultation_type = consultation_type
                    appointment.consultation_fee = doctor.consultation_fee
                    appointment.notes = notes
                    appointment.save(update_fields=[
                        'consultation_type', 'consultation_fee', 'notes', 'updated_at',
                    ])
                    try:
                        payment = appointment.payment
                        payment.payment_method = payment_method
                        payment.amount = appointment.consultation_fee
                        _refresh_payment_for_retry(payment, payment_details)
                    except Payment.DoesNotExist:
                        payment = _create_booking_payment(appointment, payment_method, payment_details)
                else:
                    appointment = Appointment.objects.create(
                        patient=request.user,
                        doctor=doctor,
                        appointment_date=appointment_datetime,
                        consultation_type=consultation_type,
                        consultation_fee=doctor.consultation_fee,
                        notes=notes,
                        status='pending_payment',
                    )

                    payment = _create_booking_payment(
                        appointment,
                        payment_method,
                        payment_details,
                        status='otp_sent' if getattr(settings, 'PAYMENT_TEST_MODE', True) else 'pending',
                    )

        except IntegrityError:

            messages.error(request, 'This time slot has just been booked by another patient. Please select a different time.')

            return render(request, 'patient/book_appointment.html', context)

        except ValueError as exc:

            messages.error(request, str(exc))

            context = _build_booking_context(request, doctor, appointment_date, request.POST)

            return render(request, 'patient/book_appointment.html', context)

        messages.success(request, 'Payment details validated. Enter the test OTP to confirm your appointment.')

        return redirect('verify_booking_payment', payment_id=payment.id)

    return render(request, 'patient/book_appointment.html', context)





@login_required

def process_payment(request, payment_id):

    """Backward-compatible payment URL."""

    if request.user.role != 'patient':

        return redirect('home')

    return redirect('verify_booking_payment', payment_id=payment_id)

    

    try:

        payment = Payment.objects.get(id=payment_id, appointment__patient=request.user)

        appointment = payment.appointment

        doctor = appointment.doctor

    except Payment.DoesNotExist:

        messages.error(request, 'Payment not found.')

        return redirect('patient_appointments')

    active_payment_methods = [
        method for method in get_active_payment_methods()
        if method in BOOKING_PAYMENT_METHODS
    ]
    payment_receiver = payment.payment_receiver_account or get_payment_receiver(payment.payment_method)
    if payment.payment_method not in active_payment_methods:

        messages.error(request, 'This payment method is not currently active. Please contact support or create a new booking with another method.')

        return redirect('patient_appointments')

    if payment.status in {'test_paid', 'completed'} and appointment.status == 'confirmed':

        return redirect('booking_success', appointment_id=appointment.id)

    if getattr(settings, 'PAYMENT_TEST_MODE', True):

        _complete_booking_payment(request, appointment, payment, 'TEST_PAYMENT')

        messages.success(request, 'Payment verification was bypassed for testing. Your appointment is confirmed.')

        return redirect('booking_success', appointment_id=appointment.id)

    if request.method == 'POST':

        # TODO: Enable real payment verification in production.
        gateway_response = _verify_real_payment(payment, request)

        if not gateway_response['success']:

            messages.error(request, gateway_response['message'])

        else:

            meeting_link = generate_meeting_link(appointment, request=request)

            payment.status = 'completed'

            payment.transaction_id = gateway_response['transaction_id']

            payment.receiving_account = payment_receiver.payment_method if payment_receiver else payment.payment_method

            payment.paid_at = timezone.now()

            _set_payment_commission(payment)

            payment.save(update_fields=[
                'status', 'transaction_id', 'receiving_account', 'paid_at',
                'admin_commission', 'doctor_earning', 'updated_at',
            ])

            appointment.status = 'confirmed'

            appointment.meeting_link = meeting_link

            appointment.save(update_fields=['status', 'meeting_id', 'meeting_link', 'updated_at'])

            send_booking_confirmation_email(appointment, payment, meeting_link)

            messages.success(request, 'Payment successful. Your appointment is confirmed.')

            return redirect('booking_success', appointment_id=appointment.id)

    

    context = {

        'payment': payment,

        'appointment': appointment,

        'doctor': doctor,

        'payment_receiver': payment_receiver,

        'payment_test_mode': getattr(settings, 'PAYMENT_TEST_MODE', True),

    }

    return render(request, 'patient/process_payment.html', context)


@login_required
def verify_booking_payment(request, payment_id):
    """Verify the simulated OTP/PIN step before confirming an appointment."""

    if request.user.role != 'patient':
        return redirect('home')

    try:
        payment = Payment.objects.select_related(
            'appointment__patient',
            'appointment__doctor__user',
            'payment_receiver_account',
        ).get(id=payment_id, appointment__patient=request.user)
        appointment = payment.appointment
        doctor = appointment.doctor
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found.')
        return redirect('patient_appointments')

    active_payment_methods = [
        method for method in get_active_payment_methods()
        if method in BOOKING_PAYMENT_METHODS
    ]
    payment_receiver = payment.payment_receiver_account or get_payment_receiver(payment.payment_method)
    if payment.payment_method not in active_payment_methods:
        messages.error(request, 'This payment method is not currently active. Please contact support or create a new booking with another method.')
        return redirect('patient_appointments')

    if (
        not payment.payment_receiver_account_id
        or not payment.payment_receiver_account.is_active
        or payment.payment_receiver_account.payment_method != payment.payment_method
    ):
        messages.error(request, 'The selected payment receiver account is no longer available. Your appointment was not confirmed.')
        return redirect('patient_appointments')

    if payment.status in {'test_paid', 'completed'} and appointment.status == 'confirmed':
        return redirect('booking_success', appointment_id=appointment.id)

    if appointment.status != 'pending_payment':
        messages.error(request, 'This booking is no longer awaiting payment verification.')
        return redirect('patient_appointments')

    wallet_method = payment.payment_method in {'bkash', 'nagad'}

    if request.method == 'POST':
        otp_code = _digits_only(request.POST.get('otp_code'))
        wallet_pin = _digits_only(request.POST.get('wallet_pin') or request.POST.get('pin'))

        if not otp_code:
            messages.error(request, 'Please enter the OTP code.')
        elif wallet_method and not wallet_pin:
            messages.error(request, f'Please enter your {_payment_method_label(payment.payment_method)} PIN for the test confirmation.')
        elif wallet_method and not re.fullmatch(r'\d{4,6}', wallet_pin):
            messages.error(request, 'Please enter a valid 4 to 6 digit PIN in testing format.')
        elif getattr(settings, 'PAYMENT_TEST_MODE', True):
            # TESTING MODE: Real OTP/gateway verification is bypassed
            # TODO: Enable real payment gateway verification in production
            valid_test_otps = {
                payment.otp_code,
                getattr(settings, 'PAYMENT_TEST_OTP', '123456'),
            }
            if otp_code not in valid_test_otps:
                messages.error(request, 'Invalid OTP. Please try again. Your appointment is not confirmed yet.')
            else:
                try:
                    appointment, payment, meeting_link, did_confirm = _confirm_payment_with_slot(
                        request,
                        payment.id,
                        status='test_paid',
                        transaction_prefix='TEST',
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('patient_appointments')
                if did_confirm:
                    messages.success(request, 'Payment successful in testing mode. Your appointment is confirmed.')
                    messages.info(request, f'SMS simulation: Payment Successful! Your Appointment ID is {appointment.id}.')
                return redirect('booking_success', appointment_id=appointment.id)
        else:
            gateway_response = _verify_real_payment(payment, request)

            if not gateway_response['success']:
                messages.error(request, gateway_response['message'])
            else:
                try:
                    appointment, payment, meeting_link, did_confirm = _confirm_payment_with_slot(
                        request,
                        payment.id,
                        status='completed',
                        transaction_id=gateway_response['transaction_id'],
                        transaction_prefix='LIVE',
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect('patient_appointments')
                if did_confirm:
                    messages.success(request, 'Payment successful. Your appointment is confirmed.')
                return redirect('booking_success', appointment_id=appointment.id)

    context = {
        'payment': payment,
        'appointment': appointment,
        'doctor': doctor,
        'payment_receiver': payment_receiver,
        'payment_test_mode': getattr(settings, 'PAYMENT_TEST_MODE', True),
        'payment_test_otp': getattr(settings, 'PAYMENT_TEST_OTP', '123456'),
        'generated_test_otp': payment.otp_code if getattr(settings, 'PAYMENT_TEST_MODE', True) else '',
        'payment_method_label': _payment_method_label(payment.payment_method),
        'wallet_method': wallet_method,
    }

    return render(request, 'patient/process_payment.html', context)


@login_required
def booking_success(request, appointment_id):
    """Professional booking success page after test or verified payment."""

    if request.user.role != 'patient':
        return redirect('home')

    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor__user', 'payment'),
        id=appointment_id,
        patient=request.user,
    )
    payment = getattr(appointment, 'payment', None)
    if not payment or payment.status not in {'test_paid', 'completed'} or appointment.status != 'confirmed':
        messages.error(request, 'Complete payment verification before viewing the booking receipt.')
        if payment:
            return redirect('verify_booking_payment', payment_id=payment.id)
        return redirect('patient_appointments')

    return render(request, 'patient/booking_success.html', {
        'appointment': appointment,
        'doctor': appointment.doctor,
        'payment': payment,
        'payment_method_label': _payment_method_label(payment.payment_method),
    })





def generate_meeting_link(appointment, request=None):

    """Generate unique meeting link for consultation"""

    import secrets

    

    # Generate unique meeting ID

    meeting_id = secrets.token_urlsafe(8)

    consultation_path = f"/consultation/{appointment.id}/"
    meeting_link = request.build_absolute_uri(consultation_path) if request else f"http://127.0.0.1:8000{consultation_path}"

    

    # Save meeting details

    appointment.meeting_id = meeting_id

    appointment.meeting_link = meeting_link

    

    return meeting_link





def send_booking_confirmation_email(appointment, payment, meeting_link):

    """Send booking confirmation emails without blocking appointment creation."""

    patient = appointment.patient
    doctor = appointment.doctor
    doctor_user = doctor.user

    payment_status = payment.get_status_display() if hasattr(payment, 'get_status_display') else payment.status
    local_appointment = timezone.localtime(appointment.appointment_date)
    support_contact = get_support_email()
    payment_method = _payment_method_label(payment.payment_method)
    transaction_id = payment.transaction_id or payment.reference_id or f'PAY-{payment.id}'

    patient_subject = 'Your consultation appointment is successfully booked'
    patient_message = f"""Dear {patient.get_full_name() or patient.username},

Your consultation appointment has been successfully booked.

Appointment Details:
Doctor: Dr. {doctor_user.get_full_name() or doctor_user.username}
Specialization: {doctor.specialty}
Date: {local_appointment.strftime('%B %d, %Y')}
Time: {local_appointment.strftime('%I:%M %p')}
Consultation Fee: BDT {appointment.consultation_fee}
Payment Method: {payment_method}
Payment Status: {payment_status}
Transaction ID: {transaction_id}

Meeting Link:
{meeting_link}

Please join the consultation using the meeting link at the scheduled time.
For support, contact {support_contact}.

Thank you,
Mental Wellness Platform Team
"""

    doctor_subject = 'New consultation appointment booked'
    doctor_message = f"""Dear Dr. {doctor_user.get_full_name() or doctor_user.username},

A new consultation appointment has been booked.

Appointment Details:
Patient: {patient.get_full_name() or patient.username}
Specialization: {doctor.specialty}
Date: {local_appointment.strftime('%B %d, %Y')}
Time: {local_appointment.strftime('%I:%M %p')}
Consultation Fee: BDT {appointment.consultation_fee}
Payment Method: {payment_method}
Payment Status: {payment_status}
Transaction ID: {transaction_id}

Meeting Link:
{meeting_link}

For support, contact {support_contact}.

Thank you,
Mental Wellness Platform Team
"""

    if patient.email:
        try:
            send_configured_mail(patient_subject, patient_message, [patient.email], fail_silently=False)
        except Exception as exc:
            logger.warning("Patient booking confirmation email failed for appointment %s: %s", appointment.id, exc)
    else:
        logger.warning("Booking confirmation email skipped for appointment %s: patient has no email.", appointment.id)

    if doctor_user.email:
        try:
            send_configured_mail(doctor_subject, doctor_message, [doctor_user.email], fail_silently=False)
        except Exception as exc:
            logger.warning("Doctor booking notification email failed for appointment %s: %s", appointment.id, exc)



def send_payment_notifications(appointment, doctor, meeting_link):

    """Send notifications to patient and doctor"""

    

    patient = appointment.patient

    doctor_user = doctor.user

    

    # Email to Patient

    patient_subject = "Appointment Confirmed - Meeting Link Inside"

    patient_message = f"""

    Dear {patient.get_full_name() or patient.username},

    

    Your appointment has been confirmed!

    

    Appointment Details:

    - Doctor: Dr. {doctor_user.get_full_name()}

    - Date: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}

    - Meeting Link: {meeting_link}

    

    Please join the meeting 5 minutes before your scheduled time.

    

    Best regards,

    Wellness Platform Team

    """

    

    # Email to Doctor

    doctor_subject = "New Appointment Scheduled - Meeting Link Inside"

    doctor_message = f"""

    Dear Dr. {doctor_user.get_full_name()},

    

    You have a new appointment scheduled!

    

    Appointment Details:

    - Patient: {patient.get_full_name() or patient.username}

    - Date: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}

    - Meeting Link: {meeting_link}

    

    Please join the meeting 5 minutes before the scheduled time.

    

    Best regards,

    Wellness Platform Team

    """

    

    try:

        if patient.email:
            send_configured_mail(patient_subject, patient_message, [patient.email], fail_silently=False)
        if doctor_user.email:
            send_configured_mail(doctor_subject, doctor_message, [doctor_user.email], fail_silently=False)

        

    except Exception as e:

        # Log error but don't fail the payment process

        logger.warning("Appointment email notification failed: %s", e)

    

    # Create in-app notifications (you might want to create a Notification model)

    """

    # Patient notification

    Notification.objects.create(

        user=patient,

        title="Appointment Confirmed",

        message=f"Your appointment with Dr. {doctor_user.get_full_name()} is confirmed. Meeting link: {meeting_link}",

        appointment=appointment

    )

    

    # Doctor notification

    Notification.objects.create(

        user=doctor_user,

        title="New Appointment",

        message=f"New appointment with {patient.get_full_name() or patient.username}. Meeting link: {meeting_link}",

        appointment=appointment

    )

    """





@login_required

def mark_appointment_completed(request, appointment_id):

    """Mark an appointment as completed"""

    if request.user.role != 'patient':

        return JsonResponse({'success': False, 'error': 'Unauthorized'})

    

    if request.method == 'POST':

        try:

            appointment = Appointment.objects.get(id=appointment_id, patient=request.user)

            if appointment.status in ['scheduled', 'confirmed']:

                appointment.status = 'completed'

                appointment.save()

                

                return JsonResponse({

                    'success': True,

                    'message': 'Appointment marked as completed successfully!'

                })

            else:

                return JsonResponse({

                    'success': False,

                    'error': 'Appointment cannot be marked as completed'

                })

                

        except Appointment.DoesNotExist:

            return JsonResponse({'success': False, 'error': 'Appointment not found'})

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def delete_appointment(request, appointment_id):

    """Delete appointment with pending payment or missed appointments"""

    if request.user.role != 'patient':

        return redirect('home')

    

    try:

        appointment = Appointment.objects.get(id=appointment_id, patient=request.user)

        

        # Allow deletion of appointments with pending payment or missed/cancelled appointments

        if appointment.status not in ['pending_payment', 'missed', 'cancelled']:

            messages.error(request, 'You can only delete appointments with pending payment or missed/cancelled appointments.')

            return redirect('patient_appointments')

        

        # Delete the appointment and related payment if exists

        if hasattr(appointment, 'payment'):

            appointment.payment.delete()

        appointment.delete()

        

        messages.success(request, 'Appointment deleted successfully.')

        

    except Appointment.DoesNotExist:

        messages.error(request, 'Appointment not found.')

    

    return redirect('patient_appointments')





@login_required

def patient_appointments(request):

    """Patient appointments list"""

    if request.user.role != 'patient':

        return redirect('home')

    

    from django.utils import timezone

    today = timezone.now().date()

    now = timezone.now()

    

    # Get all appointments for the patient

    all_appointments = _annotate_consultation_access(Appointment.objects.filter(

        patient=request.user

    ).select_related('doctor__user').order_by('-appointment_date'))

    

    # Separate today's appointments (only active ones)

    today_appointments = [
        appointment for appointment in all_appointments
        if timezone.localtime(appointment.appointment_date).date() == today
        and appointment.status in ['pending_payment', 'scheduled', 'confirmed', 'waiting', 'in_progress']
    ]

    

    # Upcoming appointments (excluding today)

    upcoming_appointments = [
        appointment for appointment in all_appointments
        if timezone.localtime(appointment.appointment_date).date() > today
        and appointment.status in ['pending_payment', 'scheduled', 'confirmed', 'waiting', 'in_progress']
    ]

    

    # Past appointments (including completed, cancelled, missed, and old scheduled/confirmed)

    past_appointments = [
        appointment for appointment in all_appointments
        if timezone.localtime(appointment.appointment_date).date() < today
        or appointment.status in ['completed', 'cancelled', 'missed', 'incomplete', 'expired']
    ]

    

    context = {

        'appointments': all_appointments,

        'today_appointments': today_appointments,

        'upcoming_appointments': upcoming_appointments,

        'past_appointments': past_appointments,

    }

    return render(request, 'patient/appointments.html', context)





@login_required

def doctor_details(request, doctor_id):

    """Doctor details page"""

    try:

        doctor = Doctor.objects.get(id=doctor_id)

        

        # Get doctor's upcoming appointments for availability

        upcoming_appointments = Appointment.objects.filter(

            doctor=doctor,

            status__in=['scheduled', 'confirmed'],

            appointment_date__gte=timezone.now().date()

        ).order_by('appointment_date')[:5]

        

        # Get doctor's completed appointments count

        completed_appointments = Appointment.objects.filter(

            doctor=doctor,

            status='completed'

        ).count()

        

        context = {

            'doctor': doctor,

            'upcoming_appointments': upcoming_appointments,

            'completed_appointments': completed_appointments,

        }

        return render(request, 'patient/doctor_details.html', context)

        

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor not found.')

        return redirect('doctors_list')





@login_required

def doctor_appointments(request):

    """Doctor appointments list"""

    if request.user.role != 'doctor':

        return redirect('home')

    

    try:

        doctor = request.user.doctor_profile

        

        # Get all appointments for this doctor

        all_appointments = _annotate_consultation_access(Appointment.objects.filter(

            doctor=doctor

        ).select_related('patient').order_by('-appointment_date'))

        

        # Filter upcoming appointments (future dates and not completed)

        upcoming_appointments = [
            appointment for appointment in all_appointments
            if appointment.appointment_date > timezone.now()
            and appointment.status in ['scheduled', 'confirmed', 'waiting', 'in_progress']
        ]

        

        # Filter past appointments (completed or cancelled)

        past_appointments = [
            appointment for appointment in all_appointments
            if appointment.appointment_date < timezone.now()
            or appointment.status in ['completed', 'cancelled', 'incomplete', 'expired']
        ]

        

        context = {

            'appointments': all_appointments,

            'upcoming_appointments': upcoming_appointments,

            'past_appointments': past_appointments,

            'doctor': doctor

        }

        return render(request, 'doctor/appointments.html', context)

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor profile not found')

        return redirect('home')





@login_required

def consultation_room(request, appointment_id):

    """Video consultation room"""

    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor', 'doctor__user'),
            id=appointment_id,
        )

        participant_role = _consultation_participant_role(request.user, appointment)
        if not participant_role:
            logger.warning(
                "Unauthorized consultation room access: appointment_id=%s user_id=%s",
                appointment_id,
                request.user.id,
            )
            return _consultation_forbidden()

        access = _appointment_access_state(appointment)
        if not access['can_join'] and participant_role != 'admin':
            messages.error(request, access['message'])
            return redirect(_consultation_redirect_name(request.user))

        consultation = _get_or_create_consultation_for_appointment(appointment)
        if participant_role in {'patient', 'doctor'}:
            _mark_participant_joined(consultation, request.user)

        doctor = appointment.doctor
        patient = appointment.patient
        doctor_user = getattr(doctor, 'user', None)
        doctor_image_url = ''
        if getattr(doctor, 'profile_image', None):
            try:
                doctor_image_url = doctor.profile_image.url
            except ValueError:
                doctor_image_url = ''

        context = {
            'appointment': appointment,
            'consultation': consultation,
            'room_name': consultation.room_name,
            'consultation_access': access,
            'participant_role': participant_role,
            'patient_display_name': _safe_user_name(patient),
            'doctor_display_name': _safe_user_name(doctor_user),
            'doctor_image_url': doctor_image_url,
            'patient_image_url': getattr(patient, 'profile_picture_url', '') or '',
            'websocket_available': False,
            'realtime_notice': 'Live status uses safe polling on this deployment. WebSocket signaling is not required for this page to load.',
        }

        return render(request, 'consultation/room.html', context)
    except Http404:
        raise
    except Exception:
        logger.exception(
            "Consultation room render failed: appointment_id=%s user_id=%s",
            appointment_id,
            request.user.id,
        )
        messages.error(request, 'The consultation room could not be loaded right now. Please try again or contact support.')
        return render(
            request,
            'consultation/room_unavailable.html',
            {'appointment_id': appointment_id},
            status=503,
        )





@login_required

def save_consultation_notes(request, appointment_id):

    """Save consultation notes (doctors only)"""

    if request.user.role != 'doctor':

        return JsonResponse({'error': 'Unauthorized'}, status=403)

    

    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor', 'doctor__user'),
        id=appointment_id,
    )

    

    # Check if doctor owns this appointment

    if appointment.doctor.user_id != request.user.id:

        return JsonResponse({'error': 'Unauthorized'}, status=403)

    

    if request.method == 'POST':

        try:

            data = json.loads(request.body)

            notes = data.get('notes', '')

            

            consultation = _get_or_create_consultation_for_appointment(appointment)
            consultation.notes = notes
            consultation.last_activity_at = timezone.now()
            consultation.save(update_fields=['notes', 'last_activity_at'])

            

            return JsonResponse({'success': True, 'message': 'Notes saved successfully'})

            

        except Exception as e:

            return JsonResponse({'error': str(e)}, status=400)

    

    return JsonResponse({'error': 'Method not allowed'}, status=405)





@login_required

def complete_consultation(request, appointment_id):

    """Complete consultation"""

    appointment = get_object_or_404(Appointment.objects.select_related('patient', 'doctor', 'doctor__user'), id=appointment_id)

    

    # Check permissions

    if request.user.role != 'doctor' or appointment.doctor.user_id != request.user.id:

        return JsonResponse({'success': False, 'error': 'Only the assigned doctor can complete this consultation'}, status=403)

    

    if request.method == 'POST':

        try:

            appointment.status = 'completed'

            appointment.save(update_fields=['status', 'updated_at'])

            consultation = _get_or_create_consultation_for_appointment(appointment)

            consultation.end_time = timezone.now()
            consultation.completed_at = consultation.completed_at or consultation.end_time
            consultation.status = 'completed'
            consultation.last_activity_at = timezone.now()

            consultation.save(update_fields=['end_time', 'completed_at', 'status', 'last_activity_at'])

            

            return JsonResponse({'success': True, 'message': 'Consultation completed'})

            

        except Exception as e:

            return JsonResponse({'error': str(e)}, status=400)

    

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def leave_consultation(request, appointment_id):
    appointment = get_object_or_404(Appointment.objects.select_related('patient', 'doctor', 'doctor__user'), id=appointment_id)
    participant_role = _consultation_participant_role(request.user, appointment)
    if not participant_role:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        consultation = _get_or_create_consultation_for_appointment(appointment)
        consultation.last_activity_at = timezone.now()
        consultation.save(update_fields=['last_activity_at'])
        return JsonResponse({'success': True, 'message': 'Participant left consultation'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def consultation_status(request, appointment_id):
    appointment = get_object_or_404(Appointment.objects.select_related('patient', 'doctor', 'doctor__user'), id=appointment_id)
    participant_role = _consultation_participant_role(request.user, appointment)
    if not participant_role:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    access = _appointment_access_state(appointment)
    try:
        consultation = appointment.consultation
    except Consultation.DoesNotExist:
        consultation = None

    return JsonResponse({
        'success': True,
        'appointment_status': appointment.status,
        'consultation_status': consultation.status if consultation else 'scheduled',
        'doctor_joined': bool(consultation and consultation.doctor_joined_at),
        'patient_joined': bool(consultation and consultation.patient_joined_at),
        'can_join': access['can_join'],
        'message': access['message'],
        'room_name': consultation.room_name if consultation else appointment.meeting_id,
        'meeting_id': appointment.meeting_id,
    })





@login_required

def save_consultation_data(request):

    """Save consultation data including notes, prescription, and tasks"""

    if request.method != 'POST':

        return JsonResponse({'error': 'Method not allowed'}, status=405)

    

    if request.user.role != 'doctor':

        return JsonResponse({'error': 'Only doctors can save consultation data'}, status=403)

    

    try:

        data, daily_tasks_raw, daily_tasks = _load_consultation_save_payload(request)

        logger.debug("POST DATA: %s", request.POST)
        logger.debug("BODY: %s", _safe_request_body(request))
        logger.debug("DAILY TASKS RAW: %s", daily_tasks_raw)
        logger.debug("PARSED DAILY TASKS: %s", daily_tasks)

        appointment_id = data.get('appointmentId') or data.get('appointment_id')

        patient_id = data.get('patientId') or data.get('patient_id')

        if not appointment_id:
            return JsonResponse({'error': 'appointmentId is required'}, status=400)

        

        # Get appointment and consultation

        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor', 'doctor__user'),
            id=appointment_id,
        )

        if patient_id and str(appointment.patient_id) != str(patient_id):
            return JsonResponse({'error': 'Patient is not assigned to this appointment'}, status=403)

        consultation = _get_or_create_consultation_for_appointment(appointment)
        logger.debug("PATIENT: %s", appointment.patient)
        logger.debug("CONSULTATION: %s", consultation)

        

        # Save consultation notes

        notes_data = data.get('notes', {})

        consultation.notes = json.dumps(notes_data)

        consultation.save()

        

        try:
            doctor_profile = request.user.doctor_profile
        except Doctor.DoesNotExist:
            logger.warning(
                "Doctor profile missing while saving consultation data: user_id=%s appointment_id=%s",
                request.user.id,
                appointment_id,
            )
            return JsonResponse({'error': 'Doctor profile is missing.'}, status=403)

        if appointment.doctor_id != doctor_profile.id:
            return JsonResponse({'error': 'Doctor is not assigned to this appointment'}, status=403)

        prescription_data = _parse_json_value(data.get('prescription') or data.get('prescription_json'), {})
        tasks_data = daily_tasks
        prescription = None
        prescription_created = False

        from django.db import transaction

        with transaction.atomic():
            prescription = Prescription.objects.filter(consultation=consultation).first()
            if prescription_data.get('details') or prescription_data.get('instructions') or prescription_data.get('medications'):
                prescription, prescription_created = Prescription.objects.update_or_create(
                    consultation=consultation,
                    defaults={
                        'doctor': doctor_profile,
                        'patient': appointment.patient,
                        'prescription_text': prescription_data.get('details', ''),
                        'instructions': prescription_data.get('instructions', ''),
                        'medications': prescription_data.get('medications', []),
                    },
                )

            replace_result = replace_active_daily_tasks(
                patient=appointment.patient,
                doctor=doctor_profile,
                consultation=consultation,
                tasks_data=tasks_data,
                prescription=prescription,
            )

        tasks_created = replace_result['created_count']
        logger.debug("save_consultation_data created DailyTask objects: %s", list(replace_result['created_tasks']))

        

        return JsonResponse({

            'success': True, 

            'message': f'Consultation saved and {tasks_created} daily tasks assigned.',

            'prescription_created': prescription_created,

            'tasks_created': tasks_created,

            'tasks_saved': tasks_created

        })

        

    except json.JSONDecodeError:

        return JsonResponse({'error': 'Invalid JSON data'}, status=400)

    except Http404:

        return JsonResponse({'error': 'Appointment not found'}, status=404)

    except Exception as e:

        logger.exception("Consultation data save failed")

        return JsonResponse({'error': str(e)}, status=500)





# OTP functionality (commented for future implementation)

# def send_otp(request):

#     """Send OTP for verification"""

#     if request.method == 'POST':

#         phone = request.POST.get('phone')

#         

#         try:

#             user = User.objects.get(phone=phone)

#             user.generate_otp()

#             

#             # Send SMS logic here

#             # sms_service.send(phone, f"Your OTP is: {user.otp_code}")

#             

#             return JsonResponse({'success': True, 'message': 'OTP sent successfully'})

#         except User.DoesNotExist:

#             return JsonResponse({'success': False, 'message': 'Phone number not found'})

#     

#     return JsonResponse({'success': False, 'message': 'Invalid request'})





# def verify_otp(request):

#     """Verify OTP code"""

#     if request.method == 'POST':

#         phone = request.POST.get('phone')

#         otp_code = request.POST.get('otp_code')

#         

#         try:

#             user = User.objects.get(phone=phone, otp_code=otp_code)

#             

#             if user.otp_expires and user.otp_expires > timezone.now():

#                 user.is_verified = True

#                 user.otp_code = None

#                 user.otp_expires = None

#                 user.save()

#                 return JsonResponse({'success': True, 'message': 'OTP verified successfully'})

#             else:

#                 return JsonResponse({'success': False, 'message': 'OTP expired'})

#         except User.DoesNotExist:

#             return JsonResponse({'success': False, 'message': 'Invalid OTP'})

#     

#     return JsonResponse({'success': False, 'message': 'Invalid request'})





# Payment integration (commented for future implementation)

# def process_payment(request, appointment_id):

#     """Process payment for appointment"""

#     appointment = get_object_or_404(Appointment, id=appointment_id)

#     payment = appointment.payment

#     

#     if request.method == 'POST':

#         # SSLCommerz integration

#         sslcommerz = SSLCommerzPayment()

#         response = sslcommerz.create_payment(payment)

#         

#         if response['success']:

#             return redirect(response['gateway_url'])

#         else:

#             messages.error(request, 'Payment processing failed')

#             return redirect('patient_appointments')

#     

#     context = {'appointment': appointment, 'payment': payment}

#     return render(request, 'payment/process.html', context)





# def payment_success(request):

#     """Payment success callback"""

#     transaction_id = request.GET.get('transaction_id')

#     

#     # Verify payment with SSLCommerz

#     sslcommerz = SSLCommerzPayment()

#     result = sslcommerz.verify_payment(transaction_id)

#     

#     if result['success']:

#         # Update payment status

#         payment = Payment.objects.get(transaction_id=transaction_id)

#         payment.status = 'completed'

#         payment.transaction_id = transaction_id

#         payment.save()

#         

#         # Update appointment status

#         payment.appointment.status = 'confirmed'

#         payment.appointment.save()

#         

#         return redirect('payment_success')

#     

#     return redirect('payment_fail')





# def payment_fail(request):

#     """Payment failure callback"""

#     return render(request, 'payment/fail.html')





# Admin Management Views

@login_required

def admin_users(request):

    """Admin users management page"""

    if request.user.role != 'admin':

        return redirect('home')

    

    # Get all users with statistics

    users = User.objects.all().order_by('-date_joined')

    total_users = users.count()

    total_patients = users.filter(role='patient').count()

    total_doctors = users.filter(role='doctor').count()

    total_admins = users.filter(role='admin').count()

    

    context = {

        'users': users,

        'total_users': total_users,

        'total_patients': total_patients,

        'total_doctors': total_doctors,

        'total_admins': total_admins,

    }

    return render(request, 'admin/users_detail.html', context)





# Task and Prescription Management Views

@login_required

def complete_daily_task(request, task_id):

    """Mark a daily task as completed"""
    

    if request.user.role != 'patient':

        return JsonResponse({'success': False, 'error': 'Unauthorized'})

    

    if request.method == 'POST':

        try:

            daily_task = DailyTask.objects.get(id=task_id, patient=request.user, is_active=True)

            completion, _created, was_updated = mark_task_completed(
                request.user,
                daily_task,
                notes=request.POST.get('notes', ''),
            )

            if was_updated:

                

                # Create success notification

                Notification.objects.create(

                    user=request.user,

                    title="Task Completed!",

                    message=f"Great job! You completed: {daily_task.title}",

                    notification_type="system",

                    is_actionable=False

                )

                

                return JsonResponse({

                    'success': True,

                    'message': 'Task marked as completed!',

                    'completed_at': completion.completed_at.strftime('%I:%M %p')

                })

            else:

                return JsonResponse({

                    'success': False,

                    'error': 'Task already completed'

                })

                

        except DailyTask.DoesNotExist:

            return JsonResponse({'success': False, 'error': 'Task not found'})

        except Exception as e:

            logger.warning("Task completion failed: %s", e)

            return JsonResponse({'success': False, 'error': 'Server error occurred'})

    

    return JsonResponse({'success': False, 'error': 'Invalid request method'})





@login_required

def save_prescription_and_tasks(request, consultation_id):

    """Save prescription and assign tasks during consultation"""

    if request.user.role != 'doctor':

        return JsonResponse({'success': False, 'error': 'Unauthorized'})

    

    if request.method == 'POST':

        try:

            consultation = get_object_or_404(
                Consultation.objects.select_related('appointment', 'appointment__patient', 'appointment__doctor', 'appointment__doctor__user'),
                id=consultation_id,
            )

            appointment = consultation.appointment

            try:
                doctor = request.user.doctor_profile
            except Doctor.DoesNotExist:
                logger.warning(
                    "Doctor profile missing while saving prescription/tasks: user_id=%s consultation_id=%s",
                    request.user.id,
                    consultation_id,
                )
                return JsonResponse({'success': False, 'error': 'Doctor profile is missing.'}, status=403)

            if appointment.doctor_id != doctor.id:

                return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

            

            data, daily_tasks_raw, daily_tasks = _load_consultation_save_payload(request)

            logger.debug("POST DATA: %s", request.POST)
            logger.debug("BODY: %s", _safe_request_body(request))
            logger.debug("DAILY TASKS RAW: %s", daily_tasks_raw)
            logger.debug("PARSED DAILY TASKS: %s", daily_tasks)
            logger.debug("PATIENT: %s", appointment.patient)
            logger.debug("CONSULTATION: %s", consultation)

            prescription_data = _parse_json_value(data.get('prescription') or data.get('prescription_json'), {})

            tasks_data = daily_tasks

            

            from django.db import transaction

            with transaction.atomic():
                prescription = Prescription.objects.filter(consultation=consultation).first()
                prescription_text = prescription_data.get('text') or prescription_data.get('details') or ''
                if prescription_text or prescription_data.get('instructions') or prescription_data.get('medications'):
                    prescription, _prescription_created = Prescription.objects.update_or_create(
                        consultation=consultation,
                        defaults={
                            'doctor': doctor,
                            'patient': consultation.appointment.patient,
                            'prescription_text': prescription_text,
                            'medications': prescription_data.get('medications', []),
                            'instructions': prescription_data.get('instructions', ''),
                        },
                    )

                replace_result = replace_active_daily_tasks(
                    patient=consultation.appointment.patient,
                    doctor=doctor,
                    consultation=consultation,
                    tasks_data=tasks_data,
                    prescription=prescription,
                )

            old_task_count = replace_result['deactivated_count']
            tasks_created = replace_result['created_count']
            logger.debug("save_prescription_and_tasks created DailyTask objects: %s", list(replace_result['created_tasks']))

            

            # Notify patient

            Notification.objects.create(

                user=consultation.appointment.patient,

                title="New Prescription & Tasks",

                message=f"Dr. {doctor.user.get_full_name()} has assigned new tasks and prescription.",

                notification_type="prescription_update",

                is_actionable=True,

                action_url="/patient/dashboard/"

            )

            

            return JsonResponse({

                'success': True,

                'prescription_id': prescription.id if prescription else None,

                'tasks_created': tasks_created,
                'tasks_saved': tasks_created,

                'old_tasks_deactivated': old_task_count,

                'message': f'Consultation saved and {tasks_created} daily tasks assigned.'

            })

            

        except Http404:

            return JsonResponse({'success': False, 'error': 'Consultation not found'}, status=404)

        except Exception as e:

            logger.exception("Prescription and task save failed for consultation %s", consultation_id)

            return JsonResponse({'success': False, 'error': str(e)})

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def get_health_task_templates(request):

    """Get predefined health task templates for doctors"""

    if request.user.role != 'doctor':

        return JsonResponse({'success': False, 'error': 'Unauthorized'})

    

    templates = HealthTaskTemplate.objects.filter(is_active=True)

    

    template_data = []

    for template in templates:

        template_data.append({

            'id': template.id,

            'title': template.title,

            'description': template.description,

            'category': template.category,

            'icon': template.icon,

            'default_duration': template.default_duration_days

        })

    

    return JsonResponse({'success': True, 'templates': template_data})





@login_required

def clear_all_patient_tasks(request):

    """Debug function to clear all tasks for current patient"""

    if request.user.role != 'patient':

        return JsonResponse({'success': False, 'error': 'Only patients can use this'})

    

    try:

        active_tasks = DailyTask.objects.filter(patient=request.user, is_active=True)

        task_count = active_tasks.count()

        active_tasks.update(is_active=False, updated_at=timezone.now())

        

        return JsonResponse({

            'success': True,

            'message': f'Deactivated {task_count} active tasks successfully'

        })

        

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)})





@login_required

def refresh_tasks(request):

    """Force refresh tasks for patient dashboard"""

    if request.user.role != 'patient':

        return JsonResponse({'success': False, 'error': 'Only patients can use this'})

    

    try:

        # Force database refresh

        from django.db import transaction

        transaction.commit()

        

        # Get fresh task data

        all_tasks = DailyTask.objects.filter(patient=request.user)

        active_tasks = DailyTask.objects.filter(patient=request.user, is_active=True)

        

        return JsonResponse({

            'success': True,

            'total_tasks': all_tasks.count(),

            'active_tasks': active_tasks.count(),

            'tasks': [

                {

                    'title': task.title,

                    'active': task.is_active,

                    'created': task.created_at.date().isoformat()

                }

                for task in active_tasks

            ]

        })

        

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)})





@login_required

def mark_all_notifications_read(request):

    """Mark all notifications as read for the user"""

    if request.method == 'POST':

        try:

            # Mark all unread notifications as read

            updated_count = Notification.objects.filter(

                user=request.user,

                is_read=False

            ).update(is_read=True)

            

            return JsonResponse({

                'success': True,

                'message': f'Marked {updated_count} notifications as read',

                'count': updated_count

            })

        except Exception as e:

            return JsonResponse({

                'success': False,

                'error': 'Error marking notifications as read'

            })

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def check_notifications(request):

    """Check for new notifications"""

    if request.method == 'GET':

        try:

            unread_count = Notification.objects.filter(

                user=request.user,

                is_read=False

            ).count()

            

            # Get all notifications (both read and unread)

            notifications = Notification.objects.filter(

                user=request.user

            ).order_by('-created_at')[:20]  # Get last 20 notifications

            

            notification_data = []

            for notification in notifications:

                notification_data.append({

                    'id': notification.id,

                    'title': notification.title,

                    'message': notification.message,

                    'notification_type': notification.notification_type,

                    'is_read': notification.is_read,

                    'is_actionable': notification.is_actionable,

                    'action_url': notification.action_url,

                    'created_at': notification.created_at.isoformat()

                })

            

            return JsonResponse({

                'success': True,

                'unread_count': unread_count,

                'notifications': notification_data

            })

        except Exception as e:

            return JsonResponse({

                'success': False,

                'error': f'Error loading notifications: {str(e)}'

            })

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def mark_notification_read(request, notification_id):

    """Mark notification as read"""

    if request.method == 'POST':

        try:

            notification = Notification.objects.get(id=notification_id, user=request.user)

            notification.is_read = True

            notification.save()

            

            return JsonResponse({'success': True})

        except Notification.DoesNotExist:

            return JsonResponse({'success': False, 'error': 'Notification not found'})

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def get_prescription_details(request, prescription_id):

    """Get prescription details for modal display"""

    if request.method == 'GET':

        try:

            prescription = Prescription.objects.get(id=prescription_id, patient=request.user)

            

            # Prepare medications data

            medications = []

            if prescription.medications:

                for med in prescription.medications:

                    medications.append({

                        'name': med.get('name', ''),

                        'dosage': med.get('dosage', ''),

                        'frequency': med.get('frequency', '')

                    })

            

            prescription_data = {

                'id': prescription.id,

                'doctor_name': prescription.doctor.user.get_full_name() or prescription.doctor.user.username,

                'date': prescription.created_at.strftime('%B %d, %Y'),

                'status': 'Active',

                'medications': medications,

                'notes': prescription.prescription_text,

                'instructions': prescription.instructions

            }

            

            return JsonResponse({

                'success': True,

                'prescription': prescription_data

            })

        except Prescription.DoesNotExist:

            return JsonResponse({'success': False, 'error': 'Prescription not found'})

        except Exception as e:

            return JsonResponse({'success': False, 'error': str(e)})

    

    return JsonResponse({'success': False, 'error': 'Invalid request'})





@login_required

def download_prescription_pdf(request, prescription_id):

    """Generate and download prescription PDF"""

    from django.http import HttpResponse

    from django.template.loader import render_to_string

    

    if request.user.role != 'patient':

        return JsonResponse({'success': False, 'error': 'Unauthorized'})

    

    try:

        prescription = Prescription.objects.get(id=prescription_id, patient=request.user)

        

        # Generate HTML content for prescription

        html_content = render_to_string('patient/prescription_pdf.html', {

            'prescription': prescription,

            'patient': request.user,

            'doctor': prescription.doctor,

        })

        

        # Return HTML as downloadable file

        response = HttpResponse(html_content, content_type='text/html')

        response['Content-Disposition'] = f'attachment; filename="prescription_{prescription.id}.html"'

        

        return response

        

    except Prescription.DoesNotExist:

        return JsonResponse({'success': False, 'error': 'Prescription not found'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)})





@login_required

def admin_appointments(request):

    """Admin appointments management page"""

    if request.user.role != 'admin':

        return redirect('home')

    

    # Get all appointments with statistics

    appointments = Appointment.objects.all().order_by('-created_at')

    total_appointments = appointments.count()

    scheduled_appointments = appointments.filter(status='scheduled').count()

    completed_appointments = appointments.filter(status='completed').count()

    cancelled_appointments = appointments.filter(status='cancelled').count()

    

    context = {

        'appointments': appointments,

        'total_appointments': total_appointments,

        'scheduled_appointments': scheduled_appointments,

        'completed_appointments': completed_appointments,

        'cancelled_appointments': cancelled_appointments,

    }

    return render(request, 'admin/appointments_detail.html', context)





@login_required

def admin_assessments(request):

    """Admin assessments management page"""

    if request.user.role != 'admin':

        return redirect('home')

    

    # Get all assessment questions and results

    questions = AssessmentQuestion.objects.all().order_by('-created_at')

    assessments = PatientAssessment.objects.all().order_by('-created_at')

    total_questions = questions.count()

    total_assessments = assessments.count()

    completed_assessments = assessments.filter(completed=True).count()

    

    context = {

        'questions': questions,

        'assessments': assessments,

        'total_questions': total_questions,

        'total_assessments': total_assessments,

        'completed_assessments': completed_assessments,

    }

    return render(request, 'admin/assessments_detail.html', context)

#     messages.error(request, 'Payment failed. Please try again.')

#     return redirect('patient_appointments')





# ==================== BLOG SYSTEM VIEWS ====================



@login_required

def doctor_write_blog(request):

    """Doctor blog writing page - create new blog post"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can write blogs.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor profile not found.')

        return redirect('home')

    

    if request.method == 'POST':

        title = request.POST.get('title', '').strip()

        excerpt = request.POST.get('excerpt', '').strip()

        content = request.POST.get('content', '').strip()

        category = request.POST.get('category', 'mental-health')

        featured_image = request.POST.get('featured_image', '').strip()

        status = request.POST.get('status', 'published')  # Get status from form

        

        if not title or not content:

            messages.error(request, 'Title and content are required.')

            return render(request, 'doctor/write_blog.html', {

                'title': title,

                'excerpt': excerpt,

                'content': content,

                'category': category,

                'featured_image': featured_image,

                'categories': BlogPost.CATEGORY_CHOICES,

            })

        

        # Create blog post

        blog_post = BlogPost.objects.create(

            title=title,

            excerpt=excerpt or title,

            content=content,

            author=doctor,

            category=category,

            featured_image=featured_image if featured_image else None,

            status=status

        )

        

        # Publish only if status is published

        if status == 'published':

            blog_post.publish()

            messages.success(request, f'Blog post "{title}" published successfully!')

        else:

            messages.success(request, f'Blog post "{title}" saved as draft!')

        

        return redirect('doctor_blog_management')

    

    return render(request, 'doctor/write_blog.html', {

        'categories': BlogPost.CATEGORY_CHOICES,

    })





@login_required

def doctor_blog_management(request):

    """Doctor blog management page - view, edit, delete own blogs"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can manage blogs.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor profile not found.')

        return redirect('home')

    

    # Get all blogs by this doctor

    blogs = BlogPost.objects.filter(author=doctor).order_by('-created_at')

    

    context = {

        'blogs': blogs,

        'total_blogs': blogs.count(),

        'published_count': blogs.filter(status='published').count(),

        'draft_count': blogs.filter(status='draft').count(),

    }

    return render(request, 'doctor/blog_management.html', context)





@login_required

def doctor_edit_blog(request, blog_id):

    """Edit existing blog post"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can edit blogs.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

        blog = BlogPost.objects.get(id=blog_id, author=doctor)

    except (Doctor.DoesNotExist, BlogPost.DoesNotExist):

        messages.error(request, 'Blog post not found or you do not have permission to edit it.')

        return redirect('doctor_blog_management')

    

    if request.method == 'POST':

        title = request.POST.get('title', '').strip()

        excerpt = request.POST.get('excerpt', '').strip()

        content = request.POST.get('content', '').strip()

        category = request.POST.get('category', 'mental-health')

        featured_image = request.POST.get('featured_image', '').strip()

        status = request.POST.get('status', 'draft')

        

        if not title or not content:

            messages.error(request, 'Title and content are required.')

            return render(request, 'doctor/edit_blog.html', {

                'blog': blog,

                'categories': BlogPost.CATEGORY_CHOICES,

            })

        

        # Update blog post

        blog.title = title

        blog.excerpt = excerpt or title

        blog.content = content

        blog.category = category

        blog.featured_image = featured_image if featured_image else None

        blog.status = status

        

        if status == 'published' and not blog.published_at:

            blog.publish()

        else:

            blog.save()

        

        messages.success(request, f'Blog post "{title}" updated successfully!')

        return redirect('doctor_blog_management')

    

    return render(request, 'doctor/edit_blog.html', {

        'blog': blog,

        'categories': BlogPost.CATEGORY_CHOICES,

    })





@login_required

def doctor_delete_blog(request, blog_id):

    """Delete blog post"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can delete blogs.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

        blog = BlogPost.objects.get(id=blog_id, author=doctor)

        blog_title = blog.title

        blog.delete()

        messages.success(request, f'Blog post "{blog_title}" deleted successfully!')

    except (Doctor.DoesNotExist, BlogPost.DoesNotExist):

        messages.error(request, 'Blog post not found or you do not have permission to delete it.')

    

    return redirect('doctor_blog_management')





def blog_detail(request, slug):

    """Blog detail page - view full article"""

    blog = get_object_or_404(BlogPost, slug=slug, status='published')

    

    # Increment view count

    blog.increment_views()

    

    # Get related blogs by same author or same category

    related_blogs = BlogPost.objects.filter(

        status='published'

    ).filter(

        Q(author=blog.author) | Q(category=blog.category)

    ).exclude(id=blog.id)[:3]

    

    context = {

        'blog': blog,

        'related_blogs': related_blogs,

        'author_name': blog.author.user.get_full_name() or blog.author.user.username,

        'author_specialty': blog.author.specialty,

    }

    return render(request, 'home/blog_detail.html', context)





def update_blogs_view(request):

    """Updated blogs view - fetch real published blogs from database"""

    # Get user's last assessment result (only for logged-in patients)

    last_assessment = None

    recommended_categories = []

    stress_level = None

    

    # If user is authenticated and is a patient, get personalized recommendations

    if request.user.is_authenticated and request.user.role == 'patient':

        try:

            last_assessment = PatientAssessment.objects.filter(

                patient=request.user

            ).order_by('-created_at').first()

            

            if last_assessment:

                stress_level = last_assessment.stress_level

                # Map stress levels to recommended blog categories

                stress_level_mapping = {

                    'low': ['mindfulness', 'self-care', 'sleep'],

                    'moderate': ['anxiety', 'workplace', 'self-care'],

                    'high': ['depression', 'therapy', 'relationships'],

                    'severe': ['therapy', 'depression', 'anxiety']

                }

                

                recommended_categories = stress_level_mapping.get(

                    last_assessment.stress_level, 

                    ['mindfulness', 'self-care']

                )

        except:

            pass

    

    # Get published blogs from database

    published_blogs = BlogPost.objects.filter(status='published').order_by('-published_at')

    

    # Get featured blog

    featured_blog = published_blogs.filter(is_featured=True).first()

    if not featured_blog:

        featured_blog = published_blogs.first()

    

    # Get recommended blogs based on assessment

    recommended_blogs = []

    if recommended_categories:

        recommended_blogs = published_blogs.filter(

            category__in=recommended_categories

        ).exclude(id=featured_blog.id if featured_blog else None)[:3]

    

    # Get all other blogs

    all_blogs = published_blogs.exclude(

        id__in=[b.id for b in recommended_blogs] + ([featured_blog.id] if featured_blog else [])

    )

    

    # Get blogs by category

    categories = BlogPost.CATEGORY_CHOICES

    category_blogs = {}

    for cat_key, cat_name in categories:

        cat_blogs = published_blogs.filter(category=cat_key)[:4]

        if cat_blogs.exists():

            category_blogs[cat_key] = {

                'name': cat_name,

                'blogs': cat_blogs,

                'count': published_blogs.filter(category=cat_key).count()

            }

    

    context = {

        'last_assessment': last_assessment,

        'recommended_categories': recommended_categories,

        'recommended_blogs': recommended_blogs,

        'stress_level': stress_level,

        'featured_blog': featured_blog,

        'all_blogs': all_blogs,

        'category_blogs': category_blogs,

    }

    return render(request, 'patient/blogs.html', context)





# ==================== DOCTOR SCHEDULE MANAGEMENT VIEWS ====================



@login_required

def doctor_schedule(request):

    """Doctor schedule management page - manage availability"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can manage schedules.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor profile not found.')

        return redirect('home')

    

    # Get existing schedules grouped by day

    schedules = DoctorSchedule.objects.filter(doctor=doctor, is_available=True)

    

    # Group by day

    day_schedules = {}

    for day_code, day_name in DoctorSchedule.DAY_CHOICES:

        day_schedules[day_code] = {

            'name': day_name,

            'slots': schedules.filter(day_of_week=day_code).order_by('start_time')

        }

    

    context = {

        'day_schedules': day_schedules,

        'has_schedule': schedules.exists(),

    }

    return render(request, 'doctor/schedule.html', context)





@login_required

def doctor_add_schedule(request):

    """Add new schedule slot for doctor"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can manage schedules.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

    except Doctor.DoesNotExist:

        messages.error(request, 'Doctor profile not found.')

        return redirect('home')

    

    if request.method == 'POST':

        day_of_week = request.POST.get('day_of_week')

        start_time = request.POST.get('start_time')

        end_time = request.POST.get('end_time')

        slot_duration = request.POST.get('slot_duration', 30)

        

        if not day_of_week or not start_time or not end_time:

            messages.error(request, 'Please fill in all fields.')

            return redirect('doctor_schedule')

        

        try:

            # Convert string times to time objects

            from datetime import datetime

            start_time_obj = datetime.strptime(start_time, '%H:%M').time()

            end_time_obj = datetime.strptime(end_time, '%H:%M').time()

            

            if start_time_obj >= end_time_obj:

                messages.error(request, 'Start time must be before end time.')

                return redirect('doctor_schedule')

            

            # Check for overlapping schedules

            existing_schedules = DoctorSchedule.objects.filter(

                doctor=doctor,

                day_of_week=int(day_of_week),

                is_available=True

            )

            

            # Check if new schedule overlaps with existing

            for schedule in existing_schedules:

                if (start_time_obj < schedule.end_time and 

                    end_time_obj > schedule.start_time):

                    messages.error(

                        request, 

                        f'This time slot overlaps with an existing schedule: '

                        f'{schedule.start_time.strftime("%H:%M")} - {schedule.end_time.strftime("%H:%M")}'

                    )

                    return redirect('doctor_schedule')

            

            # Create schedule

            schedule = DoctorSchedule.objects.create(

                doctor=doctor,

                day_of_week=int(day_of_week),

                start_time=start_time_obj,

                end_time=end_time_obj,

                slot_duration=int(slot_duration),

                is_available=True

            )

            

            day_name = dict(DoctorSchedule.DAY_CHOICES)[int(day_of_week)]

            messages.success(

                request, 

                f'Schedule added: {day_name} ({start_time} - {end_time})'

            )

        except Exception as e:

            messages.error(request, f'Error adding schedule: {str(e)}')

        

        return redirect('doctor_schedule')

    

    return redirect('doctor_schedule')





@login_required

def doctor_delete_schedule(request, schedule_id):

    """Delete schedule slot"""

    if request.user.role != 'doctor':

        messages.error(request, 'Only doctors can manage schedules.')

        return redirect('home')

    

    try:

        doctor = Doctor.objects.get(user=request.user)

        schedule = DoctorSchedule.objects.get(id=schedule_id, doctor=doctor)

        

        day_name = dict(DoctorSchedule.DAY_CHOICES)[schedule.day_of_week]

        time_str = f"{schedule.start_time.strftime('%H:%M')} - {schedule.end_time.strftime('%H:%M')}"

        

        schedule.delete()

        messages.success(request, f'Schedule removed: {day_name} ({time_str})')

    except (Doctor.DoesNotExist, DoctorSchedule.DoesNotExist):

        messages.error(request, 'Schedule not found or you do not have permission to delete it.')

    

    return redirect('doctor_schedule')





@login_required

def get_available_slots_api(request, doctor_id):

    """API endpoint to get available time slots for a doctor on a specific date"""

    from datetime import datetime, timedelta

    

    try:

        doctor = Doctor.objects.get(id=doctor_id)

        date_str = request.GET.get('date')

        

        if not date_str:

            return JsonResponse({'error': 'Date parameter is required'}, status=400)

        

        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        day_of_week = selected_date.weekday()

        

        # Get doctor's schedules for this day

        schedules = DoctorSchedule.objects.filter(

            doctor=doctor,

            day_of_week=day_of_week,

            is_available=True

        )

        

        if not schedules.exists():

            return JsonResponse({

                'available': False,

                'message': 'Doctor is not available on this day',

                'slots': []

            })

        

        # Get already booked slots for this date

        booked_slots = BookedSlot.objects.filter(

            doctor=doctor,

            appointment_date=selected_date,

            is_active=True

        ).values_list('appointment_time', flat=True)

        

        # Generate available slots

        all_slots = []

        for schedule in schedules:

            slots = schedule.get_time_slots()

            for slot_time_str in slots:

                slot_time = datetime.strptime(slot_time_str, '%H:%M').time()

                is_booked = slot_time in booked_slots

                

                # For today, hide past times

                is_past = False

                if selected_date == datetime.now().date():

                    current_time = datetime.now().time()

                    if slot_time <= current_time:

                        is_past = True

                

                # Convert to 12-hour format for display

                hour = slot_time.hour

                minute = slot_time.minute

                if hour < 12:

                    period = "AM"

                    display_hour = hour if hour != 0 else 12

                else:

                    period = "PM"

                    display_hour = hour - 12 if hour != 12 else 12

                

                time_str = f"{display_hour}:{minute:02d} {period}"

                

                all_slots.append({

                    'time': time_str,

                    'time_24h': slot_time_str,

                    'available': not is_booked and not is_past

                })

        

        return JsonResponse({

            'available': True,

            'date': date_str,

            'slots': all_slots

        })

        

    except Doctor.DoesNotExist:

        return JsonResponse({'error': 'Doctor not found'}, status=404)

    except Exception as e:

        return JsonResponse({'error': str(e)}, status=500)

