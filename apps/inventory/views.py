from decimal import Decimal
from datetime import timedelta

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsOperatorOrHigher, IsAdminOrOwner

from .models import ColdStorage, InwardEntry, OutwardEntry, Person
from .serializers import (
    ColdStorageSerializer, 
    ColdStorageCreateSerializer,
    ColdStorageSummarySerializer,
    InwardEntrySerializer, 
    OutwardEntrySerializer, 
    PersonSerializer
)


class PersonViewSet(viewsets.ModelViewSet):
	queryset = Person.objects.all().order_by('-id')
	serializer_class = PersonSerializer
	permission_classes = [IsOperatorOrHigher]
	http_method_names = ['get', 'post']

	def get_queryset(self):
		qs = super().get_queryset()
		search = self.request.query_params.get('search', '').strip()
		
		if search:
			# Search by name or mobile number
			from django.db.models import Q
			qs = qs.filter(Q(name__icontains=search) | Q(mobile_number__icontains=search))
		
		return qs

	@action(detail=False, methods=['get'], url_path='by-mobile')
	def by_mobile(self, request):
		mobile = (request.query_params.get('mobile_number') or request.query_params.get('mobile') or '').strip()
		if not mobile:
			return Response({'detail': 'mobile_number is required'}, status=status.HTTP_400_BAD_REQUEST)
		person = Person.objects.filter(mobile_number=mobile).first()
		if not person:
			return Response({'detail': 'Person not found'}, status=status.HTTP_404_NOT_FOUND)
		return Response(self.get_serializer(person).data)


class ColdStorageViewSet(viewsets.ModelViewSet):
    """ViewSet for managing cold storages (Owner only)"""
    serializer_class = ColdStorageSerializer
    permission_classes = [IsAdminOrOwner]

    def get_queryset(self):
        user = self.request.user
        # Owners see only their cold storages
        if user.role == 'owner':
            return ColdStorage.objects.filter(owner=user)
        # Admins see all
        return ColdStorage.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return ColdStorageCreateSerializer
        if self.action == 'list_summary':
            return ColdStorageSummarySerializer
        return ColdStorageSerializer

    @action(detail=False, methods=['get'], url_path='summary')
    def list_summary(self, request):
        """Get lightweight list for dropdowns"""
        qs = self.get_queryset().filter(is_active=True)
        serializer = ColdStorageSummarySerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='assign-manager')
    def assign_manager(self, request, pk=None):
        """Assign a manager to the cold storage"""
        cold_storage = self.get_object()
        manager_id = request.data.get('manager_id')
        
        if manager_id:
            from apps.users.models import User
            try:
                manager = User.objects.get(id=manager_id, role='manager', is_active=True)
                cold_storage.manager = manager
            except User.DoesNotExist:
                return Response(
                    {'detail': 'Manager not found or not a valid manager'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            cold_storage.manager = None
        
        cold_storage.save()
        return Response(ColdStorageSerializer(cold_storage).data)


class InwardEntryViewSet(viewsets.ModelViewSet):
	queryset = InwardEntry.objects.select_related('person', 'created_by', 'cold_storage').all().order_by('-id')
	serializer_class = InwardEntrySerializer
	permission_classes = [IsOperatorOrHigher]
	http_method_names = ['get', 'post']
	parser_classes = [JSONParser, FormParser, MultiPartParser]

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)

	@action(detail=False, methods=['get'], url_path='stock')
	def stock(self, request):
		qs = self.get_queryset()
		person_id = request.query_params.get('person')
		crop_name = request.query_params.get('crop')
		cold_storage_id = request.query_params.get('cold_storage')
		search = request.query_params.get('search', '').strip()

		if person_id:
			qs = qs.filter(person_id=person_id)
		if crop_name:
			qs = qs.filter(crop_name__iexact=crop_name)
		if cold_storage_id:
			qs = qs.filter(cold_storage_id=cold_storage_id)
		if search:
			# Search by person name, phone, or crop name
			qs = qs.filter(
				Q(person__name__icontains=search) |
				Q(person__mobile_number__icontains=search) |
				Q(crop_name__icontains=search)
			)

		results = []
		for inward in qs:
			remaining = inward.remaining_quantity
			if remaining <= 0:
				continue
			results.append(
				{
					'id': inward.id,
					'person': inward.person_id,
					'person_name': inward.person.name if inward.person else None,
					'person_phone': inward.person.mobile_number if inward.person else None,
					'cold_storage': inward.cold_storage_id,
					'cold_storage_name': inward.cold_storage.name if inward.cold_storage else None,
					'crop_name': inward.crop_name,
					'crop_variety': inward.crop_variety,
					'packaging_type': inward.packaging_type,
					'quality_grade': inward.quality_grade,
					'quantity': str(inward.quantity),
					'remaining_quantity': str(remaining),
					'storage_room': inward.storage_room,
					'entry_date': str(inward.entry_date) if inward.entry_date else None,
					'expected_storage_duration_days': inward.expected_storage_duration_days,
					'created_at': inward.created_at.isoformat() if inward.created_at else None,
				}
			)
		return Response(results)


class OutwardEntryViewSet(viewsets.ModelViewSet):
	queryset = OutwardEntry.objects.select_related('inward_entry', 'created_by').all().order_by('-id')
	serializer_class = OutwardEntrySerializer
	permission_classes = [IsOperatorOrHigher]
	http_method_names = ['get', 'post']

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		inward = serializer.validated_data['inward_entry']
		qty = serializer.validated_data['quantity']
		if Decimal(qty) <= 0:
			return Response({'detail': 'Quantity must be > 0'}, status=status.HTTP_400_BAD_REQUEST)

		remaining = inward.remaining_quantity
		if qty > remaining:
			return Response(
				{'detail': f'Insufficient stock. Remaining: {remaining}'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		outward = serializer.save(created_by=request.user)
		return Response(self.get_serializer(outward).data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=['get'], url_path='receipt')
	def receipt(self, request, pk=None):
		outward = self.get_object()
		return Response(
			{
				'receipt_number': outward.receipt_number,
				'payment_status': outward.payment_status,
				'payment_method': outward.payment_method,
				'timestamp': outward.created_at,
			}
		)

	@action(detail=True, methods=['post'], url_path='trigger-payment')
	def trigger_payment(self, request, pk=None):
		outward = self.get_object()
		method = (request.data.get('payment_method') or outward.payment_method or '').strip()
		outward.payment_method = method
		outward.payment_status = 'pending'
		outward.save(update_fields=['payment_method', 'payment_status'])

		from apps.payments.models import PaymentRequest

		payment = PaymentRequest.objects.create(
			outward_entry=outward,
			status='requested',
			method=method,
			payload={'mock': True},
		)
		return Response({'detail': 'Payment request triggered (mock)', 'payment_request_id': payment.id})


class OwnerDashboardView(APIView):
    """Owner dashboard with multi-cold-storage overview"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        cold_storage_id = request.query_params.get('cold_storage')
        
        # Get cold storages owned by user
        if user.role == 'owner':
            cold_storages = ColdStorage.objects.filter(owner=user, is_active=True)
        elif user.role in ['admin']:
            cold_storages = ColdStorage.objects.filter(is_active=True)
        else:
            return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        # If specific cold storage requested, filter to that one
        if cold_storage_id:
            cold_storages = cold_storages.filter(id=cold_storage_id)
        
        if not cold_storages.exists():
            return Response({
                'cold_storages': [],
                'stats': None,
                'message': 'No cold storages found. Create one to get started.'
            })
        
        # Get list of cold storages for dropdown
        cold_storage_list = ColdStorageSummarySerializer(cold_storages, many=True).data
        
        # Calculate stats for selected cold storage (first one if not specified)
        selected_cs = cold_storages.first()
        if cold_storage_id:
            selected_cs = cold_storages.filter(id=cold_storage_id).first() or selected_cs
        
        stats = self._calculate_stats(selected_cs)
        
        return Response({
            'cold_storages': cold_storage_list,
            'selected_cold_storage': ColdStorageSerializer(selected_cs).data,
            'stats': stats
        })

    def _calculate_stats(self, cold_storage):
        """Calculate dashboard stats for a cold storage"""
        from apps.temperature.models import TemperatureAlert, AlertStatus
        
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Storage utilization
        total_inward = InwardEntry.objects.filter(cold_storage=cold_storage).aggregate(
            total=Sum('quantity')
        )['total'] or Decimal('0')
        
        total_outward = Decimal('0')
        for inward in InwardEntry.objects.filter(cold_storage=cold_storage):
            total_outward += Decimal(str(inward.outward_total_quantity))
        
        occupied = float(total_inward) - float(total_outward)
        total_capacity = float(cold_storage.total_capacity)
        available = max(0, total_capacity - occupied)
        utilization = round((occupied / total_capacity) * 100, 1) if total_capacity > 0 else 0
        
        # This month inflow/outflow
        month_inward = InwardEntry.objects.filter(
            cold_storage=cold_storage,
            created_at__gte=month_start
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        month_outward = OutwardEntry.objects.filter(
            inward_entry__cold_storage=cold_storage,
            created_at__gte=month_start
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        # Active bookings (current inventory entries with stock remaining)
        active_inwards = InwardEntry.objects.filter(cold_storage=cold_storage)
        active_bookings = 0
        confirmed = 0
        for inward in active_inwards:
            if inward.remaining_quantity > 0:
                active_bookings += 1
                confirmed += 1  # All existing entries are confirmed
        
        pending = InwardEntry.objects.filter(
            cold_storage=cold_storage,
            created_at__gte=now - timedelta(days=7)
        ).count()
        
        # Temperature alerts
        # Note: We'd need to link storage rooms to cold storage for accurate alerts
        active_alerts = TemperatureAlert.objects.filter(
            status=AlertStatus.ACTIVE
        ).count()
        
        temperature_alerts = TemperatureAlert.objects.filter(
            status=AlertStatus.ACTIVE
        ).count()
        
        # Avg storage duration
        avg_duration = InwardEntry.objects.filter(
            cold_storage=cold_storage,
            expected_storage_duration_days__isnull=False
        ).aggregate(avg=Avg('expected_storage_duration_days'))['avg'] or 0
        
        # Estimated revenue (mock calculation: quantity * rate)
        rate_per_mt_per_day = 100  # Rs per MT per day (configurable)
        estimated_revenue = occupied * avg_duration * rate_per_mt_per_day / 100000  # In Lakhs
        
        return {
            'storage': {
                'total_capacity': round(total_capacity, 2),
                'occupied': round(occupied, 2),
                'available': round(available, 2),
                'utilization_percent': utilization,
            },
            'this_month': {
                'inflow': float(month_inward),
                'outflow': float(month_outward),
            },
            'bookings': {
                'active': active_bookings,
                'confirmed': confirmed,
                'pending': pending,
            },
            'alerts': {
                'active': active_alerts,
                'temperature_alerts': temperature_alerts,
                'equipment_status': 'operational',
            },
            'financials': {
                'estimated_revenue': round(estimated_revenue, 2),
                'avg_storage_duration': round(avg_duration) if avg_duration else 0,
            }
        }


class ManagerDashboardView(APIView):
    """Manager dashboard - returns assigned cold storage and stats"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Managers see their assigned cold storages
        if user.role == 'manager':
            cold_storages = ColdStorage.objects.filter(manager=user, is_active=True)
        elif user.role == 'operator':
            # Operators see cold storages where they have inward entries
            # For now, show all active cold storages
            cold_storages = ColdStorage.objects.filter(is_active=True)[:1]
        elif user.role in ['admin', 'owner']:
            cold_storages = ColdStorage.objects.filter(is_active=True)
        else:
            return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        if not cold_storages.exists():
            return Response({
                'cold_storages': [],
                'selected_cold_storage': None,
                'stats': None,
                'message': 'No cold storages assigned. Contact your owner.'
            })
        
        # Get list of cold storages for dropdown
        cold_storage_list = ColdStorageSummarySerializer(cold_storages, many=True).data
        
        # Select first cold storage for stats
        selected_cs = cold_storages.first()
        cold_storage_id = request.query_params.get('cold_storage')
        if cold_storage_id:
            selected_cs = cold_storages.filter(id=cold_storage_id).first() or selected_cs
        
        stats = self._calculate_stats(selected_cs)
        
        return Response({
            'cold_storages': cold_storage_list,
            'selected_cold_storage': ColdStorageSerializer(selected_cs).data if selected_cs else None,
            'stats': stats
        })

    def _calculate_stats(self, cold_storage):
        """Calculate dashboard stats for a cold storage"""
        if not cold_storage:
            return None
            
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Storage utilization
        total_inward = InwardEntry.objects.filter(cold_storage=cold_storage).aggregate(
            total=Sum('quantity')
        )['total'] or Decimal('0')
        
        total_outward = Decimal('0')
        for inward in InwardEntry.objects.filter(cold_storage=cold_storage):
            total_outward += Decimal(str(inward.outward_total_quantity))
        
        occupied = float(total_inward) - float(total_outward)
        total_capacity = float(cold_storage.total_capacity)
        available = max(0, total_capacity - occupied)
        utilization = round((occupied / total_capacity) * 100, 1) if total_capacity > 0 else 0
        
        # This month inflow/outflow
        month_inward = InwardEntry.objects.filter(
            cold_storage=cold_storage,
            created_at__gte=month_start
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        month_outward = OutwardEntry.objects.filter(
            inward_entry__cold_storage=cold_storage,
            created_at__gte=month_start
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        # Active bookings (current inventory entries with stock remaining)
        active_inwards = InwardEntry.objects.filter(cold_storage=cold_storage)
        active_bookings = 0
        for inward in active_inwards:
            if inward.remaining_quantity > 0:
                active_bookings += 1
        
        return {
            'storage': {
                'total_capacity': round(total_capacity, 2),
                'occupied': round(occupied, 2),
                'available': round(available, 2),
                'utilization_percent': utilization,
            },
            'this_month': {
                'inflow': float(month_inward),
                'outflow': float(month_outward),
            },
            'active_bookings': active_bookings,
        }
