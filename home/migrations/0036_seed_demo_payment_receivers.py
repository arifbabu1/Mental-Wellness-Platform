from django.db import migrations


DEMO_RECEIVERS = [
    {
        'payment_method': 'bkash',
        'account_name': 'Demo bKash Receiver',
        'merchant_number': '01710000001',
        'is_default': True,
        'instructions': 'Use this demo bKash receiver for test booking confirmation only.',
    },
    {
        'payment_method': 'nagad',
        'account_name': 'Demo Nagad Receiver',
        'merchant_number': '01710000002',
        'is_default': True,
        'instructions': 'Use this demo Nagad receiver for test booking confirmation only.',
    },
    {
        'payment_method': 'card',
        'account_name': 'Demo Card Receiver',
        'card_processor_name': 'Demo Card Gateway',
        'card_receiver_account': 'DEMO-CARD-SETTLEMENT',
        'is_default': True,
        'instructions': 'Use this demo card receiver for test booking confirmation only.',
    },
]


def seed_demo_payment_receivers(apps, schema_editor):
    PaymentReceiverAccount = apps.get_model('home', 'PaymentReceiverAccount')

    for receiver in DEMO_RECEIVERS:
        account, _created = PaymentReceiverAccount.objects.update_or_create(
            payment_method=receiver['payment_method'],
            account_name=receiver['account_name'],
            defaults={
                'merchant_number': receiver.get('merchant_number', ''),
                'card_processor_name': receiver.get('card_processor_name', ''),
                'card_receiver_account': receiver.get('card_receiver_account', ''),
                'instructions': receiver.get('instructions', ''),
                'is_active': True,
                'is_default': receiver.get('is_default', True),
            },
        )
        if receiver.get('is_default', True):
            PaymentReceiverAccount.objects.filter(
                payment_method=receiver['payment_method'],
                is_default=True,
            ).exclude(pk=account.pk).update(is_default=False)


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0035_seed_core_assessment_questions'),
    ]

    operations = [
        migrations.RunPython(
            seed_demo_payment_receivers,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
