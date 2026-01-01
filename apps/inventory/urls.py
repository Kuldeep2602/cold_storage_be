from rest_framework.routers import DefaultRouter

from .views import InwardEntryViewSet, OutwardEntryViewSet, PersonViewSet

router = DefaultRouter()
router.register(r'persons', PersonViewSet, basename='persons')
router.register(r'inwards', InwardEntryViewSet, basename='inwards')
router.register(r'outwards', OutwardEntryViewSet, basename='outwards')

urlpatterns = router.urls
