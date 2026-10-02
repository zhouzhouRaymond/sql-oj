from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """登录接口限流：按来源 IP 限制尝试频率，缓解密码暴力破解。

    速率在 settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login'] 配置。
    """

    scope = 'login'
