from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PhoneOTP, User
from .permissions import IsManagerOrAdmin
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
	permission_classes = [IsManagerOrAdmin]
	http_method_names = ['get', 'post', 'patch']

	def get_serializer_class(self):
		if self.action == 'create':
			return CreateUserSerializer
		return UserSerializer

	@action(detail=False, methods=['get'], url_path='me')
	def me(self, request):
		return Response(UserSerializer(request.user).data)


class StaffViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing staff members.
    """
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsManagerOrAdmin]
    search_fields = ['phone_number', 'name']
    ordering_fields = ['created_at', 'role']
    
    
    def get_queryset(self):
        user = self.request.user
        # Owners see staff they created
        # Managers see staff they created
        # Filter out superusers and only show staff managed by current user
        if user.role == 'owner':
            return User.objects.filter(managed_by=user).exclude(is_superuser=True).order_by('-id')
        elif user.role == 'manager':
            return User.objects.filter(managed_by=user).exclude(is_superuser=True).order_by('-id')
        # Admins see all
        return User.objects.exclude(is_superuser=True).order_by('-id')

    def perform_create(self, serializer):
        # Set managed_by to current user when creating staff
        new_user = serializer.save(managed_by=self.request.user)
        
        # Handle storage assignment
        # If 'storage_ids' provided, use those (filtered by permission)
        # If not provided, fallback to auto-assigning ALL of manager's storages
        
        storage_ids = self.request.data.get('storage_ids')
        
        if self.request.user.role in ['owner', 'manager']:
            storages_to_assign = []
            
            # Get valid scope for the current user
            available_storages = self.request.user.assigned_storages.all()
            if self.request.user.role == 'owner':
                # Owner can assign any of their owned storages
                # (Note: owned_cold_storages contains all storages owned by user)
                 available_storages = available_storages | self.request.user.owned_cold_storages.all()
            
            if storage_ids is not None:
                # Filter requested IDs against available scope
                # Ensure we only pick IDs that are integers (handling potential bad input)
                valid_ids = []
                if isinstance(storage_ids, list):
                    for sid in storage_ids:
                         try:
                             valid_ids.append(int(sid))
                         except (ValueError, TypeError):
                             continue
                
                storages_to_assign = available_storages.filter(id__in=valid_ids)
            else:
                # Default: Assign ALL if storage_ids param is missing entirely
                storages_to_assign = available_storages

            if storages_to_assign.exists():
                new_user.assigned_storages.set(storages_to_assign)
            elif storage_ids is not None:
                # If explicit empty list provided, clear assignments
                new_user.assigned_storages.clear()

    @action(detail=True, methods=['post'], url_path='update-role')
    def update_role(self, request, pk=None):
        user = self.get_object()
        role = request.data.get('role')
        if role:
            user.role = role
            user.save()
            return Response({'status': 'role updated', 'role': user.role})
        return Response({'error': 'role required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        return Response({'status': 'status updated', 'is_active': user.is_active})

    @action(detail=True, methods=['post'], url_path='assign-storages')
    def assign_storages(self, request, pk=None):
        """Assign cold storages to a staff member (manager/operator/technician)"""
        user = self.get_object()
        storage_ids = request.data.get('storage_ids', [])
        
        from apps.inventory.models import ColdStorage
        
        # Clear existing assignments
        user.assigned_storages.clear()
        
        # Add new assignments
        if storage_ids:
            # Verify all storages belong to the requesting user (owner)
            storages = ColdStorage.objects.filter(
                id__in=storage_ids,
                owner=request.user
            )
            user.assigned_storages.add(*storages)
        
        return Response({
            'status': 'storages assigned',
            'assigned_count': user.assigned_storages.count()
        })


class DashboardView(APIView):
    """
    API View for dashboard statistics.
    """
    permission_classes = [IsManagerOrAdmin]

    def get(self, request):
        user = request.user
        
        data = {
            'user': {
                'id': user.id,
                'phone_number': user.phone_number,
                'name': user.name,
                'role': user.role,
            },
            'assigned_storages': [],
        }
        
        # Add assigned storages for managers/operators
        if user.role in ['manager', 'operator', 'technician']:
            from apps.inventory.serializers import ColdStorageSummarySerializer
            data['assigned_storages'] = ColdStorageSummarySerializer(
                user.assigned_storages.all(), 
                many=True
            ).data
        
        # Add owned storages for owners
        if user.role == 'owner':
            from apps.inventory.serializers import ColdStorageSummarySerializer
            data['owned_storages'] = ColdStorageSummarySerializer(
                user.owned_cold_storages.all(), 
                many=True
            ).data
            data['staff_count'] = user.staff_members.count()
        
        return Response(data, status=status.HTTP_200_OK)
