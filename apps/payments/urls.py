from rest_framework.routers import DefaultRouter

from .views import PaymentRequestViewSet

router = DefaultRouter()
router.register(r'requests', PaymentRequestViewSet, basename='payment-requests')

urlpatterns = router.urls
