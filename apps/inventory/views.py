from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.users.permissions import IsOperatorOrHigher

from .models import InwardEntry, OutwardEntry, Person
from .serializers import InwardEntrySerializer, OutwardEntrySerializer, PersonSerializer


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


class InwardEntryViewSet(viewsets.ModelViewSet):
	queryset = InwardEntry.objects.select_related('person', 'created_by').all().order_by('-id')
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

		if person_id:
			qs = qs.filter(person_id=person_id)
		if crop_name:
			qs = qs.filter(crop_name__iexact=crop_name)

		results = []
		for inward in qs:
			remaining = inward.remaining_quantity
			if remaining <= 0:
				continue
			results.append(
				{
					'id': inward.id,
					'person': inward.person_id,
					'crop_name': inward.crop_name,
					'crop_variety': inward.crop_variety,
					'packaging_type': inward.packaging_type,
					'quantity': inward.quantity,
					'remaining_quantity': remaining,
					'created_at': inward.created_at,
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
