import urllib.request
import urllib.parse
import json
import sys

BASE_URL = 'http://127.0.0.1:8000'
PHONE = '+1234567890'

def request_json(url, method='GET', data=None, headers=None):
    if headers is None:
        headers = {}
    
    headers['Content-Type'] = 'application/json'
    
    if data:
        data_bytes = json.dumps(data).encode('utf-8')
    else:
        data_bytes = None

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            resp_body = response.read().decode('utf-8')
            return response.status, json.loads(resp_body)
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {resp_body}")
        return e.code, json.loads(resp_body) if resp_body else {}
    except Exception as e:
        print(f"Error: {e}")
        return None, None

def test_auth():
    print("Testing Auth Flow...")
    
    # 1. Request OTP
    print(f"Requesting OTP for {PHONE}...")
    status, data = request_json(f"{BASE_URL}/api/auth/request-otp/", method='POST', data={'phone_number': PHONE})
    
    if status != 200:
        print("Failed to request OTP")
        return

    otp = data.get('otp_code')
    # If OTP_DEBUG_RETURN_CODE is False, we won't get it. But we assume it is True.
    # If not, let's try '123456' or similar if there was a hardcoded fallback, but usually distinct.
    if not otp:
        print("OTP not returned. Cannot proceed with automatic verification.")
        print(f"Response: {data}")
        return
        
    print(f"OTP Received: {otp}")
    
    # 2. Verify OTP
    print("Verifying OTP...")
    status, tokens = request_json(f"{BASE_URL}/api/auth/verify-otp/", method='POST', data={'phone_number': PHONE, 'code': otp})
    
    if status != 200:
        print("Failed to verify OTP")
        return

    access_token = tokens.get('access')
    if not access_token:
        print("No access token found")
        return
        
    print("Access Token Received")
    
    # 3. Get User Me
    print("Fetching User Profile...")
    headers = {'Authorization': f'Bearer {access_token}'}
    status, user_data = request_json(f"{BASE_URL}/api/users/me/", headers=headers)
    
    if status != 200:
        print("Failed to fetch user profile")
        return
        
    print(f"User Data: {user_data}")
    print("\nSUCCESS: Backend is running and auth flow works!")

if __name__ == "__main__":
    test_auth()
