from rest_framework import serializers
from .models import Submission


class SubmissionSerializer(serializers.ModelSerializer):
    """提交详情：包含 submitted_sql 与判题用例明细（前端点开详情时按需懒加载）"""
    # 展示用用户名（自定义用户名，为空时后端回退为登录名）与登录名
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_desc = serializers.CharField(source='question.description', read_only=True)
    # 考试名称：列表 / 详情都直接给出可读标题，前端不必再按 id 反查；
    # 练习提交（不属于任何考试）为 None，前端据此回退显示「练习」。
    exam_title = serializers.CharField(source='exam.title', read_only=True, allow_null=True)
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

        # 是否需要一并返回失败用例的「测试输入 / 预期输出」：
        # - 教师始终可见（题目本来就是教师自己出的）；
        # - 学生仅在题目开启 show_case_details 开关时可见（默认关闭，避免泄露答案）
        request = self.context.get('request')
        is_teacher = bool(
            request and getattr(request.user, 'user_type', '') == 'teacher'
        )
        show_case_data = is_teacher or bool(
            getattr(obj.question, 'show_case_details', False)
        )
        # 用例按 id 升序排列，与判题时下发的顺序一致（test_case_id 即其下标）
        test_cases = (
            list(obj.question.test_cases.order_by('id')) if show_case_data else []
        )

        failed_cases = []
        for case in cases:
            if case.get('passed', False):
                continue
            idx = int(case.get('test_case_id') or 0)
            item = {
                'index': idx + 1,  # 前端按 1 开始显示
                'actual_output': case.get('actual_output') or '',
                'error_message': case.get('error_message') or '',
            }
            if show_case_data and 0 <= idx < len(test_cases):
                item['test_input'] = test_cases[idx].test_input or ''
                item['expected_output'] = test_cases[idx].expected_output or ''
            failed_cases.append(item)
        # 答对（ACCEPTED）时额外返回各用例的实际输出，供前端直接展示运行结果；
        # 未通过时不返回，避免提前泄露隐藏用例对应的结果数据。
        case_outputs = []
        if obj.execution_status == 'ACCEPTED':
            case_outputs = [
                {'index': idx + 1, 'actual_output': case.get('actual_output') or ''}
                for idx, case in enumerate(cases)
            ]

        return {
            'total': len(cases),
            'passed_count': len(cases) - len(failed_cases),
            'failed_cases': failed_cases,
            'case_outputs': case_outputs,
            'error_message': raw.get('error_message') or '',
        }


class SubmissionListSerializer(serializers.ModelSerializer):
    """提交列表：不返回体积较大的 submitted_sql，需要时再按 id 请求详情"""
    # 展示用用户名（自定义用户名，为空时后端回退为登录名）与登录名
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_desc = serializers.CharField(source='question.description', read_only=True)
    # 考试名称（练习提交为 None），供前端「来源」列直接显示标题
    exam_title = serializers.CharField(source='exam.title', read_only=True, allow_null=True)

    class Meta:
        model = Submission
        fields = (
            'id', 'student', 'student_name', 'student_username',
            'question', 'question_title', 'question_desc',
            'exam', 'exam_title', 'execution_status', 'score', 'submission_time',
        )
        read_only_fields = (
            'student', 'submission_time', 'execution_status', 'score'
        )
