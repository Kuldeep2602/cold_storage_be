from django.contrib import admin

from .models import TemperatureLog


@admin.register(TemperatureLog)
class TemperatureLogAdmin(admin.ModelAdmin):
	list_display = ['id', 'logged_at', 'temperature', 'created_by', 'created_at']
	list_filter = ['logged_at', 'created_at']
