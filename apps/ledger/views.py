from decimal import Decimal

from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsManagerOrAdmin
from apps.inventory.models import InwardEntry, OutwardEntry


class LedgerView(APIView):
	permission_classes = [IsAuthenticated, IsManagerOrAdmin]

	def get(self, request):
		qp = request.query_params
		date_from = qp.get('date_from')
		date_to = qp.get('date_to')
		person_id = qp.get('person')
		crop = qp.get('crop')

		inwards = InwardEntry.objects.select_related('person').all()
		outwards = OutwardEntry.objects.select_related('inward_entry__person').all()

		if person_id:
			inwards = inwards.filter(person_id=person_id)
			outwards = outwards.filter(inward_entry__person_id=person_id)
		if crop:
			inwards = inwards.filter(crop_name__iexact=crop)
			outwards = outwards.filter(inward_entry__crop_name__iexact=crop)

		if date_from:
			dt = parse_datetime(date_from) or None
			if dt:
				inwards = inwards.filter(created_at__gte=dt)
				outwards = outwards.filter(created_at__gte=dt)
		if date_to:
			dt = parse_datetime(date_to) or None
			if dt:
				inwards = inwards.filter(created_at__lte=dt)
				outwards = outwards.filter(created_at__lte=dt)

		entries = []
		inward_total = Decimal('0')
		outward_total = Decimal('0')

		for i in inwards.order_by('created_at'):
			inward_total += i.quantity
			entries.append(
				{
					'type': 'inward',
					'timestamp': i.created_at,
					'person': {'id': i.person_id, 'name': i.person.name, 'mobile_number': i.person.mobile_number},
					'crop_name': i.crop_name,
					'crop_variety': i.crop_variety,
					'quantity': i.quantity,
					'packaging_type': i.packaging_type,
					'reference': {'inward_entry_id': i.id},
				}
			)

		for o in outwards.order_by('created_at'):
			outward_total += o.quantity
			i = o.inward_entry
			p = i.person
			entries.append(
				{
					'type': 'outward',
					'timestamp': o.created_at,
					'person': {'id': p.id, 'name': p.name, 'mobile_number': p.mobile_number},
					'crop_name': i.crop_name,
					'crop_variety': i.crop_variety,
					'quantity': o.quantity,
					'packaging_type': o.packaging_type,
					'receipt_number': o.receipt_number,
					'payment_status': o.payment_status,
					'payment_method': o.payment_method,
					'reference': {'outward_entry_id': o.id, 'inward_entry_id': i.id},
				}
			)

		entries.sort(key=lambda e: e['timestamp'])

		return Response(
			{
				'filters': {'date_from': date_from, 'date_to': date_to, 'person': person_id, 'crop': crop},
				'totals': {
					'inward_quantity_total': inward_total,
					'outward_quantity_total': outward_total,
					'net_quantity': inward_total - outward_total,
				},
				'entries': entries,
			}
		)
