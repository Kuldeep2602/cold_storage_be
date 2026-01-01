from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from datetime import timedelta

from django.utils import timezone


class UserRole(models.TextChoices):
	OWNER = 'owner', 'Owner'
	ADMIN = 'admin', 'Admin'
	MANAGER = 'manager', 'Manager'
	TECHNICIAN = 'technician', 'Technician'
	OPERATOR = 'operator', 'Operator'


class PreferredLanguage(models.TextChoices):
	ENGLISH = 'en', 'English'
	HINDI = 'hi', 'Hindi'


class UserManager(BaseUserManager):
	use_in_migrations = True

	def create_user(self, phone_number: str, password: str | None = None, **extra_fields):
		if not phone_number:
			raise ValueError('phone_number is required')

		phone_number = str(phone_number).strip()

		# Role should not be auto-assigned - use None as default
		role = extra_fields.get('role', None)
		extra_fields['role'] = role
		extra_fields.setdefault('is_active', True)

		user = self.model(phone_number=phone_number, **extra_fields)
		if password:
			user.set_password(password)
		else:
			user.set_unusable_password()
		user.save(using=self._db)
		return user

	def create_superuser(self, phone_number: str, password: str, **extra_fields):
		extra_fields.setdefault('is_staff', True)
		extra_fields.setdefault('is_superuser', True)
		extra_fields.setdefault('role', UserRole.ADMIN)

		if extra_fields.get('is_staff') is not True:
			raise ValueError('Superuser must have is_staff=True.')
		if extra_fields.get('is_superuser') is not True:
			raise ValueError('Superuser must have is_superuser=True.')

		return self.create_user(phone_number=phone_number, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
	phone_number = models.CharField(max_length=20, unique=True)
	name = models.CharField(max_length=255, blank=True)
	preferred_language = models.CharField(
		max_length=5,
		choices=PreferredLanguage.choices,
		default=PreferredLanguage.ENGLISH
	)
	role = models.CharField(max_length=20, choices=UserRole.choices, null=True, blank=True)

	is_active = models.BooleanField(default=True)
	is_staff = models.BooleanField(default=False)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	objects = UserManager()

	USERNAME_FIELD = 'phone_number'
	REQUIRED_FIELDS: list[str] = []

	def __str__(self) -> str:
		return f"{self.phone_number} ({self.role})"


class PhoneOTP(models.Model):
	phone_number = models.CharField(max_length=20, db_index=True)
	code_hash = models.CharField(max_length=128)
	created_at = models.DateTimeField(auto_now_add=True)
	expires_at = models.DateTimeField(db_index=True)
	used_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [
			models.Index(fields=['phone_number', '-created_at']),
		]

	@property
	def is_used(self) -> bool:
		return self.used_at is not None

	def mark_used(self):
		self.used_at = timezone.now()
		self.save(update_fields=['used_at'])

	@classmethod
	def create_otp(cls, *, phone_number: str, code: str, ttl_seconds: int) -> 'PhoneOTP':
		now = timezone.now()
		return cls.objects.create(
			phone_number=phone_number,
			code_hash=make_password(code),
			expires_at=now + timedelta(seconds=ttl_seconds),
		)

	def verify(self, code: str) -> bool:
		if self.is_used:
			return False
		if timezone.now() > self.expires_at:
			return False
		return check_password(code, self.code_hash)
