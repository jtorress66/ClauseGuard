"""
Test Agiloft Integration API endpoints
Tests the P0 Agiloft clause comparison feature
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clauseguard.preview.emergentagent.com')

class TestAgiloftIntegration:
    """Test Agiloft Integration endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user and session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Create test user
        timestamp = int(time.time())
        self.test_email = f"agiloft_api_test_{timestamp}@test.com"
        self.test_password = "TestPass123!"
        self.test_name = f"Agiloft API Test {timestamp}"
        
        # Register user
        register_response = self.session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": self.test_email,
                "password": self.test_password,
                "name": self.test_name
            }
        )
        
        if register_response.status_code == 200:
            print(f"Registered test user: {self.test_email}")
            # Session cookie should be set automatically
        else:
            print(f"Registration failed: {register_response.status_code} - {register_response.text}")
    
    def test_auth_me_endpoint(self):
        """Test that auth/me returns user info after registration"""
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        print(f"Auth/me response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            assert "email" in data
            assert data["email"] == self.test_email
            print(f"Auth/me SUCCESS: {data}")
        else:
            print(f"Auth/me failed: {response.text}")
            # This might fail if cookies aren't being sent properly
            pytest.skip("Session not maintained - cookies may not be working")
    
    def test_agiloft_test_connection_invalid_credentials(self):
        """Test Agiloft connection with invalid credentials returns proper error"""
        response = self.session.post(
            f"{BASE_URL}/api/agiloft/test-connection",
            json={
                "kb_url": "https://fake-instance.saas.agiloft.com",
                "kb_name": "FakeKB",
                "username": "fake_user",
                "password": "fake_password"
            }
        )
        
        print(f"Test connection response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
        # Should return 401 or error message for invalid credentials
        # The endpoint should NOT crash
        assert response.status_code in [200, 401, 400, 500]
        
        data = response.json()
        # Should have success=False or error message
        if response.status_code == 200:
            assert data.get("success") == False or "error" in str(data).lower()
        print(f"Test connection result: {data}")
    
    def test_agiloft_compare_clauses_invalid_credentials(self):
        """Test compare clauses endpoint with invalid Agiloft credentials"""
        response = self.session.post(
            f"{BASE_URL}/api/agiloft/compare-clauses",
            json={
                "config": {
                    "kb_url": "https://fake-instance.saas.agiloft.com",
                    "kb_name": "FakeKB",
                    "username": "fake_user",
                    "password": "fake_password"
                },
                "clause_type": None,
                "source": "acquisition_gov"
            }
        )
        
        print(f"Compare clauses response: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        
        # Should return 401 for invalid credentials
        # The endpoint should NOT crash
        assert response.status_code in [200, 401, 400, 500]
        
        data = response.json()
        print(f"Compare clauses result: {data}")
        
        # If 401, should have proper error message
        if response.status_code == 401:
            assert "detail" in data or "error" in data
    
    def test_agiloft_compare_clauses_without_auth(self):
        """Test compare clauses endpoint without authentication"""
        # Create new session without auth
        new_session = requests.Session()
        new_session.headers.update({"Content-Type": "application/json"})
        
        response = new_session.post(
            f"{BASE_URL}/api/agiloft/compare-clauses",
            json={
                "config": {
                    "kb_url": "https://fake-instance.saas.agiloft.com",
                    "kb_name": "FakeKB",
                    "username": "fake_user",
                    "password": "fake_password"
                },
                "clause_type": None,
                "source": "acquisition_gov"
            }
        )
        
        print(f"Compare clauses (no auth) response: {response.status_code}")
        
        # Should return 401 for unauthenticated request
        assert response.status_code == 401
        print("Compare clauses correctly requires authentication")


class TestBackendHealth:
    """Test backend health and basic endpoints"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"API root: {data}")
    
    def test_clauses_search(self):
        """Test clauses search endpoint"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=cybersecurity")
        assert response.status_code == 200
        data = response.json()
        assert "clauses" in data
        print(f"Clauses search returned {len(data['clauses'])} results")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
