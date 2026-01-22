# Federal Clause Management App - PRD

## Problem Statement
Build a Federal Clause Management app that helps government contractors manage FAR/DFARS clause compliance, with full Agiloft CLM integration for bidirectional sync and contract analysis.

## User Personas
1. **Government Contractors** - Search and understand FAR/DFARS requirements
2. **Compliance Officers** - Analyze contracts for regulatory compliance
3. **Legal/Contracts Teams** - Manage clause libraries in Agiloft CLM

## Core Features Implemented ✅

### Clause Management
- [x] Smart Clause Search (basic + AI-powered via OpenAI GPT-5.2)
- [x] Full text extraction from acquisition.gov
- [x] 10+ sample FAR/DFARS clauses pre-loaded
- [x] Clause detail pages with full text and metadata
- [x] Favorites, saved searches, annotations

### Contract Analysis
- [x] Contract upload with automatic clause identification
- [x] AI-powered contract analysis
- [x] Contract comparison (side-by-side)
- [x] Compliance checklist generator

### Flowdown Analysis
- [x] Contract type and value-based filtering
- [x] Required flowdown clause identification
- [x] Present vs Missing clause analysis
- [x] PDF flowdown report export

### Agiloft Integration (Bidirectional) - UPDATED 2025-01-22
- [x] **Push Clauses TO Agiloft**: Update Agiloft KB with our clauses
  - From our database
  - Live from acquisition.gov
- [x] **Analyze Agiloft Contracts**: Fetch contracts and check compliance
  - View contracts from Agiloft KB
  - Identify correct/missing/needs-update clauses
  - Check flowdown requirements
  - Update contracts with compliance flags
- [x] **Clause Comparison** (P0 FIX): Compare FAR/DFARS clauses between acquisition.gov and Agiloft KB
  - **NEW**: Uses AgiloftClient class with correct REST API format
  - **API Format**: POST /clause/search with body `{"search": "", "field": ["clause_number"], "query": ""}`
  - Identify clauses missing in Agiloft
  - Upload missing clauses from acquisition.gov to Agiloft
  - View matched clauses and clauses only in Agiloft
- [x] **Upload Missing Clauses** (P1): Updated to use new AgiloftClient for proper clause_number field handling

### Local Database Caching (P1) - NEW 2025-01-22
- [x] Enhanced sync endpoint to cache acquisition.gov clauses locally
- [x] Supports both FAR and DFARS clause types
- [x] Force refresh option to update existing entries
- [x] Reduces API calls to acquisition.gov during comparisons

### Export & Reporting
- [x] Batch export (PDF, JSON, CSV)
- [x] Flowdown report PDF
- [x] Include/exclude full text and flowdown info

### Authentication
- [x] Custom email/password authentication with JWT
- [x] User registration with validation
- [x] Protected routes for all sensitive features

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses
- `GET /api/clauses/ai-search` - AI-powered search (requires auth)
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Enhanced sync with FAR/DFARS support

### Contracts
- `POST /api/contracts/upload` - Upload contract
- `POST /api/contracts/compare` - Compare contracts
- `POST /api/contracts/{id}/analyze` - AI analysis

### Flowdown
- `POST /api/flowdown/analyze` - Flowdown analysis

### Agiloft Integration (UPDATED)
- `POST /api/agiloft/test-connection` - Test Agiloft connection
- `POST /api/agiloft/push-clauses` - Push clauses TO Agiloft
- `POST /api/agiloft/compare-clauses` - **FIXED**: Now uses AgiloftClient with correct API format
- `POST /api/agiloft/upload-missing-clauses` - **IMPROVED**: Now uses AgiloftClient and includes clause_number field
- `POST /api/agiloft/contracts` - Get Agiloft contracts
- `POST /api/agiloft/analyze-contract` - Analyze contract compliance
- `POST /api/agiloft/update-contract` - Update contract in Agiloft

### Comparison Routes (NEW)
- `GET /api/comparison/acqgov/clauses` - Fetch clauses from acquisition.gov with caching
- `POST /api/comparison/agiloft/clauses/search` - Search Agiloft clauses
- `POST /api/comparison/compare` - Full comparison between sources
- `POST /api/comparison/upload` - Upload clauses to Agiloft

### Export
- `POST /api/export/batch` - Batch export (PDF/JSON/CSV)
- `POST /api/export/flowdown-report` - Flowdown PDF report

## Tech Stack
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python) with Modular Architecture
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Custom JWT-based email/password
- **External**: acquisition.gov, Agiloft REST API

## Backend Architecture (UPDATED 2025-01-22)
```
/app/backend/
├── server.py              # Main FastAPI app with routers
├── agiloft_client.py      # NEW: Correct Agiloft REST API client
├── acqgov_scraper.py      # NEW: Robust acquisition.gov scraper
├── comparison_routes.py   # NEW: Modular comparison endpoints
└── requirements.txt
```

### Key Modules
- **agiloft_client.py**: Contains AgiloftClient class with correct API format
  - Login: POST /login with `{login, password, KB, lang}`
  - Search: POST /clause/search with `{search: "", field: ["clause_number"], query: ""}`
  - Create/Upsert: POST /clause or /clause/upsert
- **acqgov_scraper.py**: Robust scraper for FAR Part 52 and DFARS Part 252
  - Regex pattern: `(\d{1,4}\.\d{1,4}(?:[-–—](?=\d)\d{1,6})*)`
  - Handles various dash characters and normalizes clause numbers
- **comparison_routes.py**: Modular router for comparison operations

## Agiloft API Configuration (CRITICAL)
- **Instance URL format**: `https://yourinstance.agiloft.com` or `https://yourinstance.saas.agiloft.com`
- **Full REST API URL**: `{base}/ewws/alrest/{KB}/{endpoint}`
- **Login endpoint**: POST `/login` with JSON body `{login, password, KB, lang}`
- **Token location**: `response.result.access_token`
- **Clause table**: `clause` (lowercase, singular)
- **Clause search**: POST `/clause/search` with body `{"search": "", "field": ["clause_number"], "query": ""}`
- **THIS IS THE CORRECT FORMAT** - Do not use OData-style $select syntax

## Next Tasks (P1) - PARTIALLY COMPLETED
- [x] Upload functionality to push missing clauses to Agiloft - Uses new AgiloftClient
- [x] Local database caching for scraped acquisition.gov clauses - Enhanced sync endpoint
- [ ] Real-time notifications for tracking changes to clauses

## Future/Backlog Tasks (P2)
- [ ] Enhanced UI for Agiloft field mapping configuration
- [ ] Scheduled sync jobs for Agiloft
- [ ] Email notifications for clause changes
- [ ] Bulk clause update from acquisition.gov
- [ ] Enhanced semantic matching for AI search
- [ ] Fallback to Playwright UI automation if REST API proves unreliable

## Change Log
- **2025-01-22 (Session 2)**: 
  - FIXED P0 Agiloft comparison bug - Now uses correct API format via new AgiloftClient
  - Updated upload-missing-clauses to use AgiloftClient and include clause_number field
  - Enhanced sync-from-acquisition-gov endpoint with FAR/DFARS support and force refresh
  - Fixed frontend Cloudflare 520 error handling in connection test
  - Added pytest test suite for Agiloft integration
- **2025-01-22 (Session 1)**: Major backend refactor into modular architecture. Fixed AI Search, login UI, DFARS scraper, and URL construction bugs.
- **2025-01-21**: Changed authentication from Google OAuth to email/password. Updated entire UI to modern SaaS-style design.
- **2025-01-15**: Fixed Agiloft URL format and contract data mapping.

## Notes
- Agiloft integration now uses the correct REST API format via AgiloftClient
- The key is the POST /clause/search with `field: ["clause_number"]` - without this, Agiloft doesn't return the clause_number field
- All protected routes require authentication
- AI features require Emergent LLM key (already configured)
- AI Search ONLY uses indexed acquisition.gov data - never fabricates clauses
