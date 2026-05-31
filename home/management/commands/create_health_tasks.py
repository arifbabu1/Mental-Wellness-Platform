from django.core.management.base import BaseCommand
from home.models import HealthTaskTemplate


class Command(BaseCommand):
    help = 'Create sample health task templates for doctors'
    
    def handle(self, *args, **options):
        templates = [
            # Physical Activity
            {
                'title': 'Walk 30 minutes',
                'description': 'Take a brisk walk for 30 minutes to improve cardiovascular health and mental clarity.',
                'category': 'physical',
                'icon': 'fas fa-walking',
                'default_duration_days': 7
            },
            {
                'title': 'Morning stretching',
                'description': 'Perform 10-15 minutes of gentle stretching exercises to improve flexibility and reduce stress.',
                'category': 'physical',
                'icon': 'fas fa-child',
                'default_duration_days': 14
            },
            {
                'title': 'Yoga or meditation',
                'description': 'Practice 20 minutes of yoga or meditation to reduce anxiety and improve mental well-being.',
                'category': 'mental',
                'icon': 'fas fa-spa',
                'default_duration_days': 21
            },
            
            # Nutrition
            {
                'title': 'Drink 3L water',
                'description': 'Drink at least 3 liters of water throughout the day to stay hydrated and support overall health.',
                'category': 'diet',
                'icon': 'fas fa-tint',
                'default_duration_days': 7
            },
            {
                'title': 'Eat 5 servings of fruits/vegetables',
                'description': 'Consume at least 5 servings of fruits and vegetables daily for optimal nutrition.',
                'category': 'diet',
                'icon': 'fas fa-apple-alt',
                'default_duration_days': 14
            },
            {
                'title': 'Take vitamins/supplements',
                'description': 'Take prescribed vitamins and supplements as directed by your healthcare provider.',
                'category': 'diet',
                'icon': 'fas fa-pills',
                'default_duration_days': 30
            },
            
            # Medical Monitoring
            {
                'title': 'Blood sugar check',
                'description': 'Check blood sugar levels as recommended by your doctor and record the readings.',
                'category': 'medical',
                'icon': 'fas fa-tint',
                'default_duration_days': 7
            },
            {
                'title': 'Blood pressure monitoring',
                'description': 'Measure and record blood pressure twice daily, morning and evening.',
                'category': 'medical',
                'icon': 'fas fa-heartbeat',
                'default_duration_days': 14
            },
            {
                'title': 'Take prescribed medication',
                'description': 'Take all prescribed medications at the correct times and dosages.',
                'category': 'medical',
                'icon': 'fas fa-prescription',
                'default_duration_days': 30
            },
            
            # Mental Wellness
            {
                'title': 'Journal writing',
                'description': 'Write in a journal for 10-15 minutes to process thoughts and emotions.',
                'category': 'mental',
                'icon': 'fas fa-book',
                'default_duration_days': 21
            },
            {
                'title': 'Practice deep breathing',
                'description': 'Practice deep breathing exercises for 5 minutes, 3 times daily to reduce stress.',
                'category': 'mental',
                'icon': 'fas fa-wind',
                'default_duration_days': 14
            },
            {
                'title': 'Gratitude practice',
                'description': 'Write down 3 things you are grateful for each day to improve mental well-being.',
                'category': 'mental',
                'icon': 'fas fa-heart',
                'default_duration_days': 30
            },
            
            # Lifestyle Habits
            {
                'title': 'Get 8 hours sleep',
                'description': 'Aim for 8 hours of quality sleep each night to support physical and mental health.',
                'category': 'lifestyle',
                'icon': 'fas fa-bed',
                'default_duration_days': 21
            },
            {
                'title': 'Limit screen time before bed',
                'description': 'Avoid screens for at least 1 hour before bedtime to improve sleep quality.',
                'category': 'lifestyle',
                'icon': 'fas fa-mobile-alt',
                'default_duration_days': 14
            },
            {
                'title': 'Social connection',
                'description': 'Connect with friends or family for at least 15 minutes daily.',
                'category': 'lifestyle',
                'icon': 'fas fa-users',
                'default_duration_days': 7
            }
        ]
        
        created_count = 0
        for template_data in templates:
            template, created = HealthTaskTemplate.objects.get_or_create(
                title=template_data['title'],
                defaults=template_data
            )
            if created:
                created_count += 1
                self.stdout.write(f'Created template: {template.title}')
            else:
                self.stdout.write(f'Template already exists: {template.title}')
        
        self.stdout.write(f'\nCreated {created_count} new health task templates')
        self.stdout.write(f'Total templates: {HealthTaskTemplate.objects.count()}')
