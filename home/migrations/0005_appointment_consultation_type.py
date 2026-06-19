# Generated migration for consultation_type field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0004_alter_appointment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='consultation_type',
            field=models.CharField(
                choices=[('video', 'Video Consultation'), ('phone', 'Phone Consultation'), ('in_person', 'In Person')],
                default='video',
                max_length=15
            ),
        ),
    ]
