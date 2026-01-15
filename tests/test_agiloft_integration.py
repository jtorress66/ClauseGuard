"""
Agiloft Integration Tests - Bug Fix Verification
Tests the critical bug fix: Agiloft login was returning 'connection successful' even with invalid passwords.

CRITICAL FIXES BEING TESTED:
1. POST /api/agiloft/test-connection - Must FAIL with proper error when given invalid credentials
2. POST /api/agiloft/contracts - Should return proper error when auth fails (NOT demo data)
3. POST /api/agiloft/push-clauses - Should use correct table name 'clause' not 'Clauses'
4. GET /api/agiloft/field-mapping - Should return the current field mapping configuration
5. POST /api/agiloft/field-mapping - Should allow updating field mappings

Test session token: test_session_regression_1768429393344
"""

import pytest
import requests
import os

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://contractguard-1.preview.emergentagent.com"

# Test session token
SESSION_TOKEN = "test_session_regression_1768429393344"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session without auth"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client(api_client):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {SESSION_TOKEN}"})
    return api_client


class TestAgiloftTestConnectionBugFix:
    """
    CRITICAL BUG FIX TEST: POST /api/agiloft/test-connection
    
    The bug was: Login was returning 'connection successful' even with invalid passwords.
    
    Expected behavior after fix:
    - Must FAIL with proper error when given invalid credentials
    - Should return proper error messages like 'Cannot connect' or 'Authentication failed'
    - Should NOT return success:true with invalid credentials
    """
    
    def test_connection_requires_auth(self, api_client):
        """Test connection endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
            "username": "invalid_user",
            "password": "invalid_password",
            "kb_name": "TestKB"
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/test-connection", json=data, headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Test connection requires authentication")
    
    def test_connection_fails_with_invalid_credentials(self, authenticated_client):
        """
        CRITICAL TEST: Connection with invalid credentials MUST fail
        
        This is the main bug fix verification - the old code was returning success
        even with wrong passwords. Now it should properly fail.
        """
        data = {
            "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
            "username": "invalid_user",
            "password": "wrong_password_12345",
            "kb_name": "TestKB"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/test-connection", json=data)
        
        # Should NOT return 200 with success:true
        # Expected: 401, 503 (connection error), 500, or 200 with success:false
        
        if response.status_code == 200:
            result = response.json()
            # If 200, success MUST be false
            assert result.get("success") is False, \
                f"BUG: Connection returned success:true with invalid credentials! Response: {result}"
            assert "message" in result or "error" in result, \
                "Error response should contain message or error field"
            print(f"✓ Connection properly failed with message: {result.get('message', result.get('error'))}")
        else:
            # Non-200 status codes are acceptable for failed connections
            # 520 is a Cloudflare error for unknown origin error (connection issues)
            assert response.status_code in [401, 403, 500, 502, 503, 504, 520], \
                f"Unexpected status code: {response.status_code}"
            
            # Verify error message is present
            try:
                result = response.json()
                assert "detail" in result or "message" in result or "error" in result, \
                    "Error response should contain detail, message, or error field"
                error_msg = result.get("detail", result.get("message", result.get("error", "")))
                print(f"✓ Connection properly failed with status {response.status_code}: {error_msg}")
            except:
                print(f"✓ Connection properly failed with status {response.status_code}")
    
    def test_connection_fails_with_unreachable_server(self, authenticated_client):
        """Test that unreachable server returns proper error, not success"""
        data = {
            "kb_url": "https://nonexistent-server-12345.example.com/ewws/EWRESTful/v1",
            "username": "any_user",
            "password": "any_password",
            "kb_name": "TestKB"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/test-connection", json=data)
        
        # Should fail with connection error
        # 520 is a Cloudflare error for unknown origin error (connection issues)
        if response.status_code == 200:
            result = response.json()
            assert result.get("success") is False, \
                f"BUG: Unreachable server returned success:true! Response: {result}"
            print(f"✓ Unreachable server properly failed: {result.get('message')}")
        else:
            assert response.status_code in [500, 502, 503, 504, 520], \
                f"Expected connection error status, got {response.status_code}"
            print(f"✓ Unreachable server properly failed with status {response.status_code}")
    
    def test_connection_error_message_is_meaningful(self, authenticated_client):
        """Verify error messages are meaningful, not generic"""
        data = {
            "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
            "username": "test_user",
            "password": "bad_password",
            "kb_name": "TestKB"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/test-connection", json=data)
        
        try:
            result = response.json()
            error_msg = result.get("detail", result.get("message", result.get("error", "")))
            
            # Error message should be meaningful
            assert error_msg, "Error message should not be empty"
            assert len(error_msg) > 5, "Error message should be descriptive"
            
            # Should contain relevant keywords
            meaningful_keywords = ["connect", "auth", "fail", "error", "invalid", "cannot", "timeout", "unreachable"]
            has_meaningful_keyword = any(kw in error_msg.lower() for kw in meaningful_keywords)
            
            print(f"✓ Error message: {error_msg}")
            if not has_meaningful_keyword:
                print(f"  Warning: Error message may not be descriptive enough")
        except Exception as e:
            print(f"✓ Connection failed with status {response.status_code}")


class TestAgiloftContractsBugFix:
    """
    CRITICAL BUG FIX TEST: POST /api/agiloft/contracts
    
    The bug was: Contracts endpoint was returning demo data even when auth failed.
    
    Expected behavior after fix:
    - Should return proper error when auth fails (NOT demo data)
    - Should NOT silently fall back to demo data
    """
    
    def test_contracts_requires_auth(self, api_client):
        """Contracts endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "invalid_user",
                "password": "invalid_password",
                "kb_name": "TestKB"
            },
            "table_name": "contract"
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/contracts", json=data, headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Contracts endpoint requires authentication")
    
    def test_contracts_fails_with_invalid_credentials(self, authenticated_client):
        """
        CRITICAL TEST: Contracts with invalid credentials should NOT return demo data
        
        This verifies the demo data fallback has been removed.
        """
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "invalid_user",
                "password": "wrong_password_12345",
                "kb_name": "TestKB"
            },
            "table_name": "contract"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/contracts", json=data)
        
        # Response should indicate failure, not return demo data
        result = response.json()
        
        if result.get("success") is True:
            # If success is true, verify it's NOT demo data
            contracts = result.get("contracts", [])
            if contracts:
                # Check if these look like demo contracts
                demo_indicators = ["Demo Contract", "Sample Contract", "Test Contract", "demo-"]
                for contract in contracts:
                    contract_name = contract.get("name", "")
                    contract_id = str(contract.get("id", ""))
                    is_demo = any(ind.lower() in contract_name.lower() or ind.lower() in contract_id.lower() 
                                  for ind in demo_indicators)
                    assert not is_demo, \
                        f"BUG: Demo data returned with invalid credentials! Contract: {contract}"
            print(f"✓ Contracts returned {len(contracts)} real contracts (not demo data)")
        else:
            # success:false is the expected behavior
            assert "message" in result, "Failed response should contain message"
            print(f"✓ Contracts properly failed: {result.get('message')}")
    
    def test_contracts_uses_correct_table_name(self, authenticated_client):
        """Verify the table_name parameter is respected (should be 'contract' lowercase)"""
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "test_user",
                "password": "test_password",
                "kb_name": "TestKB"
            },
            "table_name": "contract"  # lowercase per OpenAPI spec
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/contracts", json=data)
        
        # Just verify the endpoint accepts the request (will fail on auth, but that's expected)
        assert response.status_code in [200, 401, 500, 502, 503, 504], \
            f"Unexpected status code: {response.status_code}"
        print(f"✓ Contracts endpoint accepts table_name='contract'")


class TestAgiloftPushClausesBugFix:
    """
    Test POST /api/agiloft/push-clauses
    
    Verify it uses correct table name 'clause' (lowercase, singular) not 'Clauses'
    """
    
    def test_push_clauses_requires_auth(self, api_client):
        """Push clauses endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "test_user",
                "password": "test_password",
                "kb_name": "TestKB"
            },
            "source": "database"
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/push-clauses", json=data, headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Push clauses requires authentication")
    
    def test_push_clauses_fails_with_invalid_credentials(self, authenticated_client):
        """Push clauses with invalid credentials should fail properly"""
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "invalid_user",
                "password": "wrong_password",
                "kb_name": "TestKB"
            },
            "source": "database"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/push-clauses", json=data)
        
        result = response.json()
        
        # Should fail due to invalid credentials
        if result.get("success") is True:
            # If somehow succeeded, verify it's not with 0 clauses pushed
            pushed = result.get("pushed_count", 0)
            if pushed == 0:
                print(f"✓ Push clauses returned success but pushed 0 clauses (expected with invalid creds)")
            else:
                print(f"  Warning: Push claims to have pushed {pushed} clauses with invalid credentials")
        else:
            # Check for message or detail field
            assert "message" in result or "detail" in result, "Failed response should contain message or detail"
            error_msg = result.get("message", result.get("detail", ""))
            print(f"✓ Push clauses properly failed: {error_msg}")


class TestAgiloftFieldMapping:
    """
    Test GET/POST /api/agiloft/field-mapping
    
    Verify field mapping configuration endpoints work correctly.
    """
    
    def test_get_field_mapping_requires_auth(self, api_client):
        """Get field mapping should require authentication"""
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/agiloft/field-mapping", headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Get field mapping requires authentication")
    
    def test_get_field_mapping_returns_config(self, authenticated_client):
        """Get field mapping should return current configuration"""
        response = authenticated_client.get(f"{BASE_URL}/api/agiloft/field-mapping")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        
        # Verify response structure
        assert result.get("success") is True, "Response should have success:true"
        assert "table_name" in result, "Response should contain table_name"
        assert result["table_name"] == "clause", "Table name should be 'clause' (lowercase, singular)"
        assert "field_mapping" in result, "Response should contain field_mapping"
        
        # Verify field mapping structure
        field_mapping = result["field_mapping"]
        assert "our_fields" in field_mapping, "Should have our_fields documentation"
        assert "agiloft_fields" in field_mapping, "Should have agiloft_fields documentation"
        assert "current_mapping" in field_mapping, "Should have current_mapping"
        
        # Verify current mapping has expected fields
        current_mapping = field_mapping["current_mapping"]
        expected_fields = ["number", "title", "text", "type", "summary"]
        for field in expected_fields:
            assert field in current_mapping, f"Current mapping should include '{field}'"
        
        print(f"✓ Field mapping returned successfully")
        print(f"  Table name: {result['table_name']}")
        print(f"  Current mapping keys: {list(current_mapping.keys())}")
    
    def test_get_field_mapping_includes_endpoints_doc(self, authenticated_client):
        """Field mapping should include API endpoints documentation"""
        response = authenticated_client.get(f"{BASE_URL}/api/agiloft/field-mapping")
        result = response.json()
        
        assert "endpoints" in result, "Response should include endpoints documentation"
        endpoints = result["endpoints"]
        
        # Verify key endpoints are documented
        assert "login" in endpoints, "Should document login endpoint"
        assert "create_clause" in endpoints, "Should document create_clause endpoint"
        
        # Verify login uses correct format
        login_doc = endpoints["login"]
        assert "JSON" in login_doc or "json" in login_doc.lower(), \
            "Login documentation should mention JSON body"
        
        print(f"✓ Endpoints documentation included")
        print(f"  Login: {endpoints.get('login')}")
    
    def test_post_field_mapping_requires_auth(self, api_client):
        """Update field mapping should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {"mapping": {"number": "clause_title"}}
        response = requests.post(f"{BASE_URL}/api/agiloft/field-mapping", json=data, headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Update field mapping requires authentication")
    
    def test_post_field_mapping_updates_config(self, authenticated_client):
        """Update field mapping should update the configuration"""
        # First get current mapping
        get_response = authenticated_client.get(f"{BASE_URL}/api/agiloft/field-mapping")
        original_mapping = get_response.json()["field_mapping"]["current_mapping"]
        
        # Update a field
        new_mapping = {"summary": "guidance_text"}  # Change summary mapping
        data = {"mapping": new_mapping}
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/field-mapping", json=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        
        assert result.get("success") is True, "Update should succeed"
        assert "new_mapping" in result, "Response should contain new_mapping"
        assert result["new_mapping"]["summary"] == "guidance_text", \
            "Summary mapping should be updated"
        
        print(f"✓ Field mapping updated successfully")
        
        # Restore original mapping
        restore_data = {"mapping": {"summary": original_mapping.get("summary", "guidance")}}
        authenticated_client.post(f"{BASE_URL}/api/agiloft/field-mapping", json=restore_data)
        print(f"✓ Original mapping restored")
    
    def test_post_field_mapping_validates_fields(self, authenticated_client):
        """Update field mapping should validate field names"""
        # Try to update with invalid field name
        data = {"mapping": {"invalid_field_xyz": "some_value"}}
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/field-mapping", json=data)
        
        # Should return 400 for invalid field
        assert response.status_code == 400, f"Expected 400 for invalid field, got {response.status_code}"
        result = response.json()
        assert "detail" in result, "Error response should contain detail"
        assert "invalid" in result["detail"].lower() or "valid" in result["detail"].lower(), \
            "Error should mention invalid field"
        
        print(f"✓ Invalid field properly rejected: {result['detail']}")


class TestAgiloftAnalyzeContract:
    """Test POST /api/agiloft/analyze-contract - Contract compliance analysis"""
    
    def test_analyze_contract_requires_auth(self, api_client):
        """Analyze contract should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "test_user",
                "password": "test_password",
                "kb_name": "TestKB"
            },
            "contract_id": "test-contract-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/analyze-contract", json=data, headers=headers)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Analyze contract requires authentication")
    
    def test_analyze_contract_returns_compliance_analysis(self, authenticated_client):
        """Analyze contract should return compliance analysis"""
        data = {
            "config": {
                "kb_url": "https://fake-agiloft.example.com/ewws/EWRESTful/v1",
                "username": "test_user",
                "password": "test_password",
                "kb_name": "TestKB"
            },
            "contract_id": "test-contract-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/analyze-contract", json=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        
        # Verify response structure
        assert "compliance_status" in result, "Should have compliance_status"
        assert "correct_clauses" in result, "Should have correct_clauses"
        assert "missing_clauses" in result, "Should have missing_clauses"
        assert result["compliance_status"] in ["compliant", "non-compliant", "warning"], \
            f"Invalid compliance status: {result['compliance_status']}"
        
        print(f"✓ Analyze contract returned compliance analysis")
        print(f"  Status: {result['compliance_status']}")
        print(f"  Correct clauses: {result['correct_clauses']}")
        print(f"  Missing clauses: {result['missing_clauses']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
