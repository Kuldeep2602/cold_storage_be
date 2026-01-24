from django.contrib.auth.backends import ModelBackend
from apps.users.models import User


class PhoneNumberRoleBackend(ModelBackend):
    """
    Custom authentication backend that authenticates users by phone_number and role.
    This allows the same phone number to exist for different owners/managers.
    """
    
    def authenticate(self, request, username=None, password=None, role=None, **kwargs):
        """
        Authenticate user by phone number (username) and optionally role.
        If role is provided, it helps disambiguate users with the same phone number.
        """
        if username is None:
            username = kwargs.get('phone_number')
        
        if username is None:
            return None
        
        try:
            # Filter by phone number
            users = User.objects.filter(phone_number=username, is_active=True)
            
            # If role is provided, use it to narrow down the user
            if role:
                users = users.filter(role=role)
            
            user = users.first()
            
            if user and user.check_password(password):
                return user
            
        except User.DoesNotExist:
            return None
        
        return None
