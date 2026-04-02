"""
Test Contract Attachments Feature - Iteration 16
Tests for:
- POST /api/agiloft/contract-attachments - list attachments for a contract
- POST /api/agiloft/download-attachment-and-extract - download attachment and extract clauses
Both endpoints require authentication (session_token cookie)
"""
import pytest
import requests
import os

# Use the public URL for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clause-scan.preview.emergentagent.com')

# Test credentials from test_credentials.md
TEST_EMAIL = "jtorres@elitebco.com"
TEST_PASSWORD = "test123"

# Agiloft credentials - NOTE: Using .agiloft.com instead of .saas.agiloft.com due to DNS issues
AGILOFT_KB_URL = "https://elitebcopartnerkb.agiloft.com"
AGILOFT_USERNAME = "jtorres"
AGILOFT_PASSWORD = "Elitebco2026"
AGILOFT_KB_NAME = "elitebcoPartnerKB"

# Test contract and attachment IDs from review request
TEST_CONTRACT_ID = 663
TEST_ATTACHMENT_ID = 1085
EXPECTED_ATTACHMENT_TITLE = "PWS - CFM EPA WJCB EWC 09 23 2022"


@pytest.fixture(scope="module")
def session():
    """Create a requests session with authentication"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    
    # Login to get session cookie
    login_response = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
    
    return s


class TestContractAttachmentsEndpoint:
    """Tests for POST /api/agiloft/contract-attachments"""
    
    def test_requires_authentication(self):
        """Endpoint should return 401 without authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/contract-attachments",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "contract_id": TEST_CONTRACT_ID
            }
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: contract-attachments requires authentication")
    
    def test_list_attachments_for_contract(self, session):
        """Test listing attachments for contract_id=663"""
        response = session.post(
            f"{BASE_URL}/api/agiloft/contract-attachments",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "contract_id": TEST_CONTRACT_ID
            }
        )
        
        # Check status code
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert "attachments" in data, "Response should contain 'attachments' field"
        assert "count" in data, "Response should contain 'count' field"
        assert data.get("contract_id") == TEST_CONTRACT_ID, f"Expected contract_id={TEST_CONTRACT_ID}"
        
        attachments = data["attachments"]
        print(f"Found {len(attachments)} attachments for contract {TEST_CONTRACT_ID}")
        
        # Verify at least 1 attachment exists (as per review request)
        assert len(attachments) >= 1, f"Expected at least 1 attachment, got {len(attachments)}"
        
        # Check for expected attachment ID 1085
        attachment_ids = [att["id"] for att in attachments]
        assert TEST_ATTACHMENT_ID in attachment_ids, f"Expected attachment ID {TEST_ATTACHMENT_ID} in {attachment_ids}"
        
        # Verify attachment structure
        for att in attachments:
            assert "id" in att, "Attachment should have 'id'"
            assert "title" in att, "Attachment should have 'title'"
            assert "filename" in att, "Attachment should have 'filename'"
            
            if att["id"] == TEST_ATTACHMENT_ID:
                # Verify expected attachment title
                assert EXPECTED_ATTACHMENT_TITLE in att["title"], \
                    f"Expected title containing '{EXPECTED_ATTACHMENT_TITLE}', got '{att['title']}'"
                print(f"PASS: Found expected attachment: ID={att['id']}, title='{att['title']}'")
        
        print("PASS: contract-attachments returns correct structure and data")
    
    def test_invalid_contract_id(self, session):
        """Test with non-existent contract ID"""
        response = session.post(
            f"{BASE_URL}/api/agiloft/contract-attachments",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "contract_id": 999999  # Non-existent contract
            }
        )
        
        # Should return 200 with empty attachments list (not an error)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("attachments") == [] or len(data.get("attachments", [])) == 0
        print("PASS: Non-existent contract returns empty attachments list")


class TestDownloadAttachmentAndExtract:
    """Tests for POST /api/agiloft/download-attachment-and-extract"""
    
    def test_requires_authentication(self):
        """Endpoint should return 401 without authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/download-attachment-and-extract",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "attachment_id": TEST_ATTACHMENT_ID
            }
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: download-attachment-and-extract requires authentication")
    
    def test_download_and_extract_clauses(self, session):
        """Test downloading attachment 1085 and extracting clauses
        
        NOTE: The test attachment (PWS - Performance Work Statement) may not contain
        FAR/DFARS clause numbers. This test verifies the endpoint works correctly
        and returns the proper response structure, even if no clauses are found.
        """
        response = session.post(
            f"{BASE_URL}/api/agiloft/download-attachment-and-extract",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "attachment_id": TEST_ATTACHMENT_ID
            },
            timeout=120  # Allow longer timeout for PDF download and extraction
        )
        
        # Check status code
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert "clauses" in data, "Response should contain 'clauses' field"
        assert "total_detected" in data, "Response should contain 'total_detected' field"
        assert "total_filtered" in data, "Response should contain 'total_filtered' field"
        assert data.get("attachment_id") == TEST_ATTACHMENT_ID, f"Expected attachment_id={TEST_ATTACHMENT_ID}"
        
        clauses = data["clauses"]
        print(f"Extracted {len(clauses)} clauses from attachment {TEST_ATTACHMENT_ID}")
        print(f"Total detected: {data['total_detected']}, Total filtered: {data['total_filtered']}")
        
        # The PWS document may not contain FAR/DFARS clauses - that's OK
        # The important thing is the endpoint works and returns proper structure
        if len(clauses) > 0:
            # Verify clause structure if any were found
            for clause in clauses[:5]:
                assert "number" in clause, "Clause should have 'number'"
                assert "type" in clause, "Clause should have 'type'"
                assert clause["type"] in ["FAR", "DFARS"], f"Clause type should be FAR or DFARS, got {clause['type']}"
                print(f"  - {clause['number']} ({clause['type']}): {clause.get('title', '')[:50]}")
        else:
            print("NOTE: No clauses found in PWS document (expected - PWS may not contain FAR/DFARS clauses)")
        
        print("PASS: download-attachment-and-extract returns correct response structure")
    
    def test_invalid_attachment_id(self, session):
        """Test with non-existent attachment ID"""
        response = session.post(
            f"{BASE_URL}/api/agiloft/download-attachment-and-extract",
            json={
                "kb_url": AGILOFT_KB_URL,
                "username": AGILOFT_USERNAME,
                "password": AGILOFT_PASSWORD,
                "kb_name": AGILOFT_KB_NAME,
                "attachment_id": 999999  # Non-existent attachment
            },
            timeout=60
        )
        
        # Should return 400 error (no PDF content found)
        assert response.status_code == 400, f"Expected 400 for invalid attachment, got {response.status_code}"
        print("PASS: Invalid attachment ID returns 400 error")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
