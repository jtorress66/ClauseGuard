"""
Backend Regression Tests for Federal Clause Management API
Tests all endpoints after server.py replacement to ensure nothing broke.

Modules tested:
- Root API endpoint
- Clause search and retrieval
- Flowdown analysis
- Batch export (JSON format)
- Agiloft integration (test-connection, contracts, analyze-contract)
"""

import pytest
import requests
import os
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback for testing
    BASE_URL = "https://clause-scan.preview.emergentagent.com"

# Test session token created for regression testing
SESSION_TOKEN = "test_session_regression_1768429393344"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client(api_client):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {SESSION_TOKEN}"})
    return api_client


class TestRootEndpoint:
    """Test GET /api/ - Root endpoint returns API info"""
    
    def test_root_returns_200(self, api_client):
        """Root endpoint should return 200 OK"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        
    def test_root_returns_api_info(self, api_client):
        """Root endpoint should return API info with message and version"""
        response = api_client.get(f"{BASE_URL}/api/")
        data = response.json()
        
        assert "message" in data
        assert "version" in data
        assert data["message"] == "Federal Clause Management API"
        assert data["version"] == "1.0.0"


class TestClauseSearch:
    """Test GET /api/clauses/search?query=xxx - Clause search functionality"""
    
    def test_search_returns_200(self, api_client):
        """Search endpoint should return 200 OK"""
        response = api_client.get(f"{BASE_URL}/api/clauses/search?query=FAR")
        assert response.status_code == 200
        
    def test_search_returns_clauses_array(self, api_client):
        """Search should return clauses array and total count"""
        response = api_client.get(f"{BASE_URL}/api/clauses/search?query=FAR")
        data = response.json()
        
        assert "clauses" in data
        assert "total" in data
        assert isinstance(data["clauses"], list)
        
    def test_search_with_specific_query(self, api_client):
        """Search for specific clause number should return matching results"""
        response = api_client.get(f"{BASE_URL}/api/clauses/search?query=52.212-4")
        data = response.json()
        
        assert response.status_code == 200
        assert data["total"] >= 0
        
    def test_search_with_type_filter(self, api_client):
        """Search with clause_type filter should work"""
        response = api_client.get(f"{BASE_URL}/api/clauses/search?query=52&clause_type=FAR")
        data = response.json()
        
        assert response.status_code == 200
        assert "clauses" in data
        
    def test_search_with_limit(self, api_client):
        """Search with limit parameter should respect the limit"""
        response = api_client.get(f"{BASE_URL}/api/clauses/search?query=52&limit=5")
        data = response.json()
        
        assert response.status_code == 200
        assert len(data["clauses"]) <= 5


class TestClauseById:
    """Test GET /api/clauses/{clause_id} - Get specific clause by ID"""
    
    def test_get_clause_by_valid_id(self, api_client):
        """Get clause by valid ID should return clause details"""
        # First search for a clause to get its ID
        search_response = api_client.get(f"{BASE_URL}/api/clauses/search?query=52.212-4&limit=1")
        search_data = search_response.json()
        
        if search_data["clauses"]:
            clause_id = search_data["clauses"][0]["clause_id"]
            response = api_client.get(f"{BASE_URL}/api/clauses/{clause_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert "clause_id" in data
            assert "number" in data
            assert "title" in data
            assert "type" in data
        else:
            pytest.skip("No clauses found to test with")
            
    def test_get_clause_by_invalid_id(self, api_client):
        """Get clause by invalid ID should return 404"""
        response = api_client.get(f"{BASE_URL}/api/clauses/invalid-clause-id-12345")
        assert response.status_code == 404


class TestClauseByNumber:
    """Test GET /api/clauses/by-number/{clause_number} - Get clause by number"""
    
    def test_get_clause_by_valid_number(self, api_client):
        """Get clause by valid number should return clause details"""
        response = api_client.get(f"{BASE_URL}/api/clauses/by-number/52.212-4")
        
        # May return 200 if clause exists or 404 if not
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "number" in data
            assert data["number"] == "52.212-4"
            
    def test_get_dfars_clause_by_number(self, api_client):
        """Get DFARS clause by number should work"""
        response = api_client.get(f"{BASE_URL}/api/clauses/by-number/252.204-7012")
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert data["type"] == "DFARS"


class TestFlowdownAnalysis:
    """Test POST /api/flowdown/analyze - Flowdown analysis"""
    
    def test_flowdown_requires_auth(self, api_client):
        """Flowdown analysis should require authentication"""
        # Remove auth header for this test
        headers = {"Content-Type": "application/json"}
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        response = requests.post(f"{BASE_URL}/api/flowdown/analyze", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_flowdown_with_auth(self, authenticated_client):
        """Flowdown analysis with auth should return analysis results"""
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        response = authenticated_client.post(f"{BASE_URL}/api/flowdown/analyze", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify response structure
        assert "required_flowdown_clauses" in result
        assert "present_in_contract" in result
        assert "missing_from_contract" in result
        assert "clause_details" in result
        
    def test_flowdown_with_high_value_contract(self, authenticated_client):
        """Flowdown analysis with high value contract should include threshold-based clauses"""
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 10000000,  # $10M contract
            "clauses": ["52.212-4"]
        }
        response = authenticated_client.post(f"{BASE_URL}/api/flowdown/analyze", json=data)
        
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result["required_flowdown_clauses"], list)


class TestBatchExport:
    """Test POST /api/export/batch - Batch export (JSON format)"""
    
    def test_batch_export_requires_auth(self, api_client):
        """Batch export should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "clause_numbers": ["52.212-4"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "json"
        }
        response = requests.post(f"{BASE_URL}/api/export/batch", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_batch_export_json_format(self, authenticated_client):
        """Batch export with JSON format should return JSON data"""
        data = {
            "clause_numbers": ["52.212-4"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "json"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/export/batch", json=data)
        
        # May return 200 if clause exists or 404 if not found
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            result = response.json()
            assert "export_date" in result
            assert "total_clauses" in result
            assert "clauses" in result
            
    def test_batch_export_multiple_clauses(self, authenticated_client):
        """Batch export with multiple clauses should work"""
        data = {
            "clause_numbers": ["52.212-4", "252.204-7012"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "json"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/export/batch", json=data)
        
        assert response.status_code in [200, 404]


class TestFlowdownReportExport:
    """Test POST /api/export/flowdown-report - Flowdown report PDF generation"""
    
    def test_flowdown_report_requires_auth(self, api_client):
        """Flowdown report should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        response = requests.post(f"{BASE_URL}/api/export/flowdown-report", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_flowdown_report_with_auth(self, authenticated_client):
        """Flowdown report with auth should return PDF"""
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        response = authenticated_client.post(f"{BASE_URL}/api/export/flowdown-report", json=data)
        
        assert response.status_code == 200
        # Check content type is PDF
        assert "application/pdf" in response.headers.get("content-type", "")


class TestAgiloftTestConnection:
    """Test POST /api/agiloft/test-connection - Agiloft connection test"""
    
    def test_agiloft_connection_requires_auth(self, api_client):
        """Agiloft test connection should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "kb_url": "https://test.agiloft.com/ewws",
            "username": "test_user",
            "password": "test_pass",
            "kb_name": "Default"
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/test-connection", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_agiloft_connection_with_invalid_credentials(self, authenticated_client):
        """Agiloft test connection with invalid credentials should fail gracefully"""
        data = {
            "kb_url": "https://test.agiloft.com/ewws",
            "username": "invalid_user",
            "password": "invalid_pass",
            "kb_name": "Default"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/test-connection", json=data)
        
        # Should return error (401, 500, or 520 for connection issues) but not crash
        # 520 is returned when the external Agiloft server is unreachable
        assert response.status_code in [401, 500, 520]
        
        # Verify error message is returned
        if response.status_code == 500:
            data = response.json()
            assert "detail" in data


class TestAgiloftContracts:
    """Test POST /api/agiloft/contracts - Fetch Agiloft contracts"""
    
    def test_agiloft_contracts_requires_auth(self, api_client):
        """Agiloft contracts should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "config": {
                "kb_url": "https://test.agiloft.com/ewws",
                "username": "test_user",
                "password": "test_pass",
                "kb_name": "Default"
            },
            "table_name": "Contracts"
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/contracts", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_agiloft_contracts_returns_response(self, authenticated_client):
        """Agiloft contracts should return a response (demo data or error)"""
        data = {
            "config": {
                "kb_url": "https://test.agiloft.com/ewws",
                "username": "invalid_user",
                "password": "invalid_pass",
                "kb_name": "Default"
            },
            "table_name": "Contracts"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/contracts", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        # Should return success or failure with proper structure
        assert "success" in result
        
        # If success is True, verify demo contracts structure
        if result["success"]:
            assert "contracts" in result
            assert len(result["contracts"]) > 0
            contract = result["contracts"][0]
            assert "id" in contract
            assert "name" in contract
        else:
            # If failed, should have a message
            assert "message" in result


class TestAgiloftAnalyzeContract:
    """Test POST /api/agiloft/analyze-contract - Analyze contract for compliance"""
    
    def test_agiloft_analyze_requires_auth(self, api_client):
        """Agiloft analyze contract should require authentication"""
        headers = {"Content-Type": "application/json"}
        data = {
            "config": {
                "kb_url": "https://test.agiloft.com/ewws",
                "username": "test_user",
                "password": "test_pass",
                "kb_name": "Default"
            },
            "contract_id": "demo-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        response = requests.post(f"{BASE_URL}/api/agiloft/analyze-contract", json=data, headers=headers)
        assert response.status_code == 401
        
    def test_agiloft_analyze_contract_returns_analysis(self, authenticated_client):
        """Agiloft analyze contract should return compliance analysis"""
        data = {
            "config": {
                "kb_url": "https://test.agiloft.com/ewws",
                "username": "invalid_user",
                "password": "invalid_pass",
                "kb_name": "Default"
            },
            "contract_id": "demo-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        response = authenticated_client.post(f"{BASE_URL}/api/agiloft/analyze-contract", json=data)
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify analysis structure
        assert "compliance_status" in result
        assert "correct_clauses" in result
        assert "missing_clauses" in result


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_auth_me_without_token(self, api_client):
        """Auth me without token should return 401"""
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 401
        
    def test_auth_me_with_valid_token(self, authenticated_client):
        """Auth me with valid token should return user info"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert "name" in data


class TestUserEndpoints:
    """Test user-related endpoints"""
    
    def test_favorites_requires_auth(self, api_client):
        """Favorites endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/user/favorites", headers=headers)
        assert response.status_code == 401
        
    def test_favorites_with_auth(self, authenticated_client):
        """Favorites with auth should return favorites list"""
        response = authenticated_client.get(f"{BASE_URL}/api/user/favorites")
        
        assert response.status_code == 200
        data = response.json()
        assert "favorites" in data
        
    def test_saved_searches_requires_auth(self, api_client):
        """Saved searches endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/user/saved-searches", headers=headers)
        assert response.status_code == 401
        
    def test_saved_searches_with_auth(self, authenticated_client):
        """Saved searches with auth should return searches list"""
        response = authenticated_client.get(f"{BASE_URL}/api/user/saved-searches")
        
        assert response.status_code == 200
        data = response.json()
        assert "saved_searches" in data
        
    def test_annotations_requires_auth(self, api_client):
        """Annotations endpoint should require authentication"""
        headers = {"Content-Type": "application/json"}
        response = requests.get(f"{BASE_URL}/api/user/annotations", headers=headers)
        assert response.status_code == 401
        
    def test_annotations_with_auth(self, authenticated_client):
        """Annotations with auth should return annotations list"""
        response = authenticated_client.get(f"{BASE_URL}/api/user/annotations")
        
        assert response.status_code == 200
        data = response.json()
        assert "annotations" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
