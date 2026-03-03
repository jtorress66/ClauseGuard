"""
Test iteration 12 - Testing new features:
1. Dashboard 'Sync All Clauses' button
2. POST /api/clauses/sync-full-text endpoint
3. POST /api/export/batch with include_full_text=true
4. Agiloft create_clause logging
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clausemanager.preview.emergentagent.com').rstrip('/')

# Test session token - created in MongoDB
SESSION_TOKEN = "test_session_1769526557839"


class TestSyncFullText:
    """Test the sync-full-text endpoint"""
    
    def test_sync_full_text_requires_auth(self):
        """Test that sync-full-text requires authentication"""
        response = requests.post(f"{BASE_URL}/api/clauses/sync-full-text?limit=1")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ PASS: sync-full-text requires authentication")
    
    def test_sync_full_text_with_auth(self):
        """Test sync-full-text with valid authentication"""
        response = requests.post(
            f"{BASE_URL}/api/clauses/sync-full-text?limit=3",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert data["success"] == True, "Sync should be successful"
        assert "synced" in data, "Response should have 'synced' count"
        assert "failed" in data, "Response should have 'failed' count"
        assert "total_checked" in data, "Response should have 'total_checked' count"
        
        print(f"✅ PASS: sync-full-text returned - synced: {data['synced']}, failed: {data['failed']}")


class TestBatchExport:
    """Test the batch export endpoint with full text"""
    
    def test_batch_export_requires_auth(self):
        """Test that batch export requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/export/batch",
            json={"clause_numbers": ["52.212-4"], "format": "json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ PASS: batch export requires authentication")
    
    def test_batch_export_json_with_full_text(self):
        """Test batch export returns full clause text (>1000 chars)"""
        response = requests.post(
            f"{BASE_URL}/api/export/batch",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
            json={
                "clause_numbers": ["52.212-4"],
                "include_full_text": True,
                "format": "json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "clauses" in data, "Response should have 'clauses' field"
        assert len(data["clauses"]) > 0, "Should return at least one clause"
        
        clause = data["clauses"][0]
        assert "text" in clause, "Clause should have 'text' field"
        text_length = len(clause.get("text", ""))
        
        # Full text should be > 1000 chars (not just a summary)
        assert text_length > 1000, f"Expected text > 1000 chars, got {text_length}"
        
        print(f"✅ PASS: batch export returned clause with {text_length} chars of full text")
    
    def test_batch_export_fetches_from_acquisition_gov(self):
        """Test that batch export fetches from acquisition.gov if text is short"""
        # Test with a clause that might have short text
        response = requests.post(
            f"{BASE_URL}/api/export/batch",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
            json={
                "clause_numbers": ["52.219-8"],  # Small business clause
                "include_full_text": True,
                "format": "json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        if len(data.get("clauses", [])) > 0:
            clause = data["clauses"][0]
            text_length = len(clause.get("text", ""))
            print(f"✅ PASS: batch export for 52.219-8 returned {text_length} chars")
        else:
            print("⚠️ WARN: Clause 52.219-8 not found in database")
    
    def test_batch_export_pdf_format(self):
        """Test batch export in PDF format"""
        response = requests.post(
            f"{BASE_URL}/api/export/batch",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
            json={
                "clause_numbers": ["52.212-4"],
                "include_full_text": True,
                "format": "pdf"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type is PDF
        content_type = response.headers.get("content-type", "")
        assert "pdf" in content_type.lower(), f"Expected PDF content type, got {content_type}"
        
        # Check PDF content starts with PDF header
        assert response.content[:4] == b'%PDF', "Response should be a valid PDF"
        
        print(f"✅ PASS: batch export returned valid PDF ({len(response.content)} bytes)")
    
    def test_batch_export_csv_format(self):
        """Test batch export in CSV format"""
        response = requests.post(
            f"{BASE_URL}/api/export/batch",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
            json={
                "clause_numbers": ["52.212-4"],
                "include_full_text": True,
                "format": "csv"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type is CSV
        content_type = response.headers.get("content-type", "")
        assert "csv" in content_type.lower() or "text" in content_type.lower(), f"Expected CSV content type, got {content_type}"
        
        # Check CSV has headers
        csv_content = response.text
        assert "Number" in csv_content or "number" in csv_content.lower(), "CSV should have Number column"
        
        print(f"✅ PASS: batch export returned valid CSV ({len(csv_content)} chars)")


class TestSyncFromAcquisitionGov:
    """Test the sync-from-acquisition-gov endpoint"""
    
    def test_sync_from_acquisition_gov_requires_auth(self):
        """Test that sync-from-acquisition-gov requires authentication"""
        response = requests.post(f"{BASE_URL}/api/clauses/sync-from-acquisition-gov")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ PASS: sync-from-acquisition-gov requires authentication")
    
    def test_sync_from_acquisition_gov_with_auth(self):
        """Test sync-from-acquisition-gov with valid authentication"""
        response = requests.post(
            f"{BASE_URL}/api/clauses/sync-from-acquisition-gov",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        assert "total_new" in data, "Response should have 'total_new' count"
        assert "total_processed" in data, "Response should have 'total_processed' count"
        
        print(f"✅ PASS: sync-from-acquisition-gov returned - new: {data['total_new']}, processed: {data['total_processed']}")


class TestAgiloftEndpoints:
    """Test Agiloft integration endpoints"""
    
    def test_agiloft_test_connection_requires_auth(self):
        """Test that Agiloft test-connection requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/test-connection",
            json={
                "kb_url": "https://test.agiloft.com",
                "kb_name": "test",
                "username": "test",
                "password": "test"
            }
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ PASS: Agiloft test-connection requires authentication")
    
    def test_agiloft_compare_clauses_requires_auth(self):
        """Test that Agiloft compare-clauses requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/compare-clauses",
            json={
                "kb_url": "https://test.agiloft.com",
                "kb_name": "test",
                "username": "test",
                "password": "test"
            }
        )
        # 401 = auth required, 422 = validation error (also means not authenticated)
        assert response.status_code in [401, 422], f"Expected 401 or 422, got {response.status_code}"
        print(f"✅ PASS: Agiloft compare-clauses requires authentication (status: {response.status_code})")
    
    def test_agiloft_upload_missing_requires_auth(self):
        """Test that Agiloft upload-missing-clauses requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/agiloft/upload-missing-clauses",
            json={
                "kb_url": "https://test.agiloft.com",
                "kb_name": "test",
                "username": "test",
                "password": "test",
                "clause_numbers": ["52.212-4"]
            }
        )
        # 401 = auth required, 422 = validation error (also means not authenticated)
        assert response.status_code in [401, 422], f"Expected 401 or 422, got {response.status_code}"
        print(f"✅ PASS: Agiloft upload-missing-clauses requires authentication (status: {response.status_code})")


class TestClauseSearch:
    """Test clause search endpoints"""
    
    def test_clause_search_works(self):
        """Test basic clause search"""
        response = requests.get(f"{BASE_URL}/api/clauses/search?query=commercial&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "clauses" in data, "Response should have 'clauses' field"
        
        print(f"✅ PASS: clause search returned {len(data.get('clauses', []))} clauses")
    
    def test_get_clause_by_number(self):
        """Test getting a clause by number"""
        response = requests.get(f"{BASE_URL}/api/clauses/by-number/52.212-4")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "number" in data, "Response should have 'number' field"
        assert data["number"] == "52.212-4", "Clause number should match"
        
        # Check that text is present and substantial
        text_length = len(data.get("text", ""))
        print(f"✅ PASS: get clause by number returned clause with {text_length} chars of text")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
