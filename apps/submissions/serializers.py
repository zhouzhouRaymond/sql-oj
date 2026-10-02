from rest_framework import serializers
from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    """提交详情：包含 submitted_sql（前端点开详情时按需懒加载）"""
    # 展示用用户名（自定义用户名，为空时后端回退为登录名）
    student_name = serializers.CharField(source='student.name', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_desc = serializers.CharField(source='question.description', read_only=True)

    class Meta:
        model = Submission
        fields = '__all__'
        read_only_fields = (
            'student', 'submission_time', 'execution_status', 'score'
        )


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
