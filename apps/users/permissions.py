from rest_framework.permissions import BasePermission


class IsTeacher(BasePermission):
    """允许教师角色访问。

    本项目所有教师都相当于管理员（都拥有账号管理等全部管理功能），
    因此管理类接口一律以「是否教师」作为唯一判据。
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'teacher'


class IsOwnerOrTeacher(BasePermission):
    """只有本人或教师可以访问对象"""
    def has_object_permission(self, request, view, obj):
        return request.user == obj or request.user.user_type == 'teacher'
