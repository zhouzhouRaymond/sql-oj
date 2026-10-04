from django.conf import settings
from rest_framework import filters, generics, viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken, OutstandingToken,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .auth_cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from .models import User
from .serializers import (
    LoginSerializer, RegisterSerializer, UserAdminSerializer, UserSerializer,
)
from .permissions import IsTeacher
from .throttles import LoginRateThrottle
from apps.submissions.models import Submission
from apps.questions.models import Question
from apps.exams.models import Exam


class RegisterView(generics.CreateAPIView):
    """用户注册 — 公开接口"""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


class LoginView(TokenObtainPairView):
    """登录（签发 JWT + 写入登录 Cookie）。开启单点登录时，新登录会踢掉该账号的旧会话。"""

    serializer_class = LoginSerializer
    # 按来源 IP 限流，缓解密码暴力破解
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh_token = response.data.get('refresh')
        if refresh_token:
            # 登录 Cookie（HttpOnly）：关闭浏览器后，窗口内可免登录自动续期
            set_refresh_cookie(response, refresh_token)
            # 告知前端免登录窗口长度（窗口过期后前端直接要求重新登录）
            response.data['remember_days'] = settings.LOGIN_REMEMBER_DAYS
        return response


class RefreshView(TokenRefreshView):
    """刷新 access token：refresh token 优先取自 HttpOnly 登录 Cookie。

    - 浏览器端：Cookie 自动携带（前端不保存 refresh token），刷新成功后 Cookie 轮换、窗口顺延；
    - 脚本 / 第三方客户端：仍可在请求体里传 ``refresh``；
    - 刷新失败（过期 / 已拉黑 / 已登出）时顺手清掉浏览器上的登录 Cookie。
    """

    def post(self, request, *args, **kwargs):
        try:
            payload = request.data
        except Exception:
            payload = {}
        if not (isinstance(payload, dict) and payload.get('refresh')):
            cookie_token = read_refresh_cookie(request)
            if cookie_token:
                payload['refresh'] = cookie_token
            else:
                # 既没有登录 Cookie 也没有请求体里的 refresh：视为未登录（401）
                response = Response(
                    {'detail': '登录状态已失效，请重新登录', 'code': 'not_authenticated'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
                clear_refresh_cookie(response)
                return response

        try:
            response = super().post(request, *args, **kwargs)
        except Exception as exc:
            # 交给 DRF 生成标准 401 响应，并清掉已失效的登录 Cookie
            response = self.handle_exception(exc)
            clear_refresh_cookie(response)
            return response

        new_refresh = response.data.get('refresh')
        if new_refresh:
            set_refresh_cookie(response, new_refresh)
        response.data['remember_days'] = settings.LOGIN_REMEMBER_DAYS
        return response


class LogoutView(APIView):
    """登出：使该账号已签发的 token 立即失效。

    拉黑所有已签发的 refresh token；开启单点登录时再清空当前会话标识，
    从而让已签发的 access token 也立即失效。
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        if getattr(settings, 'SINGLE_SESSION_ENFORCED', False):
            user.current_session = ''
            user.save(update_fields=['current_session'])
        response = Response({'message': '已退出登录'})
        clear_refresh_cookie(response)   # 同时清掉浏览器上的登录 Cookie
        return response


class UserViewSet(viewsets.ModelViewSet):
    """用户 / 账号管理 ViewSet"""
    # 固定排序，避免分页时顺序不稳定导致列表重复/遗漏
    queryset = User.objects.all().order_by('id')
    serializer_class = UserAdminSerializer
    # 账号管理页支持关键词搜索（登录名 / 用户名 / 邮箱）
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'display_name', 'email']

    def get_serializer_class(self):
        # 自助接口（/users/me/）不允许改角色等敏感字段，避免自行提权
        if self.action == 'me':
            return UserSerializer
        return UserAdminSerializer

    def get_permissions(self):
        # 账号管理相关操作（含新建账号）仅教师可用
        if self.action in (
            'list', 'retrieve', 'create', 'update', 'partial_update', 'destroy',
        ):
            return [permissions.IsAuthenticated(), IsTeacher()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """教师可管理所有账号（学生 + 教师），学生只能看自己"""
        qs = super().get_queryset()
        user = self.request.user
        if user.user_type != 'teacher':
            return qs.filter(id=user.id)
        # 教师：默认返回全部账号，可用 ?user_type=student|teacher 过滤
        user_type = self.request.query_params.get('user_type')
        if user_type in ('student', 'teacher'):
            return qs.filter(user_type=user_type)
        return qs

    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        """查看或修改当前登录用户信息"""
        if request.method == 'GET':
            return Response(self.get_serializer(request.user).data)
        serializer = self.get_serializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='change-password')
    def change_password(self, request):
        """修改当前登录用户密码（需校验原密码）"""
        old_password = request.data.get('old_password') or ''
        new_password = request.data.get('new_password') or ''

        if not old_password or not new_password:
            return Response(
                {'error': '原密码和新密码均为必填'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not request.user.check_password(old_password):
            return Response(
                {'error': '原密码不正确'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if len(new_password) < 6:
            return Response(
                {'error': '新密码至少 6 位'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if new_password == old_password:
            return Response(
                {'error': '新密码不能与原密码相同'},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])

        # 安全增强：把该用户已签发的 refresh token 全部拉黑，
        # 使其在过期前也不能再换取新的 access token（配合 CHECK_REVOKE_TOKEN，
        # 旧的 access token 同样会因密码哈希声明不匹配而立即失效）。
        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)

        return Response({'message': '密码修改成功，请使用新密码重新登录'})

    @action(detail=False, methods=['get'], url_path='me/stats')
    def my_stats(self, request):
        """当前用户的个人统计数据"""
        user = request.user

        if user.user_type == 'teacher':
            # 教师：统计自己创建的题目和考试数量
            total_submissions = Submission.objects.count()
            return Response({
                'username': user.username,
                'display_name': user.display_name,
                'name': user.name,
                'user_type': 'teacher',
                'questions_created': Question.objects.filter(teacher=user).count(),
                'exams_created': Exam.objects.filter(teacher=user).count(),
                'total_submissions': total_submissions,
            })

        # 学生：统计提交和通过率
        submissions = Submission.objects.filter(student=user)
        total = submissions.count()
        passed = submissions.filter(execution_status='ACCEPTED').count()
        # 通过题目数：至少有一次 ACCEPTED 的不同题目数
        passed_questions = submissions.filter(
            execution_status='ACCEPTED'
        ).values('question').distinct().count()

        recent = submissions.order_by('-submission_time')[:5].values(
            'id', 'question__id', 'question__title',
            'execution_status', 'score', 'submission_time'
        )

        return Response({
            'username': user.username,
            'display_name': user.display_name,
            'name': user.name,
            'user_type': user.user_type,
            'total_submissions': total,
            'passed': passed,
            'passed_questions': passed_questions,
            'pass_rate': round(passed / total, 2) if total else 0,
            'recent_submissions': list(recent),
        })
