from django.db import migrations, models
from django.db.models import Q

from home.assessment_i18n import (
    GENERAL_QUESTION_TRANSLATIONS,
    GENERAL_QUESTION_TRANSLATIONS_BN,
    STANDARD_OPTION_CHOICES,
    STANDARD_OPTION_CHOICES_BN,
)


def seed_assessment_bangla_translations(apps, schema_editor):
    AssessmentQuestion = apps.get_model("home", "AssessmentQuestion")
    AssessmentAnswer = apps.get_model("home", "AssessmentAnswer")

    for track_number, english_text in GENERAL_QUESTION_TRANSLATIONS.items():
        matches = list(
            AssessmentQuestion.objects.filter(
                Q(track_number=track_number) | Q(question_text=english_text)
            ).order_by("id")
        )
        question = next(
            (item for item in matches if item.question_text == english_text),
            matches[0] if matches else None,
        )

        if question is None:
            question = AssessmentQuestion.objects.create(
                question_text=english_text,
                question_text_bn=GENERAL_QUESTION_TRANSLATIONS_BN.get(track_number, ""),
                category={
                    1: "Depression",
                    2: "Depression",
                    3: "Anxiety",
                    4: "Anxiety",
                    5: "Sleep",
                    6: "Energy",
                    7: "Self-esteem",
                }[track_number],
                weight_value={
                    1: 3,
                    2: 3,
                    3: 2,
                    4: 2,
                    5: 2,
                    6: 1,
                    7: 3,
                }[track_number],
                track_number=track_number,
                question_type="likert_scale",
                option_choices=STANDARD_OPTION_CHOICES,
                option_choices_bn=STANDARD_OPTION_CHOICES_BN,
                required=True,
                is_active=True,
                reverse_scoring=False,
            )
            continue

        for duplicate in matches:
            if duplicate.pk == question.pk:
                continue
            for answer in AssessmentAnswer.objects.filter(question_id=duplicate.pk):
                if AssessmentAnswer.objects.filter(
                    assessment_id=answer.assessment_id,
                    question_id=question.pk,
                ).exists():
                    answer.delete()
                else:
                    answer.question_id = question.pk
                    answer.save(update_fields=["question"])
            duplicate.delete()

        question.question_text = english_text
        question.question_text_bn = GENERAL_QUESTION_TRANSLATIONS_BN.get(track_number, "")
        question.category = {
            1: "Depression",
            2: "Depression",
            3: "Anxiety",
            4: "Anxiety",
            5: "Sleep",
            6: "Energy",
            7: "Self-esteem",
        }[track_number]
        question.weight_value = {
            1: 3,
            2: 3,
            3: 2,
            4: 2,
            5: 2,
            6: 1,
            7: 3,
        }[track_number]
        question.track_number = track_number
        question.question_type = "likert_scale"
        question.option_choices = STANDARD_OPTION_CHOICES
        question.option_choices_bn = STANDARD_OPTION_CHOICES_BN
        question.required = True
        question.is_active = True
        question.reverse_scoring = False
        question.save(
            update_fields=[
                "question_text",
                "question_text_bn",
                "category",
                "weight_value",
                "track_number",
                "question_type",
                "option_choices",
                "option_choices_bn",
                "required",
                "is_active",
                "reverse_scoring",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0036_seed_demo_payment_receivers"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentquestion",
            name="question_text_bn",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="assessmentquestion",
            name="option_choices_bn",
            field=models.JSONField(blank=True, default=list, help_text="Bangla option labels with scores."),
        ),
        migrations.RunPython(
            seed_assessment_bangla_translations,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
