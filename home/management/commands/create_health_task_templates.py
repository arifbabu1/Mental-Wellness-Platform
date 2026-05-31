from django.core.management.base import BaseCommand
from home.models import HealthTaskTemplate


class Command(BaseCommand):
    help = 'Create default health task templates'

    def handle(self, *args, **options):
        # Clear existing templates
        HealthTaskTemplate.objects.all().delete()
        
        # Create default templates
        templates = [
            {
                'title': 'Morning Exercise (30 minutes)',
                'description': 'Start your day with physical activity to boost energy and mood',
                'category': 'physical',
                'icon': 'fas fa-running',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Healthy Breakfast',
                'description': 'Eat a nutritious breakfast with protein, fiber, and vitamins',
                'category': 'diet',
                'icon': 'fas fa-utensils',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Take Morning Medication',
                'description': 'Take prescribed medications as directed by your doctor',
                'category': 'medical',
                'icon': 'fas fa-pills',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Meditation Practice (15 minutes)',
                'description': 'Practice mindfulness meditation to reduce stress and improve focus',
                'category': 'mental',
                'icon': 'fas fa-brain',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Drink 8 Glasses of Water',
                'description': 'Stay hydrated throughout the day by drinking water regularly',
                'category': 'diet',
                'icon': 'fas fa-tint',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Evening Walk (20 minutes)',
                'description': 'Take a relaxing evening walk to improve digestion and sleep',
                'category': 'physical',
                'icon': 'fas fa-walking',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Sleep by 10 PM',
                'description': 'Maintain consistent sleep schedule for better health',
                'category': 'lifestyle',
                'icon': 'fas fa-bed',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Eat Vegetables with Every Meal',
                'description': 'Include vegetables in all meals for essential nutrients',
                'category': 'diet',
                'icon': 'fas fa-carrot',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Deep Breathing Exercises',
                'description': 'Practice deep breathing exercises for stress relief',
                'category': 'mental',
                'icon': 'fas fa-wind',
                'default_duration_days': 21,
                'is_active': True
            },
            {
                'title': 'Stretching Routine',
                'description': 'Perform stretching exercises to improve flexibility',
                'category': 'physical',
                'icon': 'fas fa-child',
                'default_duration_days': 30,
                'is_active': True
            },
            {
                'title': 'Limit Screen Time Before Bed',
                'description': 'Reduce screen exposure 1 hour before bedtime',
                'category': 'lifestyle',
                'icon': 'fas fa-mobile-alt',
                'default_duration_days': 21,
                'is_active': True
            },
            {
                'title': 'Practice Gratitude',
                'description': 'Write down 3 things you are grateful for each day',
                'category': 'mental',
                'icon': 'fas fa-heart',
                'default_duration_days': 30,
                'is_active': True
            }
        ]
        
        created_count = 0
        for template_data in templates:
            template = HealthTaskTemplate.objects.create(**template_data)
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'Created template: {template.title}')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} health task templates!')
        )
