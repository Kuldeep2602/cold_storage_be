from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PhoneOTP, User
from .permissions import IsAdminOrOwner
from .serializers import (
	CreateUserSerializer,
	OTPRequestSerializer,
	OTPVerifySerializer,
	SignupSerializer,
	UserSerializer,
	create_otp_for_phone,
	issue_token_pair,
)


class SignupView(APIView):
	"""Register a new user with phone number and send OTP"""
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = SignupSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()
		
		# Generate OTP for the new user
		_, code = create_otp_for_phone(user.phone_number)
		
		payload = {'detail': 'User registered. OTP sent.', 'phone_number': user.phone_number}
		if getattr(settings, 'OTP_DEBUG_RETURN_CODE', False):
			payload['otp_code'] = code
		return Response(payload, status=status.HTTP_201_CREATED)


class RequestOTPView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = OTPRequestSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		phone_number = serializer.validated_data['phone_number'].strip()

		user = User.objects.filter(phone_number=phone_number, is_active=True).first()
		if not user:
			return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

		_, code = create_otp_for_phone(phone_number)

		payload = {'detail': 'OTP generated'}
		if getattr(settings, 'OTP_DEBUG_RETURN_CODE', False):
			payload['otp_code'] = code
		return Response(payload, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = OTPVerifySerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		phone_number = serializer.validated_data['phone_number'].strip()
		code = serializer.validated_data['code'].strip()

		# Bypass OTPs for testing
		BYPASS_OTPS = ['123456', '1234']
		is_bypass = code in BYPASS_OTPS
		
		if not is_bypass:
			# Regular OTP verification
			otp = (
				PhoneOTP.objects.filter(phone_number=phone_number, used_at__isnull=True, expires_at__gt=timezone.now())
				.order_by('-created_at')
				.first()
			)
			if not otp or not otp.verify(code):
				return Response({'detail': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

			otp.mark_used()

		user = User.objects.filter(phone_number=phone_number, is_active=True).first()
		if not user:
			return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

		return Response(issue_token_pair(user), status=status.HTTP_200_OK)


class UserViewSet(viewsets.ModelViewSet):
	queryset = User.objects.all().order_by('-id')
	http_method_names = ['get', 'post', 'patch']

	def get_permissions(self):
		if self.action == 'me' or self.action == 'update_me':
			return [IsAuthenticated()]
		return [IsAdminOrOwner()]

	def get_serializer_class(self):
		if self.action == 'create':
			return CreateUserSerializer
		return UserSerializer

	@action(detail=False, methods=['get'], url_path='me')
	def me(self, request):
		return Response(UserSerializer(request.user).data)

	@action(detail=False, methods=['patch'], url_path='me')
	def update_me(self, request):
		"""Allow users to update their own profile (name, preferred_language)"""
		serializer = UserSerializer(request.user, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		
		# Only allow updating specific fields
		allowed_fields = {'name', 'preferred_language'}
		update_data = {k: v for k, v in serializer.validated_data.items() if k in allowed_fields}
		
		for key, value in update_data.items():
			setattr(request.user, key, value)
		request.user.save()
		
		return Response(UserSerializer(request.user).data)

