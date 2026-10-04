"""接口限流。

- 登录接口：按来源 IP 限制尝试频率，缓解密码爆破（scope=login）；
- 提交判题：用户级 / 题目级 / 全局三级限流（scope=submit_user /
  submit_question / submit_global），速率在
  ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`` 配置。
"""
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """登录接口限流：按来源 IP 限制尝试频率，缓解密码爆破。"""

    scope = 'login'


class SubmitUserThrottle(UserRateThrottle):
    """用户级限流：单用户每分钟最多提交 N 次（scope=submit_user）。"""

    scope = 'submit_user'


class SubmitQuestionThrottle(SimpleRateThrottle):
    """题目级限流：热门题目防止集中冲击（scope=submit_question）。

    以「题目 ID + 提交者」为键；缺少 question_id 时返回 None（不限流）。
    """

    scope = 'submit_question'

    def get_cache_key(self, request, view):
        try:
            question_id = request.data.get('question_id')
        except Exception:  # noqa: BLE001 - 非法请求体不应触发 500
            question_id = None
        if not question_id:
            return None
        user = getattr(request, 'user', None)
        ident = (
            user.pk
            if user is not None and getattr(user, 'is_authenticated', False)
            else self.get_ident(request)
        )
        return self.cache_format % {
            'scope': self.scope,
            'ident': f'{question_id}:{ident}',
        }


class SubmitGlobalThrottle(SimpleRateThrottle):
    """全局限流：超过容器承载能力时拒绝/排队，保护判题集群（scope=submit_global）。"""

    scope = 'submit_global'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': 'global'}
