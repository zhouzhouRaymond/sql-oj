from rest_framework import serializers
from .models import Exam, ExamQuestion
from apps.users.models import User


class ExamQuestionSerializer(serializers.ModelSerializer):
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_id = serializers.IntegerField(source='question.id', read_only=True)

    class Meta:
        model = ExamQuestion
        fields = ('id', 'question', 'question_id', 'question_title', 'score')


class ExamSerializer(serializers.ModelSerializer):
    exam_questions = ExamQuestionSerializer(many=True, read_only=True)
    student_ids = serializers.PrimaryKeyRelatedField(
        source='students', many=True, queryset=User.objects.filter(user_type='student'),
        required=False, write_only=True
    )
    # 创建人（展示用）：考试由全体教师共享，列表需要显示是谁创建的
    teacher_name = serializers.SerializerMethodField()
    teacher_username = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = '__all__'
        read_only_fields = ('teacher', 'created_at', 'students')

    def get_teacher_name(self, obj):
        return obj.teacher.name if obj.teacher else ''

    def get_teacher_username(self, obj):
        return obj.teacher.username if obj.teacher else ''

    def validate_student_scope(self, value):
        """兑容前端可能发送的不同值，统一转为后端期望的值"""
        alias_map = {
            'specific': 'specified',
            'selected': 'specified',
            'specified': 'specified',
            'all': 'all',
        }
        normalized = alias_map.get(value)
        if normalized is None:
            raise serializers.ValidationError(
                f'"{value}" 不是合法的选项，可选值: all, specified'
            )
        return normalized

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 返回登录名与自定义用户名（展示名），前端优先显示用户名
        data['students'] = [
            {'id': s.id, 'username': s.username, 'name': s.name}
            for s in instance.students.all()
        ]
        return data
