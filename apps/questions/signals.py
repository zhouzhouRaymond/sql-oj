"""题目/用例变更时失效判题元数据缓存。"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate
from .models import Question, TestCase


@receiver([post_save, post_delete], sender=Question)
def _invalidate_question_cache(sender, instance, **kwargs):
    invalidate(instance.pk)


@receiver([post_save, post_delete], sender=TestCase)
def _invalidate_testcase_cache(sender, instance, **kwargs):
    invalidate(instance.question_id)
