from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserRole


class UserApiTests(APITestCase):
	def auth_header_for(self, user: User):
		token = RefreshToken.for_user(user).access_token
		return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

	def test_user_creation_by_manager(self):
		manager = User.objects.create_user(phone_number='9000000001', role=UserRole.MANAGER)

		resp = self.client.post(
			'/api/users/',
			data={'phone_number': '9000000002', 'role': UserRole.OPERATOR, 'is_active': True},
			format='json',
			**self.auth_header_for(manager),
		)
		self.assertEqual(resp.status_code, 201)
		self.assertEqual(resp.data['phone_number'], '9000000002')
