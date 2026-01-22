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
- [x] **Clause Comparison**: Compare FAR/DFARS clauses between local DB and Agiloft KB
  - Identify clauses missing in Agiloft
  - Upload missing clauses from acquisition.gov to Agiloft
  - View matched clauses and clauses only in Agiloft

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
- `POST /api/agiloft/compare-clauses` - Compare local clauses with Agiloft KB
- `POST /api/agiloft/upload-missing-clauses` - Upload missing clauses to Agiloft
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
- **Auth**: Custom JWT-based email/password
- **External**: acquisition.gov, Agiloft REST API

## Next Tasks (P1)
1. Real-time notifications for clause tracking changes
2. Enhanced UI for Agiloft field mapping configuration

## Future/Backlog Tasks (P2)
1. Add scheduled sync jobs for Agiloft
2. Email notifications for clause changes
3. Bulk clause update from acquisition.gov
4. Enhanced semantic matching for AI search

## Notes
- Agiloft integration now properly validates credentials (no longer returns success with invalid passwords)
- All protected routes require authentication
- AI features require Emergent LLM key (already configured)
- AI Search ONLY uses indexed acquisition.gov data - never fabricates clauses

## Agiloft API Configuration
- **Instance URL format**: `https://yourinstance.agiloft.com` (without "saas" subdomain)
- **Full REST API URL**: `{base}/ewws/alrest/{KB}/{endpoint}`
- **Login endpoint**: POST `/login` with JSON body `{login, password, KB, lang}`
- **Token location**: `response.result.access_token`
- **Clause table name**: `clause` (lowercase, singular)
- **Contract table name**: `contract` (lowercase, singular)
- **Contract field mapping** (Agiloft → our fields):
  - `DAOcontract_to_contract.root_contract_title` → contract_title
  - `DAOcontract_to_contract_type.contract_type` → contract_type
  - `DAOcontract_to_company.company_name` → company_name
  - `wfstate` → status
- **Search capabilities**: 
  - By Contract ID (exact match via Agiloft query)
  - By Contract Title, Company Name, Type (client-side filtering)

## Change Log
- **2025-01-22**: Fixed AI Search button not returning results - button now triggers search when toggled. Added Clause Comparison feature to compare FAR/DFARS clauses between local DB and Agiloft KB with ability to upload missing clauses. Fixed SelectItem empty value bug in Agiloft Integration page. All bugs reported by user verified fixed.
- **2025-01-21**: Updated AI search to ONLY use indexed acquisition.gov data - no fabricated clauses. Added source indicator showing "acquisition.gov". Fixed summary NoneType bug. UI now clearly shows data is from authoritative source.
- **2025-01-21**: Changed authentication from Google OAuth to email/password with registration. Updated entire UI to modern SaaS-style design with soft gradients, modern cards, teal color palette, and enhanced typography. All 12 auth tests passed.
- **2025-01-15**: Fixed contract data mapping - now properly extracts title, type, company from Agiloft's nested DAO structure. Added search/filter functionality for contracts (by ID, title, company, type).
- **2025-01-15**: Fixed Agiloft URL format - removed "saas" subdomain, now uses `/ewws/alrest/{KB}/` path. Fixed token extraction from `result.access_token`.
- **2025-01-15**: Fixed critical Agiloft login bug - no longer returns "connection successful" with invalid credentials.
- **2025-01-14**: Replaced server.py with user-provided version. Full regression testing passed (33/33 tests).
