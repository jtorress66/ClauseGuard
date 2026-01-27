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
- [x] 872+ FAR/DFARS clauses synced from acquisition.gov
- [x] Clause detail pages with full text and metadata
- [x] Favorites, saved searches, annotations
- [x] **Sync All Clauses** button on Dashboard - fetches full text for all clauses

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
- [x] **Upload Missing Clauses**: Auto-fetches from acquisition.gov if not in local DB
  - Note: Detailed logging added for debugging API issues

### Export & Reporting
- [x] **Batch export** (PDF, JSON, CSV) with **FULL clause text** from acquisition.gov
- [x] Flowdown report PDF
- [x] Single clause PDF export with full text
- [x] Automatic fetch from acquisition.gov if text is missing or short (<1000 chars)

### Authentication
- [x] Custom email/password authentication with JWT
- [x] User registration with validation
- [x] Protected routes for all sensitive features

## New Features - 2025-01-27 (Session 3)

### 1. Sync All Clauses Button ✅
- Added to Dashboard quick actions grid (7th button)
- Calls `/api/clauses/sync-from-acquisition-gov` to sync clause index
- Calls `/api/clauses/sync-full-text` to fetch full text for clauses missing it
- Shows progress toasts during sync

### 2. Full Text in PDF Export ✅
- Batch export now fetches full clause text from acquisition.gov
- Checks if existing text is <1000 chars (likely summary) and fetches full text
- Caches fetched text in MongoDB for future exports
- 52.212-4 now exports with 50,000 chars of full text

### 3. Enhanced Agiloft Logging ✅
- `create_clause` method now logs:
  - Clause number and payload
  - Response status code
  - Response text (first 500 chars)
- Helps debug "Uploaded 0 of 1" issues

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses (local DB)
- `GET /api/clauses/ai-search` - AI-powered search (requires auth)
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync clause index
- `POST /api/clauses/sync-full-text` - **NEW** - Fetch full text for clauses missing it

### Export
- `POST /api/export/pdf` - Export single clause to PDF with full text
- `POST /api/export/batch` - **UPDATED** - Batch export with automatic full text fetch
- `POST /api/export/flowdown-report` - Flowdown PDF report

### Agiloft Integration
- `POST /api/agiloft/compare-clauses` - Compare clauses
- `POST /api/agiloft/upload-missing-clauses` - Upload (auto-fetches from acquisition.gov)

## Tech Stack
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python) with Modular Architecture
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Custom JWT-based email/password
- **External**: acquisition.gov, Agiloft REST API

## Known Issues

### Agiloft Upload "Uploaded 0 of 1"
- The Agiloft `create_clause` API returns success=false for unknown reasons
- Enhanced logging added to debug this issue
- Likely causes:
  - Agiloft API permissions
  - Field name mismatches
  - Required fields missing
- User should check Agiloft API logs and field configurations

## Change Log
- **2025-01-27 (Session 3)**: Added "Sync All Clauses" button, fixed PDF export to include full text, enhanced Agiloft logging
- **2025-01-27 (Session 2)**: Fixed AI Search, PDF export format, upload missing clauses, dashboard button type
- **2025-01-27 (Session 1)**: Fixed note saving, save search, AI toggle, dashboard button, reserved clauses filter
- **2025-01-22**: P0 Agiloft comparison fix, backend modularization

## Next Tasks (P1)
- [ ] Debug Agiloft upload API issue with enhanced logs
- [ ] Real-time notifications for clause tracking changes
- [ ] Scheduled sync jobs for Agiloft

## Future/Backlog (P2)
- [ ] Enhanced UI for Agiloft field mapping
- [ ] Email notifications for clause changes
- [ ] Bulk clause update from acquisition.gov
- [ ] Fallback to Playwright UI automation
