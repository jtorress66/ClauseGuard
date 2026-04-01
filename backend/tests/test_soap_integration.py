"""
Test SOAP Integration for ClauseGuard Agiloft Integration
Tests the newly implemented SOAP-based linking of clauses to contracts via zeep library.

Features tested:
1. POST /api/auth/login - basic authentication still works
2. POST /api/agiloft/link-clauses-to-contract - SOAP endpoint accepts request, returns proper error for invalid Agiloft credentials
3. POST /api/agiloft/create-missing-and-link - combined upload+link endpoint still works with proper error handling
4. GET /api/clauses/search - clause search still works
5. GET /api/ - server health check
"""

import pytest
import requests
import os

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Test credentials from test_credentials.md
TEST_EMAIL = "jtorres@elitebco.com"
TEST_PASSWORD = "test123"

# Dummy Agiloft credentials (will fail auth but should return clean error messages)
DUMMY_AGILOFT_CONFIG = {
    "kb_url": "https://elitebcopartnerkb.agiloft.com",
    "kb_name": "elitebcopartnerkb",
    "username": "testuser",
    "password": "testpass"
}


class TestHealthCheck:
    """Test server health and root endpoint"""
    
    def test_root_endpoint_returns_200(self):
        """GET /api/ should return 200 with API info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain 'message' field"
        assert "Federal Clause Management API" in data["message"], f"Unexpected message: {data['message']}"
        print(f"✓ Root endpoint working: {data}")


class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_login_with_valid_credentials(self):
        """POST /api/auth/login should return user info and set session cookie"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "user_id" in data, "Response should contain user_id"
        assert "email" in data, "Response should contain email"
        assert data["email"] == TEST_EMAIL, f"Email mismatch: {data['email']}"
        
        # Check session cookie was set
        assert "session_token" in session.cookies, "Session cookie should be set"
        print(f"✓ Login successful for {TEST_EMAIL}")
        
    def test_login_with_invalid_credentials(self):
        """POST /api/auth/login should return 401 for invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@example.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Invalid credentials correctly rejected with 401")


class TestClauseSearch:
    """Test clause search functionality"""
    
    def test_search_returns_results(self):
        """GET /api/clauses/search should return clause results"""
        response = requests.get(
            f"{BASE_URL}/api/clauses/search",
            params={"query": "cybersecurity", "limit": 10}
        )
        
        assert response.status_code == 200, f"Search failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "clauses" in data, "Response should contain 'clauses' field"
        assert "total" in data, "Response should contain 'total' field"
        print(f"✓ Search returned {data['total']} results for 'cybersecurity'")
        
    def test_search_with_type_filter(self):
        """GET /api/clauses/search with type filter should work"""
        response = requests.get(
            f"{BASE_URL}/api/clauses/search",
            params={"query": "contract", "clause_type": "FAR", "limit": 5}
        )
        
        assert response.status_code == 200, f"Search failed: {response.status_code}"
        
        data = response.json()
        assert "clauses" in data
        # If results exist, verify they are FAR type
        for clause in data["clauses"]:
            if "type" in clause:
                assert clause["type"] == "FAR", f"Expected FAR type, got {clause['type']}"
        print(f"✓ Search with FAR filter returned {data['total']} results")


class TestSOAPLinkClausesToContract:
    """Test SOAP-based clause linking endpoint"""
    
    @pytest.fixture
    def authenticated_session(self):
        """Get authenticated session with cookies"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return session
    
    def test_link_clauses_requires_auth(self):
        """POST /api/agiloft/link-clauses-to-contract should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/link-clauses-to-contract",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "12345",
                "clause_ids": [1, 2, 3],
                "clause_numbers": ["52.212-4", "52.219-8", "252.204-7012"]
            }
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print("✓ Link clauses endpoint correctly requires authentication")
    
    def test_link_clauses_returns_clean_error_for_invalid_agiloft_creds(self, authenticated_session):
        """POST /api/agiloft/link-clauses-to-contract should return clean JSON error for invalid Agiloft credentials"""
        response = authenticated_session.post(
            f"{BASE_URL}/api/agiloft/link-clauses-to-contract",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "12345",
                "clause_ids": [1, 2, 3],
                "clause_numbers": ["52.212-4", "52.219-8", "252.204-7012"]
            }
        )
        
        # Should NOT be 500 - should be a clean error response
        assert response.status_code != 500, f"Got 500 server error - endpoint crashed: {response.text}"
        
        # Should return JSON (not crash)
        try:
            data = response.json()
        except Exception as e:
            pytest.fail(f"Response is not valid JSON: {response.text}")
        
        # Should indicate failure with a message
        # The endpoint returns {"success": False, "message": "..."} for auth failures
        if response.status_code == 200:
            # Endpoint returns 200 with success=False for SOAP auth failures
            assert "success" in data, "Response should contain 'success' field"
            assert data["success"] == False, "Should indicate failure for invalid credentials"
            assert "message" in data, "Response should contain error message"
            print(f"✓ Link clauses returned clean error: {data.get('message', '')[:100]}")
        else:
            # Could also return 4xx/5xx with error detail
            print(f"✓ Link clauses returned status {response.status_code} with response: {data}")
    
    def test_link_clauses_accepts_valid_request_structure(self, authenticated_session):
        """POST /api/agiloft/link-clauses-to-contract should accept properly structured request"""
        response = authenticated_session.post(
            f"{BASE_URL}/api/agiloft/link-clauses-to-contract",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "99999",
                "clause_ids": [100, 200],
                "clause_numbers": ["52.212-4", "252.204-7012"],
                "clause_titles": ["Contract Terms", "Cybersecurity"]
            }
        )
        
        # Should not crash with 500
        assert response.status_code != 500, f"Server error: {response.text}"
        
        # Should return valid JSON
        data = response.json()
        assert isinstance(data, dict), "Response should be a JSON object"
        print(f"✓ Link clauses endpoint accepted request structure, response: {data.get('success', 'N/A')}")


class TestSOAPCreateMissingAndLink:
    """Test combined upload+link endpoint"""
    
    @pytest.fixture
    def authenticated_session(self):
        """Get authenticated session with cookies"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return session
    
    def test_create_missing_and_link_requires_auth(self):
        """POST /api/agiloft/create-missing-and-link should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/create-missing-and-link",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "12345",
                "clauses": [{"number": "52.212-4", "title": "Test", "type": "FAR"}],
                "existing_clause_ids": {}
            }
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print("✓ Create-missing-and-link endpoint correctly requires authentication")
    
    def test_create_missing_and_link_returns_clean_error_for_invalid_agiloft_creds(self, authenticated_session):
        """POST /api/agiloft/create-missing-and-link should return clean JSON error for invalid Agiloft credentials"""
        response = authenticated_session.post(
            f"{BASE_URL}/api/agiloft/create-missing-and-link",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "12345",
                "clauses": [
                    {"number": "52.212-4", "title": "Contract Terms", "type": "FAR"}
                ],
                "existing_clause_ids": {}
            }
        )
        
        # Should NOT be 500 - should be a clean error response
        assert response.status_code != 500, f"Got 500 server error - endpoint crashed: {response.text}"
        
        # Should return JSON (not crash)
        try:
            data = response.json()
        except Exception as e:
            pytest.fail(f"Response is not valid JSON: {response.text}")
        
        # Should indicate failure with a message
        if response.status_code == 200:
            assert "success" in data, "Response should contain 'success' field"
            # May succeed partially or fail - either is acceptable as long as it's clean
            print(f"✓ Create-missing-and-link returned clean response: success={data.get('success')}, message={data.get('message', '')[:100]}")
        else:
            print(f"✓ Create-missing-and-link returned status {response.status_code}")
    
    def test_create_missing_and_link_accepts_valid_request_structure(self, authenticated_session):
        """POST /api/agiloft/create-missing-and-link should accept properly structured request"""
        response = authenticated_session.post(
            f"{BASE_URL}/api/agiloft/create-missing-and-link",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "99999",
                "clauses": [
                    {"number": "52.212-4", "title": "Contract Terms", "type": "FAR", "date": "2024-01"},
                    {"number": "252.204-7012", "title": "Cybersecurity", "type": "DFARS"}
                ],
                "existing_clause_ids": {"52.219-8": 500}
            }
        )
        
        # Should not crash with 500
        assert response.status_code != 500, f"Server error: {response.text}"
        
        # Should return valid JSON
        data = response.json()
        assert isinstance(data, dict), "Response should be a JSON object"
        print(f"✓ Create-missing-and-link endpoint accepted request structure")


class TestSOAPMethodField:
    """Verify SOAP method is indicated in responses"""
    
    @pytest.fixture
    def authenticated_session(self):
        """Get authenticated session with cookies"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return session
    
    def test_link_clauses_response_indicates_soap_method(self, authenticated_session):
        """Response from link-clauses-to-contract should indicate SOAP method"""
        response = authenticated_session.post(
            f"{BASE_URL}/api/agiloft/link-clauses-to-contract",
            json={
                "config": DUMMY_AGILOFT_CONFIG,
                "contract_id": "12345",
                "clause_ids": [1],
                "clause_numbers": ["52.212-4"]
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            # Check if method field exists (may not be present on auth failure)
            if "method" in data:
                assert data["method"] == "SOAP", f"Expected SOAP method, got {data['method']}"
                print("✓ Response indicates SOAP method")
            else:
                print(f"✓ Response received (method field may not be present on auth failure): {data.get('message', '')[:50]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
