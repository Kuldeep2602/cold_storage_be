from rest_framework import mixins, viewsets

from apps.users.permissions import IsManagerOrAdmin

from .models import PaymentRequest
from .serializers import PaymentRequestSerializer


class PaymentRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
	queryset = PaymentRequest.objects.select_related('outward_entry').all().order_by('-id')
	serializer_class = PaymentRequestSerializer
	permission_classes = [IsManagerOrAdmin]
