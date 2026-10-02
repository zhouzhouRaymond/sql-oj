"""把「作答截止时间已过但从未交卷」的考生按最后同步的草稿兜底交卷。

前端倒计时到点会自动交卷，但如果学生提前关掉浏览器（或断网），这一次作答就
不会产生提交记录。视图在 `start` / 排名 / 导出 / 我的得分 等入口会「懒执行」
兜底，本命令用于手动或运维统一兜底（例如考试刚结束时跑一遍）：

    python manage.py finalize_expired_exams
    python manage.py finalize_expired_exams --exam 3
"""
from django.core.management.base import BaseCommand

from apps.exams.services import finalize_expired_attempts


class Command(BaseCommand):
    help = '把到点未交卷但已同步过作答草稿的考生按草稿兜底交卷'

    def add_arguments(self, parser):
        parser.add_argument(
            '--exam', type=int, default=None, help='只处理指定考试 id（可选）',
        )

    def handle(self, *args, **options):
        exam_id = options.get('exam')
        exam = None
        if exam_id:
            from apps.exams.models import Exam

            exam = Exam.objects.filter(id=exam_id).first()
            if exam is None:
                self.stderr.write(self.style.ERROR(f'考试 {exam_id} 不存在'))
                return

        finalized = finalize_expired_attempts(exam=exam)
        if not finalized:
            self.stdout.write('没有需要兜底交卷的考生')
            return

        for attempt in finalized:
            self.stdout.write(
                f'已兜底交卷：{attempt.exam.title} / {attempt.student.name}'
            )
        self.stdout.write(self.style.SUCCESS(f'已兜底交卷 {len(finalized)} 人'))
