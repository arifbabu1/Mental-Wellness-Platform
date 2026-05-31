from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0015_alter_doctor_specialty'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='age',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[
                    ('male', 'Male'),
                    ('female', 'Female'),
                    ('other', 'Other'),
                    ('prefer_not_to_say', 'Prefer not to say'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='doctor',
            name='availability_score',
            field=models.PositiveSmallIntegerField(default=5, help_text='Availability score (0-5, 5 = available within 2 days)'),
        ),
        migrations.AddField(
            model_name='patientassessment',
            name='dynamic_responses',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='patientassessment',
            name='result_summary',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='assessmentquestion',
            name='category',
            field=models.CharField(
                choices=[
                    ('Depression', 'Depression'),
                    ('Anxiety', 'Anxiety'),
                    ('Sleep', 'Sleep'),
                    ('Energy', 'Energy'),
                    ('Self-esteem', 'Self-esteem'),
                ],
                max_length=100,
            ),
        ),
    ]
