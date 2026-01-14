# Federal Clause Management App - PRD

## Original Problem Statement
Build a Federal Clause Management app with comprehensive features for government contractors.

## User Personas
1. **Government Contractors** - Search and understand FAR/DFARS requirements
2. **Compliance Officers** - Analyze contracts for regulatory compliance
3. **Legal Teams** - Review clause flowdown requirements for subcontractors

## Core Requirements
- Smart Clause Search (AI-powered via OpenAI GPT-5.2)
- Contract Upload & Compare
- Flowdown Analysis
- Google OAuth Authentication
- Batch Export (PDF/JSON/CSV)
- Agiloft Knowledge Base Integration
- Live clause data from acquisition.gov

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Emergent-managed Google OAuth
- **External**: acquisition.gov, Agiloft REST API

## What's Been Implemented

### Phase 1 - MVP ✅
- [x] Landing page with shield+scale logo
- [x] Smart clause search (basic + AI-powered)
- [x] 10 sample FAR/DFARS clauses pre-loaded
- [x] Clause detail pages with full text
- [x] Google OAuth authentication
- [x] Protected dashboard with 6 quick actions
- [x] Contract upload with clause identification
- [x] AI-powered contract analysis & comparison
- [x] Compliance checklist generator
- [x] Favorites, saved searches, annotations
- [x] PDF export for single clauses

### Phase 2 - Enhanced Features ✅
- [x] Full text extraction from acquisition.gov
- [x] acquisition.gov sync endpoint for FAR clause index
- [x] Contract comparison page with AI analysis
- [x] Flowdown analysis with contract type/value filtering
- [x] Flowdown report PDF export

### Phase 3 - Integrations & Batch ✅
- [x] Agiloft integration (test-connection, sync-clauses, tables)
- [x] Batch export page with clause selection
- [x] Multi-format export (PDF, JSON, CSV)
- [x] Export options: full text, flowdown info
- [x] Dashboard with 6 quick actions

## API Endpoints
- `GET /api/clauses/search` - Search clauses
- `GET /api/clauses/ai-search` - AI-powered search
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync FAR index
- `POST /api/contracts/upload` - Upload contract
- `POST /api/contracts/compare` - Compare contracts
- `POST /api/flowdown/analyze` - Flowdown analysis
- `POST /api/export/batch` - Batch export (PDF/JSON/CSV)
- `POST /api/export/flowdown-report` - Flowdown PDF report
- `POST /api/agiloft/test-connection` - Test Agiloft connection
- `POST /api/agiloft/sync-clauses` - Sync from Agiloft

## Prioritized Backlog

### P1 - High Priority
- [ ] Email notifications for clause changes
- [ ] Scheduled Agiloft sync jobs
- [ ] Bulk clause update from acquisition.gov

### P2 - Medium Priority  
- [ ] Compliance scoring dashboard
- [ ] Collaboration features (share contracts)
- [ ] Clause change tracking with diff view

### P3 - Nice to Have
- [ ] Dark mode toggle
- [ ] Mobile app
- [ ] API keys for external integrations
