"""
Backend API Tests for Bug Fixes - Iteration 10
Tests for:
1. Note saving on clause detail page - POST /api/user/annotations
2. PDF export functionality - POST /api/export/pdf with {clauses: []} body
3. Save search functionality - POST /api/user/saved-searches?query=xxx
4. Reserved clause filtering (code review)
5. Upload missing clauses endpoint
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthAndSetup:
    """Authentication and setup tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session"""
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def test_user(self, session):
        """Register a test user and return credentials"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"bugfix_test_{unique_id}@example.com"
        password = "testpass123"
        name = f"Bug Fix Test User {unique_id}"
        
        # Register user
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password, "name": name}
        )
        
        if response.status_code == 200:
            return {"email": email, "password": password, "name": name, "user_data": response.json()}
        elif response.status_code == 400 and "already registered" in response.text:
            # User exists, try login
            login_response = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password}
            )
            if login_response.status_code == 200:
                return {"email": email, "password": password, "name": name, "user_data": login_response.json()}
        
        pytest.skip(f"Could not create test user: {response.text}")
    
    @pytest.fixture(scope="class")
    def auth_session(self, session, test_user):
        """Return authenticated session"""
        # Login to get session cookie
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": test_user["email"], "password": test_user["password"]}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return session
    
    def test_api_root(self, session):
        """Test API root endpoint"""
        response = session.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ API root: {data['message']}")
    
    def test_user_registration(self, test_user):
        """Test user registration"""
        assert test_user is not None
        assert "user_data" in test_user
        print(f"✓ User registered: {test_user['email']}")
    
    def test_auth_me(self, auth_session):
        """Test auth/me endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        print(f"✓ Auth/me works: {data['email']}")


class TestAnnotations:
    """Test note saving (annotations) on clause detail page"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Create and authenticate a test user"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"annotation_test_{unique_id}@example.com"
        
        # Register
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "testpass123", "name": f"Annotation Test {unique_id}"}
        )
        if response.status_code != 200:
            # Try login
            session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": "testpass123"}
            )
        return session
    
    @pytest.fixture(scope="class")
    def sample_clause_id(self, session):
        """Get a sample clause ID from the database"""
        response = session.get(f"{BASE_URL}/api/clauses/search?query=52.212")
        if response.status_code == 200:
            data = response.json()
            if data.get("clauses") and len(data["clauses"]) > 0:
                return data["clauses"][0]["clause_id"]
        return "test-clause-id"
    
    def test_create_annotation(self, auth_session, sample_clause_id):
        """Test POST /api/user/annotations - Bug #1: Unable to save notes"""
        unique_note = f"Test note created at {uuid.uuid4()}"
        
        response = auth_session.post(
            f"{BASE_URL}/api/user/annotations",
            json={"clause_id": sample_clause_id, "note": unique_note}
        )
        
        assert response.status_code == 200, f"Failed to create annotation: {response.status_code} - {response.text}"
        data = response.json()
        assert "annotation_id" in data, "Response missing annotation_id"
        assert data["note"] == unique_note, "Note content mismatch"
        assert data["clause_id"] == sample_clause_id, "Clause ID mismatch"
        print(f"✓ Annotation created: {data['annotation_id']}")
        return data["annotation_id"]
    
    def test_get_annotations(self, auth_session, sample_clause_id):
        """Test GET /api/user/annotations"""
        response = auth_session.get(f"{BASE_URL}/api/user/annotations?clause_id={sample_clause_id}")
        
        assert response.status_code == 200, f"Failed to get annotations: {response.text}"
        data = response.json()
        assert "annotations" in data
        print(f"✓ Retrieved {len(data['annotations'])} annotations")
    
    def test_delete_annotation(self, auth_session, sample_clause_id):
        """Test DELETE /api/user/annotations/{annotation_id}"""
        # First create an annotation
        create_response = auth_session.post(
            f"{BASE_URL}/api/user/annotations",
            json={"clause_id": sample_clause_id, "note": "Note to delete"}
        )
        assert create_response.status_code == 200
        annotation_id = create_response.json()["annotation_id"]
        
        # Then delete it
        delete_response = auth_session.delete(f"{BASE_URL}/api/user/annotations/{annotation_id}")
        assert delete_response.status_code == 200, f"Failed to delete annotation: {delete_response.text}"
        print(f"✓ Annotation deleted: {annotation_id}")


class TestPDFExport:
    """Test PDF export functionality - Bug #2"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Create and authenticate a test user"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"pdf_test_{unique_id}@example.com"
        
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "testpass123", "name": f"PDF Test {unique_id}"}
        )
        if response.status_code != 200:
            session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": "testpass123"}
            )
        return session
    
    def test_export_pdf_with_clauses(self, auth_session):
        """Test POST /api/export/pdf with {clauses: [...]} body - Bug #2"""
        # First get a valid clause number
        search_response = auth_session.get(f"{BASE_URL}/api/clauses/search?query=52.212")
        clause_numbers = []
        if search_response.status_code == 200:
            clauses = search_response.json().get("clauses", [])
            if clauses:
                clause_numbers = [clauses[0]["number"]]
        
        if not clause_numbers:
            clause_numbers = ["52.212-4"]  # Fallback to known clause
        
        # Test PDF export with JSON body
        response = auth_session.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": clause_numbers},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"PDF export failed: {response.status_code} - {response.text}"
        assert response.headers.get("content-type") == "application/pdf", "Response is not PDF"
        assert len(response.content) > 0, "PDF content is empty"
        print(f"✓ PDF exported successfully, size: {len(response.content)} bytes")
    
    def test_export_pdf_empty_clauses(self, auth_session):
        """Test PDF export with empty clauses array"""
        response = auth_session.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": []},
            headers={"Content-Type": "application/json"}
        )
        
        # Should still return 200 with empty PDF
        assert response.status_code == 200, f"PDF export with empty clauses failed: {response.text}"
        print("✓ PDF export with empty clauses works")
    
    def test_export_pdf_unauthenticated(self, session):
        """Test PDF export without authentication"""
        fresh_session = requests.Session()
        response = fresh_session.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": ["52.212-4"]},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print("✓ PDF export correctly requires authentication")


class TestSaveSearch:
    """Test save search functionality - Bug #3"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Create and authenticate a test user"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"search_test_{unique_id}@example.com"
        
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "testpass123", "name": f"Search Test {unique_id}"}
        )
        if response.status_code != 200:
            session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": "testpass123"}
            )
        return session
    
    def test_save_search(self, auth_session):
        """Test POST /api/user/saved-searches?query=xxx - Bug #3"""
        test_query = f"cybersecurity_{uuid.uuid4().hex[:6]}"
        
        response = auth_session.post(
            f"{BASE_URL}/api/user/saved-searches?query={test_query}"
        )
        
        assert response.status_code == 200, f"Save search failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "search_id" in data, "Response missing search_id"
        assert data["query"] == test_query, f"Query mismatch: expected {test_query}, got {data.get('query')}"
        print(f"✓ Search saved: {data['search_id']} for query '{test_query}'")
        return data["search_id"]
    
    def test_get_saved_searches(self, auth_session):
        """Test GET /api/user/saved-searches"""
        response = auth_session.get(f"{BASE_URL}/api/user/saved-searches")
        
        assert response.status_code == 200, f"Get saved searches failed: {response.text}"
        data = response.json()
        assert "saved_searches" in data
        print(f"✓ Retrieved {len(data['saved_searches'])} saved searches")
    
    def test_delete_saved_search(self, auth_session):
        """Test DELETE /api/user/saved-searches/{search_id}"""
        # First create a search
        test_query = f"delete_test_{uuid.uuid4().hex[:6]}"
        create_response = auth_session.post(f"{BASE_URL}/api/user/saved-searches?query={test_query}")
        assert create_response.status_code == 200
        search_id = create_response.json()["search_id"]
        
        # Then delete it
        delete_response = auth_session.delete(f"{BASE_URL}/api/user/saved-searches/{search_id}")
        assert delete_response.status_code == 200, f"Delete saved search failed: {delete_response.text}"
        print(f"✓ Saved search deleted: {search_id}")
    
    def test_save_search_without_query(self, auth_session):
        """Test save search without query parameter"""
        response = auth_session.post(f"{BASE_URL}/api/user/saved-searches")
        
        assert response.status_code == 400, f"Expected 400 for missing query, got {response.status_code}"
        print("✓ Save search correctly requires query parameter")


class TestClauseSearch:
    """Test clause search functionality"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    def test_regular_search(self, session):
        """Test regular clause search"""
        response = session.get(f"{BASE_URL}/api/clauses/search?query=52.204")
        
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        assert "clauses" in data
        print(f"✓ Regular search returned {len(data['clauses'])} clauses")
    
    def test_search_with_type_filter(self, session):
        """Test search with clause type filter"""
        response = session.get(f"{BASE_URL}/api/clauses/search?query=52&clause_type=FAR")
        
        assert response.status_code == 200
        data = response.json()
        # All results should be FAR type
        for clause in data.get("clauses", []):
            assert clause.get("type") == "FAR", f"Expected FAR, got {clause.get('type')}"
        print(f"✓ Type-filtered search works, returned {len(data['clauses'])} FAR clauses")


class TestAISearch:
    """Test AI search functionality - Bug #4 (toggle behavior)"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Create and authenticate a test user"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"ai_test_{unique_id}@example.com"
        
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "testpass123", "name": f"AI Test {unique_id}"}
        )
        if response.status_code != 200:
            session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": "testpass123"}
            )
        return session
    
    def test_ai_search_requires_auth(self, session):
        """Test that AI search requires authentication"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/clauses/ai-search?query=cybersecurity")
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated AI search, got {response.status_code}"
        print("✓ AI search correctly requires authentication")
    
    def test_ai_search_authenticated(self, auth_session):
        """Test AI search with authentication"""
        response = auth_session.get(f"{BASE_URL}/api/clauses/ai-search?query=cybersecurity")
        
        assert response.status_code == 200, f"AI search failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "clauses" in data
        assert "source" in data
        print(f"✓ AI search returned {len(data['clauses'])} clauses, source: {data.get('source')}")


class TestFavorites:
    """Test favorites functionality"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Create and authenticate a test user"""
        unique_id = str(uuid.uuid4())[:8]
        email = f"fav_test_{unique_id}@example.com"
        
        response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "testpass123", "name": f"Favorites Test {unique_id}"}
        )
        if response.status_code != 200:
            session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": "testpass123"}
            )
        return session
    
    @pytest.fixture(scope="class")
    def sample_clause_id(self, session):
        """Get a sample clause ID"""
        response = session.get(f"{BASE_URL}/api/clauses/search?query=52.212")
        if response.status_code == 200:
            data = response.json()
            if data.get("clauses") and len(data["clauses"]) > 0:
                return data["clauses"][0]["clause_id"]
        return "test-clause-id"
    
    def test_add_favorite(self, auth_session, sample_clause_id):
        """Test adding a clause to favorites"""
        response = auth_session.post(f"{BASE_URL}/api/user/favorites?clause_id={sample_clause_id}")
        
        assert response.status_code == 200, f"Add favorite failed: {response.text}"
        data = response.json()
        assert "favorite_id" in data or "clause_id" in data
        print(f"✓ Favorite added for clause: {sample_clause_id}")
    
    def test_get_favorites(self, auth_session):
        """Test getting favorites list"""
        response = auth_session.get(f"{BASE_URL}/api/user/favorites")
        
        assert response.status_code == 200, f"Get favorites failed: {response.text}"
        data = response.json()
        assert "favorites" in data
        print(f"✓ Retrieved {len(data['favorites'])} favorites")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
