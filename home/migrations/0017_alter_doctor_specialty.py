from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0016_rule_based_recommendations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='doctor',
            name='specialty',
            field=models.CharField(
                choices=[
                    ('Psychiatrist', 'Psychiatrist'),
                    ('Clinical Psychologist', 'Clinical Psychologist'),
                    ('Therapist', 'Therapist'),
                    ('Counselor', 'Counselor'),
                    ('Child Psychiatrist', 'Child Psychiatrist'),
                    ('Child Psychologist', 'Child Psychologist'),
                    ('Geriatric Psychologist', 'Geriatric Psychologist'),
                    ('Addiction Specialist', 'Addiction Specialist'),
                    ('Marriage and Family Therapist', 'Marriage and Family Therapist'),
                    ('Neuropsychiatrist', 'Neuropsychiatrist'),
                    ('Neuropsychologist', 'Neuropsychologist'),
                ],
                max_length=50,
            ),
        ),
    ]
