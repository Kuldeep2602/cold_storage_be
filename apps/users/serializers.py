from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PhoneOTP, User, UserRole


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'preferred_language', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'preferred_language', 'role', 'is_active']
        read_only_fields = ['id']

    def validate_role(self, value):
        if value not in UserRole.values:
            raise serializers.ValidationError('Invalid role')
        return value


class StaffMemberSerializer(serializers.ModelSerializer):
    """Serializer for staff management with role display"""
    role_display = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'name', 'preferred_language', 'role', 'role_display', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_role_display(self, obj):
        role_labels = {
            'operator': 'Inward/Outward Operator',
            'technician': 'Technician (Temperature)',
            'manager': 'Manager',
            'admin': 'Admin',
            'owner': 'Owner',
        }
        return role_labels.get(obj.role, obj.role or 'No Role')


class CreateStaffSerializer(serializers.ModelSerializer):
    """Serializer for creating new staff members"""
    class Meta:
        model = User
        fields = ['phone_number', 'name', 'role']

    def validate_phone_number(self, value):
        phone = str(value).strip()
        if User.objects.filter(phone_number=phone).exists():
            raise serializers.ValidationError('Phone number already registered')
        return phone

    def validate_role(self, value):
        allowed_roles = ['operator', 'technician', 'manager']
        if value not in allowed_roles:
            raise serializers.ValidationError(f'Role must be one of: {", ".join(allowed_roles)}')
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            phone_number=validated_data['phone_number'],
            name=validated_data.get('name', ''),
            role=validated_data['role'],
        )


class SignupSerializer(serializers.ModelSerializer):
	class Meta:
		model = User
		fields = ['phone_number', 'role']

	def validate_phone_number(self, value):
		phone = str(value).strip()
		if User.objects.filter(phone_number=phone).exists():
			raise serializers.ValidationError('Phone number already registered')
		return phone

	def validate_role(self, value):
		if value and value not in UserRole.values:
			raise serializers.ValidationError('Invalid role')
		return value

	def create(self, validated_data):
		# Role is now assigned during signup
		user = User.objects.create_user(
			phone_number=validated_data['phone_number'],
			role=validated_data.get('role'),  # Can be None if not provided
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
