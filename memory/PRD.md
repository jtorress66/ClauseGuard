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
- [x] Sample FAR/DFARS clauses pre-loaded
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
- [x] **Upload Missing Clauses**: Auto-fetches from acquisition.gov if not in local DB

### Export & Reporting
- [x] Batch export (PDF, JSON, CSV)
- [x] Flowdown report PDF
- [x] Single clause PDF export with full text

### Authentication
- [x] Custom email/password authentication with JWT
- [x] User registration with validation
- [x] Protected routes for all sensitive features

## Bug Fixes - 2025-01-27 (Session 2)

### Fixed Issues:
1. ✅ **AI Search** - Now triggers search when clicked (requires authentication)
   - Shows "Please sign in to use AI search" for non-authenticated users (expected)
   - Returns AI analysis and AI explanations for each clause when authenticated
2. ✅ **PDF Export** - Now includes full clause text (fetches from acquisition.gov if needed)
3. ✅ **Upload Missing Clauses** - Now auto-fetches from acquisition.gov if not in local DB
4. ✅ **Dashboard Button** - Added `type="button"` to prevent form submission behavior

### Previous Fixes (Session 1):
- Note saving (MongoDB ObjectId serialization)
- Save search functionality
- Dashboard button visibility on all pages
- Reserved clauses filtered from comparison

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses (local DB)
- `GET /api/clauses/ai-search` - AI-powered search (requires auth)
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync with FAR/DFARS support

### User Features
- `POST /api/user/annotations` - Save notes
- `POST /api/user/saved-searches` - Save search
- `POST /api/user/favorites` - Add favorite

### Export
- `POST /api/export/pdf` - Export clauses to PDF with full text
- `POST /api/export/batch` - Batch export (PDF/JSON/CSV)
- `POST /api/export/flowdown-report` - Flowdown PDF report

### Agiloft Integration
- `POST /api/agiloft/compare-clauses` - Compare clauses (filters Reserved)
- `POST /api/agiloft/upload-missing-clauses` - Upload (auto-fetches from acquisition.gov)

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

## Key Technical Details

### AI Search Behavior
- Requires authentication
- When NOT logged in: Shows "Please sign in to use AI search" toast
- When logged in: Triggers search and returns AI analysis + AI explanations per clause

### PDF Export
- Fetches full text from acquisition.gov if not in local DB
- Caches fetched text in MongoDB for future exports
- Includes summary, keywords, and full clause text

### Upload Missing Clauses
- Always checks local DB first
- If clause missing or no text, fetches from acquisition.gov
- Creates minimal entry if acquisition.gov fetch fails
- Stores fetched text in MongoDB

## Change Log
- **2025-01-27 (Session 2)**: Fixed AI Search trigger, PDF full text export, upload missing clauses auto-fetch, dashboard button type
- **2025-01-27 (Session 1)**: Fixed note saving, PDF export format, save search, AI toggle, dashboard button visibility, reserved clauses filter
- **2025-01-22**: P0 Agiloft comparison fix, backend modularization
- **2025-01-21**: Changed auth to email/password, updated UI design

## Next Tasks (P1)
- [ ] Real-time notifications for clause tracking changes
- [ ] Scheduled sync jobs for Agiloft

## Future/Backlog (P2)
- [ ] Enhanced UI for Agiloft field mapping
- [ ] Email notifications for clause changes
- [ ] Bulk clause update from acquisition.gov
- [ ] Fallback to Playwright UI automation
