"""
URL configuration for sql_oj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include


def health(_request):
    """轻量健康探针：供容器 healthcheck / 负载均衡使用。"""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('health', health),
    path('admin/', admin.site.urls),
    # 认证相关（注册/登录/刷新Token）
    path('api/auth/', include('apps.users.urls_auth')),
    # 用户管理
    path('api/users/', include('apps.users.urls')),
    # 题目管理
    path('api/questions/', include('apps.questions.urls')),
    # 考试管理
    path('api/exams/', include('apps.exams.urls')),
    # 提交与判题
    path('api/submissions/', include('apps.submissions.urls')),
    # 统计分析
    path('api/stats/', include('apps.submissions.urls_stats')),
]
