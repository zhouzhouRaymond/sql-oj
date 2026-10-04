"""提交判题三级限流的缓存键测试，不依赖数据库。"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .throttles import (
    SubmitGlobalThrottle,
    SubmitQuestionThrottle,
    SubmitUserThrottle,
)


class SubmitThrottleKeyTests(SimpleTestCase):
    def test_user_throttle_keys_by_user_id(self):
        request = SimpleNamespace(user=SimpleNamespace(pk=3, is_authenticated=True))
        key = SubmitUserThrottle().get_cache_key(request, view=None)
        self.assertEqual(key, 'throttle_submit_user_3')

    def test_question_throttle_keys_by_question_and_user(self):
        request = SimpleNamespace(
            data={'question_id': 5},
            user=SimpleNamespace(pk=3, is_authenticated=True),
        )
        key = SubmitQuestionThrottle().get_cache_key(request, view=None)
        self.assertEqual(key, 'throttle_submit_question_5:3')

    def test_question_throttle_without_question_id_is_unlimited(self):
        request = SimpleNamespace(
            data={},
            user=SimpleNamespace(pk=3, is_authenticated=True),
        )
        self.assertIsNone(SubmitQuestionThrottle().get_cache_key(request, view=None))

    def test_question_throttle_survives_broken_request_body(self):
        broken_data = SimpleNamespace(get=SimpleNamespace(side_effect=ValueError('bad body')))
        request = SimpleNamespace(
            data=broken_data,
            user=SimpleNamespace(pk=3, is_authenticated=True),
        )
        self.assertIsNone(SubmitQuestionThrottle().get_cache_key(request, view=None))

    def test_global_throttle_uses_single_bucket(self):
        key = SubmitGlobalThrottle().get_cache_key(request=None, view=None)
        self.assertEqual(key, 'throttle_submit_global_global')

    def test_question_throttle_falls_back_to_client_ip_for_anonymous(self):
        request = SimpleNamespace(
            data={'question_id': 5},
            user=SimpleNamespace(pk=None, is_authenticated=False),
            META={'REMOTE_ADDR': '10.0.0.1'},
        )
        with patch.object(SubmitQuestionThrottle, 'get_ident', return_value='10.0.0.1'):
            key = SubmitQuestionThrottle().get_cache_key(request, view=None)
        self.assertEqual(key, 'throttle_submit_question_5:10.0.0.1')
