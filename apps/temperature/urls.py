from rest_framework.routers import DefaultRouter

from .views import TemperatureLogViewSet

router = DefaultRouter()
router.register(r'logs', TemperatureLogViewSet, basename='temperature-logs')

urlpatterns = router.urls
