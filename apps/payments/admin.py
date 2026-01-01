from django.contrib import admin

from .models import PaymentRequest


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
	list_display = ['id', 'outward_entry', 'status', 'method', 'created_at']
	list_filter = ['status', 'created_at']
