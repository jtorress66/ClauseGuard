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
  - From our database
  - Live from acquisition.gov
- [x] **Analyze Agiloft Contracts**: Fetch contracts and check compliance
  - View contracts from Agiloft KB
  - Identify correct/missing/needs-update clauses
  - Check flowdown requirements
  - Update contracts with compliance flags

### Export & Reporting
- [x] Batch export (PDF, JSON, CSV)
- [x] Flowdown report PDF
- [x] Include/exclude full text and flowdown info

### Authentication
- [x] Google OAuth via Emergent Auth
- [x] Protected routes for all sensitive features

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses
- `GET /api/clauses/ai-search` - AI-powered search
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync FAR index

### Contracts
- `POST /api/contracts/upload` - Upload contract
- `POST /api/contracts/compare` - Compare contracts
- `POST /api/contracts/{id}/analyze` - AI analysis

### Flowdown
- `POST /api/flowdown/analyze` - Flowdown analysis

### Agiloft Integration
- `POST /api/agiloft/test-connection` - Test Agiloft connection
- `POST /api/agiloft/push-clauses` - Push clauses TO Agiloft
- `POST /api/agiloft/contracts` - Get Agiloft contracts
- `POST /api/agiloft/analyze-contract` - Analyze contract compliance
- `POST /api/agiloft/update-contract` - Update contract in Agiloft

### Export
- `POST /api/export/batch` - Batch export (PDF/JSON/CSV)
- `POST /api/export/flowdown-report` - Flowdown PDF report

## Tech Stack
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Emergent-managed Google OAuth
- **External**: acquisition.gov, Agiloft REST API

## Next Tasks (P1)
1. Add scheduled sync jobs for Agiloft
2. Email notifications for clause changes
3. Bulk clause update from acquisition.gov
4. Enhanced Agiloft field mapping configuration

## Notes
- Agiloft integration uses demo/sample data when no live connection is available
- All protected routes require authentication
- AI features require Emergent LLM key (already configured)
