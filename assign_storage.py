import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cold_storage_erp.settings')
django.setup()

from apps.users.models import User
from apps.inventory.models import ColdStorage

try:
    user = User.objects.get(name="test 2")
    storage = ColdStorage.objects.first()
    
    if storage:
        user.assigned_storages.add(storage)
        print(f"Successfully assigned '{storage.name}' to '{user.name}'")
    else:
        print("No Cold Storage found to assign!")

except User.DoesNotExist:
    print("User 'test 2' not found!")
