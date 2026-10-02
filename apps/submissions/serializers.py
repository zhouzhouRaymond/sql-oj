from rest_framework import serializers
from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    """提交详情：包含 submitted_sql 与判题用例明细（前端点开详情时按需懒加载）"""
    # 展示用用户名（自定义用户名，为空时后端回退为登录名）
    student_name = serializers.CharField(source='student.name', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_desc = serializers.CharField(source='question.description', read_only=True)
    # 判题用例明细：只回显「未通过的用例」（序号 + 实际输出 + 错误信息）。
    # 刻意不返回用例输入与预期输出，避免泄露隐藏用例答案。
    judge_details = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = '__all__'
        read_only_fields = (
            'student', 'submission_time', 'execution_status', 'score', 'judge_details'
        )

    def get_judge_details(self, obj):
        raw = obj.judge_details if isinstance(obj.judge_details, dict) else {}
        cases = raw.get('cases') if isinstance(raw.get('cases'), list) else []
        failed_cases = [
            {
                'index': int(case.get('test_case_id') or 0) + 1,  # 前端按 1 开始显示
                'actual_output': case.get('actual_output') or '',
                'error_message': case.get('error_message') or '',
            }
            for case in cases
            if not case.get('passed', False)
        ]
        return {
            'total': len(cases),
            'passed_count': len(cases) - len(failed_cases),
            'failed_cases': failed_cases,
            'error_message': raw.get('error_message') or '',
        }


class SubmissionListSerializer(serializers.ModelSerializer):
    """提交列表：不返回体积较大的 submitted_sql，需要时再按 id 请求详情"""
    # 展示用用户名（自定义用户名，为空时后端回退为登录名）
    student_name = serializers.CharField(source='student.name', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_desc = serializers.CharField(source='question.description', read_only=True)

    class Meta:
        model = Submission
        fields = (
            'id', 'student', 'student_name', 'question', 'question_title', 'question_desc',
            'exam', 'execution_status', 'score', 'submission_time',
        )
        read_only_fields = (
            'student', 'submission_time', 'execution_status', 'score'
        )
