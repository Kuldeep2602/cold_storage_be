from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.inventory.models import InwardEntry, Person
from apps.users.models import User, UserRole


class LedgerApiTests(APITestCase):
	def auth_header_for(self, user: User):
		token = RefreshToken.for_user(user).access_token
		return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

	def test_ledger_fetch(self):
		manager = User.objects.create_user(phone_number='9000000020', role=UserRole.MANAGER)
		operator = User.objects.create_user(phone_number='9000000021', role=UserRole.OPERATOR)

		person = Person.objects.create(person_type='farmer', name='Ledger Farmer', mobile_number='9222222222', address='X')
		InwardEntry.objects.create(
			person=person,
			crop_name='Onion',
			crop_variety='B',
			size_grade='M',
			quantity='10.000',
			packaging_type='box',
			quality_rating=4,
			rack_number='R2',
			created_by=operator,
		)

		resp = self.client.get('/api/ledger/', **self.auth_header_for(manager))
		self.assertEqual(resp.status_code, 200)
		self.assertIn('totals', resp.data)
		self.assertGreaterEqual(len(resp.data['entries']), 1)
