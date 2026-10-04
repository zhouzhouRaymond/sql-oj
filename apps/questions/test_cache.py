"""题目判题元数据缓存测试。"""
from django.core.cache import cache
from django.test import TestCase as DjangoTestCase

from apps.users.models import User

from .cache import bundle_key, get_bundle
from .models import Question, TestCase as QuestionTestCase


class QuestionBundleCacheTests(DjangoTestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_qcache', password='pass1234', user_type='teacher',
        )
        self.question = Question.objects.create(
            description='缓存题', difficulty='easy', teacher=self.teacher,
            create_table_sql='CREATE TABLE t (id INT);',
        )
        QuestionTestCase.objects.create(
            question=self.question, test_input='', expected_output='id\n1',
        )

    def test_bundle_is_cached(self):
        bundle = get_bundle(self.question.id)
        self.assertEqual(bundle['create_table_sql'], 'CREATE TABLE t (id INT);')
        self.assertEqual(len(bundle['test_cases']), 1)
        # 命中缓存：缓存里应存在题目包
        self.assertIsNotNone(cache.get(bundle_key(self.question.id)))

    def test_adding_test_case_invalidates_cache(self):
        get_bundle(self.question.id)  # 先填充缓存
        QuestionTestCase.objects.create(
            question=self.question, test_input='', expected_output='id\n2',
        )
        # 信号应已失效缓存，重新取到 2 个用例
        self.assertEqual(len(get_bundle(self.question.id)['test_cases']), 2)

    def test_cached_bundle_avoids_extra_queries(self):
        get_bundle(self.question.id)  # 预热缓存
        with self.assertNumQueries(0):
            bundle = get_bundle(self.question.id)
        self.assertEqual(len(bundle['test_cases']), 1)
