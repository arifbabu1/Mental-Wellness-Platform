from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import formset_factory
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count
from django.contrib.admin.models import LogEntry
import json
from datetime import datetime, timedelta
from django.utils import timezone
from .models import (
    User, Doctor, DoctorSpecialization, Appointment, AssessmentQuestion, PatientAssessment, Payment,
    BlogPost, Consultation, DailyTask, Notification, SystemEmailConfig, PaymentReceiverAccount,
    TaskCompletion,
)
from .forms import AssessmentQuestionForm, AssessmentQuestionOptionForm
from .recommendation_engine import CORE_TRACKS, DYNAMIC_QUESTION_GROUPS

# Custom decorator to check if user is a superuser for sensitive admin pages
def staff_required(view_func):
    @wraps(view_func)
    @user_passes_test(lambda user: user.is_authenticated and user.is_superuser)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper

@staff_required
def admin_dashboard(request):
    """
    Custom admin dashboard with statistics and enhanced UI
    """
    # Get statistics
    total_users = User.objects.count()
    total_appointments = Appointment.objects.count()
    total_assessments = PatientAssessment.objects.count()
    total_payments = Payment.objects.count()
    pending_consultations = Appointment.objects.filter(status__in=['confirmed', 'in_progress']).count()
    today = timezone.now()
    local_today = timezone.localdate()
    today_appointments = Appointment.objects.filter(appointment_date__date=local_today).count()
    upcoming_appointments = Appointment.objects.filter(
        appointment_date__gte=today,
        status__in=['scheduled', 'confirmed', 'waiting', 'in_progress'],
    ).count()
    completed_consultations = Consultation.objects.filter(status='completed').count()
    incomplete_consultations = Consultation.objects.filter(status__in=['incomplete', 'expired', 'cancelled']).count()
    
    # User growth analytics - last 6 months
    user_growth_labels = []
    user_growth_data = []
    
    for i in range(5, -1, -1):
        # Get month name and year
        month_date = today - timedelta(days=i*30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i > 0:
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            month_end = today
        
        # Count users created in this month
        month_count = User.objects.filter(
            date_joined__gte=month_start,
            date_joined__lte=month_end
        ).count()
        
        user_growth_labels.append(month_start.strftime('%b'))
        user_growth_data.append(month_count)
    
    # Weekly appointments analytics - last 7 days
    appointment_labels = []
    appointment_data = []
    
    for i in range(6, -1, -1):
        day_date = today - timedelta(days=i)
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        day_count = Appointment.objects.filter(
            appointment_date__gte=day_start,
            appointment_date__lte=day_end
        ).count()
        
        appointment_labels.append(day_date.strftime('%a'))
        appointment_data.append(day_count)
        
    # Role distribution
    total_patients = User.objects.filter(role='patient').count()
    total_doctors = User.objects.filter(role='doctor').count()
    total_admins = User.objects.filter(role='admin').count()

    # Content, task, and notification health
    total_blogs = BlogPost.objects.count()
    published_blogs = BlogPost.objects.filter(status='published').count()
    pending_blogs = BlogPost.objects.filter(status='pending').count()
    total_daily_tasks = DailyTask.objects.count()
    active_daily_tasks = DailyTask.objects.filter(is_active=True).count()
    completed_task_entries = TaskCompletion.objects.filter(is_completed=True).count()
    unread_notifications = Notification.objects.filter(is_read=False).count()
    
    # Real revenue data
    paid_statuses = ['completed', 'test_paid']
    total_revenue = Payment.objects.filter(status__in=paid_statuses).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    # Convert to int for display
    if total_revenue:
        total_revenue = int(total_revenue)

    active_email_config = SystemEmailConfig.active()
    active_payment_accounts = list(PaymentReceiverAccount.objects.filter(is_active=True).order_by('payment_method', 'account_name'))
    active_payment_methods = sorted({account.get_payment_method_display() for account in active_payment_accounts})
    default_receivers = {
        method: PaymentReceiverAccount.default_for_method(method)
        for method in ['bkash', 'nagad', 'card', 'bank']
    }
    recent_payments = Payment.objects.select_related(
        'appointment__patient',
        'appointment__doctor__user',
        'payment_receiver_account',
    ).order_by('-created_at')[:5]
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_appointments = Appointment.objects.select_related('patient', 'doctor__user').order_by('-appointment_date')[:5]
    recent_consultations = Consultation.objects.select_related(
        'appointment__patient',
        'appointment__doctor__user',
    ).order_by('-created_at')[:5]
    recent_notifications = Notification.objects.select_related('user').order_by('-created_at')[:5]
    recent_activity = LogEntry.objects.select_related('content_type', 'user').order_by('-action_time')[:10]
    
    context = {
        'total_users': total_users,
        'total_appointments': total_appointments,
        'total_assessments': total_assessments,
        'total_payments': total_payments,
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'total_admins': total_admins,
        'total_revenue': total_revenue,
        'pending_consultations': pending_consultations,
        'local_today': local_today,
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_appointments,
        'completed_consultations': completed_consultations,
        'incomplete_consultations': incomplete_consultations,
        'total_blogs': total_blogs,
        'published_blogs': published_blogs,
        'pending_blogs': pending_blogs,
        'total_daily_tasks': total_daily_tasks,
        'active_daily_tasks': active_daily_tasks,
        'completed_task_entries': completed_task_entries,
        'unread_notifications': unread_notifications,
        'active_email_config': active_email_config,
        'email_config_active': bool(active_email_config),
        'default_from_email': active_email_config.default_from_email if active_email_config else '',
        'active_payment_accounts': active_payment_accounts,
        'active_payment_methods': active_payment_methods,
        'active_payment_method_count': len(active_payment_methods),
        'default_receivers': default_receivers,
        'active_bkash_receiver': default_receivers['bkash'],
        'active_nagad_receiver': default_receivers['nagad'],
        'active_card_receiver': default_receivers['card'],
        'active_bank_receiver': default_receivers['bank'],
        'recent_payments': recent_payments,
        'recent_users': recent_users,
        'recent_appointments': recent_appointments,
        'recent_consultations': recent_consultations,
        'recent_notifications': recent_notifications,
        'failed_email_logs': [],
        'action_list': recent_activity,
        # Chart data - properly serialized for JavaScript
        'user_growth_labels': json.dumps(user_growth_labels),
        'user_growth_data': json.dumps(user_growth_data),
        'appointment_labels': json.dumps(appointment_labels),
        'appointment_data': json.dumps(appointment_data),
        'title': 'Admin Dashboard',
    }
    
    return render(request, 'admin/admin_dashboard.html', context)

@staff_required
def users_detail(request):
    """
    Users management detail page
    """
    role_filter = request.GET.get('role')
    
    # Start with all users for counts
    all_users = User.objects.all().order_by('-date_joined')
    total_users = all_users.count()
    total_patients = all_users.filter(role='patient').count()
    total_doctors = all_users.filter(role='doctor').count()
    total_admins = all_users.filter(role='admin').count()
    
    # Filter users based on role parameter
    if role_filter:
        users = all_users.filter(role=role_filter)
    else:
        users = all_users
    
    context = {
        'users': users,
        'total_users': total_users,
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'total_admins': total_admins,
        'title': 'Users Management',
    }
    
    return render(request, 'admin/users_detail.html', context)

@staff_required
def doctors_detail(request):
    """
    Doctors management detail page
    """
    doctors = Doctor.objects.prefetch_related('specializations', 'primary_focuses').select_related('user').order_by('-created_at')
    total_doctors = doctors.count()
    active_doctors = doctors.filter(is_available=True).count()
    specialties = list(
        DoctorSpecialization.objects.filter(doctors__in=doctors).distinct().values_list('label', flat=True)
    )
    total_appointments = Appointment.objects.filter(doctor__in=doctors).count()
    
    context = {
        'doctors': doctors,
        'total_doctors': total_doctors,
        'active_doctors': active_doctors,
        'specialties': specialties,
        'total_appointments': total_appointments,
        'title': 'Doctors Management',
    }
    
    return render(request, 'admin/doctors_detail.html', context)

@staff_required
def appointments_detail(request):
    """
    Appointments management detail page
    """
    appointments = Appointment.objects.select_related(
        'patient',
        'doctor__user'
    ).order_by('-appointment_date')
    
    total_appointments = appointments.count()
    pending_appointments = appointments.filter(status='pending_payment').count()
    scheduled_appointments = appointments.filter(status='scheduled').count()
    confirmed_appointments = appointments.filter(status='confirmed').count()
    in_progress_appointments = appointments.filter(status='in_progress').count()
    completed_appointments = appointments.filter(status='completed').count()
    cancelled_appointments = appointments.filter(status='cancelled').count()
    
    context = {
        'appointments': appointments,
        'total_appointments': total_appointments,
        'pending_appointments': pending_appointments,
        'scheduled_appointments': scheduled_appointments,
        'confirmed_appointments': confirmed_appointments,
        'in_progress_appointments': in_progress_appointments,
        'completed_appointments': completed_appointments,
        'cancelled_appointments': cancelled_appointments,
        'status_choices': Appointment.STATUS_CHOICES,
        'title': 'Appointments Management',
    }
    
    return render(request, 'admin/appointments_detail.html', context)

@staff_required
def assessments_detail(request):
    """
    Assessments management detail page
    """
    assessments = PatientAssessment.objects.select_related('patient').order_by('-created_at')
    total_assessments = assessments.count()
    stress_counts = {
        level: assessments.filter(stress_level=level).count()
        for level, _label in PatientAssessment.STRESS_LEVEL_CHOICES
    }
    
    context = {
        'assessments': assessments,
        'questions': AssessmentQuestion.objects.order_by('track_number', 'category'),
        'total_questions': AssessmentQuestion.objects.count(),
        'total_assessments': total_assessments,
        'completed_assessments': total_assessments,
        'stress_counts': stress_counts,
        'stress_chart_labels': json.dumps([label for _level, label in PatientAssessment.STRESS_LEVEL_CHOICES]),
        'stress_chart_data': json.dumps([stress_counts[level] for level, _label in PatientAssessment.STRESS_LEVEL_CHOICES]),
        'title': 'Assessments Management',
    }
    
    return render(request, 'admin/assessments_detail.html', context)


def _assessment_question_option_initial(question=None):
    if not question:
        return [
            {'option_order': 1, 'option_text': 'Never', 'score': 0},
            {'option_order': 2, 'option_text': 'Rarely', 'score': 1},
            {'option_order': 3, 'option_text': 'Sometimes', 'score': 2},
            {'option_order': 4, 'option_text': 'Often', 'score': 3},
            {'option_order': 5, 'option_text': 'Always', 'score': 4},
        ]
    options = question.option_choices or []
    initial = []
    for index, option in enumerate(options, start=1):
        if isinstance(option, dict):
            initial.append({
                'option_order': option.get('option_order') or option.get('order') or index,
                'option_text': option.get('option_text') or option.get('text') or '',
                'score': option.get('score', ''),
            })
    return initial or [
        {'option_order': 1, 'option_text': '', 'score': ''},
        {'option_order': 2, 'option_text': '', 'score': ''},
    ]


def _assessment_question_formset(post_data=None, question=None):
    option_formset_cls = formset_factory(AssessmentQuestionOptionForm, extra=0, can_delete=True)
    prefix = 'options'
    if post_data is not None:
        return option_formset_cls(post_data, prefix=prefix)
    return option_formset_cls(prefix=prefix, initial=_assessment_question_option_initial(question))


def _assessment_question_common_context(request, question_form, option_formset, instance=None):
    standard_options = [
        {'option_order': 1, 'option_text': 'Never', 'score': 0},
        {'option_order': 2, 'option_text': 'Rarely', 'score': 1},
        {'option_order': 3, 'option_text': 'Sometimes', 'score': 2},
        {'option_order': 4, 'option_text': 'Often', 'score': 3},
        {'option_order': 5, 'option_text': 'Always', 'score': 4},
    ]
    return {
        'question_form': question_form,
        'option_formset': option_formset,
        'question': instance,
        'choice_based_types': {'single_choice', 'multiple_choice', 'likert_scale', 'yes_no'},
        'standard_options_json': json.dumps(standard_options),
        'standard_options': standard_options,
        'core_tracks': CORE_TRACKS,
        'dynamic_question_groups': DYNAMIC_QUESTION_GROUPS,
        'title': 'Assessment Question',
    }


@staff_required
def assessment_questions_manage(request):
    questions = AssessmentQuestion.objects.order_by('track_number', 'id')
    group_filter = request.GET.get('group', 'all')
    status_filter = request.GET.get('status', 'all')
    category_filter = request.GET.get('category', 'all')

    if group_filter == 'general':
        questions = questions.filter(track_number__lte=7)
    elif group_filter == 'dynamic':
        questions = questions.filter(track_number__gt=7)

    if status_filter == 'active':
        questions = questions.filter(is_active=True)
    elif status_filter == 'inactive':
        questions = questions.filter(is_active=False)

    if category_filter != 'all':
        questions = questions.filter(category=category_filter)

    total_questions = AssessmentQuestion.objects.count()
    general_count = AssessmentQuestion.objects.filter(track_number__lte=7).count()
    dynamic_count = AssessmentQuestion.objects.filter(track_number__gt=7).count()
    return render(request, 'admin/assessment_questions.html', {
        'questions': questions,
        'total_questions': total_questions,
        'filtered_questions': questions.count(),
        'general_count': general_count,
        'dynamic_count': dynamic_count,
        'active_count': AssessmentQuestion.objects.filter(is_active=True).count(),
        'inactive_count': AssessmentQuestion.objects.filter(is_active=False).count(),
        'category_choices': AssessmentQuestion.CATEGORY_CHOICES,
        'current_group': group_filter,
        'current_status': status_filter,
        'current_category': category_filter,
        'dynamic_question_groups': DYNAMIC_QUESTION_GROUPS,
        'title': 'Assessment Questions',
    })


def _clean_assessment_options(option_formset):
    cleaned_options = [
        form.cleaned_data for form in option_formset
        if form.cleaned_data and not form.cleaned_data.get('DELETE') and (form.cleaned_data.get('option_text') or '').strip()
    ]
    cleaned_options = sorted(
        cleaned_options,
        key=lambda item: (item.get('option_order') or 9999, item.get('option_text') or '')
    )
    return [
        {
            'option_order': int(item.get('option_order') or index),
            'option_text': (item['option_text'] or '').strip(),
            'score': float(item['score']) if item.get('score') is not None else 0,
        }
        for index, item in enumerate(cleaned_options, start=1)
    ]


@staff_required
def assessment_question_add(request):
    if request.method == 'POST':
        question_form = AssessmentQuestionForm(request.POST)
        option_formset = _assessment_question_formset(request.POST)
        if question_form.is_valid() and option_formset.is_valid():
            question_type = question_form.cleaned_data['question_type']
            question_text = question_form.cleaned_data['question_text'].strip()
            track_number = question_form.cleaned_data['track_number']
            category = question_form.cleaned_data['category']
            duplicate_order = AssessmentQuestion.objects.exclude(
                id=getattr(question_form.instance, 'id', None)
            ).filter(track_number=track_number).exists()
            if duplicate_order:
                question_form.add_error('track_number', 'Another assessment question already uses this order number.')
            cleaned_options = _clean_assessment_options(option_formset)
            if question_type in {'single_choice', 'multiple_choice', 'likert_scale', 'yes_no'} and len(cleaned_options) < 2:
                question_form.add_error(None, 'Choice-based questions need at least two options.')
            if question_form.errors:
                pass
            else:
                question = question_form.save(commit=False)
                question.question_text = question_text
                question.option_choices = cleaned_options
                question.save()
                messages.success(request, 'Assessment question added successfully.')
                return redirect('assessment_questions_manage')
    else:
        question_form = AssessmentQuestionForm()
        option_formset = _assessment_question_formset()
    return render(request, 'admin/assessment_question_form.html', _assessment_question_common_context(request, question_form, option_formset))


@staff_required
def assessment_question_edit(request, question_id):
    question = get_object_or_404(AssessmentQuestion, id=question_id)
    if request.method == 'POST':
        question_form = AssessmentQuestionForm(request.POST, instance=question)
        option_formset = _assessment_question_formset(request.POST, question=question)
        if question_form.is_valid() and option_formset.is_valid():
            question_type = question_form.cleaned_data['question_type']
            category = question_form.cleaned_data['category']
            track_number = question_form.cleaned_data['track_number']
            duplicate_order = AssessmentQuestion.objects.exclude(id=question.id).filter(track_number=track_number).exists()
            if duplicate_order:
                question_form.add_error('track_number', 'Another assessment question already uses this order number.')
            cleaned_options = _clean_assessment_options(option_formset)
            if question_type in {'single_choice', 'multiple_choice', 'likert_scale', 'yes_no'} and len(cleaned_options) < 2:
                question_form.add_error(None, 'Choice-based questions need at least two options.')
            if not question_form.errors:
                updated_question = question_form.save(commit=False)
                updated_question.option_choices = cleaned_options
                updated_question.save()
                messages.success(request, 'Assessment question updated successfully.')
                return redirect('assessment_questions_manage')
    else:
        question_form = AssessmentQuestionForm(instance=question)
        option_formset = _assessment_question_formset(question=question)
    return render(request, 'admin/assessment_question_form.html', _assessment_question_common_context(request, question_form, option_formset, question))


@staff_required
@require_http_methods(['POST'])
def assessment_question_delete(request, question_id):
    question = get_object_or_404(AssessmentQuestion, id=question_id)
    question.delete()
    messages.success(request, 'Assessment question deleted successfully.')
    return redirect('assessment_questions_manage')


@staff_required
@require_http_methods(["POST"])
def toggle_doctor_availability(request, doctor_id):
    """
    Toggle doctor availability status via AJAX
    """
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        
        # Parse JSON data
        data = json.loads(request.body)
        new_availability = data.get('is_available', not doctor.is_available)
        
        # Update availability
        doctor.is_available = new_availability
        doctor.save()
        
        return JsonResponse({
            'success': True,
            'is_available': doctor.is_available,
            'message': 'Doctor availability updated successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@staff_required
def admin_redirect(request):
    """
    Redirect to admin dashboard
    """
    return render(request, 'admin/admin_dashboard.html')

@staff_required
def admin_payments(request):
    """
    Admin payments management page with comprehensive payment details
    """
    # Get all payments with related data
    payments = Payment.objects.select_related(
        'appointment__patient',
        'appointment__doctor__user'
    ).order_by('-created_at')
    
    # Calculate statistics
    paid_statuses = ['completed', 'test_paid']
    total_payments = payments.count()
    total_revenue = payments.filter(status__in=paid_statuses).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    total_commission = payments.filter(status__in=paid_statuses).aggregate(
        commission=Sum('admin_commission')
    )['commission'] or 0
    
    total_doctor_earnings = payments.filter(status__in=paid_statuses).aggregate(
        earnings=Sum('doctor_earning')
    )['earnings'] or 0
    
    # Payment status breakdown
    status_counts = {}
    for status, label in Payment.STATUS_CHOICES:
        status_counts[status] = payments.filter(status=status).count()
    
    # Recent transactions (last 10)
    recent_payments = payments[:10]
    
    # Monthly revenue data for charts
    today = timezone.now()
    monthly_revenue = []
    monthly_labels = []
    
    for i in range(6, -1, -1):
        month_date = today - timedelta(days=i*30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i > 0:
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            month_end = today
        
        month_revenue = payments.filter(
            status__in=paid_statuses,
            created_at__gte=month_start,
            created_at__lte=month_end
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        monthly_labels.append(month_start.strftime('%b'))
        monthly_revenue.append(float(month_revenue))
    
    # Doctor earnings breakdown
    doctor_earnings = payments.filter(status__in=paid_statuses).values(
        'appointment__doctor__user__first_name',
        'appointment__doctor__user__last_name'
    ).annotate(
        total_earnings=Sum('doctor_earning'),
        total_appointments=Count('id')
    ).order_by('-total_earnings')[:10]
    
    context = {
        'payments': payments,
        'total_payments': total_payments,
        'total_revenue': total_revenue,
        'total_commission': total_commission,
        'total_doctor_earnings': total_doctor_earnings,
        'status_counts': status_counts,
        'recent_payments': recent_payments,
        'monthly_labels': monthly_labels,
        'monthly_revenue': monthly_revenue,
        'doctor_earnings': doctor_earnings,
        'status_choices': Payment.STATUS_CHOICES,
        'active_payment_accounts': PaymentReceiverAccount.objects.filter(is_active=True).order_by('payment_method', 'account_name'),
    }
    
    return render(request, 'admin/admin_payments.html', context)
