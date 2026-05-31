# home/urls.py

from django.urls import path

from . import views
from . import views_clinical



urlpatterns = [

    # Main pages

    path('', views.home, name='home'),

    path('emergency/', views.emergency, name='emergency'),
    path('emergency/chat/', views.emergency_chat, name='emergency_chat'),
    path('emergency/chat/history/', views.emergency_chat_history, name='emergency_chat_history'),
    path('emergency/chat/recommend-doctors/', views.emergency_doctor_recommendations, name='emergency_doctor_recommendations'),
    path('emergency/chat/detect-emergency/', views.emergency_detect, name='emergency_detect'),

    path('about/', views.about, name='about'),

    path('services/', views.services, name='services'),

    path('contact/', views.contact, name='contact'),

    path('blogs/', views.blogs, name='blogs'),

    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),

    

    # Doctor Blog Management

    path('doctor/blog/write/', views.doctor_write_blog, name='doctor_write_blog'),

    path('doctor/blogs/', views.doctor_blog_management, name='doctor_blog_management'),

    path('doctor/blog/<int:blog_id>/edit/', views.doctor_edit_blog, name='doctor_edit_blog'),

    path('doctor/blog/<int:blog_id>/delete/', views.doctor_delete_blog, name='doctor_delete_blog'),

    

    # Authentication

    path('register/', views.register, name='register'),

    path('login/', views.login_view, name='login'),

    path('accounts/login/', views.login_view, name='account_login_alias'),  # Compatibility alias

    path('auth/redirect/', views.auth_redirect, name='auth_redirect'),

    path('auth/complete-profile/', views.complete_social_profile, name='complete_social_profile'),

    path('logout/', views.logout_view, name='logout'),

    path('Quit/', views.logout_view, name='quit'),

    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('forgot-password/verify/', views.forgot_password_verify, name='forgot_password_verify'),
    path('forgot-password/reset/', views.forgot_password_reset, name='forgot_password_reset'),

    

    # Doctor URLs

    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),

    path('doctor/appointments/', views.doctor_appointments, name='doctor_appointments'),

    path('doctor/schedule/', views.doctor_schedule, name='doctor_schedule'),

    path('doctor/schedule/add/', views.doctor_add_schedule, name='doctor_add_schedule'),

    path('doctor/schedule/<int:schedule_id>/delete/', views.doctor_delete_schedule, name='doctor_delete_schedule'),

    path('doctor/complete-profile/<int:user_id>/', views.complete_doctor_profile, name='complete_doctor_profile'),

    path('doctor/edit-profile/', views.edit_doctor_profile, name='edit_doctor_profile'),

    

    # Dashboards

    path('patient/dashboard/', views.patient_dashboard, name='patient_dashboard'),

    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),

    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),

    

    # Admin Management Pages

    path('admin/users/', views.admin_users, name='admin_users'),

    path('admin/appointments/', views.admin_appointments, name='admin_appointments'),

    path('admin/assessments/', views.admin_assessments, name='admin_assessments'),

    
    # Assessment

    path('patient/assessment/', views.assessment, name='assessment'),

    path('patient/assessment/<int:assessment_id>/results/', views.assessment_results, name='assessment_results'),

    

    # Clinical Assessment (PHQ-9 + GAD-7)

    path('patient/clinical-assessment/', views_clinical.clinical_assessment, name='clinical_assessment'),

    path('patient/clinical-assessment/submit/', views_clinical.submit_clinical_assessment, name='submit_clinical_assessment'),

    path('patient/emergency-support/', views_clinical.emergency_support, name='emergency_support'),

    

    # Doctors and Appointments

    path('patient/doctors/', views.doctors_list, name='doctors_list'),

    path('patient/doctor/<int:doctor_id>/', views.doctor_details, name='doctor_details'),

    path('patient/book-appointment/<int:doctor_id>/', views.book_appointment, name='book_appointment'),

    path('get-available-slots/<int:doctor_id>/', views.get_available_slots_api, name='get_available_slots'),

    path('patient/appointments/', views.patient_appointments, name='patient_appointments'),

    path('patient/mark-completed/<int:appointment_id>/', views.mark_appointment_completed, name='mark_appointment_completed'),

    path('patient/delete-appointment/<int:appointment_id>/', views.delete_appointment, name='delete_appointment'),

    path('patient/payment/<int:payment_id>/', views.process_payment, name='process_payment'),
    path('patient/booking/payment/<int:payment_id>/verify/', views.verify_booking_payment, name='verify_booking_payment'),

    path('patient/booking-success/<int:appointment_id>/', views.booking_success, name='booking_success'),

    path('doctor/appointments/', views.doctor_appointments, name='doctor_appointments'),

    

    # Consultation

    path('consultation/<int:appointment_id>/', views.consultation_room, name='consultation_room'),

    path('consultation/<int:appointment_id>/save-notes/', views.save_consultation_notes, name='save_consultation_notes'),
    
    path('save-consultation-data/', views.save_consultation_data, name='save_consultation_data'),
    
    path('test-patient-data/', views.test_patient_data, name='test_patient_data'),
    
    path('consultation/<int:appointment_id>/complete/', views.complete_consultation, name='complete_consultation'),
    path('consultation/<int:appointment_id>/leave/', views.leave_consultation, name='leave_consultation'),
    path('consultation/<int:appointment_id>/status/', views.consultation_status, name='consultation_status'),

    path('consultation/<int:appointment_id>/save-prescription-and-tasks/', views.save_prescription_and_tasks, name='save_prescription_and_tasks'),

    

    # API endpoints (commented for future implementation)

    # path('api/send-otp/', views.send_otp, name='send_otp'),

    # path('api/verify-otp/', views.verify_otp, name='verify_otp'),

    

    # Task and Prescription Management

    path('api/complete-task/<int:task_id>/', views.complete_daily_task, name='complete_daily_task'),

    path('consultation/<int:consultation_id>/save-prescription-tasks/', views.save_prescription_and_tasks, name='save_prescription_and_tasks'),

    path('api/health-task-templates/', views.get_health_task_templates, name='get_health_task_templates'),
    path('api/clear-all-tasks/', views.clear_all_patient_tasks, name='clear_all_patient_tasks'),
    path('api/refresh-tasks/', views.refresh_tasks, name='refresh_tasks'),

    path('api/notifications/', views.check_notifications, name='check_notifications'),

    path('api/notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    path('api/prescription/<int:prescription_id>/details/', views.get_prescription_details, name='get_prescription_details'),

    path('patient/prescription/<int:prescription_id>/download/', views.download_prescription_pdf, name='download_prescription_pdf'),

    

    # Doctor API endpoints

    path('doctor/appointment-details/<int:appointment_id>/', views.appointment_details, name='appointment_details'),

    path('doctor/analytics/', views.analytics, name='doctor_analytics'),

    path('doctor/send-message/', views.send_message, name='send_message'),

    

    # Payment (commented for future implementation)

    # path('payment/process/<int:appointment_id>/', views.process_payment, name='process_payment'),

    # path('payment/success/', views.payment_success, name='payment_success'),

    # path('payment/fail/', views.payment_fail, name='payment_fail'),

]

