from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import UserViewSet, StaffViewSet, DashboardView

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'staff', StaffViewSet, basename='staff')

urlpatterns = router.urls + [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
