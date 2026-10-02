from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )

    # 说明：教师即管理员——所有教师（user_type == 'teacher'）都拥有账号管理等
    # 全部管理功能，不再区分「admin / teacher」权限级别。
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    teacher = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='students',
        limit_choices_to={'user_type': 'teacher'}
    )
    # 登录名沿用 AbstractUser.username（唯一，用于登录）；
    # display_name 是可自定义的「用户名」（展示名），为空时回退到登录名
    display_name = models.CharField(
        '用户名', max_length=50, blank=True, default=''
    )
    # 单点登录：记录该账号当前唯一有效的会话标识。
    # 每次登录都会生成新的 sid 并写入 token；认证时校验两者一致，
    # 因此新登录会自动覆盖该值，使旧会话的 token 立即失效
    # （见 authentication.SingleSessionJWTAuthentication）。
    current_session = models.CharField(
        '当前会话标识', max_length=64, blank=True, default=''
    )

    @property
    def name(self):
        """展示用用户名：优先自定义用户名，否则回退登录名"""
        return self.display_name or self.username

    def save(self, *args, **kwargs):
        # 未设置自定义用户名时自动使用登录名，保证新注册/老数据都有展示名
        if not self.display_name:
            self.display_name = self.username
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = list(update_fields) + ['display_name']
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'user'
