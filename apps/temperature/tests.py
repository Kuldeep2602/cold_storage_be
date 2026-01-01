from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User, UserRole


class TemperatureApiTests(APITestCase):
	def auth_header_for(self, user: User):
		token = RefreshToken.for_user(user).access_token
		return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

	def test_operator_add_manager_edit(self):
		operator = User.objects.create_user(phone_number='9000000030', role=UserRole.OPERATOR)
		manager = User.objects.create_user(phone_number='9000000031', role=UserRole.MANAGER)

		create_resp = self.client.post(
			'/api/temperature/logs/',
			data={'logged_at': timezone.now().isoformat(), 'temperature': '4.25'},
			format='json',
			**self.auth_header_for(operator),
		)
		self.assertEqual(create_resp.status_code, 201)
		log_id = create_resp.data['id']

		edit_resp = self.client.patch(
			f'/api/temperature/logs/{log_id}/',
			data={'temperature': '5.00'},
			format='json',
			**self.auth_header_for(manager),
		)
		self.assertEqual(edit_resp.status_code, 200)
		self.assertEqual(str(edit_resp.data['temperature']), '5.00')
