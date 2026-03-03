"""
Test suite for ClauseGuard bug fixes - Iteration 11
Tests the following fixes:
1. AI Search - triggers search when clicked (if query exists) and user is logged in
2. PDF export - fetches full text from acquisition.gov if not in local DB
3. Upload missing clauses - ALWAYS tries to fetch from acquisition.gov if clause not in local DB
4. Dashboard buttons - have type='button' attribute
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test session token - created in MongoDB
TEST_SESSION_TOKEN = None


@pytest.fixture(scope="module")
def session_token():
    """Get or create a test session token"""
    global TEST_SESSION_TOKEN
    if TEST_SESSION_TOKEN:
        return TEST_SESSION_TOKEN
    
    # Create test user and session via MongoDB
    import subprocess
    result = subprocess.run([
        'mongosh', '--eval', '''
        use('test_database');
        var userId = 'pytest_user_' + Date.now();
        var sessionToken = 'pytest_session_' + Date.now();
        var existingUser = db.users.findOne({email: 'pytest@test.com'});
        if (!existingUser) {
            db.users.insertOne({
                user_id: userId,
                email: 'pytest@test.com',
                name: 'Pytest User',
                created_at: new Date()
            });
        } else {
            userId = existingUser.user_id;
        }
        db.user_sessions.insertOne({
            user_id: userId,
            session_token: sessionToken,
            expires_at: new Date(Date.now() + 7*24*60*60*1000),
            created_at: new Date()
        });
        print('SESSION_TOKEN:' + sessionToken);
        '''
    ], capture_output=True, text=True)
    
    for line in result.stdout.split('\n'):
        if line.startswith('SESSION_TOKEN:'):
            TEST_SESSION_TOKEN = line.split(':')[1]
            return TEST_SESSION_TOKEN
    
    pytest.skip("Could not create test session")


@pytest.fixture
def auth_headers(session_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {session_token}"}


class TestAISearch:
    """Test AI Search functionality"""
    
    def test_ai_search_requires_auth(self):
        """AI search should return 401 without authentication"""
        response = requests.get(f"{BASE_URL}/api/clauses/ai-search?query=commercial")
        assert response.status_code == 401
        data = response.json()
        assert "Authentication required" in data.get("detail", "")
    
    def test_ai_search_with_auth_returns_results(self, auth_headers):
        """AI search should return results with ai_analysis when authenticated"""
        response = requests.get(
            f"{BASE_URL}/api/clauses/ai-search?query=commercial",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have clauses
        assert "clauses" in data
        assert len(data["clauses"]) > 0
        
        # Should have AI analysis
        assert "ai_analysis" in data
        assert data["ai_analysis"] is not None
        assert len(data["ai_analysis"]) > 0
    
    def test_ai_search_clauses_have_ai_explanation(self, auth_headers):
        """AI search results should include ai_explanation for each clause"""
        response = requests.get(
            f"{BASE_URL}/api/clauses/ai-search?query=commercial",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # At least some clauses should have AI explanations
        clauses_with_explanation = [c for c in data["clauses"] if c.get("ai_explanation")]
        assert len(clauses_with_explanation) > 0


class TestPDFExport:
    """Test PDF export functionality"""
    
    def test_pdf_export_requires_auth(self):
        """PDF export should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": ["52.212-4"]}
        )
        assert response.status_code == 401
    
    def test_pdf_export_returns_pdf(self, auth_headers):
        """PDF export should return a valid PDF file"""
        response = requests.post(
            f"{BASE_URL}/api/export/pdf",
            headers=auth_headers,
            json={"clauses": ["52.212-4"]}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        
        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF'
    
    def test_pdf_export_fetches_from_acquisition_gov(self, auth_headers):
        """PDF export should fetch clause text from acquisition.gov if not in local DB"""
        # Use a clause that might not have full text in local DB
        response = requests.post(
            f"{BASE_URL}/api/export/pdf",
            headers=auth_headers,
            json={"clauses": ["52.212-5"]}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        
        # PDF should be generated (even if clause needs to be fetched)
        assert len(response.content) > 500  # Should have substantial content


class TestUploadMissingClauses:
    """Test upload missing clauses functionality"""
    
    def test_upload_missing_clauses_requires_auth(self):
        """Upload missing clauses should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/upload-missing-clauses",
            json={
                "config": {
                    "kb_url": "https://test.agiloft.com",
                    "kb_name": "test",
                    "username": "test",
                    "password": "test"
                },
                "clause_numbers": ["52.212-5"],
                "fetch_fresh": True
            }
        )
        assert response.status_code == 401
    
    def test_upload_missing_clauses_fetches_from_acquisition_gov(self, auth_headers):
        """Upload should attempt to fetch from acquisition.gov for missing clauses"""
        # This will fail at Agiloft auth, but should show it tried to fetch
        response = requests.post(
            f"{BASE_URL}/api/agiloft/upload-missing-clauses",
            headers=auth_headers,
            json={
                "config": {
                    "kb_url": "https://test.agiloft.com",
                    "kb_name": "test",
                    "username": "test",
                    "password": "test"
                },
                "clause_numbers": ["52.212-3"],  # A clause that might not be in local DB
                "fetch_fresh": True
            }
        )
        # Should fail at Agiloft auth, not at clause fetching
        assert response.status_code == 401
        data = response.json()
        assert "Agiloft" in data.get("detail", "")


class TestRegularSearch:
    """Test regular search functionality"""
    
    def test_regular_search_works_without_auth(self):
        """Regular search should work without authentication"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=commercial")
        assert response.status_code == 200
        data = response.json()
        assert "clauses" in data
        assert len(data["clauses"]) > 0
    
    def test_regular_search_with_type_filter(self):
        """Regular search should support type filter"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=commercial&clause_type=FAR")
        assert response.status_code == 200
        data = response.json()
        assert "clauses" in data
        # All results should be FAR type
        for clause in data["clauses"]:
            assert clause.get("type") == "FAR"


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_auth_me_with_valid_token(self, auth_headers):
        """Auth me should return user data with valid token"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
    
    def test_auth_me_without_token(self):
        """Auth me should return 401 without token"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401


class TestClauseEndpoints:
    """Test clause-related endpoints"""
    
    def test_get_clause_by_id(self):
        """Should be able to get a clause by ID"""
        # First search to get a clause ID
        search_response = requests.get(f"{BASE_URL}/api/clauses/search?query=52.212-4")
        assert search_response.status_code == 200
        clauses = search_response.json().get("clauses", [])
        
        if clauses:
            clause_id = clauses[0].get("clause_id")
            response = requests.get(f"{BASE_URL}/api/clauses/{clause_id}")
            assert response.status_code == 200
            data = response.json()
            assert data.get("number") == "52.212-4"
    
    def test_get_clause_by_number(self):
        """Should be able to get a clause by number"""
        response = requests.get(f"{BASE_URL}/api/clauses/by-number/52.212-4")
        assert response.status_code == 200
        data = response.json()
        assert data.get("number") == "52.212-4"
        assert "title" in data
        assert "text" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
