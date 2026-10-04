from rest_framework import serializers
from .models import Question, Answer, TestCase


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ('id', 'correct_sql')


class TestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCase
        fields = ('id', 'test_input', 'expected_output', 'expected_schema', 'probes')


class QuestionSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, read_only=True)
    test_cases = TestCaseSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = '__all__'
        read_only_fields = ('teacher', 'created_at')


class QuestionStudentSerializer(serializers.ModelSerializer):
    """学生视角：不暴露参考答案、建表语句与隐藏测试用例。

    注意：隐藏测试用例的 expected_output 绝不能返回给学生，
    否则可以直接照着预期输出硬编码答案，判题形同虚设。
    """

    class Meta:
        model = Question
        fields = (
            'id', 'title', 'description', 'difficulty', 'sample_input',
            'sample_output', 'teacher', 'created_at',
        )
        read_only_fields = ('teacher', 'created_at')
