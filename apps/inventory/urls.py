from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ColdStorageViewSet, 
    InwardEntryViewSet, 
    OutwardEntryViewSet, 
    PersonViewSet,
    OwnerDashboardView,
    ManagerDashboardView
)

router = DefaultRouter()
router.register(r'cold-storages', ColdStorageViewSet, basename='cold-storages')
router.register(r'persons', PersonViewSet, basename='persons')
router.register(r'inwards', InwardEntryViewSet, basename='inwards')
router.register(r'outwards', OutwardEntryViewSet, basename='outwards')

urlpatterns = router.urls + [
    path('owner-dashboard/', OwnerDashboardView.as_view(), name='owner-dashboard'),
    path('manager-dashboard/', ManagerDashboardView.as_view(), name='manager-dashboard'),
]

