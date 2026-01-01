from rest_framework import viewsets

from apps.users.permissions import IsManagerOrAdmin, IsOperatorOrHigher

from .models import TemperatureLog
from .serializers import TemperatureLogSerializer


class TemperatureLogViewSet(viewsets.ModelViewSet):
	queryset = TemperatureLog.objects.select_related('created_by').all().order_by('-logged_at', '-id')
	serializer_class = TemperatureLogSerializer
	http_method_names = ['get', 'post', 'patch', 'put']

	def get_permissions(self):
		if self.action in {'update', 'partial_update'}:
			return [IsManagerOrAdmin()]
		return [IsOperatorOrHigher()]

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)
