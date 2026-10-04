from django.apps import AppConfig


class QuestionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.questions'

    def ready(self):
        # 注册题目/用例变更信号，及时失效判题元数据缓存
        from . import signals  # noqa: F401
