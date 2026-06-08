import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render

from home.models import ClinicalAssessment, Doctor, EmergencyLog, Notification, User


logger = logging.getLogger(__name__)

BANGLADESH_EMERGENCY_NUMBER = '999'
PHQ9_QUESTIONS = [
    'Little interest or pleasure in doing things',
    'Feeling down, depressed, or hopeless',
    'Trouble sleeping or sleeping too much',
    'Feeling tired or having little energy',
    'Poor appetite or overeating',
    'Feeling bad about yourself',
    'Trouble concentrating on things',
    'Moving or speaking slowly or being restless',
    'Thoughts that you would be better off dead or of hurting yourself',
]
GAD7_QUESTIONS = [
    'Feeling nervous, anxious, or on edge',
    'Not being able to stop or control worrying',
    'Worrying too much about different things',
    'Trouble relaxing',
    'Being so restless that it\'s hard to sit still',
    'Becoming easily annoyed or irritable',
    'Feeling afraid as if something awful might happen',
]
ANSWER_SCALE = [
    ('0', 'Not at all'),
    ('1', 'Several days'),
    ('2', 'More than half the days'),
    ('3', 'Nearly every day'),
]


def _parse_required_scale_responses(request, prefix, total_questions):
    responses = []
    for index in range(1, total_questions + 1):
        raw_value = request.POST.get(f'{prefix}_{index}')
        if raw_value is None or raw_value == '':
            return None, f'Please answer all {prefix.upper()} questions before submitting.'
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None, f'Please answer all {prefix.upper()} questions before submitting.'
        if value not in {0, 1, 2, 3}:
            return None, f'Please answer all {prefix.upper()} questions before submitting.'
        responses.append(value)
    return responses, None


def get_depression_severity(score):
    if score <= 4:
        return 'minimal'
    if score <= 9:
        return 'mild'
    if score <= 14:
        return 'moderate'
    if score <= 19:
        return 'moderately_severe'
    return 'severe'


def get_anxiety_severity(score):
    if score <= 4:
        return 'minimal'
    if score <= 9:
        return 'mild'
    if score <= 14:
        return 'moderate'
    return 'severe'


def get_suicide_risk_level(answer):
    if answer == 0:
        return 'none'
    if answer == 1:
        return 'low'
    if answer == 2:
        return 'moderate'
    return 'high'


def _primary_condition_from_scores(phq9_score, gad7_score):
    if phq9_score >= 10 and gad7_score >= 10:
        return 'Depression & Anxiety'
    if phq9_score >= gad7_score:
        return 'Depression'
    return 'Anxiety'


def get_allowed_specialties(assessment):
    if assessment.emergency_risk or assessment.depression_severity in {'moderately_severe', 'severe'} or assessment.anxiety_severity == 'severe':
        return ['Psychiatrist', 'Clinical Psychologist']
    if assessment.depression_severity == 'moderate' or assessment.anxiety_severity == 'moderate':
        return ['Clinical Psychologist', 'Therapist']
    return ['Counselor', 'Therapist', 'Clinical Psychologist']


def get_relevant_expertise_tags(assessment):
    tags = []
    if assessment.depression_severity in {'moderate', 'moderately_severe', 'severe'}:
        tags.extend(['depression', 'sadness', 'hopeless', 'low self-esteem', 'fatigue'])
    if assessment.anxiety_severity in {'moderate', 'severe'}:
        tags.extend(['anxiety', 'panic', 'worry', 'fear', 'nervous'])
    if assessment.phq9_responses and len(assessment.phq9_responses) >= 4 and assessment.phq9_responses[2] >= 2:
        tags.extend(['insomnia', 'sleep', 'tired'])
    if assessment.phq9_responses and len(assessment.phq9_responses) >= 4 and assessment.phq9_responses[3] >= 2:
        tags.extend(['energy', 'fatigue', 'exhausted'])
    return tags


def calculate_clinical_doctor_score(doctor, assessment):
    score = 0
    specializations = set(doctor.specialization_values)
    focus_areas = set(doctor.primary_focus_values)

    if specializations & {'Psychiatrist', 'Clinical Psychologist'}:
        score += 40
    elif 'Therapist' in specializations:
        score += 30
    else:
        score += 20

    if assessment.primary_condition in focus_areas:
        score += 30
    elif focus_areas & {'Depression', 'Anxiety'}:
        score += 20
    else:
        score += 10

    if doctor.expertise_tags:
        relevant_tags = get_relevant_expertise_tags(assessment)
        if any(tag in doctor.expertise_tags for tag in relevant_tags):
            score += 15
        else:
            score += 5

    if doctor.years_of_experience >= 10:
        score += 10
    elif doctor.years_of_experience >= 5:
        score += 7
    elif doctor.years_of_experience >= 2:
        score += 4
    else:
        score += 2

    if doctor.available_online:
        score += 5

    if assessment.emergency_risk and doctor.emergency_support:
        score += 10

    return min(100, score)


def generate_clinical_match_reason(doctor, assessment, score):
    severity_label = assessment.depression_severity if 'Depression' in assessment.primary_condition else assessment.anxiety_severity
    condition_label = assessment.primary_condition.lower()
    reasons = {
        'Psychiatrist': f'Medical specialist for {severity_label} {condition_label}. Can provide medication management and psychiatric care.',
        'Clinical Psychologist': f'Clinical psychology expert for {severity_label} {condition_label}. Uses evidence-based therapy.',
        'Therapist': f'Therapeutic specialist for {severity_label} {condition_label}. Focuses on coping strategies and support.',
        'Counselor': f'Counseling professional for {severity_label} {condition_label}. Focuses on practical emotional support.',
    }

    primary_specialty = doctor.specialization_values[0] if doctor.specialization_values else doctor.specialty
    base_reason = reasons.get(primary_specialty, f'Mental health professional for {severity_label} {condition_label}.')
    if assessment.primary_condition in doctor.primary_focus_values:
        base_reason += f' Specializes in {assessment.primary_condition} treatment.'
    if assessment.emergency_risk and doctor.emergency_support:
        base_reason += ' Provides emergency crisis support.'
    return base_reason


def get_medical_disclaimer():
    return (
        'This assessment is a screening tool based on PHQ-9 and GAD-7. '
        'It is not a diagnosis or emergency service. '
        'If you are in immediate danger or thinking about self-harm, call Bangladesh emergency services at 999 now.'
    )


def _notify_emergency_flags(assessment):
    admins = User.objects.filter(Q(is_staff=True) | Q(role='admin')).distinct()
    for admin_user in admins:
        Notification.objects.create(
            user=admin_user,
            title='Critical clinical assessment flag',
            message=f'{assessment.patient.get_full_name() or assessment.patient.username} submitted a high-risk assessment.',
            notification_type='system',
            is_actionable=True,
            action_url='/admin/home/clinicalassessment/',
        )


def _log_emergency_assessment(request_user, assessment, suicide_answer):
    EmergencyLog.objects.create(
        user=request_user,
        message='High-risk PHQ-9 response detected during clinical assessment.',
        detected_terms=['phq9_q9_high'],
        risk_level='critical' if suicide_answer >= 3 else 'high',
        recommended_action='Contact emergency services at 999 and notify the care team.',
    )
    _notify_emergency_flags(assessment)


@login_required
def clinical_assessment(request):
    if request.user.role != 'patient':
        return redirect('home')

    context = {
        'phq9_questions': enumerate(PHQ9_QUESTIONS, 1),
        'gad7_questions': enumerate(GAD7_QUESTIONS, 1),
        'answer_scale': ANSWER_SCALE,
        'emergency_hotline': BANGLADESH_EMERGENCY_NUMBER,
        'page_title': 'Mental Health Clinical Assessment',
    }
    return render(request, 'patient/clinical_assessment.html', context)


@login_required
def submit_clinical_assessment(request):
    if request.user.role != 'patient' or request.method != 'POST':
        return redirect('home')

    phq9_responses, error = _parse_required_scale_responses(request, 'phq9', 9)
    if error:
        messages.error(request, error)
        return redirect('clinical_assessment')

    gad7_responses, error = _parse_required_scale_responses(request, 'gad7', 7)
    if error:
        messages.error(request, error)
        return redirect('clinical_assessment')

    try:
        session_duration = int(request.POST.get('session_duration') or 0)
    except (TypeError, ValueError):
        session_duration = 0

    phq9_score = sum(phq9_responses)
    gad7_score = sum(gad7_responses)
    depression_severity = get_depression_severity(phq9_score)
    anxiety_severity = get_anxiety_severity(gad7_score)
    primary_condition = _primary_condition_from_scores(phq9_score, gad7_score)
    suicide_answer = phq9_responses[8]
    emergency_risk = suicide_answer >= 2
    suicide_risk_level = get_suicide_risk_level(suicide_answer)

    assessment = ClinicalAssessment.objects.create(
        patient=request.user,
        phq9_score=phq9_score,
        depression_severity=depression_severity,
        gad7_score=gad7_score,
        anxiety_severity=anxiety_severity,
        primary_condition=primary_condition,
        emergency_risk=emergency_risk,
        suicide_risk_level=suicide_risk_level,
        phq9_responses=phq9_responses,
        gad7_responses=gad7_responses,
        session_duration=session_duration,
    )

    if emergency_risk:
        logger.warning('High-risk clinical assessment detected for user_id=%s', request.user.id)
        _log_emergency_assessment(request.user, assessment, suicide_answer)
        messages.error(
            request,
            'Your answers suggest urgent support may be needed. This platform is not an emergency service. Please call 999 or go to the nearest emergency department now.',
        )
        return redirect('emergency_support')

    recommended_doctors = get_clinical_doctor_recommendations(assessment)
    context = {
        'assessment': assessment,
        'phq9_questions': PHQ9_QUESTIONS,
        'gad7_questions': GAD7_QUESTIONS,
        'recommended_doctors': recommended_doctors,
        'emergency_hotline': BANGLADESH_EMERGENCY_NUMBER,
        'medical_disclaimer': get_medical_disclaimer(),
    }
    return render(request, 'patient/clinical_assessment_results.html', context)


def get_clinical_doctor_recommendations(assessment):
    allowed_specialties = get_allowed_specialties(assessment)
    candidate_doctors = Doctor.objects.filter(
        Q(specializations__value__in=allowed_specialties) | Q(primary_focuses__value__in={assessment.primary_condition, 'Depression', 'Anxiety'}),
        available_online=True,
    ).distinct().prefetch_related('specializations', 'primary_focuses')

    scored_doctors = []
    for doctor in candidate_doctors:
        score = calculate_clinical_doctor_score(doctor, assessment)
        scored_doctors.append({
            'doctor': doctor,
            'score': score,
            'match_percentage': min(99, score),
            'match_reason': generate_clinical_match_reason(doctor, assessment, score),
        })

    scored_doctors.sort(key=lambda item: item['score'], reverse=True)
    return scored_doctors[:3]


@login_required
def emergency_support(request):
    if request.user.role != 'patient':
        return redirect('home')

    context = {
        'emergency_hotline': BANGLADESH_EMERGENCY_NUMBER,
        'crisis_resources': get_crisis_resources(),
        'emergency_doctors': get_emergency_doctors(),
    }
    return render(request, 'patient/emergency_support.html', context)


def get_crisis_resources():
    return [
        {
            'name': 'Bangladesh Emergency Services',
            'phone': BANGLADESH_EMERGENCY_NUMBER,
            'available': '24/7',
            'description': 'For immediate medical emergencies and urgent safety concerns.',
        },
        {
            'name': 'Nearest Hospital Emergency Department',
            'phone': BANGLADESH_EMERGENCY_NUMBER,
            'available': '24/7',
            'description': 'Go to the nearest emergency department if you are in immediate danger.',
        },
    ]


def get_emergency_doctors():
    return Doctor.objects.filter(
        emergency_support=True,
        available_online=True,
    ).order_by('-years_of_experience', '-patients_helped')[:3]
