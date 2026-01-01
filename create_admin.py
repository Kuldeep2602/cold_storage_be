import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.users.models import User

phone = '+1234567890'
try:
    if User.objects.filter(phone_number=phone).exists():
        print(f"User {phone} already exists, resetting password")
        u = User.objects.get(phone_number=phone)
        u.set_password('password123')
        u.is_superuser = True
        u.is_staff = True # Ensure admin access
        u.role = 'admin'
        u.save()
    else:
        print(f"Creating user {phone}")
        User.objects.create_superuser(phone_number=phone, password='password123')
    print("Superuser created/updated successfully")
except Exception as e:
    print(f"Error: {e}")
