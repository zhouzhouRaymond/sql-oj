from rest_framework import serializers
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    # 自定义用户名（展示名）可选，为空时后端自动使用登录名
    display_name = serializers.CharField(
        required=False, allow_blank=True, max_length=50
    )

    class Meta:
        model = User
        fields = ('username', 'display_name', 'email', 'password', 'user_type')

    def validate_display_name(self, value):
        return (value or '').strip()

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    # 展示用用户名：自定义用户名，为空时后端回退为登录名
    name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'display_name', 'name', 'email', 'user_type',
            'permission_level', 'teacher'
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'display_name': {
                'required': False, 'allow_blank': True, 'max_length': 50,
            },
        }

    def validate_display_name(self, value):
        return (value or '').strip()
