"""判题结果异步批量回写（result_writer.py）单元测试，不依赖数据库。"""
from unittest.mock import patch

from django.test import SimpleTestCase

from .result_writer import SubmissionResultWriter


class ResultWriterBufferTests(SimpleTestCase):
    def setUp(self):
        # flush_interval 设大、并屏蔽后台线程启动，让缓冲/刷写行为可确定地断言
        self.writer = SubmissionResultWriter(flush_interval=60.0, flush_batch=100)

    def _enqueue(self, submission_id, status, score, details=None):
        with patch.object(self.writer, '_ensure_started'):
            self.writer.enqueue(submission_id, status, score, details or {})

    def test_flush_empty_buffer_returns_zero(self):
        self.assertEqual(self.writer.flush(), 0)

    def test_same_submission_keeps_last_result(self):
        self._enqueue(1, 'PENDING', 0)
        self._enqueue(1, 'ACCEPTED', 100, {'cases': []})

        with patch.object(self.writer, '_write', return_value=1) as write:
            flushed = self.writer.flush()

        self.assertEqual(flushed, 1)
        batch = write.call_args.args[0]
        self.assertEqual(batch[1], ('ACCEPTED', 100, {'cases': []}))

    def test_batch_size_triggers_wakeup(self):
        self.writer._flush_batch = 2
        self._enqueue(1, 'ACCEPTED', 100)
        self.assertFalse(self.writer._wakeup.is_set())
        self._enqueue(2, 'WRONG_ANSWER', 0)
        self.assertTrue(self.writer._wakeup.is_set())

    def test_stop_flushes_pending_results(self):
        self._enqueue(1, 'ACCEPTED', 100)
        with patch.object(self.writer, '_write', return_value=1) as write:
            self.writer.stop()
        write.assert_called_once()

    def test_write_bulk_updates_all_buffered_submissions(self):
        batch = {
            1: ('ACCEPTED', 100, {'cases': []}),
            2: ('WRONG_ANSWER', 0, {'cases': []}),
        }
        with patch('apps.submissions.models.Submission.objects.bulk_update') as bulk:
            written = SubmissionResultWriter._write(batch)

        self.assertEqual(written, 2)
        objects = bulk.call_args.args[0]
        fields = bulk.call_args.args[1]
        self.assertEqual(fields, ['execution_status', 'score', 'judge_details'])
        by_id = {obj.id: obj for obj in objects}
        self.assertEqual(by_id[1].execution_status, 'ACCEPTED')
        self.assertEqual(by_id[1].score, 100)
        self.assertEqual(by_id[2].execution_status, 'WRONG_ANSWER')
