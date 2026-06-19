from __future__ import annotations

from copy import deepcopy

from django.db import transaction
from django.db.models import Q

from .assessment_i18n import (
    GENERAL_QUESTION_TRANSLATIONS,
    GENERAL_QUESTION_TRANSLATIONS_BN,
    STANDARD_OPTION_CHOICES,
    STANDARD_OPTION_CHOICES_BN,
)
from .models import AssessmentAnswer, AssessmentQuestion


CORE_ASSESSMENT_WARNING = (
    'Core assessment questions cannot be deleted because they are required for patient assessment.'
)

CORE_QUESTION_SPECS = [
    {
        'core_order': 1,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[1],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[1],
        'category': 'Depression',
        'weight_value': 3,
    },
    {
        'core_order': 2,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[2],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[2],
        'category': 'Depression',
        'weight_value': 3,
    },
    {
        'core_order': 3,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[3],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[3],
        'category': 'Anxiety',
        'weight_value': 2,
    },
    {
        'core_order': 4,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[4],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[4],
        'category': 'Anxiety',
        'weight_value': 2,
    },
    {
        'core_order': 5,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[5],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[5],
        'category': 'Sleep',
        'weight_value': 2,
    },
    {
        'core_order': 6,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[6],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[6],
        'category': 'Energy',
        'weight_value': 1,
    },
    {
        'core_order': 7,
        'question_text': GENERAL_QUESTION_TRANSLATIONS[7],
        'question_text_bn': GENERAL_QUESTION_TRANSLATIONS_BN[7],
        'category': 'Self-esteem',
        'weight_value': 3,
    },
]


def _core_defaults(spec):
    core_order = spec['core_order']
    return {
        'question_text': spec['question_text'],
        'question_text_bn': spec['question_text_bn'],
        'category': spec['category'],
        'weight_value': spec['weight_value'],
        'track_number': core_order,
        'question_type': 'likert_scale',
        'option_choices': deepcopy(STANDARD_OPTION_CHOICES),
        'option_choices_bn': deepcopy(STANDARD_OPTION_CHOICES_BN),
        'required': True,
        'is_required': True,
        'is_active': True,
        'reverse_scoring': False,
        'is_core': True,
        'core_order': core_order,
    }


def _find_existing_core_question(spec):
    core_order = spec['core_order']
    matches = list(
        AssessmentQuestion.objects.filter(
            Q(is_core=True, core_order=core_order)
            | Q(track_number=core_order)
            | Q(question_text=spec['question_text'])
        ).order_by('-is_core', 'id')
    )
    primary = next(
        (question for question in matches if question.is_core and question.core_order == core_order),
        None,
    )
    if primary is None:
        primary = next(
            (question for question in matches if question.question_text == spec['question_text']),
            matches[0] if matches else None,
        )
    return primary, matches


def _merge_duplicate_question(primary, duplicate):
    for answer in AssessmentAnswer.objects.filter(question=duplicate):
        if AssessmentAnswer.objects.filter(
            assessment=answer.assessment,
            question=primary,
        ).exists():
            answer.delete()
        else:
            answer.question = primary
            answer.save(update_fields=['question'])
    AssessmentQuestion.objects.filter(pk=duplicate.pk).delete()


@transaction.atomic
def ensure_core_assessment_questions():
    summary = {'created': 0, 'repaired': 0, 'already_ok': 0}

    for spec in CORE_QUESTION_SPECS:
        defaults = _core_defaults(spec)
        question, matches = _find_existing_core_question(spec)

        if question is None:
            AssessmentQuestion.objects.create(**defaults)
            summary['created'] += 1
            continue

        for duplicate in matches:
            if duplicate.pk != question.pk:
                _merge_duplicate_question(question, duplicate)

        changed = False
        for field_name, expected_value in defaults.items():
            if getattr(question, field_name) != expected_value:
                setattr(question, field_name, deepcopy(expected_value))
                changed = True

        if changed:
            question.save()
            summary['repaired'] += 1
        else:
            summary['already_ok'] += 1

    return summary


def get_active_core_questions():
    return list(
        AssessmentQuestion.objects.filter(
            is_core=True,
            is_active=True,
            core_order__gte=1,
            core_order__lte=7,
        ).order_by('core_order', 'id')[:7]
    )
