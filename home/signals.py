import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import (
    AssessmentQuestion,
    BlogPost,
    Doctor,
    DoctorPrimaryFocus,
    DoctorSchedule,
    DoctorSpecialization,
    HealthTaskTemplate,
)
from .rag_chatbot import ensure_knowledge_base_synced

logger = logging.getLogger(__name__)


NON_CONTENT_UPDATE_FIELDS = {
    BlogPost: {'views_count', 'likes_count'},
}


def refresh_chatbot_knowledge(sender=None, update_fields=None, **_kwargs):
    if update_fields and sender in NON_CONTENT_UPDATE_FIELDS:
        if set(update_fields).issubset(NON_CONTENT_UPDATE_FIELDS[sender]):
            return

    try:
        ensure_knowledge_base_synced(force=True)
    except Exception:
        logger.exception('Unable to refresh chatbot knowledge after content change.')


for model in (
    AssessmentQuestion,
    BlogPost,
    Doctor,
    DoctorPrimaryFocus,
    DoctorSchedule,
    DoctorSpecialization,
    HealthTaskTemplate,
):
    post_save.connect(refresh_chatbot_knowledge, sender=model, weak=False)
    post_delete.connect(refresh_chatbot_knowledge, sender=model, weak=False)


@receiver(m2m_changed, sender=Doctor.specializations.through)
@receiver(m2m_changed, sender=Doctor.primary_focuses.through)
def refresh_doctor_relation_knowledge(action, **_kwargs):
    if action in {'post_add', 'post_remove', 'post_clear'}:
        refresh_chatbot_knowledge()
