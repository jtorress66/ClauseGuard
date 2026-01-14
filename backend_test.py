import requests
import sys
import json
from datetime import datetime

class FederalClauseAPITester:
    def __init__(self, base_url="https://fed-contract-hub.preview.emergentagent.com"):
        self.base_url = base_url
        self.session_token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test_name": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    Details: {details}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, expect_json=True):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.session_token:
            test_headers['Authorization'] = f'Bearer {self.session_token}'
        
        if headers:
            test_headers.update(headers)

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if success and response.content:
                if expect_json:
                    try:
                        response_data = response.json()
                        details += f", Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Non-dict response'}"
                    except:
                        details += ", Response: Non-JSON (expected for file downloads)"
                else:
                    details += f", Content-Type: {response.headers.get('content-type', 'unknown')}"
            elif not success:
                try:
                    error_data = response.json()
                    details += f", Error: {error_data.get('detail', 'Unknown error')}"
                except:
                    details += f", Raw response: {response.text[:100]}"

            self.log_test(name, success, details)
            return success, response.json() if success and expect_json and response.content else {}

        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API", "GET", "api/", 200)

    def test_clause_search_basic(self):
        """Test basic clause search"""
        return self.run_test("Basic Clause Search", "GET", "api/clauses/search?query=FAR", 200)

    def test_clause_search_with_type(self):
        """Test clause search with type filter"""
        return self.run_test("Clause Search with Type", "GET", "api/clauses/search?query=52.212&clause_type=FAR", 200)

    def test_clause_by_id(self):
        """Test getting clause by ID - first get a clause ID from search"""
        success, search_data = self.run_test("Search for Clause ID", "GET", "api/clauses/search?query=52.212-4&limit=1", 200)
        if success and search_data.get('clauses'):
            clause_id = search_data['clauses'][0]['clause_id']
            return self.run_test("Get Clause by ID", "GET", f"api/clauses/{clause_id}", 200)
        else:
            self.log_test("Get Clause by ID", False, "No clause found in search to test with")
            return False, {}

    def test_clause_by_number(self):
        """Test getting clause by number"""
        return self.run_test("Get Clause by Number", "GET", "api/clauses/by-number/52.212-4", 200)

    def test_auth_me_unauthenticated(self):
        """Test auth/me endpoint without authentication"""
        return self.run_test("Auth Me (Unauthenticated)", "GET", "api/auth/me", 401)

    def test_ai_search_unauthenticated(self):
        """Test AI search without authentication"""
        return self.run_test("AI Search (Unauthenticated)", "GET", "api/clauses/ai-search?query=cybersecurity", 401)

    def test_contracts_unauthenticated(self):
        """Test contracts endpoint without authentication"""
        return self.run_test("Contracts (Unauthenticated)", "GET", "api/contracts/", 401)

    def test_flowdown_unauthenticated(self):
        """Test flowdown analysis without authentication"""
        data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        return self.run_test("Flowdown Analysis (Unauthenticated)", "POST", "api/flowdown/analyze", 401, data)

    def create_test_session(self):
        """Create a test session using the provided test token"""
        print("\n🔧 Setting up test authentication...")
        
        # Use the provided test session token
        test_token = "test_session_batch_1768400260762"
        self.session_token = test_token
        
        # Test if the token works
        success, _ = self.run_test("Test Session Validation", "GET", "api/auth/me", 200)
        
        if success:
            print("✅ Test session token is valid")
            return True
        else:
            print("❌ Test session token is invalid - will test unauthenticated endpoints only")
            self.session_token = None
            return False

    def test_authenticated_features_with_token(self):
        """Test authenticated features with the test token"""
        if not self.session_token:
            print("⚠️ Skipping authenticated tests - no valid session token")
            return
            
        print("\n🔐 Testing authenticated features with test token...")
        
        # Test AI search with authentication
        self.run_test("AI Search (Authenticated)", "GET", "api/clauses/ai-search?query=cybersecurity", 200)
        
        # Test contracts endpoint
        self.run_test("Get Contracts (Authenticated)", "GET", "api/contracts/", 200)
        
        # Test flowdown analysis
        flowdown_data = {
            "contract_type": "Fixed-Price", 
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        self.run_test("Flowdown Analysis (Authenticated)", "POST", "api/flowdown/analyze", 200, flowdown_data)
        
        # Test batch export with different formats
        export_data_pdf = {
            "clause_numbers": ["52.212-4"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "pdf"
        }
        success, _ = self.run_test("Batch Export PDF (Authenticated)", "POST", "api/export/batch", 200, export_data_pdf, expect_json=False)
        
        export_data_json = {
            "clause_numbers": ["52.212-4"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "json"
        }
        success, _ = self.run_test("Batch Export JSON (Authenticated)", "POST", "api/export/batch", 200, export_data_json)
        
        export_data_csv = {
            "clause_numbers": ["52.212-4"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "csv"
        }
        success, _ = self.run_test("Batch Export CSV (Authenticated)", "POST", "api/export/batch", 200, export_data_csv, expect_json=False)
        
        # Test flowdown report export - this endpoint expects query parameters
        flowdown_query = f"contract_type={flowdown_data['contract_type']}&contract_value={flowdown_data['contract_value']}"
        for clause in flowdown_data['clauses']:
            flowdown_query += f"&clauses={clause}"
        success, _ = self.run_test("Flowdown Report Export (Authenticated)", "POST", f"api/export/flowdown-report?{flowdown_query}", 200, expect_json=False)
        
        # Test Agiloft endpoints (will likely fail due to invalid credentials, but should return proper error)
        agiloft_config = {
            "kb_url": "https://test.agiloft.com/ewws",
            "username": "test_user", 
            "password": "test_pass",
            "kb_name": "Default"
        }
        self.run_test("Agiloft Test Connection (Authenticated)", "POST", "api/agiloft/test-connection", 200, agiloft_config)
        
        # Test new Agiloft push clauses endpoint
        push_data = {
            "config": agiloft_config,
            "source": "database"
        }
        self.run_test("Agiloft Push Clauses (Authenticated)", "POST", "api/agiloft/push-clauses", 200, push_data)
        
        # Test new Agiloft contracts endpoint (should return demo data)
        contracts_data = {
            "config": agiloft_config,
            "table_name": "Contracts"
        }
        self.run_test("Agiloft Get Contracts (Authenticated)", "POST", "api/agiloft/contracts", 200, contracts_data)
        
        # Test new Agiloft analyze contract endpoint
        analyze_data = {
            "config": agiloft_config,
            "contract_id": "demo-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        self.run_test("Agiloft Analyze Contract (Authenticated)", "POST", "api/agiloft/analyze-contract", 200, analyze_data)
        
        # Test new Agiloft update contract endpoint
        update_data = {
            "config": agiloft_config,
            "contract_id": "demo-1",
            "updates": {
                "missing_clauses": ["52.219-8"],
                "flowdown_clauses": ["52.212-4"]
            }
        }
        self.run_test("Agiloft Update Contract (Authenticated)", "POST", "api/agiloft/update-contract", 200, update_data)
        
        # Test acquisition.gov sync
        self.run_test("Sync from acquisition.gov (Authenticated)", "POST", "api/clauses/sync-from-acquisition-gov", 200)
        
        # Test user endpoints
        self.run_test("Get Favorites (Authenticated)", "GET", "api/user/favorites", 200)
        self.run_test("Get Saved Searches (Authenticated)", "GET", "api/user/saved-searches", 200)
        self.run_test("Get Annotations (Authenticated)", "GET", "api/user/annotations", 200)

    def test_new_acquisition_gov_endpoints(self):
        """Test new acquisition.gov integration endpoints"""
        print("\n🌐 Testing acquisition.gov integration endpoints...")
        
        # Test sync endpoint (requires auth)
        self.run_test("Sync from acquisition.gov (Unauth)", "POST", "api/clauses/sync-from-acquisition-gov", 401)
        
        # Test fetch live endpoint (requires auth)
        self.run_test("Fetch Live Clause (Unauth)", "GET", "api/clauses/fetch-live/52.212-4", 401)

    def test_contract_comparison_endpoint(self):
        """Test contract comparison endpoint"""
        print("\n📊 Testing contract comparison endpoint...")
        
        # Test comparison endpoint (requires auth and contract IDs)
        self.run_test("Contract Comparison (Unauth)", "POST", "api/contracts/compare?contract_id_1=test1&contract_id_2=test2", 401)

    def test_batch_export_endpoints(self):
        """Test new batch export endpoints"""
        print("\n📦 Testing batch export endpoints...")
        
        # Test batch export endpoint (requires auth)
        export_data = {
            "clause_numbers": ["52.212-4", "252.204-7012"],
            "clause_ids": [],
            "include_full_text": True,
            "include_flowdown_info": True,
            "format": "pdf"
        }
        self.run_test("Batch Export PDF (Unauth)", "POST", "api/export/batch", 401, export_data)
        
        # Test flowdown report export (requires auth)
        flowdown_data = {
            "contract_type": "Fixed-Price",
            "contract_value": 1000000,
            "clauses": ["52.212-4", "252.204-7012"]
        }
        self.run_test("Flowdown Report Export (Unauth)", "POST", "api/export/flowdown-report", 401, flowdown_data)

    def test_agiloft_integration_endpoints(self):
        """Test Agiloft integration endpoints"""
        print("\n🔗 Testing Agiloft integration endpoints...")
        
        # Test connection endpoint (requires auth)
        agiloft_config = {
            "kb_url": "https://test.agiloft.com/ewws",
            "username": "test_user",
            "password": "test_pass",
            "kb_name": "Default"
        }
        self.run_test("Agiloft Test Connection (Unauth)", "POST", "api/agiloft/test-connection", 401, agiloft_config)
        
        # Test push clauses endpoint (requires auth) - NEW ENDPOINT
        push_data = {
            "config": agiloft_config,
            "source": "database"
        }
        self.run_test("Agiloft Push Clauses (Unauth)", "POST", "api/agiloft/push-clauses", 401, push_data)
        
        # Test contracts endpoint (requires auth) - NEW ENDPOINT
        contracts_data = {
            "config": agiloft_config,
            "table_name": "Contracts"
        }
        self.run_test("Agiloft Get Contracts (Unauth)", "POST", "api/agiloft/contracts", 401, contracts_data)
        
        # Test analyze contract endpoint (requires auth) - NEW ENDPOINT
        analyze_data = {
            "config": agiloft_config,
            "contract_id": "demo-1",
            "contract_clauses": ["52.212-4", "252.204-7012"],
            "contract_type": "Fixed-Price",
            "contract_value": 1000000
        }
        self.run_test("Agiloft Analyze Contract (Unauth)", "POST", "api/agiloft/analyze-contract", 401, analyze_data)
        
        # Test update contract endpoint (requires auth) - NEW ENDPOINT
        update_data = {
            "config": agiloft_config,
            "contract_id": "demo-1",
            "updates": {
                "missing_clauses": ["52.219-8"],
                "flowdown_clauses": ["52.212-4"]
            }
        }
        self.run_test("Agiloft Update Contract (Unauth)", "POST", "api/agiloft/update-contract", 401, update_data)

    def test_authenticated_endpoints(self):
        """Test endpoints that require authentication"""
        print("\n📝 Testing authenticated endpoints (will fail without session)...")
        
        # These tests will fail without proper authentication
        # but we can verify they return 401 as expected
        
        self.test_ai_search_unauthenticated()
        self.test_contracts_unauthenticated()
        self.test_flowdown_unauthenticated()
        
        # Test new endpoints
        self.test_new_acquisition_gov_endpoints()
        self.test_contract_comparison_endpoint()
        self.test_batch_export_endpoints()
        self.test_agiloft_integration_endpoints()
        
        # Test user endpoints
        self.run_test("Get Favorites (Unauth)", "GET", "api/user/favorites", 401)
        self.run_test("Get Saved Searches (Unauth)", "GET", "api/user/saved-searches", 401)
        self.run_test("Get Annotations (Unauth)", "GET", "api/user/annotations", 401)

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Federal Clause Management API Tests")
        print(f"Testing against: {self.base_url}")
        print("=" * 60)

        # Test public endpoints
        print("\n📋 Testing public endpoints...")
        self.test_root_endpoint()
        self.test_clause_search_basic()
        self.test_clause_search_with_type()
        self.test_clause_by_id()
        self.test_clause_by_number()

        # Test auth requirements
        print("\n🔒 Testing authentication requirements...")
        self.test_auth_me_unauthenticated()
        
        # Try to set up test session
        session_valid = self.create_test_session()
        
        if session_valid:
            # Test authenticated features
            self.test_authenticated_features_with_token()
        else:
            # Test authenticated endpoints (without auth - should return 401)
            self.test_authenticated_endpoints()

        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("⚠️  Some tests failed - see details above")
            return 1

    def get_test_report(self):
        """Get detailed test report"""
        return {
            "summary": {
                "total_tests": self.tests_run,
                "passed_tests": self.tests_passed,
                "failed_tests": self.tests_run - self.tests_passed,
                "success_rate": f"{(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%"
            },
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }

def main():
    tester = FederalClauseAPITester()
    exit_code = tester.run_all_tests()
    
    # Save detailed report
    report = tester.get_test_report()
    with open('/app/test_reports/backend_api_test_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Detailed report saved to: /app/test_reports/backend_api_test_report.json")
    return exit_code

if __name__ == "__main__":
    sys.exit(main())