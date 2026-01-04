from django.conf import settings
from django.db.models import Sum, Count, Q, Avg
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
		requested_role = serializer.validated_data.get('role')

		# Find user with matching phone and active status
		# If role is specified, ensure it matches (Strict RBAC)
		# Admin can login without role restriction if needed, but for app we enforce it
		query = Q(phone_number=phone_number, is_active=True)
		if requested_role:
			query &= Q(role=requested_role)

		user = User.objects.filter(query).first()
		
		if not user:
			# If specific role was requested but not found, check if user exists at all for better error
			if requested_role and User.objects.filter(phone_number=phone_number).exists():
				return Response(
					{'detail': f'This number is not registered as {requested_role}'}, 
					status=status.HTTP_403_FORBIDDEN
				)
			return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

		# RBAC: Check hierarchy
		# Managers/Operators must be "registered" (have managed_by or assigned storages or just exist validly)
		# We assume existence implies registration validation was done at creation.
		# But we can add a check: if you are Manager/Operator, must be active (already checked).

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
		user = self.request.user
		# Admin sees all
		if user.role == UserRole.ADMIN:
			return User.objects.filter(
				role__in=['operator', 'technician', 'manager']
			).order_by('name', '-created_at')
		
		# Owner/Manager sees only staff they manage
		return User.objects.filter(
			role__in=['operator', 'technician', 'manager'],
			managed_by=user
		).order_by('name', '-created_at')

	def perform_create(self, serializer):
		# Auto-assign managed_by to the current user
		extra_data = {'managed_by': self.request.user}
		
		# If creator is a Manager, auto-assign their managed cold storages to the new staff
		if self.request.user.role == 'manager':
			from apps.inventory.models import ColdStorage
			managed_storages = ColdStorage.objects.filter(manager=self.request.user, is_active=True).values_list('id', flat=True)
			if managed_storages:
				extra_data['assigned_storages'] = list(managed_storages)
				
		serializer.save(**extra_data)

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
		from apps.inventory.models import InwardEntry, OutwardEntry, ColdStorage
		from apps.temperature.models import TemperatureAlert, AlertStatus
		from apps.inventory.serializers import ColdStorageSerializer, ColdStorageSummarySerializer

		user = request.user
		cold_storage_id = request.query_params.get('cold_storage')
		
		# --- DISPATCH LOGIC BASED ON ROLE ---
		
		# 1. MANAGER / OPERATOR / TECHNICIAN
		if user.role in ['manager', 'operator', 'technician']:
			# Managers see assigned storages (via FK 'manager')
			# Operators/Technicians might use M2M 'assigned_storages'?
			# Let's combine both to be safe.
			
			if user.role == 'manager':
				cold_storages = ColdStorage.objects.filter(manager=user, is_active=True)
			else:
				# For operators/technicians, check assigned_storages M2M
				cold_storages = user.assigned_storages.filter(is_active=True)
				if not cold_storages.exists():
				    # Fallback to all active if logic dictates, but 'assigned' implies strict
					# For now, let's stick to strict assignment for operators too
					pass

			if not cold_storages.exists():
				return Response({
					'cold_storages': [],
					'selected_cold_storage': None,
					'stats': None,
					'message': 'No cold storages assigned.'
				})
			
			cold_storage_list = ColdStorageSummarySerializer(cold_storages, many=True).data
			
			selected_cs = cold_storages.first()
			if cold_storage_id:
				selected_cs = cold_storages.filter(id=cold_storage_id).first() or selected_cs
			
			stats = self._calculate_manager_stats(selected_cs)
			
			response_data = {
				'cold_storages': cold_storage_list,
				'selected_cold_storage': ColdStorageSerializer(selected_cs).data if selected_cs else None,
				'stats': stats
			}
			# Add assigned names for header
			if selected_cs:
				response_data['assigned_storage_names'] = [selected_cs.name]
			elif cold_storages.exists():
				response_data['assigned_storage_names'] = [cs.name for cs in cold_storages]
				
			return Response(response_data)

		# 2. OWNER / ADMIN
		elif user.role in ['owner', 'admin']:
			if user.role == 'owner':
				cold_storages = ColdStorage.objects.filter(owner=user, is_active=True)
			else:
				cold_storages = ColdStorage.objects.filter(is_active=True)
			
			if not cold_storages.exists():
				return Response({'cold_storages': [], 'stats': None, 'message': 'No cold storages found.'})
			
			cold_storage_list = ColdStorageSummarySerializer(cold_storages, many=True).data
			
			selected_cs = cold_storages.first()
			if cold_storage_id:
				selected_cs = cold_storages.filter(id=cold_storage_id).first() or selected_cs
			
			stats = self._calculate_owner_stats(selected_cs)
			
			return Response({
				'cold_storages': cold_storage_list,
				'selected_cold_storage': ColdStorageSerializer(selected_cs).data,
				'stats': stats
			})
			
		else:
			return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

	def _calculate_manager_stats(self, cold_storage):
		from apps.inventory.models import InwardEntry, OutwardEntry
		if not cold_storage: return None
		
		# Logic from ManagerDashboardView._calculate_stats
		total_inward = InwardEntry.objects.filter(cold_storage=cold_storage).aggregate(total=Sum('quantity'))['total'] or 0
		
		# Outward total (iterative sum of property is reliable)
		total_outward = 0
		inward_entries = InwardEntry.objects.filter(cold_storage=cold_storage)
		for inward in inward_entries:
			total_outward += inward.outward_total_quantity
			
		occupied = float(total_inward) - float(total_outward)
		total_capacity = float(cold_storage.total_capacity)
		available = max(0, total_capacity - occupied)
		utilization = round((occupied / total_capacity) * 100, 1) if total_capacity > 0 else 0
		
		now = timezone.now()
		month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
		month_inward = InwardEntry.objects.filter(cold_storage=cold_storage, created_at__gte=month_start).aggregate(total=Sum('quantity'))['total'] or 0
		month_outward = OutwardEntry.objects.filter(inward_entry__cold_storage=cold_storage, created_at__gte=month_start).aggregate(total=Sum('quantity'))['total'] or 0
		
		# Active bookings: entries where remaining_quantity > 0
		# Filter in python because remaining_quantity is a property
		active_bookings = 0
		for inward in inward_entries:
			if inward.remaining_quantity > 0:
				active_bookings += 1
		
		pending_requests = InwardEntry.objects.filter(cold_storage=cold_storage, created_at__gte=now - timezone.timedelta(days=7)).count()
		
		return {
			'storage': {'available': round(available, 2), 'occupied': round(occupied, 2), 'total_capacity': total_capacity, 'utilization_percent': utilization},
			'pending_requests': pending_requests,
			'active_bookings': active_bookings,
			'this_month': {'inflow': float(month_inward), 'outflow': float(month_outward)}
		}

	def _calculate_owner_stats(self, cold_storage):
		from apps.inventory.models import InwardEntry, OutwardEntry
		from apps.temperature.models import TemperatureAlert, AlertStatus
		
		if not cold_storage: return None
		
		total_inward = InwardEntry.objects.filter(cold_storage=cold_storage).aggregate(total=Sum('quantity'))['total'] or 0
		
		total_outward = 0
		inward_entries = InwardEntry.objects.filter(cold_storage=cold_storage)
		for inward in inward_entries:
			total_outward += inward.outward_total_quantity
			
		occupied = float(total_inward) - float(total_outward)
		total_capacity = float(cold_storage.total_capacity)
		available = max(0, total_capacity - occupied)
		utilization = round((occupied / total_capacity) * 100, 1) if total_capacity > 0 else 0
		
		now = timezone.now()
		month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
		month_inward = InwardEntry.objects.filter(cold_storage=cold_storage, created_at__gte=month_start).aggregate(total=Sum('quantity'))['total'] or 0
		month_outward = OutwardEntry.objects.filter(inward_entry__cold_storage=cold_storage, created_at__gte=month_start).aggregate(total=Sum('quantity'))['total'] or 0
		
		active_bookings = 0
		for inward in inward_entries:
			if inward.remaining_quantity > 0:
				active_bookings += 1
				
		pending = InwardEntry.objects.filter(cold_storage=cold_storage, created_at__gte=now - timezone.timedelta(days=7)).count()
		active_alerts = TemperatureAlert.objects.filter(status=AlertStatus.ACTIVE).count()
		
		avg_duration = InwardEntry.objects.filter(cold_storage=cold_storage, expected_storage_duration_days__isnull=False).aggregate(avg=Avg('expected_storage_duration_days'))['avg'] or 0
		estimated_revenue = occupied * avg_duration * 100 / 100000 
		
		return {
			'storage': {'total_capacity': round(total_capacity, 2), 'occupied': round(occupied, 2), 'available': round(available, 2), 'utilization_percent': utilization},
			'this_month': {'inflow': float(month_inward), 'outflow': float(month_outward)},
			'bookings': {'active': active_bookings, 'confirmed': active_bookings, 'pending': pending},
			'alerts': {'active': active_alerts, 'temperature_alerts': active_alerts, 'equipment_status': 'operational'},
			'financials': {'estimated_revenue': round(estimated_revenue, 2), 'avg_storage_duration': round(avg_duration) if avg_duration else 0}
		}
