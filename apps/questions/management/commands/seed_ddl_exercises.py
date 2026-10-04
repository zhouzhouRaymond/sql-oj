"""把内置的 DDL 练习题库导入系统（schema 判题）。

用法：

    python manage.py seed_ddl_exercises --verify          # 导入并校验参考答案
    python manage.py seed_ddl_exercises --dry-run --verify # 只校验、不写库
    python manage.py seed_ddl_exercises --category relationships
    python manage.py seed_ddl_exercises --reset           # 删除导入的题目

标准答案 DDL 会写入 ``Answer.correct_sql``（与查询题一致，教师端可见），期望结构
则由标准答案经判题服务 ``/introspect`` 生成，因此教师的期望结构与判题引擎的
规范化规则永远一致；``--verify`` 会再用标准答案跑一次判题，要求 ACCEPTED。
"""
import json
import os
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from apps.questions.ddl_exercise_bank import (
    CATEGORIES,
    DDL_EXERCISES,
    supported_exercises,
    validate_bank,
)
from apps.questions.models import Answer, Question, TestCase
from apps.users.models import User

def _default_judge_url() -> str:
    """服务根地址：容器里的 JUDGE_SERVICE_URL 指向 /judge，这里去掉该路径。"""
    raw = os.environ.get('JUDGE_SERVICE_URL', 'http://localhost:8080').rstrip('/')
    if raw.endswith('/judge'):
        raw = raw[: -len('/judge')]
    return raw


DEFAULT_JUDGE_URL = _default_judge_url()


def _post_json(base_url, path, payload, timeout=60):
    request = urllib.request.Request(
        base_url.rstrip('/') + path,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def introspect_reference(base_url, setup_sql, reference_sql):
    """把「前置语句 + 标准答案」交给 /introspect，得到期望结构快照。"""
    combined = '\n'.join(
        part for part in (setup_sql or '', reference_sql or '') if part.strip()
    )
    data = _post_json(base_url, '/introspect', {'sql': combined})
    if data.get('error_message'):
        raise CommandError(f'参考 DDL 内省失败: {data["error_message"]}')
    return data.get('expected_schema') or {}


def verify_reference(base_url, exercise, expected_schema):
    """用标准答案跑一次 schema 判题，返回判题结果。"""
    payload = {
        'mode': 'schema',
        'submitted_sql': exercise['reference_sql'],
        'timeout': 60,
        'test_cases': [{
            'test_input': exercise.get('setup_sql') or '',
            'expected_schema': expected_schema,
            'probes': exercise.get('probes') or [],
        }],
    }
    return _post_json(base_url, '/judge', payload)


class Command(BaseCommand):
    help = '导入内置 DDL 练习题库（schema 判题）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--judge-url', default=DEFAULT_JUDGE_URL,
            help='判题服务地址（默认取 JUDGE_SERVICE_URL）',
        )
        parser.add_argument(
            '--category', choices=sorted(CATEGORIES), help='只导入某个分类',
        )
        parser.add_argument('--limit', type=int, help='最多导入多少道题')
        parser.add_argument('--teacher', help='题目归属教师的登录名（默认第一个教师）')
        parser.add_argument('--hidden', action='store_true', help='导入后对学生隐藏')
        parser.add_argument('--dry-run', action='store_true', help='只生成/校验期望结构，不写库')
        parser.add_argument('--verify', action='store_true', help='用标准答案跑判题，必须 ACCEPTED')
        parser.add_argument('--reset', action='store_true', help='删除本命令导入的题目后退出')

    def handle(self, *args, **options):
        problems = validate_bank()
        if problems:
            raise CommandError('题库校验失败:\n- ' + '\n- '.join(problems))

        if options['reset']:
            titles = [item['title'] for item in DDL_EXERCISES]
            deleted, _ = Question.objects.filter(title__in=titles).delete()
            self.stdout.write(self.style.SUCCESS(f'已删除题库导入的题目（{deleted} 行受影响）'))
            return

        teacher = self._resolve_teacher(options.get('teacher'))
        exercises = supported_exercises()
        if options.get('category'):
            exercises = [e for e in exercises if e['category'] == options['category']]
        if options.get('limit'):
            exercises = exercises[: max(0, options['limit'])]

        skipped = [e for e in DDL_EXERCISES if not e.get('supported', True)]
        if skipped:
            self.stdout.write(self.style.WARNING(
                '跳过暂不支持自动判题的题目：' + ', '.join(e['slug'] for e in skipped)
            ))

        created = updated = 0
        for exercise in exercises:
            expected = introspect_reference(
                options['judge_url'],
                exercise.get('setup_sql', ''),
                exercise['reference_sql'],
            )
            if options.get('verify'):
                result = verify_reference(options['judge_url'], exercise, expected)
                if result.get('execution_status') != 'ACCEPTED':
                    raise CommandError(
                        f"{exercise['slug']} 标准答案未通过判题: "
                        f"{result.get('execution_status')} {result.get('details')}"
                    )

            if options.get('dry_run'):
                table_count = len((expected.get('tables') or {}))
                self.stdout.write(
                    f"[dry-run] {exercise['slug']} 期望结构已生成（{table_count} 张表）"
                )
                continue

            question = Question.objects.filter(title=exercise['title']).first()
            was_created = question is None
            if was_created:
                question = Question.objects.create(
                    title=exercise['title'],
                    description=exercise['description'],
                    difficulty=exercise['difficulty'],
                    teacher=teacher,
                    judge_mode='schema',
                    is_visible=not options.get('hidden'),
                )
            else:
                question.description = exercise['description']
                question.difficulty = exercise['difficulty']
                question.teacher = teacher
                question.judge_mode = 'schema'
                question.is_visible = not options.get('hidden')
                question.save(update_fields=[
                    'description', 'difficulty', 'teacher', 'judge_mode', 'is_visible',
                ])

            # 标准答案写入 Answer.correct_sql（与查询题一致，教师端可见）
            question.answers.all().delete()
            Answer.objects.create(
                question=question, correct_sql=exercise['reference_sql'],
            )

            question.test_cases.all().delete()
            TestCase.objects.create(
                question=question,
                test_input=exercise.get('setup_sql') or '',
                expected_output='',
                expected_schema=expected,
                probes=exercise.get('probes') or [],
            )
            created += int(was_created)
            updated += int(not was_created)
            self.stdout.write(f"导入 {exercise['slug']}: {exercise['title']}")

        if options.get('dry_run'):
            self.stdout.write(self.style.SUCCESS(f'dry-run 完成：校验 {len(exercises)} 道题'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'完成：新增 {created} 题，更新 {updated} 题')
            )

    def _resolve_teacher(self, username):
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'教师账号不存在: {username}')
        teacher = User.objects.filter(user_type='teacher').order_by('id').first()
        if teacher is None:
            raise CommandError('系统里没有教师账号，请用 --teacher 指定或先创建教师')
        return teacher
