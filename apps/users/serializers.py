from rest_framework import serializers
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """公开注册：只允许注册学生账号。

    仅当系统内还没有任何教师时，允许注册一个教师账号用于初始化
    （此后教师账号只能由教师在「账号管理」中创建）。
    """
    password = serializers.CharField(write_only=True, min_length=6)
    # 自定义用户名（展示名）可选，为空时后端自动使用登录名
    display_name = serializers.CharField(
        required=False, allow_blank=True, max_length=50
    )

    class Meta:
        model = User
        fields = ('username', 'display_name', 'email', 'password', 'user_type')
        extra_kwargs = {
            # 邮箱选填：不填也能注册
            'email': {'required': False, 'allow_blank': True},
        }

    def validate_display_name(self, value):
        return (value or '').strip()

    def validate_email(self, value):
        return (value or '').strip()

    def validate_user_type(self, value):
        if value == 'teacher' and User.objects.filter(user_type='teacher').exists():
            raise serializers.ValidationError(
                '教师账号不可自助注册，请由已登录的教师在「账号管理」中创建'
            )
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    """自助接口（/users/me/）：只能修改自己的用户名（展示名）/ 邮箱 / 密码。

    角色、登录名、启用状态等一律只读，防止通过 /users/me/ 自行提权。
    """
    # 展示用用户名：自定义用户名，为空时后端回退为登录名
    name = serializers.CharField(read_only=True)
    # 仅写入：修改自己的密码
    password = serializers.CharField(
        write_only=True, required=False, min_length=6
    )

    class Meta:
        model = User
        fields = (
            'id', 'username', 'display_name', 'name', 'email', 'user_type',
            'permission_level', 'teacher', 'password', 'is_active',
            'date_joined', 'last_login',
        )
        read_only_fields = (
            'id', 'username', 'user_type', 'permission_level', 'teacher',
            'is_active', 'date_joined', 'last_login',
        )
        extra_kwargs = {
            'display_name': {
                'required': False, 'allow_blank': True, 'max_length': 50,
            },
            # 邮箱选填：个人中心 / 账号管理都允许留空
            'email': {'required': False, 'allow_blank': True},
        }

    def validate_display_name(self, value):
        return (value or '').strip()

    def validate_email(self, value):
        return (value or '').strip()

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user


class UserAdminSerializer(UserSerializer):
    """账号管理接口（仅教师可用）：新建任意角色账号、改登录名/角色/启用状态、重置密码。"""

    class Meta(UserSerializer.Meta):
        # 账号管理需要能写登录名 / 角色 / 启用状态
        read_only_fields = ('id', 'date_joined', 'last_login')

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError(
                {'password': '新建账号时必须设置初始密码'}
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
