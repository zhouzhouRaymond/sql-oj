from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SingleSessionJWTAuthentication(JWTAuthentication):
    """单点登录版 JWT 认证。

    在父类完成签名 / 过期 / 用户状态 / 密码未变更等校验后，额外校验 token 中的
    `sid`（会话标识）是否与用户当前的会话一致：

    * 开启单点登录（``SINGLE_SESSION_ENFORCED=True``）：只有 sid 与用户当前
      会话相同的 token 才有效。新登录会写入新的 sid，从而让旧会话签发的
      access token 立即失效（refresh token 同时被拉黑，见 LoginSerializer）。
    * 关闭单点登录：退化为原生 JWTAuthentication 行为。
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not getattr(settings, 'SINGLE_SESSION_ENFORCED', False):
            return user

        sid = validated_token.get('sid')
        # 缺少 sid（例如开启单点登录前签发的旧 token）或与当前会话不一致，都拒绝
        if not sid or sid != user.current_session:
            raise AuthenticationFailed(
                _('账号已在其它设备登录，请重新登录'),
                code='single_session_expired',
            )
        return user
