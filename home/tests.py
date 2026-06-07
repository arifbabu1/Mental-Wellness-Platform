from io import StringIO
import json
from datetime import timedelta
from types import SimpleNamespace

from django.core import mail
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from .adapters import MentalWellnessSocialAccountAdapter
from .models import (
    Appointment,
    AssessmentQuestion,
    BookedSlot,
    Consultation,
    DailyTask,
    DailyTaskReminderLog,
    Doctor,
    DoctorSchedule,
    PatientAssessment,
    Payment,
    PaymentReceiverAccount,
    Prescription,
    SystemEmailConfig,
    TaskCompletion,
    User,
)
from .recommendation_engine import build_assessment_profile, recommend_doctors
from .system_config import get_active_payment_methods, get_default_payment_account, send_platform_email
from .task_services import mark_task_completed, replace_active_daily_tasks


class RecommendationEngineTests(SimpleTestCase):
    def test_core_scores_and_dynamic_triggers(self):
        user = SimpleNamespace(age=16, gender='female')
        core_answers = [4, 4, 3, 3, 1, 1, 4]

        profile = build_assessment_profile(core_answers, user)

        self.assertEqual(profile['primary_condition'], 'Depression')
        self.assertEqual(profile['severity_level'], 'High')
        self.assertEqual(profile['emotional_risk_level'], 'High')
        self.assertEqual(profile['category_scores']['Depression']['normalized'], 1.0)
        self.assertEqual(profile['category_scores']['Self-esteem']['normalized'], 1.0)
        self.assertIn('addiction', [module['key'] for module in profile['triggered_modules']])
        self.assertIn('child', [module['key'] for module in profile['triggered_modules']])

    def test_doctor_recommendations_use_weighted_100_point_rules(self):
        user = SimpleNamespace(age=65, gender='male')
        core_answers = [2, 2, 4, 4, 4, 1, 1]
        dynamic_responses = {
            'neurological': [4, 4, 4],
            'geriatric': [4, 3, 3],
        }
        profile = build_assessment_profile(core_answers, user, dynamic_responses)
        neuro_doctor = SimpleNamespace(
            specialty='Neuropsychiatrist',
            primary_focus='Neurological Disorders',
            years_of_experience=12,
            availability_score=5,
        )
        counselor = SimpleNamespace(
            specialty='Counselor',
            primary_focus='Talk Therapy',
            years_of_experience=1,
            availability_score=2,
        )

        recommendations = recommend_doctors([counselor, neuro_doctor], profile)

        self.assertEqual(recommendations[0]['doctor'], neuro_doctor)
        self.assertEqual(recommendations[0]['match_percentage'], 100)
        self.assertEqual(recommendations[0]['score_breakdown']['experience'], 20)
        self.assertEqual(recommendations[0]['score_breakdown']['availability'], 10)

    def test_doctor_recommendations_match_any_multi_value_field(self):
        user = SimpleNamespace(age=35, gender='female')
        profile = build_assessment_profile([4, 4, 1, 1, 1, 1, 3], user)
        multi_match_doctor = SimpleNamespace(
            specialization_values=['Counselor', 'Clinical Psychologist'],
            primary_focus_values=['Anxiety', 'Depression'],
            specialty='Clinical Psychologist',
            primary_focus='Anxiety, Depression',
            years_of_experience=6,
            availability_score=5,
        )
        no_match_doctor = SimpleNamespace(
            specialization_values=['Neuropsychologist'],
            primary_focus_values=['Schizophrenia'],
            specialty='Neuropsychologist',
            primary_focus='Schizophrenia',
            years_of_experience=20,
            availability_score=5,
        )

        recommendations = recommend_doctors([no_match_doctor, multi_match_doctor], profile)

        self.assertEqual(recommendations[0]['doctor'], multi_match_doctor)
        self.assertEqual(len(recommendations), 1)
        self.assertGreater(recommendations[0]['score_breakdown']['multi_match_bonus'], 0)


class AssessmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='patient',
            password='pass1234',
            role='patient',
            age=17,
            gender='female',
        )
        questions = [
            ('Over the past two weeks, how often have you felt down, depressed, or hopeless?', 'Depression', 3),
            ('Over the past two weeks, how often have you had little interest or pleasure in doing things?', 'Depression', 3),
            ('Over the past two weeks, how often have you felt nervous, anxious, or on edge?', 'Anxiety', 2),
            ('Over the past two weeks, how often have you been unable to stop or control worrying?', 'Anxiety', 2),
            ('Over the past two weeks, how often have you had trouble falling or staying asleep, or sleeping too much?', 'Sleep', 2),
            ('Over the past two weeks, how often have you felt tired or had little energy?', 'Energy', 1),
            ('Over the past two weeks, how often have you felt that you are a failure or have let yourself or your family down?', 'Self-esteem', 3),
        ]
        for index, (text, category, weight) in enumerate(questions, start=1):
            AssessmentQuestion.objects.create(
                question_text=text,
                category=category,
                weight_value=weight,
                track_number=index,
            )
        self.client.login(username='patient', password='pass1234')

    def test_assessment_page_renders_dynamic_modules(self):
        response = self.client.get(reverse('assessment'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-module="addiction"')
        self.assertContains(response, 'data-module="child"')

    def test_assessment_post_stores_rule_profile(self):
        data = {}
        for question in AssessmentQuestion.objects.order_by('track_number'):
            data[f'question_{question.id}'] = '4'
        for module in ('addiction', 'family', 'neurological', 'child'):
            for index in range(3):
                data[f'dynamic_{module}_{index}'] = '4'

        response = self.client.post(reverse('assessment'), data, follow=True)
        assessment = PatientAssessment.objects.get(patient=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(assessment.result_summary['primary_condition'], 'Depression')
        self.assertEqual(assessment.result_summary['severity_level'], 'High')
        self.assertEqual(assessment.result_summary['emotional_risk_level'], 'High')
        self.assertIn('addiction', assessment.dynamic_responses)
        self.assertContains(response, 'Recommendation Engine Summary')


class AuthenticationUpgradeTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username='auth_patient',
            email='auth_patient@example.com',
            password='pass1234',
            role='patient',
        )

    def test_manual_login_still_redirects_by_role(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'auth_patient', 'password': 'pass1234'},
        )

        self.assertRedirects(response, reverse('patient_dashboard'), fetch_redirect_response=False)

    def test_login_and_register_include_google_option(self):
        login_response = self.client.get(reverse('login'))
        register_response = self.client.get(reverse('register'))

        self.assertContains(login_response, 'Continue with Google')
        self.assertContains(register_response, 'Continue with Google')
        self.assertContains(login_response, 'href="/accounts/google/login/?process=login"')
        self.assertContains(register_response, 'href="/accounts/google/login/?process=signup"')
        self.assertNotContains(login_response, 'google-login-btn disabled')
        self.assertNotContains(register_response, 'google-login-btn disabled')

    def test_google_login_url_is_allauth_view(self):
        match = resolve('/accounts/google/login/')

        self.assertEqual(reverse('google_login'), '/accounts/google/login/')
        self.assertEqual(match.url_name, 'google_login')

    def test_auth_redirect_uses_platform_role(self):
        self.client.login(username='auth_patient', password='pass1234')

        response = self.client.get(reverse('auth_redirect'))

        self.assertRedirects(response, reverse('patient_dashboard'), fetch_redirect_response=False)

    def test_google_adapter_populates_profile_defaults(self):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {}
        sociallogin = SocialLogin(
            user=User(username='google_user', email='google@example.com'),
            account=SocialAccount(
                provider='google',
                uid='google-123',
                extra_data={
                    'email': 'google@example.com',
                    'email_verified': True,
                    'given_name': 'Google',
                    'family_name': 'Patient',
                    'picture': 'https://example.com/avatar.jpg',
                },
            ),
            email_addresses=[
                EmailAddress(email='google@example.com', verified=True, primary=True),
            ],
        )
        adapter = MentalWellnessSocialAccountAdapter()

        user = adapter.populate_user(
            request,
            sociallogin,
            {'email': 'google@example.com', 'first_name': 'Google', 'last_name': 'Patient'},
        )

        self.assertEqual(user.role, 'patient')
        self.assertEqual(user.first_name, 'Google')
        self.assertEqual(user.last_name, 'Patient')
        self.assertEqual(user.profile_picture_url, 'https://example.com/avatar.jpg')

    def test_google_adapter_blocks_existing_doctor_email(self):
        doctor = User.objects.create_user(
            username='google_doctor',
            email='google_doctor@example.com',
            password='pass1234',
            role='doctor',
        )
        request = RequestFactory().get('/accounts/google/login/callback/')
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        sociallogin = SocialLogin(
            user=User(username='google_doctor', email=doctor.email),
            account=SocialAccount(
                provider='google',
                uid='google-doctor-123',
                extra_data={'email': doctor.email, 'email_verified': True},
            ),
            email_addresses=[EmailAddress(email=doctor.email, verified=True, primary=True)],
        )

        with self.assertRaises(ImmediateHttpResponse):
            MentalWellnessSocialAccountAdapter().pre_social_login(request, sociallogin)


class BookingPaymentFlowTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username='booking_patient',
            email='booking_patient@example.com',
            password='pass1234',
            role='patient',
        )
        self.doctor_user = User.objects.create_user(
            username='booking_doctor',
            email='booking_doctor@example.com',
            password='pass1234',
            role='doctor',
            first_name='Booking',
            last_name='Doctor',
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name='Dr. Booking Doctor',
            qualification='MBBS',
            years_of_experience=8,
            consultation_fee=1000,
            license_number='BOOK-1',
            is_available=True,
        )
        self.booking_date = timezone.localdate() + timedelta(days=1)
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            day_of_week=self.booking_date.weekday(),
            start_time='09:00',
            end_time='10:00',
            slot_duration=30,
            is_available=True,
        )
        self.bkash_receiver = PaymentReceiverAccount.objects.create(
            payment_method='bkash',
            account_name='Primary bKash',
            merchant_number='01711111111',
            is_active=True,
            is_default=True,
            instructions='Send Money to the masked bKash merchant number.',
        )
        self.nagad_receiver = PaymentReceiverAccount.objects.create(
            payment_method='nagad',
            account_name='Primary Nagad',
            merchant_number='01811111111',
            is_active=True,
            is_default=True,
            instructions='Use Nagad test payment instructions.',
        )
        self.card_receiver = PaymentReceiverAccount.objects.create(
            payment_method='card',
            account_name='Primary Card Processor',
            card_processor_name='Test Card Processor',
            card_receiver_account='CARD-MERCHANT-001',
            is_active=True,
            is_default=True,
            instructions='Use test card details only.',
        )

    def test_booking_page_loads_without_booking_context_name_error(self):
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.get(reverse('book_appointment', args=[self.doctor.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Book Your Consultation')
        self.assertContains(response, 'BDT')
        self.assertContains(response, 'bKash')
        self.assertContains(response, 'Nagad')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PAYMENT_TEST_MODE=True, PAYMENT_TEST_OTP='123456')
    def test_booking_requires_payment_details_and_otp_before_confirming(self):
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.post(
            reverse('book_appointment', args=[self.doctor.id]),
            {
                'appointment_date': self.booking_date.isoformat(),
                'appointment_time': '9:00 AM',
                'consultation_type': 'video',
                'payment_method': 'bkash',
                'wallet_number': '01712345678',
                'reference_id': 'BKASH-TEST-1',
                'notes': 'Need help with anxiety.',
            },
        )

        appointment = Appointment.objects.get(patient=self.patient, doctor=self.doctor)
        payment = Payment.objects.get(appointment=appointment)
        self.assertRedirects(response, reverse('verify_booking_payment', args=[payment.id]), fetch_redirect_response=False)
        self.assertEqual(appointment.status, 'pending_payment')
        self.assertEqual(payment.status, 'otp_sent')
        self.assertEqual(payment.payment_method, 'bkash')
        self.assertEqual(payment.payment_receiver_account, self.bkash_receiver)
        self.assertEqual(payment.receiver_payment_method, 'bkash')
        self.assertEqual(payment.receiver_account_snapshot['account_name'], 'Primary bKash')
        self.assertEqual(payment.wallet_number_masked, '017*****678')
        self.assertEqual(payment.reference_id, 'BKASH-TEST-1')
        self.assertEqual(payment.card_last4, '')
        self.assertIsNone(payment.paid_at)
        self.assertFalse(appointment.meeting_link)
        self.assertFalse(BookedSlot.objects.filter(doctor=self.doctor, appointment_date=self.booking_date).exists())
        self.assertEqual(len(mail.outbox), 0)

        verify_response = self.client.post(
            reverse('verify_booking_payment', args=[payment.id]),
            {
                'otp_code': '123456',
                'wallet_pin': '1234',
            },
        )

        appointment.refresh_from_db()
        payment.refresh_from_db()
        self.assertRedirects(verify_response, reverse('booking_success', args=[appointment.id]), fetch_redirect_response=False)
        self.assertEqual(appointment.status, 'confirmed')
        self.assertEqual(payment.status, 'test_paid')
        self.assertIsNotNone(payment.paid_at)
        self.assertIsNotNone(payment.otp_verified_at)
        self.assertTrue(appointment.meeting_link)
        self.assertTrue(payment.transaction_id.startswith('TEST-BKASH-'))
        self.assertEqual(payment.payment_receiver_account, self.bkash_receiver)
        self.assertTrue(BookedSlot.objects.filter(doctor=self.doctor, appointment_date=self.booking_date).exists())
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].subject, 'Your consultation appointment is successfully booked')
        self.assertEqual(mail.outbox[1].subject, 'New consultation appointment booked')
        self.assertIn('Dr. Booking Doctor', mail.outbox[0].body)
        self.assertIn('Meeting Link', mail.outbox[0].body)

        success_response = self.client.get(reverse('booking_success', args=[appointment.id]))
        self.assertEqual(success_response.status_code, 200)
        self.assertContains(success_response, 'Booking Confirmed')
        self.assertContains(success_response, 'Test Paid')
        self.assertContains(success_response, payment.transaction_id)

    @override_settings(PAYMENT_TEST_MODE=True, PAYMENT_TEST_OTP='123456')
    def test_duplicate_slot_is_blocked(self):
        self.client.login(username='booking_patient', password='pass1234')
        url = reverse('book_appointment', args=[self.doctor.id])
        payload = {
            'appointment_date': self.booking_date.isoformat(),
            'appointment_time': '9:00 AM',
            'consultation_type': 'video',
            'payment_method': 'card',
            'cardholder_name': 'Booking Patient',
            'card_number': '4242 4242 4242 4242',
            'expiry_month': '12',
            'expiry_year': str(timezone.localdate().year + 1),
            'cvv': '123',
        }

        self.client.post(url, payload)
        payment = Payment.objects.get()
        self.client.post(reverse('verify_booking_payment', args=[payment.id]), {'otp_code': '123456'})
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This time slot has just been booked')
        self.assertEqual(Appointment.objects.filter(patient=self.patient, doctor=self.doctor).count(), 1)

    @override_settings(PAYMENT_TEST_MODE=True, PAYMENT_TEST_OTP='123456')
    def test_wrong_otp_does_not_confirm_booking(self):
        self.client.login(username='booking_patient', password='pass1234')
        self.client.post(
            reverse('book_appointment', args=[self.doctor.id]),
            {
                'appointment_date': self.booking_date.isoformat(),
                'appointment_time': '9:00 AM',
                'consultation_type': 'video',
                'payment_method': 'nagad',
                'wallet_number': '01812345678',
            },
        )
        payment = Payment.objects.get()

        response = self.client.post(
            reverse('verify_booking_payment', args=[payment.id]),
            {'otp_code': '000000', 'wallet_pin': '1234'},
        )

        appointment = payment.appointment
        payment.refresh_from_db()
        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid OTP')
        self.assertEqual(payment.status, 'otp_sent')
        self.assertEqual(appointment.status, 'pending_payment')
        self.assertFalse(BookedSlot.objects.exists())

    def test_invalid_mobile_number_is_rejected(self):
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.post(
            reverse('book_appointment', args=[self.doctor.id]),
            {
                'appointment_date': self.booking_date.isoformat(),
                'appointment_time': '9:00 AM',
                'consultation_type': 'video',
                'payment_method': 'bkash',
                'wallet_number': '012345',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a valid Bangladesh mobile number')
        self.assertFalse(Appointment.objects.exists())

    def test_booking_page_shows_only_active_payment_methods(self):
        PaymentReceiverAccount.objects.filter(payment_method__in=['nagad', 'card']).update(is_active=False)
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.get(reverse('book_appointment', args=[self.doctor.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bKash')
        self.assertNotContains(response, 'Nagad mobile banking')
        self.assertNotContains(response, 'Pay with Visa')

    def test_payment_fails_if_selected_method_has_no_active_receiver(self):
        PaymentReceiverAccount.objects.filter(payment_method='bkash').update(is_active=False)
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.post(
            reverse('book_appointment', args=[self.doctor.id]),
            {
                'appointment_date': self.booking_date.isoformat(),
                'appointment_time': '9:00 AM',
                'consultation_type': 'video',
                'payment_method': 'bkash',
                'wallet_number': '01712345678',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please select an active payment method.')
        self.assertFalse(Appointment.objects.exists())

    def test_missing_booking_fields_show_validation_error(self):
        self.client.login(username='booking_patient', password='pass1234')

        response = self.client.post(
            reverse('book_appointment', args=[self.doctor.id]),
            {'payment_method': 'card'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please select both date and time')

    def test_non_patient_cannot_book(self):
        self.client.login(username='booking_doctor', password='pass1234')

        response = self.client.get(reverse('book_appointment', args=[self.doctor.id]))

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)


class AdminSettingsConfigTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='settings_admin',
            email='settings_admin@example.com',
            password='pass1234',
            role='admin',
        )
        self.staff_user = User.objects.create_user(
            username='settings_staff',
            email='settings_staff@example.com',
            password='pass1234',
            role='admin',
            is_staff=True,
        )

    def test_only_one_active_email_config(self):
        first = SystemEmailConfig.objects.create(
            name='First SMTP',
            email_host='smtp.first.example.com',
            email_port=587,
            email_host_user='first@example.com',
            email_host_password='first-secret',
            default_from_email='first@example.com',
            is_active=True,
        )
        second = SystemEmailConfig.objects.create(
            name='Second SMTP',
            email_host='smtp.second.example.com',
            email_port=587,
            email_host_user='second@example.com',
            email_host_password='second-secret',
            default_from_email='second@example.com',
            is_active=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(SystemEmailConfig.active(), second)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_platform_email_uses_active_config(self):
        SystemEmailConfig.objects.create(
            name='Active SMTP',
            email_host='smtp.active.example.com',
            email_port=587,
            email_host_user='active@example.com',
            email_host_password='active-secret',
            default_from_email='noreply@example.com',
            is_active=True,
        )

        sent = send_platform_email('Config test', 'Body', ['patient@example.com'], fail_silently=False)

        self.assertEqual(sent, 1)
        self.assertEqual(mail.outbox[0].from_email, 'noreply@example.com')
        self.assertEqual(mail.outbox[0].to, ['patient@example.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='fallback@example.com')
    def test_send_platform_email_falls_back_to_settings(self):
        sent = send_platform_email('Fallback test', 'Body', ['patient@example.com'], fail_silently=False)

        self.assertEqual(sent, 1)
        self.assertEqual(mail.outbox[0].from_email, 'fallback@example.com')

    def test_only_one_default_payment_receiver_per_method(self):
        first = PaymentReceiverAccount.objects.create(
            payment_method='bkash',
            account_name='First bKash',
            merchant_number='01711111111',
            is_active=True,
            is_default=True,
        )
        second = PaymentReceiverAccount.objects.create(
            payment_method='bkash',
            account_name='Second bKash',
            merchant_number='01722222222',
            is_active=True,
            is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_active)
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_active)
        self.assertTrue(second.is_default)
        self.assertEqual(get_default_payment_account('bkash'), second)
        self.assertIn('bkash', get_active_payment_methods())

    def test_non_superuser_cannot_manage_sensitive_settings(self):
        self.client.login(username='settings_staff', password='pass1234')

        email_response = self.client.get(reverse('admin:home_systememailconfig_changelist'))
        payment_response = self.client.get(reverse('admin:home_paymentreceiveraccount_changelist'))

        self.assertNotEqual(email_response.status_code, 200)
        self.assertNotEqual(payment_response.status_code, 200)

    def test_superuser_admin_core_pages_render(self):
        SystemEmailConfig.objects.create(
            name='Smoke SMTP',
            email_host='smtp.smoke.example.com',
            email_port=587,
            email_host_user='smoke@example.com',
            email_host_password='smoke-secret',
            default_from_email='noreply@example.com',
            is_active=True,
        )
        PaymentReceiverAccount.objects.create(
            payment_method='bkash',
            account_name='Smoke bKash',
            merchant_number='01711111111',
            is_active=True,
            is_default=True,
        )
        self.client.login(username='settings_admin', password='pass1234')

        pages = [
            reverse('admin:index'),
            reverse('admin_dashboard'),
            reverse('admin:home_user_changelist'),
            reverse('admin:home_systememailconfig_changelist'),
            reverse('admin:home_paymentreceiveraccount_changelist'),
            reverse('admin:home_appointment_changelist'),
            reverse('admin:home_payment_changelist'),
            reverse('admin:home_blogpost_changelist'),
            reverse('admin:home_dailytask_changelist'),
            reverse('admin:home_notification_changelist'),
        ]

        for page in pages:
            with self.subTest(page=page):
                response = self.client.get(page)
                self.assertEqual(response.status_code, 200)


class DailyTaskFeatureTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username='task_patient',
            password='pass1234',
            email='patient@example.com',
            first_name='Task',
            last_name='Patient',
            role='patient',
        )
        self.doctor_user = User.objects.create_user(
            username='task_doctor',
            password='pass1234',
            email='doctor@example.com',
            first_name='Task',
            last_name='Doctor',
            role='doctor',
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name='Dr. Task Doctor',
            qualification='MBBS',
            years_of_experience=7,
            consultation_fee=800,
            license_number='DOC-TASK-1',
        )

    def make_consultation(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=timezone.now(),
            status='completed',
            consultation_fee=800,
        )
        return Consultation.objects.create(
            appointment=appointment,
            room_name=f'task-room-{appointment.id}',
            start_time=timezone.now(),
            end_time=timezone.now(),
        )

    def task_payloads(self, *titles):
        return [
            {
                'title': title,
                'description': f'{title} description',
                'category': 'mental',
                'duration': 7,
            }
            for title in titles
        ]

    def replace_tasks(self, consultation, *titles):
        return replace_active_daily_tasks(
            patient=self.patient,
            doctor=self.doctor,
            consultation=consultation,
            tasks_data=self.task_payloads(*titles),
        )

    def test_new_consultation_replaces_old_active_tasks(self):
        first_consultation = self.make_consultation()
        self.replace_tasks(first_consultation, '10th breathing', '10th journal', '10th walk')

        second_consultation = self.make_consultation()
        result = self.replace_tasks(
            second_consultation,
            '13th breathing',
            '13th journal',
            '13th gratitude',
            '13th sleep routine',
            '13th hydration',
        )

        self.assertEqual(result['deactivated_count'], 3)
        self.assertEqual(result['created_count'], 5)
        self.assertFalse(DailyTask.objects.filter(consultation=first_consultation, is_active=True).exists())
        self.assertEqual(
            list(DailyTask.objects.filter(patient=self.patient, is_active=True).order_by('title').values_list('title', flat=True)),
            [
                '13th breathing',
                '13th gratitude',
                '13th hydration',
                '13th journal',
                '13th sleep routine',
            ],
        )

    def test_consultation_with_no_tasks_deactivates_previous_active_tasks(self):
        self.replace_tasks(self.make_consultation(), 'morning breathing', 'evening journal')

        result = replace_active_daily_tasks(
            patient=self.patient,
            doctor=self.doctor,
            consultation=self.make_consultation(),
            tasks_data=[],
        )

        self.assertEqual(result['deactivated_count'], 2)
        self.assertEqual(result['created_count'], 0)
        self.assertFalse(DailyTask.objects.filter(patient=self.patient, is_active=True).exists())

    def test_replacement_creates_today_valid_active_tasks(self):
        today = timezone.localdate()
        result = replace_active_daily_tasks(
            patient=self.patient,
            doctor=self.doctor,
            consultation=self.make_consultation(),
            tasks_data=[
                {
                    'title': 'today breathing',
                    'description': 'Practice breathing today',
                    'category': 'mental',
                    'duration': '3 days',
                    'priority': 'high',
                    'start_date': (today + timedelta(days=10)).isoformat(),
                    'end_date': (today + timedelta(days=12)).isoformat(),
                }
            ],
        )

        self.assertEqual(result['created_count'], 1)
        task = result['created_tasks'][0]
        self.assertEqual(task.patient, self.patient)
        self.assertEqual(task.consultation.appointment.patient, self.patient)
        self.assertTrue(task.is_active)
        self.assertEqual(task.start_date, today)
        self.assertEqual(task.end_date, today + timedelta(days=2))
        self.assertEqual(task.duration_days, 3)
        self.assertEqual(task.priority, 'high')
        self.assertTrue(task.is_today)

    def test_patient_dashboard_shows_only_latest_active_tasks(self):
        self.replace_tasks(self.make_consultation(), 'old breathing task')
        self.replace_tasks(self.make_consultation(), 'latest grounding task')
        today = timezone.localdate()
        DailyTask.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation=self.make_consultation(),
            title='expired active task',
            description='Should be hidden because it ended before today',
            category='mental',
            icon='fas fa-tasks',
            source='custom',
            start_date=today - timedelta(days=4),
            end_date=today - timedelta(days=1),
            duration_days=4,
            priority='medium',
            is_active=True,
        )
        DailyTask.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation=self.make_consultation(),
            title='future active task',
            description='Should be hidden because it starts later',
            category='mental',
            icon='fas fa-tasks',
            source='custom',
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=3,
            priority='medium',
            is_active=True,
        )
        self.client.login(username='task_patient', password='pass1234')

        response = self.client.get(reverse('patient_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'latest grounding task')
        self.assertNotContains(response, 'old breathing task')
        self.assertNotContains(response, 'expired active task')
        self.assertNotContains(response, 'future active task')

    def test_save_consultation_data_replaces_tasks_from_json_payload(self):
        old_consultation = self.make_consultation()
        self.replace_tasks(old_consultation, 'old dashboard task')
        consultation = self.make_consultation()
        self.client.login(username='task_doctor', password='pass1234')

        response = self.client.post(
            reverse('save_consultation_data'),
            data=json.dumps({
                'appointmentId': consultation.appointment_id,
                'patientId': self.patient.id,
                'notes': {'assessment': 'stable'},
                'prescription': {
                    'details': 'Prescription still saves',
                    'instructions': 'Take with food',
                    'medications': [{'name': 'Med A', 'dosage': '5mg'}],
                },
                'daily_tasks': [
                    {
                        'title': 'Sleep Schedule',
                        'description': 'Maintain regular sleep hours',
                        'category': 'mental',
                        'duration_days': 2,
                        'priority': 'high',
                    },
                    {
                        'title': 'Take Medication',
                        'description': 'Take prescribed medications on time',
                        'category': 'medical',
                        'duration_days': 3,
                        'priority': 'high',
                    }
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['tasks_saved'], 2)
        self.assertEqual(response.json()['message'], 'Consultation saved and 2 daily tasks assigned.')
        self.assertFalse(DailyTask.objects.filter(consultation=old_consultation, is_active=True).exists())

        today = timezone.localdate()
        tasks = DailyTask.objects.filter(patient=self.patient, consultation=consultation, is_active=True).order_by('title')
        self.assertEqual(tasks.count(), 2)
        self.assertEqual(list(tasks.values_list('title', flat=True)), ['Sleep Schedule', 'Take Medication'])
        for task in tasks:
            self.assertEqual(task.patient, self.patient)
            self.assertEqual(task.consultation, consultation)
            self.assertEqual(task.start_date, today)
            self.assertGreaterEqual(task.end_date, today)
            self.assertTrue(task.is_today)

        prescription = Prescription.objects.get(consultation=consultation)
        self.assertEqual(prescription.patient, self.patient)
        self.assertEqual(prescription.prescription_text, 'Prescription still saves')

        self.client.logout()
        self.client.login(username='task_patient', password='pass1234')
        dashboard_response = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(dashboard_response.context['total_tasks'], 2)
        self.assertEqual(dashboard_response.context['completed_tasks'], 0)
        self.assertEqual(dashboard_response.context['completed_count'], 0)
        self.assertContains(dashboard_response, '0/2 Completed')
        self.assertContains(dashboard_response, 'Sleep Schedule')
        self.assertContains(dashboard_response, 'Take Medication')

    def test_save_consultation_data_accepts_form_daily_tasks_json(self):
        old_consultation = self.make_consultation()
        self.replace_tasks(old_consultation, 'old form task')
        consultation = self.make_consultation()
        self.client.login(username='task_doctor', password='pass1234')

        response = self.client.post(
            reverse('save_consultation_data'),
            data={
                'appointment_id': consultation.appointment_id,
                'patient_id': self.patient.id,
                'daily_tasks_json': json.dumps([
                    {
                        'title': 'Form Sleep Schedule',
                        'description': 'Maintain sleep schedule',
                        'category': 'lifestyle',
                        'duration_days': 2,
                        'priority': 'medium',
                    },
                    {
                        'title': 'Form Take Medication',
                        'description': 'Take medicine on time',
                        'category': 'medical',
                        'duration_days': 4,
                        'priority': 'high',
                    },
                ]),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['tasks_saved'], 2)
        self.assertFalse(DailyTask.objects.filter(consultation=old_consultation, is_active=True).exists())
        self.assertEqual(
            list(DailyTask.objects.filter(patient=self.patient, is_active=True).order_by('title').values_list('title', flat=True)),
            ['Form Sleep Schedule', 'Form Take Medication'],
        )

    def test_consultation_room_renders_save_all_task_serializer(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=timezone.now(),
            status='confirmed',
            consultation_fee=800,
        )
        Consultation.objects.create(
            appointment=appointment,
            room_name=f'task-room-{appointment.id}',
            start_time=timezone.now(),
        )
        self.client.login(username='task_doctor', password='pass1234')

        response = self.client.get(reverse('consultation_room', args=[appointment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="saveAllData"')
        self.assertContains(response, 'id="dailyTasksJson"')
        self.assertContains(response, 'daily_tasks: selectedTasks')
        self.assertContains(response, 'daily_tasks_json:')
        self.assertContains(response, 'tasks: selectedTasks')
        self.assertContains(response, "source: item.dataset.source || 'custom'")
        self.assertNotContains(response, 'Implementation depends on how you track selected tasks')

    def test_task_completion_is_idempotent_and_limited_to_owner_active_tasks(self):
        self.replace_tasks(self.make_consultation(), 'daily reflection')
        task = DailyTask.objects.get(title='daily reflection')
        self.client.login(username='task_patient', password='pass1234')

        first_response = self.client.post(reverse('complete_daily_task', args=[task.id]))
        second_response = self.client.post(reverse('complete_daily_task', args=[task.id]))

        self.assertJSONEqual(
            first_response.content,
            {
                'success': True,
                'message': 'Task marked as completed!',
                'completed_at': TaskCompletion.objects.get(daily_task=task).completed_at.strftime('%I:%M %p'),
            },
        )
        self.assertEqual(second_response.json()['error'], 'Task already completed')
        self.assertEqual(TaskCompletion.objects.filter(daily_task=task, completion_date=timezone.localdate()).count(), 1)

        other_patient = User.objects.create_user(
            username='other_patient',
            password='pass1234',
            email='other@example.com',
            role='patient',
        )
        self.client.logout()
        self.client.login(username='other_patient', password='pass1234')
        unauthorized_response = self.client.post(reverse('complete_daily_task', args=[task.id]))

        self.assertFalse(unauthorized_response.json()['success'])
        self.assertEqual(TaskCompletion.objects.filter(patient=other_patient).count(), 0)

        task.is_active = False
        task.save(update_fields=['is_active'])
        self.client.logout()
        self.client.login(username='task_patient', password='pass1234')
        inactive_response = self.client.post(reverse('complete_daily_task', args=[task.id]))
        self.assertFalse(inactive_response.json()['success'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_incomplete_task_reminder_email_sends_once_with_task_list(self):
        self.replace_tasks(self.make_consultation(), 'complete mood check', 'pending breathing')
        completed_task = DailyTask.objects.get(title='complete mood check')
        mark_task_completed(self.patient, completed_task)

        stdout = StringIO()
        stderr = StringIO()
        call_command('check_task_reminders', '--force', stdout=stdout, stderr=stderr)
        call_command('check_task_reminders', '--force', stdout=stdout, stderr=stderr)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['patient@example.com'])
        self.assertIn('pending breathing', mail.outbox[0].body)
        self.assertNotIn('complete mood check', mail.outbox[0].body)
        self.assertEqual(
            DailyTaskReminderLog.objects.filter(user=self.patient, date=timezone.localdate()).count(),
            1,
        )
        self.assertEqual(DailyTaskReminderLog.objects.get(user=self.patient).incomplete_tasks_count, 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_no_reminder_email_sends_when_all_tasks_completed(self):
        self.replace_tasks(self.make_consultation(), 'task one', 'task two')
        for task in DailyTask.objects.filter(patient=self.patient, is_active=True):
            mark_task_completed(self.patient, task)

        call_command('check_task_reminders', '--force', stdout=StringIO(), stderr=StringIO())

        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(DailyTaskReminderLog.objects.filter(user=self.patient).exists())


class ConsultationRoomFlowTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username='room_patient',
            password='pass1234',
            email='room_patient@example.com',
            role='patient',
        )
        self.other_patient = User.objects.create_user(
            username='other_room_patient',
            password='pass1234',
            email='other_room_patient@example.com',
            role='patient',
        )
        self.doctor_user = User.objects.create_user(
            username='room_doctor',
            password='pass1234',
            email='room_doctor@example.com',
            role='doctor',
        )
        self.other_doctor_user = User.objects.create_user(
            username='other_room_doctor',
            password='pass1234',
            email='other_room_doctor@example.com',
            role='doctor',
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name='Dr. Room Doctor',
            qualification='MBBS',
            years_of_experience=5,
            consultation_fee=800,
            license_number='ROOM-DOC-1',
        )
        self.other_doctor = Doctor.objects.create(
            user=self.other_doctor_user,
            name='Dr. Other Room Doctor',
            qualification='MBBS',
            years_of_experience=5,
            consultation_fee=800,
            license_number='ROOM-DOC-2',
        )

    def make_appointment(self, offset_minutes=0, status='confirmed', meeting_id='room-flow'):
        return Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=timezone.now() + timedelta(minutes=offset_minutes),
            status=status,
            consultation_fee=800,
            meeting_id=meeting_id,
            meeting_link=f'/consultation/{meeting_id}/',
        )

    def test_patient_and_doctor_join_same_room_and_status_becomes_in_progress(self):
        appointment = self.make_appointment(meeting_id='shared-room-1')

        self.client.login(username='room_patient', password='pass1234')
        patient_response = self.client.get(reverse('consultation_room', args=[appointment.id]))
        self.assertEqual(patient_response.status_code, 200)
        self.assertContains(patient_response, 'patientWaitingRoom')
        self.assertContains(patient_response, 'Checking consultation status')
        self.assertNotContains(patient_response, 'Join Now')
        consultation = Consultation.objects.get(appointment=appointment)
        self.assertEqual(consultation.room_name, 'shared-room-1')
        self.assertIsNone(consultation.patient_joined_at)
        self.assertEqual(Appointment.objects.get(id=appointment.id).status, 'confirmed')

        self.client.logout()
        self.client.login(username='room_doctor', password='pass1234')
        doctor_response = self.client.get(reverse('consultation_room', args=[appointment.id]))
        self.assertEqual(doctor_response.status_code, 200)
        self.assertContains(doctor_response, 'startConsultationBtn')
        consultation.refresh_from_db()
        appointment.refresh_from_db()
        self.assertEqual(consultation.room_name, 'shared-room-1')
        self.assertIsNone(consultation.doctor_joined_at)
        self.assertIsNone(consultation.started_at)
        self.assertEqual(consultation.status, 'scheduled')
        self.assertEqual(appointment.status, 'confirmed')

        start_response = self.client.post(reverse('start_consultation', args=[appointment.id]))
        self.assertEqual(start_response.status_code, 200)
        self.assertTrue(start_response.json()['started'])
        consultation.refresh_from_db()
        appointment.refresh_from_db()
        self.assertIsNotNone(consultation.doctor_joined_at)
        self.assertIsNotNone(consultation.started_at)
        self.assertEqual(consultation.status, 'in_progress')
        self.assertEqual(appointment.status, 'in_progress')

        join_response = self.client.post(reverse('register_consultation_join', args=[appointment.id]))
        self.assertEqual(join_response.status_code, 200)
        self.assertTrue(join_response.json()['allowed'])
        consultation.refresh_from_db()
        self.assertEqual(consultation.doctor_join_count, 1)

    def test_unauthorized_patient_and_doctor_are_blocked(self):
        appointment = self.make_appointment(meeting_id='secure-room')

        self.client.login(username='other_room_patient', password='pass1234')
        patient_response = self.client.get(reverse('consultation_room', args=[appointment.id]))
        self.assertEqual(patient_response.status_code, 403)

        self.client.logout()
        self.client.login(username='other_room_doctor', password='pass1234')
        doctor_response = self.client.get(reverse('consultation_room', args=[appointment.id]))
        self.assertEqual(doctor_response.status_code, 403)

    def test_room_opens_twenty_minutes_before_appointment(self):
        appointment = self.make_appointment(offset_minutes=45, meeting_id='future-room')
        self.client.login(username='room_patient', password='pass1234')

        response = self.client.get(reverse('consultation_room', args=[appointment.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Consultation.objects.filter(appointment=appointment).exists())
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'confirmed')

    def test_doctor_pages_show_consultation_link_for_active_appointments(self):
        appointment = self.make_appointment(offset_minutes=45, meeting_id='doctor-link-room')
        consultation_url = reverse('consultation_room', args=[appointment.id])
        self.client.login(username='room_doctor', password='pass1234')

        dashboard_response = self.client.get(reverse('doctor_dashboard'))
        appointments_response = self.client.get(reverse('doctor_appointments'))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(appointments_response.status_code, 200)
        self.assertContains(dashboard_response, consultation_url)
        self.assertContains(dashboard_response, 'Consultation Link')
        self.assertContains(appointments_response, consultation_url)
        self.assertContains(appointments_response, 'Consultation Link')

    def test_expired_room_marks_incomplete_and_expired(self):
        appointment = self.make_appointment(offset_minutes=-130, meeting_id='expired-room')
        self.client.login(username='room_patient', password='pass1234')

        response = self.client.get(reverse('consultation_room', args=[appointment.id]))

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        consultation = Consultation.objects.get(appointment=appointment)
        self.assertEqual(appointment.status, 'expired')
        self.assertEqual(consultation.status, 'expired')
        self.assertIsNotNone(consultation.expired_at)

    def test_only_assigned_doctor_completes_consultation(self):
        appointment = self.make_appointment(meeting_id='complete-room')
        self.client.login(username='room_patient', password='pass1234')
        patient_complete = self.client.post(reverse('complete_consultation', args=[appointment.id]))
        self.assertEqual(patient_complete.status_code, 403)

        self.client.logout()
        self.client.login(username='room_doctor', password='pass1234')
        self.client.get(reverse('consultation_room', args=[appointment.id]))
        response = self.client.post(reverse('complete_consultation', args=[appointment.id]))

        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        consultation = Consultation.objects.get(appointment=appointment)
        self.assertEqual(appointment.status, 'completed')
        self.assertEqual(consultation.status, 'completed')
        self.assertIsNotNone(consultation.completed_at)

    def test_save_notes_creates_stable_consultation_room(self):
        appointment = self.make_appointment(meeting_id='notes-room')
        self.client.login(username='room_doctor', password='pass1234')

        response = self.client.post(
            reverse('save_consultation_notes', args=[appointment.id]),
            data=json.dumps({'notes': 'Patient reports better sleep.'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        consultation = Consultation.objects.get(appointment=appointment)
        self.assertEqual(consultation.room_name, 'notes-room')
        self.assertEqual(consultation.notes, 'Patient reports better sleep.')

    def test_consultation_status_endpoint_reports_joined_participants(self):
        appointment = self.make_appointment(meeting_id='status-room')
        consultation = Consultation.objects.create(
            appointment=appointment,
            room_name='status-room',
            patient_joined_at=timezone.now(),
            status='waiting',
        )
        self.client.login(username='room_doctor', password='pass1234')

        response = self.client.get(reverse('consultation_status', args=[appointment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['patient_joined'])
        self.assertFalse(response.json()['doctor_joined'])
        self.assertFalse(response.json()['started'])
        self.assertEqual(response.json()['room_name'], 'status-room')

    def test_doctor_start_endpoint_marks_consultation_started(self):
        appointment = self.make_appointment(meeting_id='start-room')
        self.client.login(username='room_doctor', password='pass1234')
        self.client.get(reverse('consultation_room', args=[appointment.id]))

        response = self.client.post(reverse('start_consultation', args=[appointment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['started'])
        consultation = Consultation.objects.get(appointment=appointment)
        appointment.refresh_from_db()
        self.assertIsNotNone(consultation.doctor_joined_at)
        self.assertIsNotNone(consultation.started_at)
        self.assertEqual(consultation.status, 'in_progress')
        self.assertEqual(appointment.status, 'in_progress')

    def test_join_attempt_limit_blocks_fourth_join(self):
        appointment = self.make_appointment(meeting_id='limit-room')
        self.client.login(username='room_doctor', password='pass1234')
        self.client.post(reverse('start_consultation', args=[appointment.id]))

        for expected_remaining in [2, 1, 0]:
            response = self.client.post(reverse('register_consultation_join', args=[appointment.id]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['remaining_attempts'], expected_remaining)

        blocked = self.client.post(reverse('register_consultation_join', args=[appointment.id]))
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(blocked.json()['allowed'])

    def test_doctor_left_auto_completes_after_grace_period(self):
        appointment = self.make_appointment(meeting_id='doctor-left-room')
        self.client.login(username='room_doctor', password='pass1234')
        self.client.post(reverse('start_consultation', args=[appointment.id]))
        self.client.post(reverse('register_consultation_join', args=[appointment.id]))
        left_response = self.client.post(
            reverse('participant_left_consultation', args=[appointment.id]),
            data=json.dumps({'role': 'doctor'}),
            content_type='application/json',
        )
        self.assertEqual(left_response.status_code, 200)
        consultation = Consultation.objects.get(appointment=appointment)
        consultation.doctor_left_at = timezone.now() - timedelta(minutes=4)
        consultation.save(update_fields=['doctor_left_at'])

        status_response = self.client.get(reverse('consultation_status', args=[appointment.id]))

        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.json()['completed'])
        appointment.refresh_from_db()
        consultation.refresh_from_db()
        self.assertEqual(appointment.status, 'completed')
        self.assertEqual(consultation.status, 'completed')
