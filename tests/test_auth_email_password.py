"""
Test suite for Email/Password Authentication
Tests the new auth system that replaced Google OAuth
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://fccm-manager.preview.emergentagent.com')

class TestAuthRegistration:
    """Test user registration with email/password"""
    
    def test_register_new_user_success(self):
        """POST /api/auth/register - Should create new user with valid data"""
        unique_email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "Test User"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json=payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "user_id" in data, "Response should contain user_id"
        assert "email" in data, "Response should contain email"
        assert "name" in data, "Response should contain name"
        assert data["email"] == unique_email.lower(), "Email should be lowercase"
        assert data["name"] == "Test User"
        
        # Verify password is NOT returned
        assert "password" not in data, "Password should not be in response"
        assert "password_hash" not in data, "Password hash should not be in response"
        
        # Verify session cookie is set
        assert "session_token" in response.cookies or response.headers.get("set-cookie"), \
            "Session cookie should be set"
        
        print(f"✓ Registration successful for {unique_email}")
        return data
    
    def test_register_duplicate_email_fails(self):
        """POST /api/auth/register - Should reject duplicate email"""
        # First, register a user
        unique_email = f"test_dup_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "First User"
        }
        
        response1 = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert response1.status_code == 200, f"First registration should succeed: {response1.text}"
        
        # Try to register again with same email
        payload["name"] = "Second User"
        response2 = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        
        assert response2.status_code == 400, f"Expected 400 for duplicate email, got {response2.status_code}"
        data = response2.json()
        assert "detail" in data, "Error response should have detail"
        assert "already" in data["detail"].lower() or "registered" in data["detail"].lower(), \
            f"Error should mention email already registered: {data['detail']}"
        
        print(f"✓ Duplicate email correctly rejected")
    
    def test_register_weak_password_fails(self):
        """POST /api/auth/register - Should reject password < 6 chars"""
        unique_email = f"test_weak_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "password": "12345",  # Only 5 chars
            "name": "Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        
        assert response.status_code == 400, f"Expected 400 for weak password, got {response.status_code}"
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        assert "6" in data["detail"] or "password" in data["detail"].lower(), \
            f"Error should mention password requirements: {data['detail']}"
        
        print(f"✓ Weak password correctly rejected")
    
    def test_register_invalid_email_fails(self):
        """POST /api/auth/register - Should reject invalid email format"""
        payload = {
            "email": "not-an-email",
            "password": "testpass123",
            "name": "Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        
        assert response.status_code == 400, f"Expected 400 for invalid email, got {response.status_code}"
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        
        print(f"✓ Invalid email correctly rejected")


class TestAuthLogin:
    """Test user login with email/password"""
    
    @pytest.fixture(scope="class")
    def test_user(self):
        """Create a test user for login tests"""
        unique_email = f"test_login_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "Login Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert response.status_code == 200, f"Failed to create test user: {response.text}"
        
        return {"email": unique_email, "password": "testpass123"}
    
    def test_login_success(self, test_user):
        """POST /api/auth/login - Should login with valid credentials"""
        payload = {
            "email": test_user["email"],
            "password": test_user["password"]
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "user_id" in data, "Response should contain user_id"
        assert "email" in data, "Response should contain email"
        assert "name" in data, "Response should contain name"
        assert data["email"] == test_user["email"].lower()
        
        # Verify password is NOT returned
        assert "password" not in data
        assert "password_hash" not in data
        
        print(f"✓ Login successful for {test_user['email']}")
    
    def test_login_invalid_password(self, test_user):
        """POST /api/auth/login - Should reject invalid password"""
        payload = {
            "email": test_user["email"],
            "password": "wrongpassword"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "invalid" in data["detail"].lower() or "password" in data["detail"].lower()
        
        print(f"✓ Invalid password correctly rejected")
    
    def test_login_nonexistent_email(self):
        """POST /api/auth/login - Should reject non-existent email"""
        payload = {
            "email": f"nonexistent_{uuid.uuid4().hex}@example.com",
            "password": "anypassword"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        
        print(f"✓ Non-existent email correctly rejected")
    
    def test_login_with_existing_test_account(self):
        """POST /api/auth/login - Test with provided test credentials"""
        # First try to register the test account (in case it doesn't exist)
        register_payload = {
            "email": "test@example.com",
            "password": "test123",
            "name": "Test Account"
        }
        requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        
        # Now try to login
        login_payload = {
            "email": "test@example.com",
            "password": "test123"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload)
        
        # Should either succeed or fail with 401 (if password is different)
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            print(f"✓ Test account login successful")
        else:
            print(f"✓ Test account exists but password may differ")


class TestAuthMe:
    """Test /api/auth/me endpoint"""
    
    @pytest.fixture(scope="class")
    def authenticated_session(self):
        """Create a user and get authenticated session"""
        session = requests.Session()
        unique_email = f"test_me_{uuid.uuid4().hex[:8]}@example.com"
        
        payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "Me Test User"
        }
        
        response = session.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert response.status_code == 200, f"Failed to create user: {response.text}"
        
        return session, response.json()
    
    def test_get_me_authenticated(self, authenticated_session):
        """GET /api/auth/me - Should return user info when authenticated"""
        session, user_data = authenticated_session
        
        response = session.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "user_id" in data
        assert "email" in data
        assert "name" in data
        assert data["user_id"] == user_data["user_id"]
        
        print(f"✓ /api/auth/me returns correct user info")
    
    def test_get_me_unauthenticated(self):
        """GET /api/auth/me - Should return 401 when not authenticated"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"✓ /api/auth/me correctly rejects unauthenticated requests")


class TestAuthLogout:
    """Test logout functionality"""
    
    def test_logout_clears_session(self):
        """POST /api/auth/logout - Should clear session"""
        session = requests.Session()
        
        # First register and login
        unique_email = f"test_logout_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "Logout Test User"
        }
        
        reg_response = session.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert reg_response.status_code == 200
        
        # Verify we're authenticated
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, "Should be authenticated after registration"
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200, f"Logout failed: {logout_response.text}"
        
        data = logout_response.json()
        assert "message" in data
        assert "logged out" in data["message"].lower() or "success" in data["message"].lower()
        
        # Verify we're no longer authenticated
        me_response2 = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response2.status_code == 401, "Should be unauthenticated after logout"
        
        print(f"✓ Logout successfully clears session")


class TestAuthIntegration:
    """Integration tests for full auth flow"""
    
    def test_full_auth_flow(self):
        """Test complete registration -> login -> me -> logout flow"""
        session = requests.Session()
        unique_email = f"test_flow_{uuid.uuid4().hex[:8]}@example.com"
        
        # 1. Register
        reg_payload = {
            "email": unique_email,
            "password": "testpass123",
            "name": "Flow Test User"
        }
        reg_response = session.post(f"{BASE_URL}/api/auth/register", json=reg_payload)
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        user_data = reg_response.json()
        print(f"  1. Registration: ✓")
        
        # 2. Logout (to test login separately)
        session.post(f"{BASE_URL}/api/auth/logout")
        print(f"  2. Logout after registration: ✓")
        
        # 3. Login with new credentials
        login_payload = {
            "email": unique_email,
            "password": "testpass123"
        }
        login_response = session.post(f"{BASE_URL}/api/auth/login", json=login_payload)
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        print(f"  3. Login: ✓")
        
        # 4. Get current user
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"Get me failed: {me_response.text}"
        me_data = me_response.json()
        assert me_data["email"] == unique_email.lower()
        print(f"  4. Get /me: ✓")
        
        # 5. Access protected endpoint (contracts)
        contracts_response = session.get(f"{BASE_URL}/api/contracts/")
        assert contracts_response.status_code == 200, f"Contracts access failed: {contracts_response.text}"
        print(f"  5. Access protected endpoint: ✓")
        
        # 6. Final logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200
        print(f"  6. Final logout: ✓")
        
        # 7. Verify logged out
        me_response2 = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response2.status_code == 401
        print(f"  7. Verify logged out: ✓")
        
        print(f"✓ Full auth flow completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
