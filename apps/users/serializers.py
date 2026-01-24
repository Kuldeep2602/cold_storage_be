from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PhoneOTP, User, UserRole


class UserSerializer(serializers.ModelSerializer):
    assigned_storages = serializers.SerializerMethodField()
    assigned_rooms = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'role', 'is_active', 'created_at', 'assigned_storages', 'assigned_rooms']
        read_only_fields = ['id', 'created_at']

    def get_assigned_storages(self, obj):
        from apps.inventory.serializers import ColdStorageSummarySerializer
        from apps.users.models import UserRole
        
        assigned = obj.assigned_storages.all()
        
        # For owners, also include their owned storages in the list
        if obj.role == UserRole.OWNER and hasattr(obj, 'owned_cold_storages'):
            owned = obj.owned_cold_storages.all()
            if owned.exists():
                assigned = assigned | owned
        
        # Use distinct to avoid duplicates if user is both assigned and owner (rare but possible)
        return ColdStorageSummarySerializer(assigned.distinct(), many=True).data
    
    def get_assigned_rooms(self, obj):
        from apps.inventory.serializers import StorageRoomSerializer
        rooms = obj.assigned_rooms.all()
        return StorageRoomSerializer(rooms, many=True).data


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'role', 'is_active']
        read_only_fields = ['id']

    def validate_role(self, value):
        if value not in UserRole.values:
            raise serializers.ValidationError('Invalid role')
        return value

    def validate(self, attrs):
        # Check if phone number already exists under the same manager
        phone_number = attrs.get('phone_number')
        if phone_number:
            request = self.context.get('request')
            if request and request.user:
                managed_by = request.user
                # Check for duplicate phone within same manager's scope
                if User.objects.filter(phone_number=phone_number, managed_by=managed_by).exists():
                    raise serializers.ValidationError({
                        'phone_number': 'This phone number is already registered under your account'
                    })
        return attrs


class SignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number']

    def validate_phone_number(self, value):
        phone = str(value).strip()
        # Only check for owners (who self-register, so managed_by=None)
        if User.objects.filter(phone_number=phone, managed_by__isnull=True).exists():
            raise serializers.ValidationError('Phone number already registered as owner')
        return phone

    def create(self, validated_data):
        user = User.objects.create_user(
            phone_number=validated_data['phone_number'],
            role=UserRole.OWNER,  # Default role for signup - only owners can self-register
        )
        return user


class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)


class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=10)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


def issue_token_pair(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh['role'] = getattr(user, 'role', None)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': UserSerializer(user).data,
    }


def create_otp_for_phone(phone_number: str) -> tuple[PhoneOTP, str]:
    import secrets

    code = ''.join(str(secrets.randbelow(10)) for _ in range(6))
    otp = PhoneOTP.create_otp(
        phone_number=phone_number,
        code=code,
        ttl_seconds=getattr(settings, 'OTP_TTL_SECONDS', 300),
    )
    return otp, code
