from collections import OrderedDict


ANSWER_MAX = 4
HIGH_THRESHOLD = 0.67
MODERATE_THRESHOLD = 0.34

CORE_TRACKS = OrderedDict([
    ('Depression', {'question_indexes': [0, 1, 6], 'weight': 3}),
    ('Anxiety', {'question_indexes': [2, 3], 'weight': 2}),
    ('Sleep', {'question_indexes': [4], 'weight': 2}),
    ('Energy', {'question_indexes': [5], 'weight': 1}),
    ('Self-esteem', {'question_indexes': [6], 'weight': 3}),
])

DYNAMIC_QUESTION_GROUPS = OrderedDict([
    ('child', {
        'label': 'Child Mental Health',
        'questions': [
            'How often are study focus issues affecting daily life?',
            'How often have there been noticeable behavior changes?',
            'How often is social isolation a concern?',
        ],
    }),
    ('geriatric', {
        'label': 'Geriatric Mental Health',
        'questions': [
            'How often are memory issues affecting daily life?',
            'How often does loneliness feel difficult to manage?',
            'How often are daily activities difficult to complete?',
        ],
    }),
    ('addiction', {
        'label': 'Addiction Screening',
        'questions': [
            'How often is it hard to control substance use or cravings?',
            'How often have attempts to cut down or stop failed?',
            'How often does dependency affect health, work, study, or relationships?',
        ],
    }),
    ('family', {
        'label': 'Family and Relationship Stress',
        'questions': [
            'How often do relationship conflicts increase your distress?',
            'How often do communication issues make problems harder?',
            'How often do you feel a lack of emotional support?',
        ],
    }),
    ('neurological', {
        'label': 'Neurological Symptoms',
        'questions': [
            'How often do memory loss symptoms concern you?',
            'How often do confusion or disorientation symptoms occur?',
            'Have head injury history or neurological symptoms affected your wellbeing?',
        ],
    }),
])

CONDITION_FOCUS_MAP = {
    'Depression': {'exact': {'Depression'}, 'partial': {'Emotional Healing', 'Talk Therapy', 'Stress', 'Sleep'}},
    'Anxiety': {'exact': {'Anxiety'}, 'partial': {'Stress', 'Talk Therapy', 'OCD'}},
    'Sleep': {'exact': {'Sleep'}, 'partial': {'Stress', 'Neurological Disorders'}},
    'Energy': {'exact': {'Stress'}, 'partial': {'Depression', 'Sleep', 'Talk Therapy'}},
    'Self-esteem': {'exact': {'Emotional Healing', 'Talk Therapy'}, 'partial': {'Depression', 'Stress'}},
}

CONDITION_SPECIALTY_MAP = {
    'Depression': {'exact': {'Psychiatrist', 'Clinical Psychologist'}, 'partial': {'Therapist', 'Counselor'}},
    'Anxiety': {'exact': {'Clinical Psychologist', 'Therapist'}, 'partial': {'Psychiatrist', 'Counselor'}},
    'Sleep': {'exact': {'Psychiatrist', 'Therapist'}, 'partial': {'Clinical Psychologist', 'Counselor', 'Neuropsychiatrist'}},
    'Energy': {'exact': {'Therapist', 'Counselor'}, 'partial': {'Psychiatrist', 'Clinical Psychologist'}},
    'Self-esteem': {'exact': {'Therapist', 'Counselor', 'Clinical Psychologist'}, 'partial': {'Marriage and Family Therapist'}},
}

SPECIALTY_BOOSTS = {
    'depression_high': {'Psychiatrist', 'Clinical Psychologist'},
    'anxiety_high': {'Clinical Psychologist', 'Therapist'},
    'addiction_high': {'Addiction Specialist'},
    'neurological_high': {'Neuropsychiatrist', 'Neuropsychologist'},
    'family_high': {'Marriage and Family Therapist'},
    'child': {'Child Psychiatrist', 'Child Psychologist'},
    'geriatric': {'Geriatric Psychologist'},
}

FOCUS_BOOSTS = {
    'addiction_high': {'Substance Abuse', 'Alcohol Addiction', 'Recovery Programs'},
    'neurological_high': {'Neurological Disorders'},
    'family_high': {'Talk Therapy', 'Emotional Healing'},
    'self_esteem_high': {'Emotional Healing', 'Talk Therapy'},
}


def normalize_answer(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(ANSWER_MAX, value))


def calculate_core_scores(core_answers):
    answers = [normalize_answer(answer) for answer in core_answers[:7]]
    while len(answers) < 7:
        answers.append(0)

    scores = OrderedDict()
    for category, config in CORE_TRACKS.items():
        raw_score = sum(answers[index] * config['weight'] for index in config['question_indexes'])
        max_score = len(config['question_indexes']) * ANSWER_MAX * config['weight']
        scores[category] = {
            'raw': raw_score,
            'max': max_score,
            'normalized': round(raw_score / max_score if max_score else 0, 3),
        }
    return scores


def severity_from_score(score):
    if score >= HIGH_THRESHOLD:
        return 'High'
    if score >= MODERATE_THRESHOLD:
        return 'Moderate'
    return 'Low'


def emotional_risk_level(scores):
    depression = scores['Depression']['normalized']
    anxiety = scores['Anxiety']['normalized']
    self_esteem = scores['Self-esteem']['normalized']

    if depression >= HIGH_THRESHOLD and self_esteem >= HIGH_THRESHOLD and anxiety >= MODERATE_THRESHOLD:
        return 'High'
    if (depression >= HIGH_THRESHOLD and self_esteem >= MODERATE_THRESHOLD) or (
        anxiety >= HIGH_THRESHOLD and self_esteem >= MODERATE_THRESHOLD
    ):
        return 'Moderate'
    return 'Low'


def rank_conditions(scores):
    ranked = sorted(scores.items(), key=lambda item: item[1]['normalized'], reverse=True)
    primary = ranked[0][0] if ranked else 'Depression'
    secondary = ranked[1][0] if len(ranked) > 1 else None
    return primary, secondary


def get_patient_age(user):
    age = getattr(user, 'age', None)
    try:
        return int(age) if age is not None else None
    except (TypeError, ValueError):
        return None


def calculate_dynamic_scores(dynamic_responses):
    dynamic_scores = {}
    for module_key, group in DYNAMIC_QUESTION_GROUPS.items():
        responses = dynamic_responses.get(module_key, [])
        normalized_responses = [normalize_answer(value) for value in responses]
        max_score = len(group['questions']) * ANSWER_MAX
        raw_score = sum(normalized_responses)
        dynamic_scores[module_key] = {
            'raw': raw_score,
            'max': max_score,
            'normalized': round(raw_score / max_score if max_score else 0, 3),
            'label': group['label'],
        }
    return dynamic_scores


def get_triggered_modules(core_scores, age=None, dynamic_scores=None):
    triggered = OrderedDict()

    depression_high = core_scores['Depression']['normalized'] >= HIGH_THRESHOLD
    anxiety_high = core_scores['Anxiety']['normalized'] >= HIGH_THRESHOLD
    sleep_high = core_scores['Sleep']['normalized'] >= HIGH_THRESHOLD
    self_esteem_high = core_scores['Self-esteem']['normalized'] >= HIGH_THRESHOLD

    if depression_high or anxiety_high:
        for key in ('addiction', 'family', 'neurological'):
            triggered[key] = DYNAMIC_QUESTION_GROUPS[key]

    if sleep_high:
        triggered['neurological'] = DYNAMIC_QUESTION_GROUPS['neurological']

    if self_esteem_high:
        triggered['family'] = DYNAMIC_QUESTION_GROUPS['family']

    if age is not None and age < 18:
        triggered['child'] = DYNAMIC_QUESTION_GROUPS['child']

    if age is not None and age > 60:
        triggered['geriatric'] = DYNAMIC_QUESTION_GROUPS['geriatric']

    if dynamic_scores and dynamic_scores.get('addiction', {}).get('normalized', 0) >= HIGH_THRESHOLD:
        triggered['addiction'] = DYNAMIC_QUESTION_GROUPS['addiction']

    return triggered


def build_assessment_profile(core_answers, user, dynamic_responses=None):
    dynamic_responses = dynamic_responses or {}
    core_scores = calculate_core_scores(core_answers)
    age = get_patient_age(user)
    dynamic_scores = calculate_dynamic_scores(dynamic_responses)
    triggered_modules = get_triggered_modules(core_scores, age=age, dynamic_scores=dynamic_scores)
    primary_condition, secondary_condition = rank_conditions(core_scores)
    highest_score = core_scores[primary_condition]['normalized']

    return {
        'age': age,
        'gender': getattr(user, 'gender', None),
        'primary_condition': primary_condition,
        'secondary_condition': secondary_condition,
        'severity_level': severity_from_score(highest_score),
        'emotional_risk_level': emotional_risk_level(core_scores),
        'category_scores': core_scores,
        'dynamic_scores': dynamic_scores,
        'triggered_modules': [
            {'key': key, 'label': group['label'], 'questions': group['questions']}
            for key, group in triggered_modules.items()
        ],
    }


def get_dynamic_response_payload(post_data, triggered_modules):
    responses = {}
    for module in triggered_modules:
        module_key = module['key']
        answers = []
        for index, _question in enumerate(DYNAMIC_QUESTION_GROUPS[module_key]['questions']):
            answers.append(normalize_answer(post_data.get(f'dynamic_{module_key}_{index}', 0)))
        responses[module_key] = answers
    return responses


def get_special_condition_flags(profile):
    scores = profile['category_scores']
    dynamic_scores = profile.get('dynamic_scores', {})
    age = profile.get('age')

    return {
        'depression_high': scores['Depression']['normalized'] >= HIGH_THRESHOLD,
        'anxiety_high': scores['Anxiety']['normalized'] >= HIGH_THRESHOLD,
        'self_esteem_high': scores['Self-esteem']['normalized'] >= HIGH_THRESHOLD,
        'addiction_high': dynamic_scores.get('addiction', {}).get('normalized', 0) >= HIGH_THRESHOLD,
        'neurological_high': dynamic_scores.get('neurological', {}).get('normalized', 0) >= HIGH_THRESHOLD,
        'family_high': dynamic_scores.get('family', {}).get('normalized', 0) >= HIGH_THRESHOLD,
        'child': age is not None and age < 18,
        'geriatric': age is not None and age > 60,
    }


def experience_points(years):
    if years >= 10:
        return 20
    if years >= 5:
        return 15
    if years >= 2:
        return 10
    return 5


def availability_points(availability_score):
    try:
        availability_score = int(availability_score)
    except (TypeError, ValueError):
        availability_score = 0
    if availability_score >= 5:
        return 10
    if availability_score >= 3:
        return 5
    return 0


def doctor_specialization_values(doctor):
    values = getattr(doctor, 'specialization_values', None)
    if values is not None:
        return set(values)

    value = getattr(doctor, 'specialty', None)
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value} if value else set()


def doctor_primary_focus_values(doctor):
    values = getattr(doctor, 'primary_focus_values', None)
    if values is not None:
        return set(values)

    value = getattr(doctor, 'primary_focus', None)
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value} if value else set()


def score_specialty(doctor, primary_condition, flags):
    specialties = doctor_specialization_values(doctor)
    match_config = CONDITION_SPECIALTY_MAP.get(primary_condition, {})
    exact_matches = specialties & match_config.get('exact', set())
    partial_matches = specialties & match_config.get('partial', set())
    boost_matches = set()

    for flag, boosted_specialties in SPECIALTY_BOOSTS.items():
        if flags.get(flag):
            boost_matches.update(specialties & boosted_specialties)

    strong_matches = exact_matches | boost_matches
    if strong_matches:
        score = 40
    elif partial_matches:
        score = min(36, 24 + max(0, len(partial_matches) - 1) * 4)
    else:
        score = 0

    return min(score, 40), len(strong_matches | partial_matches)


def score_focus(doctor, primary_condition, flags):
    focuses = doctor_primary_focus_values(doctor)
    match_config = CONDITION_FOCUS_MAP.get(primary_condition, {})
    exact_matches = focuses & match_config.get('exact', set())
    partial_matches = focuses & match_config.get('partial', set())
    boost_matches = set()

    for flag, boosted_focuses in FOCUS_BOOSTS.items():
        if flags.get(flag):
            boost_matches.update(focuses & boosted_focuses)

    strong_matches = exact_matches | boost_matches
    if strong_matches:
        score = 30
    elif partial_matches:
        score = min(27, 18 + max(0, len(partial_matches) - 1) * 3)
    else:
        score = 0

    return min(score, 30), len(strong_matches | partial_matches)


def build_match_reason(doctor, profile, breakdown):
    reasons = []
    primary = profile['primary_condition'].lower()
    if breakdown['specialty_match'] >= 40:
        reasons.append(f"{doctor.specialty} is a strong specialty fit for {primary}.")
    elif breakdown['specialty_match'] > 0:
        reasons.append(f"{doctor.specialty} partially aligns with your {primary} needs.")

    if breakdown['primary_focus_match'] >= 30:
        reasons.append(f"Primary focus matches {doctor.primary_focus}.")
    elif breakdown['primary_focus_match'] > 0:
        reasons.append(f"Primary focus is related to {primary}.")

    active_modules = [module['label'] for module in profile.get('triggered_modules', [])]
    if active_modules:
        reasons.append(f"Follow-up signals considered: {', '.join(active_modules)}.")

    reasons.append(f"{doctor.years_of_experience} years of experience and availability score {doctor.availability_score}/5.")
    return ' '.join(reasons)


def score_doctor(doctor, profile):
    flags = get_special_condition_flags(profile)
    specialty_score, specialty_match_count = score_specialty(doctor, profile['primary_condition'], flags)
    focus_score, focus_match_count = score_focus(doctor, profile['primary_condition'], flags)
    experience_score = experience_points(doctor.years_of_experience)
    availability_score = availability_points(getattr(doctor, 'availability_score', 0))
    multi_match_bonus = min(
        10,
        max(0, specialty_match_count - 1) * 2 + max(0, focus_match_count - 1) * 3,
    )

    total_score = specialty_score + focus_score + experience_score + availability_score + multi_match_bonus
    total_score = min(total_score, 100)
    breakdown = {
        'specialty_match': specialty_score,
        'primary_focus_match': focus_score,
        'experience': experience_score,
        'availability': availability_score,
        'multi_match_bonus': multi_match_bonus,
    }

    return {
        'doctor': doctor,
        'total_score': total_score,
        'match_percentage': total_score,
        'score_breakdown': breakdown,
        'match_reason': build_match_reason(doctor, profile, breakdown),
    }


def recommend_doctors(doctors, profile, limit=5):
    scored_doctors = [
        scored
        for scored in (score_doctor(doctor, profile) for doctor in doctors)
        if scored['score_breakdown']['specialty_match'] > 0
        or scored['score_breakdown']['primary_focus_match'] > 0
    ]
    scored_doctors.sort(key=lambda item: item['total_score'], reverse=True)
    return scored_doctors[:limit]
