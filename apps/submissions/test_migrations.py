"""可交付性守卫：迁移齐全、系统检查无告警。"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class ProjectHealthTests(TestCase):
    def test_no_missing_migrations(self):
        """模型改了却忘了 makemigrations 时，部署会缺表——这里直接拦住。"""
        try:
            call_command(
                'makemigrations', '--check', '--dry-run',
                verbosity=0, interactive=False, stdout=StringIO(),
            )
        except SystemExit as exc:  # pragma: no cover - 仅在漏迁移时触发
            self.fail(f'存在未生成的迁移，请运行 makemigrations（exit={exc.code}）')

    def test_system_check_has_no_issues(self):
        call_command('check', verbosity=0, stdout=StringIO())
