from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User, UserRole


class InventoryApiTests(APITestCase):
	def auth_header_for(self, user: User):
		token = RefreshToken.for_user(user).access_token
		return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

	def test_inward_and_outward_flow(self):
		operator = User.objects.create_user(phone_number='9000000010', role=UserRole.OPERATOR)

		person_resp = self.client.post(
			'/api/inventory/persons/',
			data={
				'person_type': 'farmer',
				'name': 'Test Farmer',
				'mobile_number': '9111111111',
				'address': 'Village',
			},
			format='json',
			**self.auth_header_for(operator),
		)
		self.assertEqual(person_resp.status_code, 201)
		person_id = person_resp.data['id']

		inward_resp = self.client.post(
			'/api/inventory/inwards/',
			data={
				'person': person_id,
				'crop_name': 'Potato',
				'crop_variety': 'A',
				'size_grade': 'Large',
				'quantity': '100.000',
				'packaging_type': 'crate',
				'quality_rating': 5,
				'rack_number': 'R1',
			},
			format='json',
			**self.auth_header_for(operator),
		)
		self.assertEqual(inward_resp.status_code, 201)
		inward_id = inward_resp.data['id']

		outward_resp = self.client.post(
			'/api/inventory/outwards/',
			data={
				'inward_entry': inward_id,
				'quantity': '25.000',
				'packaging_type': 'crate',
				'payment_method': 'cash',
			},
			format='json',
			**self.auth_header_for(operator),
		)
		self.assertEqual(outward_resp.status_code, 201)
		self.assertTrue(outward_resp.data['receipt_number'])
