from datetime import time, timedelta
import logging

from django.db import transaction
from django.utils import timezone

from .models import DailyTask, TaskCompletion


logger = logging.getLogger(__name__)
COMPLETION_START_TIME = time(5, 0)
COMPLETION_END_TIME = time(19, 0)


def _parse_positive_int(value, fallback):
    if isinstance(value, str):
        value = value.strip().split()[0] if value.strip() else value
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def _normalize_priority(value):
    priority = (value or 'medium').strip().lower()
    if priority not in {'low', 'medium', 'high'}:
        return 'medium'
    return priority


def normalize_task_payload(task_data, default_start=None):
    default_start = default_start or timezone.localdate()
    title = (task_data.get('title') or task_data.get('task_name') or '').strip()
    if not title:
        return None

    duration_days = _parse_positive_int(
        task_data.get('duration') or task_data.get('duration_days') or 7,
        7,
    )
    start_date = default_start
    end_date = start_date + timedelta(days=duration_days - 1)

    return {
        'title': title,
        'description': task_data.get('description', ''),
        'category': task_data.get('category', 'mental') or 'mental',
        'icon': task_data.get('icon', 'fas fa-tasks') or 'fas fa-tasks',
        'source': task_data.get('source', 'custom') or 'custom',
        'start_date': start_date,
        'end_date': end_date,
        'duration_days': duration_days,
        'priority': _normalize_priority(task_data.get('priority')),
        'frequency': task_data.get('frequency', 'daily') or 'daily',
        'recurring_days': task_data.get('recurring_days', []),
        'reminder_times': task_data.get('reminder_times', []),
    }


@transaction.atomic
def replace_active_daily_tasks(patient, doctor, consultation, tasks_data, prescription=None):
    """Deactivate a patient's previous active tasks and create the latest consultation tasks."""

    deactivated_count = DailyTask.objects.filter(patient=patient, is_active=True).update(
        is_active=False,
        updated_at=timezone.now(),
    )

    created_tasks = []
    if isinstance(tasks_data, dict):
        task_items = [tasks_data]
    elif isinstance(tasks_data, list):
        task_items = tasks_data
    else:
        task_items = []

    for raw_task in task_items:
        if not isinstance(raw_task, dict):
            continue
        normalized = normalize_task_payload(raw_task)
        if not normalized:
            continue
        task = DailyTask.objects.create(
            patient=patient,
            doctor=doctor,
            consultation=consultation,
            prescription=prescription,
            is_active=True,
            **normalized,
        )
        logger.debug(
            "CREATED DAILY TASK: %s %s %s %s %s %s",
            task.id,
            task.title,
            task.patient,
            task.is_active,
            task.start_date,
            task.end_date,
        )
        created_tasks.append(task)

    return {
        'deactivated_count': deactivated_count,
        'created_tasks': created_tasks,
        'created_count': len(created_tasks),
    }


def get_today_task_items(patient, today=None):
    today = today or timezone.localdate()
    active_tasks = (
        DailyTask.objects
        .filter(
            patient=patient,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related('doctor__user')
        .order_by('created_at', 'id')
    )
    task_items = []

    for task in active_tasks:
        completion = (
            TaskCompletion.objects
            .filter(daily_task=task, completion_date=today)
            .order_by('-is_completed', '-completed_at')
            .first()
        )
        if completion and not completion.patient_id:
            completion.patient = patient
            completion.save(update_fields=['patient'])
        task_items.append({'task': task, 'completion': completion})

    return task_items


@transaction.atomic
def mark_task_completed(patient, task, notes=''):
    if not task.is_active or task.patient_id != patient.id or not task.is_today:
        raise DailyTask.DoesNotExist

    today = timezone.localdate()
    completion = TaskCompletion.objects.filter(daily_task=task, completion_date=today).first()
    created = False
    if not completion:
        completion = TaskCompletion.objects.create(
            patient=patient,
            daily_task=task,
            completion_date=today,
            is_completed=False,
        )
        created = True
    elif not completion.patient_id:
        completion.patient = patient

    if completion.is_completed:
        return completion, created, False

    now = timezone.localtime()
    completion.patient = patient
    completion.is_completed = True
    completion.completed_at = timezone.now()
    completion.completion_time = now.time()
    completion.patient_notes = notes
    completion.save()
    return completion, created, True


def incomplete_active_tasks_by_user(today=None):
    today = today or timezone.localdate()
    user_tasks = {}
    active_tasks = (
        DailyTask.objects
        .filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related('patient')
        .order_by('patient_id', 'title')
    )

    for task in active_tasks:
        if task.patient_id not in user_tasks:
            user_tasks[task.patient_id] = {'user': task.patient, 'tasks': []}
        user_tasks[task.patient_id]['tasks'].append(task)

    incomplete = {}
    for patient_id, data in user_tasks.items():
        task_ids = [task.id for task in data['tasks']]
        completed_ids = set(
            TaskCompletion.objects.filter(
                daily_task_id__in=task_ids,
                completion_date=today,
                is_completed=True,
            ).values_list('daily_task_id', flat=True)
        )
        missing = [task for task in data['tasks'] if task.id not in completed_ids]
        if missing:
            incomplete[patient_id] = {'user': data['user'], 'tasks': missing}

    return incomplete


def is_after_completion_window(now=None):
    now = timezone.localtime(now or timezone.now())
    return now.time() >= COMPLETION_END_TIME
