from rest_framework.routers import DefaultRouter

from .views import StorageRoomViewSet, TemperatureLogViewSet, TemperatureAlertViewSet

router = DefaultRouter()
router.register(r'rooms', StorageRoomViewSet, basename='storage-rooms')
router.register(r'logs', TemperatureLogViewSet, basename='temperature-logs')
router.register(r'alerts', TemperatureAlertViewSet, basename='temperature-alerts')

urlpatterns = router.urls
