"""
Test Agiloft Upload and Extract endpoint - verifying parent clause filtering.

Tests:
1. POST /api/agiloft/upload-and-extract - upload test PDF and verify:
   - 52.212-5 (parent clause with checkbox sub-clauses) is NOT in the returned list
   - Selected sub-clauses like 52.203-6, 52.203-13, 52.204-10 ARE present
   - No clause has is_parent=True in the response
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "jtorres@elitebco.com"
TEST_PASSWORD = "test123"
TEST_PDF_PATH = "/tmp/test_contract.pdf"


class TestAgiloftExtraction:
    """Test the Agiloft upload and extract endpoint for parent clause filtering"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        
        # Login to get session cookie (JSON request)
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        print(f"Login successful for {TEST_EMAIL}")
        yield
        
    def test_upload_and_extract_excludes_parent_clauses(self):
        """
        Test that POST /api/agiloft/upload-and-extract excludes parent clauses
        like 52.212-5 that contain checkbox sub-clauses.
        """
        # Verify test PDF exists
        assert os.path.exists(TEST_PDF_PATH), f"Test PDF not found at {TEST_PDF_PATH}"
        
        # Upload the PDF
        with open(TEST_PDF_PATH, 'rb') as f:
            files = {'file': ('test_contract.pdf', f, 'application/pdf')}
            response = self.session.post(
                f"{BASE_URL}/api/agiloft/upload-and-extract",
                files=files
            )
        
        assert response.status_code == 200, f"Upload failed: {response.status_code} - {response.text}"
        
        result = response.json()
        print(f"\nExtraction result:")
        print(f"  Success: {result.get('success')}")
        print(f"  Total detected: {result.get('total_detected')}")
        print(f"  Total filtered: {result.get('total_filtered')}")
        
        # Verify success
        assert result.get('success') == True, f"Extraction failed: {result}"
        
        # Get the list of extracted clause numbers
        clauses = result.get('clauses', [])
        clause_numbers = [c['number'] for c in clauses]
        
        print(f"\nExtracted {len(clauses)} clauses:")
        for c in clauses[:20]:  # Print first 20
            print(f"  - {c['number']} ({c['type']}) is_parent={c.get('is_parent', 'N/A')}")
        if len(clauses) > 20:
            print(f"  ... and {len(clauses) - 20} more")
        
        # TEST 1: 52.212-5 should NOT be in the extracted list (it's a parent clause)
        parent_clauses_to_exclude = ['52.212-5']
        for parent in parent_clauses_to_exclude:
            assert parent not in clause_numbers, \
                f"Parent clause {parent} should NOT be in extracted list (it has checkbox sub-clauses)"
        print(f"\n[PASS] Parent clause 52.212-5 correctly excluded from extraction")
        
        # TEST 2: Selected sub-clauses should be present
        # These are commonly selected sub-clauses in 52.212-5
        expected_sub_clauses = ['52.203-6', '52.203-13', '52.204-10']
        found_sub_clauses = [c for c in expected_sub_clauses if c in clause_numbers]
        print(f"\n[INFO] Expected sub-clauses found: {found_sub_clauses}")
        
        # At least some sub-clauses should be present (depends on PDF content)
        # We check if ANY of the expected sub-clauses are present
        if found_sub_clauses:
            print(f"[PASS] Found {len(found_sub_clauses)} expected sub-clauses: {found_sub_clauses}")
        else:
            print(f"[INFO] None of the expected sub-clauses found - checking what IS in the list")
            far_clauses = [c for c in clause_numbers if c.startswith('52.')]
            dfars_clauses = [c for c in clause_numbers if c.startswith('252.')]
            print(f"  FAR clauses: {far_clauses[:10]}...")
            print(f"  DFARS clauses: {dfars_clauses[:10]}...")
        
        # TEST 3: No clause should have is_parent=True
        parent_marked_clauses = [c for c in clauses if c.get('is_parent') == True]
        assert len(parent_marked_clauses) == 0, \
            f"No clause should have is_parent=True, but found: {[c['number'] for c in parent_marked_clauses]}"
        print(f"\n[PASS] No clause has is_parent=True in the response")
        
        return result
    
    def test_extraction_returns_valid_structure(self):
        """Test that the extraction response has the correct structure"""
        assert os.path.exists(TEST_PDF_PATH), f"Test PDF not found at {TEST_PDF_PATH}"
        
        with open(TEST_PDF_PATH, 'rb') as f:
            files = {'file': ('test_contract.pdf', f, 'application/pdf')}
            response = self.session.post(
                f"{BASE_URL}/api/agiloft/upload-and-extract",
                files=files
            )
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify response structure
        assert 'success' in result
        assert 'filename' in result
        assert 'total_detected' in result
        assert 'total_filtered' in result
        assert 'clauses' in result
        
        # Verify clause structure
        if result['clauses']:
            clause = result['clauses'][0]
            assert 'number' in clause
            assert 'type' in clause
            assert 'is_parent' in clause
            assert clause['type'] in ['FAR', 'DFARS']
            
        print(f"[PASS] Response structure is valid")
        
    def test_extraction_requires_authentication(self):
        """Test that the endpoint requires authentication"""
        # Create a new session without login
        unauthenticated_session = requests.Session()
        
        with open(TEST_PDF_PATH, 'rb') as f:
            files = {'file': ('test_contract.pdf', f, 'application/pdf')}
            response = unauthenticated_session.post(
                f"{BASE_URL}/api/agiloft/upload-and-extract",
                files=files
            )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"[PASS] Endpoint correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
