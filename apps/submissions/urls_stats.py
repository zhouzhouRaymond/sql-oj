from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_stats import StatsViewSet

stats_router = DefaultRouter()
stats_router.register(r'', StatsViewSet, basename='stats')

urlpatterns = [
    path('', include(stats_router.urls)),
]
