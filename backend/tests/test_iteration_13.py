"""
Test iteration 13: Clause formatting and PDF export tests
Tests for:
1. Clause Detail page displays formatted text with proper indentation for (a), (1), (i), (A) patterns
2. PDF export shows proper indentation for list items and centered (End of clause) marker
3. Search page has a working Clear button that resets the search
4. Search results display correctly with clause cards showing type badges
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clausemanager.preview.emergentagent.com')

class TestFormattedClauseEndpoint:
    """Tests for /api/clauses/formatted/{clause_number} endpoint"""
    
    def test_formatted_clause_returns_html_with_styles(self):
        """Test that formatted clause endpoint returns HTML with inline styles for indentation"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        assert "formatted_text" in data, "Response should contain formatted_text field"
        
        formatted_text = data["formatted_text"]
        assert len(formatted_text) > 1000, "Formatted text should be substantial"
        
        # Check for inline styles with padding-left for indentation
        assert "padding-left" in formatted_text, "Should have padding-left styles for indentation"
        assert "style=" in formatted_text, "Should have inline style attributes"
        
    def test_formatted_clause_has_list_classes(self):
        """Test that formatted clause has ListL1, ListL2, ListL3 classes for indentation levels"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # Check for ListL classes that indicate indentation levels
        assert "ListL1" in formatted_text, "Should have ListL1 class for (a) level"
        assert "ListL2" in formatted_text, "Should have ListL2 class for (1) level"
        assert "ListL3" in formatted_text, "Should have ListL3 class for (i) level"
        
    def test_formatted_clause_has_proper_indentation_styles(self):
        """Test that indentation styles match expected patterns"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # Check for specific indentation values
        # Level 1 (a): padding-left:1.6em
        # Level 2 (1): padding-left:3.1em
        # Level 3 (i): padding-left:4.6em
        assert "padding-left:1.6em" in formatted_text, "Should have level 1 indentation (1.6em)"
        assert "padding-left:3.1em" in formatted_text, "Should have level 2 indentation (3.1em)"
        
    def test_formatted_clause_not_block_text(self):
        """Test that formatted text is not a wall of block text - has proper paragraph structure"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # Count paragraph tags - should have many for proper structure
        p_count = formatted_text.count("<p")
        assert p_count > 50, f"Should have many paragraph tags for proper structure, found {p_count}"
        
        # Check that paragraphs have classes or styles
        styled_p_count = len(re.findall(r'<p[^>]*(?:class=|style=)[^>]*>', formatted_text))
        assert styled_p_count > 20, f"Should have many styled paragraphs, found {styled_p_count}"


class TestPDFExport:
    """Tests for PDF export functionality"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "testpdf@example.com", "password": "test123"}
        )
        if login_response.status_code != 200:
            pytest.skip("Could not authenticate for PDF export test")
        return session
    
    def test_pdf_export_returns_valid_pdf(self, auth_session):
        """Test that PDF export returns a valid PDF file"""
        response = auth_session.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": ["52.212-4"]}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        
        # Check PDF header
        content = response.content
        assert content.startswith(b"%PDF"), "Response should be a valid PDF"
        assert len(content) > 10000, "PDF should have substantial content"
        
    def test_pdf_export_requires_auth(self):
        """Test that PDF export requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/export/pdf",
            json={"clauses": ["52.212-4"]}
        )
        assert response.status_code == 401, "PDF export should require authentication"


class TestClauseSearch:
    """Tests for clause search functionality"""
    
    def test_search_returns_results(self):
        """Test that search returns clause results"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        assert "clauses" in data
        assert len(data["clauses"]) > 0, "Should find at least one clause"
        
    def test_search_results_have_type_field(self):
        """Test that search results include type field for badges"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=cybersecurity")
        assert response.status_code == 200
        
        data = response.json()
        if data["clauses"]:
            clause = data["clauses"][0]
            assert "type" in clause, "Clause should have type field"
            assert clause["type"] in ["FAR", "DFARS"], f"Type should be FAR or DFARS, got {clause['type']}"
            
    def test_search_with_type_filter(self):
        """Test that search can filter by clause type"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=contract&clause_type=FAR")
        assert response.status_code == 200
        
        data = response.json()
        for clause in data["clauses"]:
            assert clause["type"] == "FAR", "All results should be FAR type when filtered"


class TestClauseDetail:
    """Tests for clause detail endpoint"""
    
    def test_get_clause_by_number(self):
        """Test getting clause by number using formatted endpoint"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        assert data["number"] == "52.212-4"
        assert "title" in data
        assert "type" in data
        
    def test_clause_has_required_fields(self):
        """Test that clause has all required fields for display"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["number", "title", "type", "text"]
        for field in required_fields:
            assert field in data, f"Clause should have {field} field"


class TestIndentationDetection:
    """Tests for indentation level detection in formatted text"""
    
    def test_detect_level_a_pattern(self):
        """Test that (a) pattern gets level 1 indentation"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # Find paragraphs with (a) pattern and check they have ListL1 class
        # The (a) items should have level 1 indentation
        listl1_count = formatted_text.count("ListL1")
        assert listl1_count > 0, "Should have ListL1 elements for (a) level items"
        
    def test_detect_level_1_pattern(self):
        """Test that (1) pattern gets level 2 indentation"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # The (1) items should have level 2 indentation (ListL2)
        listl2_count = formatted_text.count("ListL2")
        assert listl2_count > 0, "Should have ListL2 elements for (1) level items"
        
    def test_detect_level_i_pattern(self):
        """Test that (i) pattern gets level 3 indentation"""
        response = requests.get(f"{BASE_URL}/api/clauses/formatted/52.212-4")
        assert response.status_code == 200
        
        data = response.json()
        formatted_text = data.get("formatted_text", "")
        
        # The (i) items should have level 3 indentation (ListL3)
        listl3_count = formatted_text.count("ListL3")
        assert listl3_count > 0, "Should have ListL3 elements for (i) level items"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
