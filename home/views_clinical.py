"""
🧠 PHQ-9 + GAD-7 Clinical Assessment System
Industry-standard mental health screening with emergency detection
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
import json
import time

from home.models import ClinicalAssessment, Doctor, User


# 📋 PHQ-9 Questions (Industry Standard)
PHQ9_QUESTIONS = [
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble sleeping or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself",
    "Trouble concentrating on things",
    "Moving or speaking slowly or being restless",
    "Thoughts that you would be better off dead or of hurting yourself"
]

# 📋 GAD-7 Questions (Industry Standard)
GAD7_QUESTIONS = [
    "Feeling nervous, anxious, or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it's hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid as if something awful might happen"
]

# 🎯 Answer Scale
ANSWER_SCALE = [
    ("0", "Not at all"),
    ("1", "Several days"),
    ("2", "More than half the days"),
    ("3", "Nearly every day")
]


@login_required
def clinical_assessment(request):
    """
    🧠 Clinical Assessment Page with PHQ-9 & GAD-7
    Real-time emergency detection and professional UI
    """
    if request.user.role != 'patient':
        return redirect('home')
    
    context = {
        'phq9_questions': enumerate(PHQ9_QUESTIONS, 1),
        'gad7_questions': enumerate(GAD7_QUESTIONS, 1),
        'answer_scale': ANSWER_SCALE,
        'emergency_hotline': "+880-12345-67890",  # Bangladesh emergency number
        'page_title': 'Mental Health Clinical Assessment'
    }
    
    return render(request, 'patient/clinical_assessment.html', context)


@login_required
def submit_clinical_assessment(request):
    """
    🚀 Submit PHQ-9/GAD-7 Assessment with Advanced Scoring
    """
    if request.user.role != 'patient' or request.method != 'POST':
        return redirect('home')
    
    try:
        # 📊 Extract assessment data
        phq9_responses = [int(request.POST.get(f'phq9_{i}', 0)) for i in range(1, 10)]
        gad7_responses = [int(request.POST.get(f'gad7_{i}', 0)) for i in range(1, 8)]
        session_duration = int(request.POST.get('session_duration', 0))
        
        # 🧮 Calculate scores
        phq9_score = sum(phq9_responses)
        gad7_score = sum(gad7_responses)
        
        # 🔍 Determine severity levels
        depression_severity = get_depression_severity(phq9_score)
        anxiety_severity = get_anxiety_severity(gad7_score)
        
        # 🎯 Determine primary condition
        primary_condition = "Depression" if phq9_score > gad7_score else "Anxiety"
        
        # 🚨 Emergency detection (PHQ-9 Question 9)
        suicide_answer = phq9_responses[8]  # Question 9 (index 8)
        emergency_risk = suicide_answer >= 2
        suicide_risk_level = get_suicide_risk_level(suicide_answer)
        
        # 💾 Create clinical assessment record
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
            session_duration=session_duration
        )
        
        # 🚨 Handle emergency cases
        if emergency_risk:
            messages.error(request, 
                "⚠️ EMERGENCY: Based on your responses, we recommend immediate professional support. "
                "Please contact emergency services or a mental health crisis line immediately."
            )
            return redirect('emergency_support')
        
        # 🏥 Get doctor recommendations
        recommended_doctors = get_clinical_doctor_recommendations(assessment)
        
        # 📊 Prepare results context
        context = {
            'assessment': assessment,
            'phq9_questions': PHQ9_QUESTIONS,
            'gad7_questions': GAD7_QUESTIONS,
            'recommended_doctors': recommended_doctors,
            'emergency_hotline': "+880-12345-67890",
            'medical_disclaimer': get_medical_disclaimer()
        }
        
        return render(request, 'patient/clinical_assessment_results.html', context)
        
    except Exception as e:
        messages.error(request, "An error occurred while processing your assessment. Please try again.")
        return redirect('clinical_assessment')


def get_depression_severity(score):
    """
    🎯 PHQ-9 Severity Levels (Clinical Standard)
    """
    if score <= 4:
        return "minimal"
    elif score <= 9:
        return "mild"
    elif score <= 14:
        return "moderate"
    elif score <= 19:
        return "moderately_severe"
    else:
        return "severe"


def get_anxiety_severity(score):
    """
    🎯 GAD-7 Severity Levels (Clinical Standard)
    """
    if score <= 4:
        return "minimal"
    elif score <= 9:
        return "mild"
    elif score <= 14:
        return "moderate"
    else:
        return "severe"


def get_suicide_risk_level(answer):
    """
    🚨 Suicide Risk Level Assessment
    """
    if answer == 0:
        return "none"
    elif answer == 1:
        return "low"
    elif answer == 2:
        return "moderate"
    else:  # answer == 3
        return "high"


def get_clinical_doctor_recommendations(assessment):
    """
    🏥 Clinical Doctor Recommendation Engine
    PHQ-9/GAD-7 based matching with safety triage
    """
    # 🛡️ Step 1: Clinical Triage Filtering
    allowed_specialties = get_allowed_specialties(assessment)
    
    # 📊 Step 2: Filter available doctors
    candidate_doctors = Doctor.objects.filter(
        Q(specializations__value__in=allowed_specialties) | Q(primary_focuses__value=assessment.primary_condition),
        available_online=True
    ).distinct().prefetch_related('specializations', 'primary_focuses')
    
    # 🎯 Step 3: Score and rank doctors
    scored_doctors = []
    
    for doctor in candidate_doctors:
        score = calculate_clinical_doctor_score(doctor, assessment)
        
        scored_doctors.append({
            'doctor': doctor,
            'score': score,
            'match_percentage': min(99, int((score / 100) * 100)),
            'match_reason': generate_clinical_match_reason(doctor, assessment, score)
        })
    
    # 🏆 Step 4: Sort and return top 3
    scored_doctors.sort(key=lambda x: x['score'], reverse=True)
    return scored_doctors[:3]


def get_allowed_specialties(assessment):
    """
    🛡️ Clinical Triage: Determine allowed specialties based on severity
    """
    # High severity or emergency risk
    if (assessment.depression_severity in ['moderately_severe', 'severe'] or 
        assessment.anxiety_severity == 'severe' or 
        assessment.emergency_risk):
        
        return ['Psychiatrist', 'Clinical Psychologist']
    
    # Moderate severity
    elif (assessment.depression_severity == 'moderate' or 
          assessment.anxiety_severity == 'moderate'):
        
        return ['Clinical Psychologist', 'Therapist']
    
    # Mild severity
    else:
        return ['Counselor', 'Therapist', 'Clinical Psychologist']


def calculate_clinical_doctor_score(doctor, assessment):
    """
    📊 Clinical Doctor Scoring (100-point system)
    """
    score = 0
    
    # 🎯 Specialty Match (40 points)
    specializations = set(doctor.specialization_values)
    focus_areas = set(doctor.primary_focus_values)

    if specializations & {'Psychiatrist', 'Clinical Psychologist'}:
        score += 40
    elif 'Therapist' in specializations:
        score += 30
    else:  # Counselor
        score += 20
    
    # 🧠 Condition Focus Match (30 points)
    if assessment.primary_condition in focus_areas:
        score += 30
    elif focus_areas & {'Depression', 'Anxiety'}:
        score += 20
    else:
        score += 10
    
    # 🔍 Expertise Tags Match (15 points)
    if doctor.expertise_tags:
        # Check for relevant expertise tags
        relevant_tags = get_relevant_expertise_tags(assessment)
        if any(tag in doctor.expertise_tags for tag in relevant_tags):
            score += 15
        else:
            score += 5
    
    # 💪 Experience (10 points)
    if doctor.years_of_experience >= 10:
        score += 10
    elif doctor.years_of_experience >= 5:
        score += 7
    elif doctor.years_of_experience >= 2:
        score += 4
    else:
        score += 2
    
    # 🟢 Availability (5 points)
    if doctor.available_online:
        score += 5
    
    # 🚨 Emergency Support Bonus (for high-risk cases)
    if assessment.emergency_risk and doctor.emergency_support:
        score += 10  # Bonus for emergency capability
    
    return min(100, score)  # Cap at 100


def get_relevant_expertise_tags(assessment):
    """
    🔍 Get relevant expertise tags based on assessment results
    """
    tags = []
    
    # Depression-related tags
    if assessment.depression_severity in ['moderate', 'moderately_severe', 'severe']:
        tags.extend(['depression', 'sadness', 'hopeless', 'low self-esteem', 'fatigue'])
    
    # Anxiety-related tags
    if assessment.anxiety_severity in ['moderate', 'severe']:
        tags.extend(['anxiety', 'panic', 'worry', 'fear', 'nervous'])
    
    # Sleep issues (from PHQ-9 question 3)
    if assessment.phq9_responses and assessment.phq9_responses[2] >= 2:  # Q3 index 2
        tags.extend(['insomnia', 'sleep', 'tired'])
    
    # Energy issues (from PHQ-9 question 4)
    if assessment.phq9_responses and assessment.phq9_responses[3] >= 2:  # Q4 index 3
        tags.extend(['energy', 'fatigue', 'exhausted'])
    
    return tags


def generate_clinical_match_reason(doctor, assessment, score):
    """
    🎯 Generate clinically-relevant match reason
    """
    severity_level = assessment.depression_severity if assessment.primary_condition == 'Depression' else assessment.anxiety_severity
    
    reasons = {
        'Psychiatrist': f"🧠 Medical specialist for {severity_level} {assessment.primary_condition.lower()}. Can provide medication management and comprehensive psychiatric care.",
        'Clinical Psychologist': f"🎓 Clinical psychology expert for {severity_level} {assessment.primary_condition.lower()}. Specialized in evidence-based therapeutic interventions.",
        'Therapist': f"💊 Therapeutic specialist for {severity_level} {assessment.primary_condition.lower()}. Uses evidence-based treatment modalities.",
        'Counselor': f"💪 Counseling professional for {severity_level} {assessment.primary_condition.lower()}. Focus on practical emotional support and coping strategies."
    }
    
    primary_specialty = doctor.specialization_values[0] if doctor.specialization_values else doctor.specialty
    base_reason = reasons.get(primary_specialty, f"🏥 Mental health professional for {severity_level} {assessment.primary_condition.lower()}")
    
    # Add specific expertise context
    if assessment.primary_condition in doctor.primary_focus_values:
        base_reason += f" ✅ Specializes in {assessment.primary_condition} treatment."
    
    if assessment.emergency_risk and doctor.emergency_support:
        base_reason += f" 🚨 Provides emergency crisis support."
    
    return base_reason


def get_medical_disclaimer():
    """
    🛡️ Medical Disclaimer for Clinical Assessments
    """
    return """
    This assessment is a screening tool based on PHQ-9 and GAD-7, which are validated 
    clinical screening instruments. This tool does NOT provide a medical diagnosis. 
    Please consult with a licensed mental health professional for proper evaluation 
    and treatment. If you are in crisis or immediate danger, please contact emergency 
    services or a mental health crisis hotline immediately.
    """


@login_required
def emergency_support(request):
    """
    🚨 Emergency Support Page for High-Risk Patients
    """
    if request.user.role != 'patient':
        return redirect('home')
    
    context = {
        'emergency_hotline': "+880-12345-67890",
        'crisis_resources': get_crisis_resources(),
        'emergency_doctors': get_emergency_doctors()
    }
    
    return render(request, 'patient/emergency_support.html', context)


def get_crisis_resources():
    """
    📞 Crisis Support Resources
    """
    return [
        {
            'name': 'National Mental Health Helpline',
            'phone': '+880-12345-67890',
            'available': '24/7',
            'description': 'Free, confidential mental health support'
        },
        {
            'name': 'Suicide Prevention Hotline',
            'phone': '+880-09876-54321',
            'available': '24/7',
            'description': 'Crisis intervention and emotional support'
        },
        {
            'name': 'Emergency Medical Services',
            'phone': '999',
            'available': '24/7',
            'description': 'For immediate medical emergencies'
        }
    ]


def get_emergency_doctors():
    """
    🚑 Doctors with Emergency Support
    """
    return Doctor.objects.filter(
        emergency_support=True,
        available_online=True
    ).order_by('-years_of_experience', '-patients_helped')[:3]
