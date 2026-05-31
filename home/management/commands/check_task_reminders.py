from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from home.models import DailyTaskReminderLog, Notification
from home.system_config import send_configured_mail
from home.task_services import incomplete_active_tasks_by_user, is_after_completion_window


class Command(BaseCommand):
    help = 'Send end-of-day email reminders for incomplete active daily tasks.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Run even before the 7:00 PM completion window closes.',
        )
        parser.add_argument(
            '--date',
            help='Check a specific date in YYYY-MM-DD format. Defaults to today in the project timezone.',
        )

    def handle(self, *args, **options):
        check_date = self._get_check_date(options.get('date'))
        if not options.get('force') and not is_after_completion_window():
            self.stdout.write('Daily task reminder check skipped: it is before 7:00 PM.')
            return

        incomplete_by_user = incomplete_active_tasks_by_user(check_date)
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for patient_data in incomplete_by_user.values():
            user = patient_data['user']
            tasks = patient_data['tasks']
            if not user or not user.email:
                skipped_count += 1
                self.stdout.write(f'Skipped {getattr(user, "username", "unknown user")}: missing email address.')
                continue

            task_titles = [task.title for task in tasks]
            log = None
            try:
                with transaction.atomic():
                    log = DailyTaskReminderLog.objects.create(
                        user=user,
                        date=check_date,
                        incomplete_tasks_count=len(task_titles),
                        incomplete_task_titles=task_titles,
                    )
            except IntegrityError:
                skipped_count += 1
                self.stdout.write(f'Skipped {user.username}: reminder already sent for {check_date}.')
                continue

            try:
                self._send_incomplete_task_email(user, task_titles, check_date)
            except Exception as exc:
                failed_count += 1
                if log:
                    log.delete()
                self.stderr.write(f'Failed to send reminder to {user.email}: {exc}')
                continue

            Notification.objects.create(
                user=user,
                title='Incomplete Daily Tasks',
                message=f'You have {len(task_titles)} incomplete daily wellness task(s) for {check_date}.',
                notification_type='task_incomplete',
                is_actionable=True,
                action_url='/patient/dashboard/',
            )
            sent_count += 1
            self.stdout.write(f'Sent incomplete task reminder to {user.email}.')

        self.stdout.write(
            self.style.SUCCESS(
                f'Daily task reminder check complete: {sent_count} sent, {skipped_count} skipped, {failed_count} failed.'
            )
        )

    def _get_check_date(self, date_value):
        if not date_value:
            return timezone.localdate()
        try:
            return datetime.strptime(date_value, '%Y-%m-%d').date()
        except ValueError as exc:
            raise CommandError('Use --date in YYYY-MM-DD format.') from exc

    def _send_incomplete_task_email(self, user, task_titles, check_date):
        display_name = user.get_full_name() or user.username
        task_list = '\n'.join(f'- {title}' for title in task_titles)
        message = (
            f'Dear {display_name},\n\n'
            'You had the following daily wellness tasks today:\n'
            f'{task_list}\n\n'
            'You have not completed these tasks yet. Please complete your daily wellness tasks as soon as possible '
            'to continue your wellness progress.\n\n'
            'Thank you,\n'
            'Mental Wellness Platform Team'
        )
        subject = f'Daily wellness task reminder - {check_date.strftime("%B %d, %Y")}'
        send_configured_mail(subject, message, [user.email], fail_silently=False)
