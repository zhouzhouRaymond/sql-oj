from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )
    PERMISSION_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
    )

    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    permission_level = models.CharField(
        max_length=10, choices=PERMISSION_CHOICES,
        null=True, blank=True
    )
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
