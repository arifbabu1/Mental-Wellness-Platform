# wellness_platform/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from home import admin_views

urlpatterns = [
    # Custom admin URLs (must come before Django admin)
    path('admin/dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', admin_views.users_detail, name='users_detail'),
    path('admin/doctors/', admin_views.doctors_detail, name='doctors_detail'),
    path('admin/doctors/toggle-availability/<int:doctor_id>/', admin_views.toggle_doctor_availability, name='toggle_doctor_availability'),
    path('admin/appointments/', admin_views.appointments_detail, name='appointments_detail'),
    path('admin/assessments/', admin_views.assessments_detail, name='assessments_detail'),
    path('admin/assessment-questions/', admin_views.assessment_questions_manage, name='assessment_questions_manage'),
    path('admin/assessment-questions/add/', admin_views.assessment_question_add, name='assessment_question_add'),
    path('admin/assessment-questions/<int:question_id>/edit/', admin_views.assessment_question_edit, name='assessment_question_edit'),
    path('admin/assessment-questions/<int:question_id>/delete/', admin_views.assessment_question_delete, name='assessment_question_delete'),
    path('admin/financial/', admin_views.admin_payments, name='admin_payments'),
    # Django admin URLs
    path('admin/', admin.site.urls),
    # Main app URLs
    path('', include('home.urls')),
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
