from django.core.management.base import BaseCommand
from home.models import Doctor, DoctorPrimaryFocus, DoctorSpecialization, User
import random


class Command(BaseCommand):
    help = 'Populate sample doctors with advanced recommendation data'
    
    def handle(self, *args, **options):
        # Get or create sample users for doctors
        doctor_data = [
            {
                'username': 'dr_sarah_johnson',
                'email': 'sarah.johnson@mentalwellness.com',
                'first_name': 'Sarah',
                'last_name': 'Johnson',
                'specialty': 'Psychiatrist',
                'primary_focus': 'Depression',
                'years_of_experience': 12,
                'expertise_tags': ['depression', 'sadness', 'hopeless', 'medication', 'cognitive-therapy'],
                'patients_helped': 250,
                'success_rate': 85.0,
                'consultation_fee': 150.00
            },
            {
                'username': 'dr_michael_chen',
                'email': 'michael.chen@mentalwellness.com',
                'first_name': 'Michael',
                'last_name': 'Chen',
                'specialty': 'Clinical Psychologist',
                'primary_focus': 'Anxiety',
                'years_of_experience': 8,
                'expertise_tags': ['anxiety', 'panic-attacks', 'worry', 'fear', 'cbt', 'exposure-therapy'],
                'patients_helped': 180,
                'success_rate': 78.0,
                'consultation_fee': 120.00
            },
            {
                'username': 'dr_emily_rodriguez',
                'email': 'emily.rodriguez@mentalwellness.com',
                'first_name': 'Emily',
                'last_name': 'Rodriguez',
                'specialty': 'Therapist',
                'primary_focus': 'Stress',
                'years_of_experience': 15,
                'expertise_tags': ['stress', 'burnout', 'work-life-balance', 'mindfulness', 'relaxation'],
                'patients_helped': 320,
                'success_rate': 92.0,
                'consultation_fee': 100.00
            },
            {
                'username': 'dr_david_kim',
                'email': 'david.kim@mentalwellness.com',
                'first_name': 'David',
                'last_name': 'Kim',
                'specialty': 'Neuropsychologist',
                'primary_focus': 'Sleep',
                'years_of_experience': 6,
                'expertise_tags': ['insomnia', 'sleep-disorders', 'fatigue', 'restless-sleep', 'sleep-hygiene'],
                'patients_helped': 95,
                'success_rate': 80.0,
                'consultation_fee': 110.00
            },
            {
                'username': 'dr_lisa_anderson',
                'email': 'lisa.anderson@mentalwellness.com',
                'first_name': 'Lisa',
                'last_name': 'Anderson',
                'specialty': 'Counselor',
                'primary_focus': 'Stress',
                'years_of_experience': 4,
                'expertise_tags': ['energy', 'fatigue', 'motivation', 'goal-setting', 'positive-psychology'],
                'patients_helped': 65,
                'success_rate': 75.0,
                'consultation_fee': 90.00
            }
        ]
        
        created_doctors = []
        
        for data in doctor_data:
            # Create or get user
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'email': data['email'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'role': 'doctor',
                    'is_verified': True
                }
            )
            
            if created:
                user.set_password('Doctor123!@#')
                user.save()
            
            # Create or update doctor profile
            doctor, doctor_created = Doctor.objects.update_or_create(
                user=user,
                defaults={
                    'qualification': f"MD in {data['specialty']} with specialization in {data['primary_focus']}",
                    'years_of_experience': data['years_of_experience'],
                    'consultation_fee': data['consultation_fee'],
                    'clinic_name': f"{data['first_name']} {data['last_name']} Mental Health Clinic",
                    'clinic_address': "123 Healthcare Street, Medical City, MC 12345",
                    'license_number': f"MD{random.randint(10000, 99999)}",
                    'bio': f"Experienced {data['specialty']} with {data['years_of_experience']} years of practice focusing on {data['primary_focus']} treatment.",
                    'is_available': True,
                    'expertise_tags': data['expertise_tags'],
                    'patients_helped': data['patients_helped'],
                    'success_rate': data['success_rate'],
                    'availability_schedule': {
                        'monday': ['09:00', '17:00'],
                        'tuesday': ['09:00', '17:00'],
                        'wednesday': ['09:00', '17:00'],
                        'thursday': ['09:00', '17:00'],
                        'friday': ['09:00', '15:00'],
                        'saturday': ['10:00', '14:00'],
                        'sunday': ['closed']
                    }
                }
            )

            specialization = DoctorSpecialization.objects.filter(value=data['specialty']).first()
            focus = DoctorPrimaryFocus.objects.filter(value=data['primary_focus']).first()
            if specialization:
                doctor.specializations.set([specialization])
            if focus:
                doctor.primary_focuses.set([focus])
            
            created_doctors.append(doctor)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created/updated {len(created_doctors)} sample doctors with advanced recommendation data!'
            )
        )
        
        # Print summary
        self.stdout.write('\n📊 Sample Doctors Created:')
        for doctor in created_doctors:
            self.stdout.write(
                f'  • Dr. {doctor.user.get_full_name()} - {doctor.specialty} (Focus: {doctor.primary_focus})'
            )
