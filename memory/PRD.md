# Federal Clause Management App - PRD

## Original Problem Statement
Build a Federal Clause Management app with features:
- Smart Clause Search (AI-powered)
- Contract Upload & Compare (AI analysis)  
- Flowdown Analysis
- Google Social Login (Emergent-managed)
- Additional: Compliance checklist generator, Export reports (PDF), Saved searches & favorites, Clause annotations
- Custom shield+scale logo
- Live clause data from acquisition.gov
- Contract comparison feature

## User Personas
1. **Government Contractors** - Need to search and understand FAR/DFARS requirements
2. **Compliance Officers** - Analyze contracts for regulatory compliance
3. **Legal Teams** - Review clause flowdown requirements for subcontractors

## Core Requirements (Static)
- Search FAR/DFARS clauses with AI-enhanced search
- Upload contracts and identify referenced clauses
- Compare contracts against official requirements
- Analyze flowdown requirements
- User authentication via Google OAuth
- Save favorites and annotations
- Export reports to PDF
- Fetch live clause data from acquisition.gov
- Compare two uploaded contracts

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **AI**: OpenAI GPT-5.2 via Emergent LLM Key
- **Auth**: Emergent-managed Google OAuth
- **External Data**: acquisition.gov web scraping

## What's Been Implemented (December 2025)
### Phase 1 - MVP Complete ✅
- [x] Landing page with dark hero gradient matching reference design
- [x] Custom shield+scale SVG logo (ClauseGuardLogo component)
- [x] Smart clause search (basic + AI-powered)
- [x] 10 sample FAR/DFARS clauses pre-loaded
- [x] Clause detail pages with full text and metadata
- [x] Google OAuth authentication flow
- [x] Protected dashboard with quick actions
- [x] Contract upload with clause identification
- [x] AI-powered contract analysis
- [x] Flowdown analysis tool
- [x] Compliance checklist generator
- [x] PDF export for clauses
- [x] Favorites and saved searches
- [x] Clause annotations/notes

### Phase 2 - Live Data & Comparison ✅
- [x] acquisition.gov integration for fetching live clauses
- [x] Sync endpoint for FAR clause index
- [x] Contract comparison page (/compare)
- [x] AI-powered comparison analysis
- [x] Updated Dashboard quick actions

## API Endpoints
- `GET /api/clauses/search` - Search clauses
- `GET /api/clauses/ai-search` - AI-powered search
- `GET /api/clauses/fetch-live/{clause_number}` - Fetch from acquisition.gov
- `POST /api/clauses/sync-from-acquisition-gov` - Sync clause index
- `POST /api/contracts/upload` - Upload contract
- `POST /api/contracts/compare` - Compare two contracts
- `POST /api/flowdown/analyze` - Flowdown analysis
- `POST /api/export/pdf` - Export to PDF

## Prioritized Backlog

### P0 - Critical ✅
- [x] Core search functionality 
- [x] Authentication 
- [x] Contract upload 
- [x] Contract comparison

### P1 - High Priority
- [x] Integration with acquisition.gov for live clause data
- [ ] Email notifications for clause changes
- [ ] Full text extraction from acquisition.gov

### P2 - Medium Priority
- [ ] Batch clause export
- [ ] Compliance scoring dashboard
- [ ] Collaboration features (share clauses/contracts)
- [ ] Clause change tracking with diff view

### P3 - Nice to Have
- [ ] Mobile responsive improvements
- [ ] Dark mode toggle
- [ ] API for external integrations
- [ ] Audit log for compliance tracking

## Next Tasks
1. Implement email alerts for tracked clauses
2. Add full text extraction from acquisition.gov pages
3. Enhance PDF export with custom templates
4. Add batch operations for clause exports
