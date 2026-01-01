from django.db import models


class PaymentRequestStatus(models.TextChoices):
	REQUESTED = 'requested', 'Requested'
	PAID = 'paid', 'Paid'
	FAILED = 'failed', 'Failed'


class PaymentRequest(models.Model):
	outward_entry = models.OneToOneField('inventory.OutwardEntry', on_delete=models.CASCADE, related_name='payment_request')
	status = models.CharField(max_length=20, choices=PaymentRequestStatus.choices, default=PaymentRequestStatus.REQUESTED)
	method = models.CharField(max_length=50, blank=True)
	payload = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"PaymentRequest {self.id} ({self.status})"
