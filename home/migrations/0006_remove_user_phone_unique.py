# Generated migration to remove unique constraint from phone field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0005_appointment_consultation_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(max_length=20),
        ),
    ]
