from django.db import migrations
from django.db.models import Q


DEFAULT_OPTIONS = [
    {"option_order": 1, "option_text": "Never", "score": 0},
    {"option_order": 2, "option_text": "Rarely", "score": 1},
    {"option_order": 3, "option_text": "Sometimes", "score": 2},
    {"option_order": 4, "option_text": "Often", "score": 3},
    {"option_order": 5, "option_text": "Always", "score": 4},
]

CORE_QUESTIONS = [
    (
        "Over the past two weeks, how often have you felt down, depressed, or hopeless?",
        "Depression",
        3,
        1,
    ),
    (
        "Over the past two weeks, how often have you had little interest or pleasure in doing things?",
        "Depression",
        3,
        2,
    ),
    (
        "Over the past two weeks, how often have you felt nervous, anxious, or on edge?",
        "Anxiety",
        2,
        3,
    ),
    (
        "Over the past two weeks, how often have you been unable to stop or control worrying?",
        "Anxiety",
        2,
        4,
    ),
    (
        "Over the past two weeks, how often have you had trouble falling or staying asleep, or sleeping too much?",
        "Sleep",
        2,
        5,
    ),
    (
        "Over the past two weeks, how often have you felt tired or had little energy?",
        "Energy",
        1,
        6,
    ),
    (
        "Over the past two weeks, how often have you felt that you are a failure or have let yourself or your family down?",
        "Self-esteem",
        3,
        7,
    ),
]


def seed_assessment_questions(apps, schema_editor):
    AssessmentQuestion = apps.get_model("home", "AssessmentQuestion")
    AssessmentAnswer = apps.get_model("home", "AssessmentAnswer")

    for question_text, category, weight_value, track_number in CORE_QUESTIONS:
        matches = list(
            AssessmentQuestion.objects.filter(
                Q(track_number=track_number) | Q(question_text=question_text)
            ).order_by("id")
        )
        question = next(
            (item for item in matches if item.question_text == question_text),
            matches[0] if matches else None,
        )

        if question is None:
            question = AssessmentQuestion.objects.create(
                question_text=question_text,
                category=category,
                weight_value=weight_value,
                track_number=track_number,
                question_type="likert_scale",
                option_choices=DEFAULT_OPTIONS,
                required=True,
                is_active=True,
                reverse_scoring=False,
            )
            continue

        for duplicate in matches:
            if duplicate.pk == question.pk:
                continue
            for answer in AssessmentAnswer.objects.filter(question_id=duplicate.pk):
                existing_answer = AssessmentAnswer.objects.filter(
                    assessment_id=answer.assessment_id,
                    question_id=question.pk,
                ).exists()
                if existing_answer:
                    answer.delete()
                else:
                    answer.question_id = question.pk
                    answer.save(update_fields=["question"])
            duplicate.delete()

        question.question_text = question_text
        question.category = category
        question.weight_value = weight_value
        question.track_number = track_number
        question.question_type = "likert_scale"
        question.option_choices = DEFAULT_OPTIONS
        question.required = True
        question.is_active = True
        question.reverse_scoring = False
        question.save(
            update_fields=[
                "question_text",
                "category",
                "weight_value",
                "track_number",
                "question_type",
                "option_choices",
                "required",
                "is_active",
                "reverse_scoring",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0034_assessmentquestion_is_active_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_assessment_questions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
