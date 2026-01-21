from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PhoneOTP, User, UserRole


class UserSerializer(serializers.ModelSerializer):
    assigned_storages = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'role', 'is_active', 'created_at', 'assigned_storages']
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


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'role', 'is_active']
        read_only_fields = ['id']

    def validate_role(self, value):
        if value not in UserRole.values:
            raise serializers.ValidationError('Invalid role')
        return value


class SignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number']

    def validate_phone_number(self, value):
        phone = str(value).strip()
        if User.objects.filter(phone_number=phone).exists():
            raise serializers.ValidationError('Phone number already registered')
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
