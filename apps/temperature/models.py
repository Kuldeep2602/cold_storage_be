from django.conf import settings
from django.db import models


class TemperatureLog(models.Model):
	logged_at = models.DateTimeField()
	temperature = models.DecimalField(max_digits=6, decimal_places=2)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='temperature_logs')

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.logged_at}: {self.temperature}"
