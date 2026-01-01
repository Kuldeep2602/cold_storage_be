from django.contrib import admin

from .models import InwardEntry, OutwardEntry, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
	list_display = ['id', 'person_type', 'name', 'mobile_number', 'created_at']
	search_fields = ['name', 'mobile_number']


@admin.register(InwardEntry)
class InwardEntryAdmin(admin.ModelAdmin):
	list_display = ['id', 'person', 'crop_name', 'quantity', 'packaging_type', 'quality_grade', 'rack_number', 'created_at']
	list_filter = ['packaging_type', 'crop_name', 'created_at']


@admin.register(OutwardEntry)
class OutwardEntryAdmin(admin.ModelAdmin):
	list_display = ['id', 'receipt_number', 'inward_entry', 'quantity', 'payment_status', 'created_at']
	list_filter = ['payment_status', 'created_at']
	search_fields = ['receipt_number']
