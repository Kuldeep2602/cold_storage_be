import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cold_storage_erp.settings')
django.setup()

from apps.users.models import User
from apps.inventory.models import ColdStorage

print("--- Cold Storages ---")
for cs in ColdStorage.objects.all():
    print(f"ID: {cs.id}, Name: {cs.name}, Capacity: {cs.total_capacity}")

print("\n--- Users and Assigned Storages ---")
for user in User.objects.filter(role__in=['manager', 'operator', 'technician']):
    assigned = user.assigned_storages.all()
    names = [s.name for s in assigned]
    print(f"User: {user.name} ({user.phone_number}), Role: {user.role}, Assigned: {names}")
