"""把仍处于待判题（PENDING）状态的提交重新入队。

判题在进程内后台线程执行，进程重启会丢失队列中的任务，这些提交会停留在
``PENDING``。部署重启后可执行本命令把它们重新判一次：

    python manage.py requeue_pending
"""
from django.core.management.base import BaseCommand

from apps.submissions.judging import JudgeQueueFull, PENDING, enqueue_judge
from apps.submissions.models import Submission


class Command(BaseCommand):
    help = '重新入队仍处于 PENDING 的提交'

    def handle(self, *args, **options):
        submission_ids = list(
            Submission.objects.filter(execution_status=PENDING).values_list('id', flat=True)
        )
        if not submission_ids:
            self.stdout.write('没有待重新入队的提交')
            return

        requeued = 0
        for submission_id in submission_ids:
            try:
                enqueue_judge(submission_id)
                requeued += 1
            except JudgeQueueFull:
                self.stderr.write(self.style.WARNING('判题队列已满，停止入队'))
                break

        self.stdout.write(
            self.style.SUCCESS(f'已重新入队 {requeued}/{len(submission_ids)} 条提交')
        )
