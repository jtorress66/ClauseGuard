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

### Agiloft Integration (Bidirectional)
- [x] **Push Clauses TO Agiloft**: Update Agiloft KB with our clauses
- [x] **Analyze Agiloft Contracts**: Fetch contracts and check compliance
- [x] **Clause Comparison**: Compare FAR/DFARS clauses between acquisition.gov and Agiloft KB
  - Uses AgiloftClient with correct REST API format
  - Filters out "Reserved" clauses (empty placeholders)
- [x] **Upload Missing Clauses**: POST /clause with clause_number, clause_title, clause_text, clause_type

### Export & Reporting
- [x] Batch export (PDF, JSON, CSV)
- [x] Flowdown report PDF
- [x] Single clause PDF export

### Authentication
- [x] Custom email/password authentication with JWT
- [x] User registration with validation
- [x] Protected routes for all sensitive features

## Bug Fixes Applied - 2025-01-27

### Fixed Issues:
1. ✅ **Note Saving** - Fixed MongoDB ObjectId serialization in POST /api/user/annotations
2. ✅ **PDF Export** - Fixed endpoint to accept `{clauses: [...]}` JSON body
3. ✅ **Save Search** - Fixed MongoDB ObjectId serialization in POST /api/user/saved-searches
4. ✅ **AI Search Toggle** - No longer auto-triggers search, just toggles mode
5. ✅ **Dashboard Button** - Added to SearchResults, ClauseDetail, and AgiloftIntegration pages
6. ✅ **Reserved Clauses** - Filtered out from acquisition.gov scraping (they are empty slots)
7. ✅ **Upload Missing Clauses** - Uses POST /clause with correct field names

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses
- `GET /api/clauses/ai-search` - AI-powered search (requires auth)
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync with FAR/DFARS support

### User Features
- `POST /api/user/annotations` - Save notes (FIXED)
- `GET /api/user/annotations` - Get annotations
- `DELETE /api/user/annotations/{id}` - Delete annotation
- `POST /api/user/saved-searches` - Save search (FIXED)
- `GET /api/user/saved-searches` - Get saved searches
- `POST /api/user/favorites` - Add favorite (FIXED)
- `GET /api/user/favorites` - Get favorites

### Export
- `POST /api/export/pdf` - Export clauses to PDF (FIXED - accepts JSON body)
- `POST /api/export/batch` - Batch export (PDF/JSON/CSV)
- `POST /api/export/flowdown-report` - Flowdown PDF report

### Agiloft Integration
- `POST /api/agiloft/test-connection` - Test Agiloft connection
- `POST /api/agiloft/compare-clauses` - Compare clauses (filters Reserved)
- `POST /api/agiloft/upload-missing-clauses` - Upload using POST /clause
- `POST /api/agiloft/contracts` - Get Agiloft contracts
- `POST /api/agiloft/analyze-contract` - Analyze contract compliance

## Tech Stack
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python) with Modular Architecture
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Custom JWT-based email/password
- **External**: acquisition.gov, Agiloft REST API

## Backend Architecture
```
/app/backend/
├── server.py              # Main FastAPI app with routers
├── agiloft_client.py      # Correct Agiloft REST API client
├── acqgov_scraper.py      # Robust acquisition.gov scraper (filters Reserved)
├── comparison_routes.py   # Modular comparison endpoints
└── requirements.txt
```

## Agiloft API Configuration
- **Login**: POST `/login` with `{login, password, KB, lang}`
- **Search clauses**: POST `/clause/search` with `{search: "", field: ["clause_number"], query: ""}`
- **Create clause**: POST `/clause` with `{clause_number, clause_title, clause_text, clause_type}`

## Key MongoDB Fixes
All endpoints that insert documents now properly remove `_id` before returning:
- `ann_dict.pop('_id', None)` in annotations
- `search_dict.pop('_id', None)` in saved-searches  
- `fav_dict.pop('_id', None)` in favorites

## Change Log
- **2025-01-27**: Fixed 7 bugs - note saving, PDF export, save search, AI toggle, dashboard button, reserved clauses filter, upload missing clauses
- **2025-01-22**: P0 Agiloft comparison fix, upload-missing-clauses improvement, sync endpoint enhancement
- **2025-01-21**: Changed auth to email/password, updated UI to modern SaaS-style design

## Next Tasks (P1)
- [ ] Real-time notifications for clause tracking changes
- [ ] Scheduled sync jobs for Agiloft

## Future/Backlog (P2)
- [ ] Enhanced UI for Agiloft field mapping
- [ ] Email notifications for clause changes
- [ ] Bulk clause update from acquisition.gov
- [ ] Fallback to Playwright UI automation
