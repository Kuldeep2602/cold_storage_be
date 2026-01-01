from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Sum


class PersonType(models.TextChoices):
	FARMER = 'farmer', 'Farmer'
	VENDOR = 'vendor', 'Vendor'


class PackagingType(models.TextChoices):
	BORI = 'bori', 'Bori'
	CRATE = 'crate', 'Crate'
	BOX = 'box', 'Box'


class PaymentStatus(models.TextChoices):
	PENDING = 'pending', 'Pending'
	PAID = 'paid', 'Paid'


class PaymentMethod(models.TextChoices):
	CASH = 'cash', 'Cash'
	UPI = 'upi', 'UPI'
	BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
	CARD = 'card', 'Card'
	OTHER = 'other', 'Other'


class Person(models.Model):
	person_type = models.CharField(max_length=20, choices=PersonType.choices)
	name = models.CharField(max_length=255)
	mobile_number = models.CharField(max_length=20, unique=True)
	address = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.name} ({self.mobile_number})"


def inward_image_upload_to(instance: 'InwardEntry', filename: str) -> str:
	return f"inward/{instance.id or 'new'}/{filename}"


class InwardEntry(models.Model):
	person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='inward_entries')

	crop_name = models.CharField(max_length=100)
	crop_variety = models.CharField(max_length=100, blank=True)
	size_grade = models.CharField(max_length=100, blank=True)

	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	packaging_type = models.CharField(max_length=20, choices=PackagingType.choices)
	quality_grade = models.CharField(max_length=1, choices=[('A', 'Grade A'), ('B', 'Grade B'), ('C', 'Grade C')], default='A')

	image = models.ImageField(upload_to=inward_image_upload_to, blank=True, null=True)
	rack_number = models.CharField(max_length=50, blank=True)
	
	storage_room = models.CharField(max_length=100, blank=True)
	expected_storage_duration_days = models.PositiveIntegerField(null=True, blank=True)
	entry_date = models.DateField(auto_now_add=True)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_inwards')
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"Inward {self.id} - {self.crop_name} - {self.quantity}"

	@property
	def outward_total_quantity(self):
		value = self.outward_entries.aggregate(total=Sum('quantity'))['total']
		return value or 0

	@property
	def remaining_quantity(self):
		return self.quantity - self.outward_total_quantity


class OutwardEntry(models.Model):
	inward_entry = models.ForeignKey(InwardEntry, on_delete=models.PROTECT, related_name='outward_entries')

	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	packaging_type = models.CharField(max_length=20, choices=PackagingType.choices)

	receipt_number = models.CharField(max_length=64, unique=True, editable=False)
	payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
	payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_outwards')
	created_at = models.DateTimeField(auto_now_add=True)

	def save(self, *args, **kwargs):
		if not self.receipt_number:
			self.receipt_number = f"RCP-{uuid.uuid4().hex[:12].upper()}"
		super().save(*args, **kwargs)

	def __str__(self) -> str:
		return f"Outward {self.id} - {self.receipt_number}"
