from django.core.management.base import BaseCommand
from home.models import AssessmentQuestion


class Command(BaseCommand):
    help = 'Populate assessment questions for mental health evaluation'

    def handle(self, *args, **options):
        questions_data = [
            {
                'question_text': 'Over the past two weeks, how often have you felt down, depressed, or hopeless?',
                'category': 'Depression',
                'weight_value': 3,
                'track_number': 1
            },
            {
                'question_text': 'Over the past two weeks, how often have you had little interest or pleasure in doing things?',
                'category': 'Depression',
                'weight_value': 3,
                'track_number': 2
            },
            {
                'question_text': 'Over the past two weeks, how often have you felt nervous, anxious, or on edge?',
                'category': 'Anxiety',
                'weight_value': 2,
                'track_number': 3
            },
            {
                'question_text': 'Over the past two weeks, how often have you been unable to stop or control worrying?',
                'category': 'Anxiety',
                'weight_value': 2,
                'track_number': 4
            },
            {
                'question_text': 'Over the past two weeks, how often have you had trouble falling or staying asleep, or sleeping too much?',
                'category': 'Sleep',
                'weight_value': 2,
                'track_number': 5
            },
            {
                'question_text': 'Over the past two weeks, how often have you felt tired or had little energy?',
                'category': 'Energy',
                'weight_value': 1,
                'track_number': 6
            },
            {
                'question_text': 'Over the past two weeks, how often have you felt that you are a failure or have let yourself or your family down?',
                'category': 'Self-esteem',
                'weight_value': 3,
                'track_number': 7
            }
        ]

        created_count = 0
        for question_data in questions_data:
            question, created = AssessmentQuestion.objects.get_or_create(
                question_text=question_data['question_text'],
                defaults={
                    'category': question_data['category'],
                    'weight_value': question_data['weight_value'],
                    'track_number': question_data['track_number']
                }
            )
            if not created:
                question.category = question_data['category']
                question.weight_value = question_data['weight_value']
                question.track_number = question_data['track_number']
                question.save(update_fields=['category', 'weight_value', 'track_number'])
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created question: {question.question_text[:50]}...")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Question already exists: {question.question_text[:50]}...")
                )

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully created {created_count} new assessment questions!")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Total assessment questions: {AssessmentQuestion.objects.count()}")
        )
