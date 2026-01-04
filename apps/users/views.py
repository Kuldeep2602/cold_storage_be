from django.conf import settings
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PhoneOTP, User, UserRole
from .permissions import IsAdminOrOwner, IsManagerOrHigher
from .serializers import (
	CreateUserSerializer,
	CreateStaffSerializer,
	OTPRequestSerializer,
	OTPVerifySerializer,
	SignupSerializer,
	StaffMemberSerializer,
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


class StaffViewSet(viewsets.ModelViewSet):
	"""ViewSet for managing staff members (operators, technicians, managers)"""
	serializer_class = StaffMemberSerializer
	permission_classes = [IsManagerOrHigher]
	http_method_names = ['get', 'post', 'patch', 'delete']

	def get_queryset(self):
		# Staff members are users with specific roles
		return User.objects.filter(
			role__in=['operator', 'technician', 'manager']
		).order_by('name', '-created_at')

	def get_serializer_class(self):
		if self.action == 'create':
			return CreateStaffSerializer
		return StaffMemberSerializer

	@action(detail=True, methods=['post'], url_path='toggle-status')
	def toggle_status(self, request, pk=None):
		"""Enable or disable a staff member"""
		staff = self.get_object()
		staff.is_active = not staff.is_active
		staff.save()
		return Response(StaffMemberSerializer(staff).data)

	@action(detail=True, methods=['post'], url_path='update-role')
	def update_role(self, request, pk=None):
		"""Update staff member's role"""
		staff = self.get_object()
		new_role = request.data.get('role')
		
		allowed_roles = ['operator', 'technician', 'manager']
		if new_role not in allowed_roles:
			return Response(
				{'detail': f'Role must be one of: {", ".join(allowed_roles)}'},
				status=status.HTTP_400_BAD_REQUEST
			)
		
		staff.role = new_role
		staff.save()
		return Response(StaffMemberSerializer(staff).data)


class DashboardView(APIView):
	"""Manager dashboard statistics"""
	permission_classes = [IsAuthenticated]

	def get(self, request):
		from apps.inventory.models import InwardEntry, OutwardEntry
		from apps.temperature.models import TemperatureAlert, AlertStatus, StorageRoom
		
		# Calculate storage statistics
		total_inward = InwardEntry.objects.aggregate(
			total=Sum('quantity')
		)['total'] or 0
		
		total_outward = OutwardEntry.objects.aggregate(
			total=Sum('quantity')
		)['total'] or 0
		
		current_stock = float(total_inward) - float(total_outward)
		
		# Assuming total capacity (you can make this configurable)
		total_capacity = 500  # MT
		available = max(0, total_capacity - current_stock)
		
		# Count pending requests (inward entries from today that need approval)
		# For now, we'll show recent entries as pending
		pending_requests = InwardEntry.objects.filter(
			created_at__gte=timezone.now() - timezone.timedelta(days=7)
		).count()
		
		# Active temperature alerts
		active_alerts = TemperatureAlert.objects.filter(
			status=AlertStatus.ACTIVE
		).count()
		
		# Staff count
		staff_count = User.objects.filter(
			role__in=['operator', 'technician', 'manager'],
			is_active=True
		).count()
		
		# Inventory by crop
		inventory_by_crop = InwardEntry.objects.values('crop_name').annotate(
			total_quantity=Sum('quantity'),
			count=Count('id')
		).order_by('-total_quantity')[:10]
		
		return Response({
			'storage': {
				'available': round(available, 2),
				'occupied': round(current_stock, 2),
				'total_capacity': total_capacity,
			},
			'pending_requests': pending_requests,
			'active_alerts': active_alerts,
			'staff_count': staff_count,
			'inventory_by_crop': list(inventory_by_crop),
		})
