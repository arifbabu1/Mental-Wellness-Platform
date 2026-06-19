from copy import deepcopy

from django.db import migrations, models
from django.db.models import Q

from home.assessment_i18n import (
    GENERAL_QUESTION_TRANSLATIONS,
    GENERAL_QUESTION_TRANSLATIONS_BN,
    STANDARD_OPTION_CHOICES,
    STANDARD_OPTION_CHOICES_BN,
)


CORE_QUESTION_SPECS = [
    (1, GENERAL_QUESTION_TRANSLATIONS[1], GENERAL_QUESTION_TRANSLATIONS_BN[1], 'Depression', 3),
    (2, GENERAL_QUESTION_TRANSLATIONS[2], GENERAL_QUESTION_TRANSLATIONS_BN[2], 'Depression', 3),
    (3, GENERAL_QUESTION_TRANSLATIONS[3], GENERAL_QUESTION_TRANSLATIONS_BN[3], 'Anxiety', 2),
    (4, GENERAL_QUESTION_TRANSLATIONS[4], GENERAL_QUESTION_TRANSLATIONS_BN[4], 'Anxiety', 2),
    (5, GENERAL_QUESTION_TRANSLATIONS[5], GENERAL_QUESTION_TRANSLATIONS_BN[5], 'Sleep', 2),
    (6, GENERAL_QUESTION_TRANSLATIONS[6], GENERAL_QUESTION_TRANSLATIONS_BN[6], 'Energy', 1),
    (7, GENERAL_QUESTION_TRANSLATIONS[7], GENERAL_QUESTION_TRANSLATIONS_BN[7], 'Self-esteem', 3),
]


def _defaults(order, text, text_bn, category, weight):
    return {
        'question_text': text,
        'question_text_bn': text_bn,
        'category': category,
        'weight_value': weight,
        'track_number': order,
        'question_type': 'likert_scale',
        'option_choices': deepcopy(STANDARD_OPTION_CHOICES),
        'option_choices_bn': deepcopy(STANDARD_OPTION_CHOICES_BN),
        'required': True,
        'is_required': True,
        'is_active': True,
        'reverse_scoring': False,
        'is_core': True,
        'core_order': order,
    }


def seed_and_mark_core_questions(apps, schema_editor):
    AssessmentQuestion = apps.get_model('home', 'AssessmentQuestion')
    AssessmentAnswer = apps.get_model('home', 'AssessmentAnswer')

    for order, text, text_bn, category, weight in CORE_QUESTION_SPECS:
        matches = list(
            AssessmentQuestion.objects.filter(
                Q(is_core=True, core_order=order)
                | Q(track_number=order)
                | Q(question_text=text)
            ).order_by('-is_core', 'id')
        )
        question = next(
            (item for item in matches if item.is_core and item.core_order == order),
            None,
        )
        if question is None:
            question = next(
                (item for item in matches if item.question_text == text),
                matches[0] if matches else None,
            )

        defaults = _defaults(order, text, text_bn, category, weight)
        if question is None:
            AssessmentQuestion.objects.create(**defaults)
            continue

        for duplicate in matches:
            if duplicate.pk == question.pk:
                continue
            for answer in AssessmentAnswer.objects.filter(question=duplicate):
                if AssessmentAnswer.objects.filter(
                    assessment=answer.assessment,
                    question=question,
                ).exists():
                    answer.delete()
                else:
                    answer.question = question
                    answer.save(update_fields=['question'])
            duplicate.delete()

        for field_name, expected_value in defaults.items():
            setattr(question, field_name, expected_value)
        question.save()


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0037_add_assessment_bangla_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessmentquestion',
            name='is_core',
            field=models.BooleanField(default=False, help_text='Protected default screening question.'),
        ),
        migrations.AddField(
            model_name='assessmentquestion',
            name='core_order',
            field=models.PositiveSmallIntegerField(blank=True, help_text='Protected core question order from 1 to 7.', null=True),
        ),
        migrations.AddField(
            model_name='assessmentquestion',
            name='is_required',
            field=models.BooleanField(default=False, help_text='System-required question that should not be disabled.'),
        ),
        migrations.RunPython(seed_and_mark_core_questions, reverse_code=migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='assessmentquestion',
            constraint=models.UniqueConstraint(
                fields=('core_order',),
                condition=Q(is_core=True),
                name='unique_core_assessment_order',
            ),
        ),
    ]
