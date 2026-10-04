from django.db.models import Count, Q
from rest_framework import serializers

from apps.submissions.status import ACCEPTED

from .difficulty import recommend_difficulty
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
    # 历史表现（通过率 / 难度建议）只随教师序列化器暴露，学生序列化器不含该字段
    history = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = '__all__'
        read_only_fields = ('teacher', 'created_at')

    def get_history(self, obj):
        """题目历史表现：通过率与难度建议。

        优先复用列表接口的聚合注解（避免逐题查询）；直接实例化（例如创建后回包）
        时回退为一次聚合查询。
        """
        if hasattr(obj, 'total_submissions'):
            total = obj.total_submissions or 0
            accepted = obj.accepted_submissions or 0
            attempted = obj.attempted_students or 0
            passed = obj.passed_students or 0
        else:
            stats = obj.submissions.filter(
                student__user_type='student'
            ).aggregate(
                total=Count('id'),
                accepted=Count('id', filter=Q(execution_status=ACCEPTED)),
                attempted=Count('student', distinct=True),
                passed=Count(
                    'student',
                    filter=Q(execution_status=ACCEPTED),
                    distinct=True,
                ),
            )
            total = stats['total'] or 0
            accepted = stats['accepted'] or 0
            attempted = stats['attempted'] or 0
            passed = stats['passed'] or 0

        recommendation = recommend_difficulty(
            attempted_students=attempted, passed_students=passed
        )
        return {
            'total_submissions': total,
            'accepted_submissions': accepted,
            'attempted_students': attempted,
            'passed_students': passed,
            # 提交通过率（ACCEPTED 提交 / 总提交）
            'pass_rate': round(accepted / total, 4) if total else 0.0,
            # 学生通过率（至少通过一次的学生 / 尝试过的学生），难度建议以此为准
            'student_pass_rate': round(passed / attempted, 4) if attempted else 0.0,
            **recommendation,
        }


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
