from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

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


class StaffPagination(PageNumberPagination):
    """Custom pagination for staff list - 50 items per page for better UX"""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


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
		
		# Accept optional role parameter to help identify the correct user
		# If multiple users exist with same phone, role helps narrow it down
		role = request.data.get('role', '').strip().lower()

		# Check if any active user exists with this phone number
		users_query = User.objects.filter(phone_number=phone_number, is_active=True)
		
		# If role is provided, filter by role
		if role:
			users_query = users_query.filter(role=role)
		
		user = users_query.first()
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
		
		# Accept optional role parameter to identify the correct user when multiple exist
		role = request.data.get('role', '').strip().lower()

		otp = (
			PhoneOTP.objects.filter(phone_number=phone_number, used_at__isnull=True, expires_at__gt=timezone.now())
			.order_by('-created_at')
			.first()
		)
		if not otp or not otp.verify(code):
			return Response({'detail': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

		otp.mark_used()

		# Find the user - if role is provided, use it to disambiguate
		users_query = User.objects.filter(phone_number=phone_number, is_active=True)
		
		if role:
			users_query = users_query.filter(role=role)
		
		user = users_query.first()
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
    Optimized with prefetch_related to prevent N+1 queries.
    Returns 50 staff members per page (configurable via ?page_size=N).
    """
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsManagerOrAdmin]
    pagination_class = StaffPagination  # 50 items per page
    search_fields = ['phone_number', 'name']
    ordering_fields = ['created_at', 'role']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateUserSerializer
        return UserSerializer
    
    def get_queryset(self):
        user = self.request.user

        # Prefetch related data to prevent N+1 queries (213+ queries -> 6-8 queries)
        # This loads assigned_storages, assigned_rooms, and owned_cold_storages in bulk
        qs = User.objects.prefetch_related(
            'assigned_storages',
            'assigned_storages__rooms',
            'assigned_rooms',
            'assigned_rooms__cold_storage',
            'owned_cold_storages',
            'owned_cold_storages__rooms'
        ).select_related('managed_by')

        # Owners see staff they created
        # Managers see staff they created
        # Filter out superusers and only show staff managed by current user
        if user.role == 'owner':
            qs = qs.filter(managed_by=user).exclude(is_superuser=True)
        elif user.role == 'manager':
            qs = qs.filter(managed_by=user).exclude(is_superuser=True)
        else:
            # Admins see all
            qs = qs.exclude(is_superuser=True)

        # Apply cold_storage query parameter filter if provided
        cold_storage_id = self.request.query_params.get('cold_storage')
        if cold_storage_id:
            # Filter to staff members assigned to the specified cold storage
            qs = qs.filter(assigned_storages__id=cold_storage_id).distinct()

        return qs.order_by('-id')

    def perform_create(self, serializer):
        # Set managed_by to current user when creating staff
        new_user = serializer.save(managed_by=self.request.user)
        
        # Handle storage assignment
        # If 'storage_ids' provided, use those (filtered by permission)
        # If not provided, fallback to auto-assigning ALL of manager's storages
        
        storage_ids = self.request.data.get('storage_ids')
        room_ids = self.request.data.get('room_ids')
        
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
                
        # Handle room assignment
        if room_ids is not None and self.request.user.role in ['owner', 'manager']:
            from apps.inventory.models import StorageRoom
            
            # Get rooms that belong to storages accessible to the current user
            available_storages = self.request.user.assigned_storages.all()
            if self.request.user.role == 'owner':
                available_storages = available_storages | self.request.user.owned_cold_storages.all()
            
            # Filter rooms by available storages
            valid_room_ids = []
            if isinstance(room_ids, list):
                for rid in room_ids:
                    try:
                        valid_room_ids.append(int(rid))
                    except (ValueError, TypeError):
                        continue
            
            rooms_to_assign = StorageRoom.objects.filter(
                id__in=valid_room_ids,
                cold_storage__in=available_storages
            )
            
            if rooms_to_assign.exists():
                new_user.assigned_rooms.set(rooms_to_assign)

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
