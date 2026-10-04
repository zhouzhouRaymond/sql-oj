"""判题服务 HTTP 客户端（judge.py）单元测试，不依赖数据库与真实判题服务。"""
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from . import judge
from .judge import (
    JudgeTransportError,
    _build_payload,
    judge_submission,
    judge_submission_strict,
)


def _response(json_data=None, raise_error=None, json_error=None):
    response = Mock()
    if raise_error is not None:
        response.raise_for_status.side_effect = raise_error
    if json_error is not None:
        response.json.side_effect = json_error
    elif json_data is not None:
        response.json.return_value = json_data
    return response


class JudgePayloadTests(SimpleTestCase):
    def test_formats_cases_and_drops_unknown_fields(self):
        payload = _build_payload(
            'select 1',
            [{'test_input': 'x', 'expected_output': 'y', 'internal_note': 'drop'}],
            'CREATE TABLE t (id INT);',
        )
        self.assertEqual(payload['submitted_sql'], 'select 1')
        self.assertEqual(
            payload['test_cases'], [{'expected_output': 'y', 'test_input': 'x'}]
        )
        self.assertEqual(payload['create_table_sql'], 'CREATE TABLE t (id INT);')

    def test_missing_case_fields_default_to_empty_strings(self):
        payload = _build_payload('select 1', [{}], '')
        self.assertEqual(payload['test_cases'], [{'expected_output': '', 'test_input': ''}])

    def test_timeout_is_clamped_by_http_and_sql_limits(self):
        with patch.object(judge, 'JUDGE_HTTP_TIMEOUT', 35), patch.object(
            judge, 'JUDGE_MAX_SQL_TIMEOUT', 60
        ):
            self.assertEqual(_build_payload('select 1', [{}], '')['timeout'], 30)
        with patch.object(judge, 'JUDGE_HTTP_TIMEOUT', 100), patch.object(
            judge, 'JUDGE_MAX_SQL_TIMEOUT', 5
        ):
            self.assertEqual(_build_payload('select 1', [{}], '')['timeout'], 5)
        with patch.object(judge, 'JUDGE_HTTP_TIMEOUT', 3), patch.object(
            judge, 'JUDGE_MAX_SQL_TIMEOUT', 60
        ):
            self.assertEqual(_build_payload('select 1', [{}], '')['timeout'], 1)


class JudgeClientTests(SimpleTestCase):
    def test_strict_client_posts_to_configured_url(self):
        with patch(
            'apps.submissions.judge.requests.post',
            return_value=_response({'passed': True, 'execution_status': 'ACCEPTED'}),
        ) as post:
            result = judge_submission_strict('select 1', [{'expected_output': 'x'}], '')

        self.assertEqual(result['execution_status'], 'ACCEPTED')
        args, kwargs = post.call_args
        self.assertEqual(args[0], judge.JUDGE_SERVICE_URL)
        self.assertIn('json', kwargs)
        self.assertEqual(kwargs['timeout'], judge.JUDGE_HTTP_TIMEOUT)

    def test_transport_failures_raise_transport_error(self):
        cases = {
            'timeout': requests.Timeout('timed out'),
            'connection': requests.ConnectionError('refused'),
            'http': requests.HTTPError('500'),
        }
        for name, exc in cases.items():
            with self.subTest(failure=name):
                with patch(
                    'apps.submissions.judge.requests.post',
                    return_value=_response(raise_error=exc),
                ):
                    with self.assertRaises(JudgeTransportError):
                        judge_submission_strict('select 1', [], '')

    def test_invalid_json_raises_transport_error(self):
        with patch(
            'apps.submissions.judge.requests.post',
            return_value=_response(json_error=ValueError('not json')),
        ):
            with self.assertRaises(JudgeTransportError):
                judge_submission_strict('select 1', [], '')

    def test_compatible_client_degrades_to_timeout_result(self):
        with patch(
            'apps.submissions.judge.requests.post',
            side_effect=requests.ConnectionError('refused'),
        ):
            result = judge_submission('select 1', [], '')

        self.assertFalse(result['passed'])
        self.assertEqual(result['execution_status'], 'TIMEOUT')
        self.assertEqual(result['score'], 0)

    def test_compatible_client_returns_parsed_json(self):
        with patch(
            'apps.submissions.judge.requests.post',
            return_value=_response({'passed': False, 'execution_status': 'WRONG_ANSWER'}),
        ):
            result = judge_submission('select 1', [], '')

        self.assertEqual(result['execution_status'], 'WRONG_ANSWER')
