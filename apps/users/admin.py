from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import PhoneOTP, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
	ordering = ['-id']
	list_display = ['id', 'phone_number', 'role', 'is_active', 'is_staff', 'created_at']
	search_fields = ['phone_number']
	fieldsets = (
		(None, {'fields': ('phone_number', 'password')}),
		('Role', {'fields': ('role',)}),
		('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Dates', {'fields': ('last_login',)}),
	)
	add_fieldsets = (
		(None, {'classes': ('wide',), 'fields': ('phone_number', 'role', 'password1', 'password2')}),
	)
	filter_horizontal = ('groups', 'user_permissions')
	readonly_fields = ('created_at', 'updated_at')


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
	list_display = ['id', 'phone_number', 'created_at', 'expires_at', 'used_at']
	search_fields = ['phone_number']
	list_filter = ['created_at', 'expires_at', 'used_at']
