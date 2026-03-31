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
- [x] **Formatted clause text display** with proper indentation (ListL1/L2/L3 classes)

### Contract Analysis
- [x] Contract upload with automatic clause identification
- [x] **Smart Clause Header Detection** - Only detects actual clause headers, not references within clauses
  - Ignores clause numbers mentioned inside other clauses (e.g., 52.212-5 referencing 52.203-19)
  - Detects patterns like "52.xxx-xx Title" at start of lines
  - Filters out checkbox lists, numbered references, and "see/per/pursuant to" mentions
  - **NEW:** Handles numbered list formats like "XX (1) 52.203-6" in contract documents
- [x] **Rescan Clauses** button - Re-analyze existing contracts with improved detection
- [x] AI-powered contract analysis
- [x] Contract comparison (side-by-side)
- [x] **Compliance Checklist Generator** - FIXED (2025-02-05) - Generates checklists from contract clauses
- [x] **NEW: Agiloft Extraction Feature** - Extract clauses with checkbox detection for Agiloft KB upload
  - Detects clauses marked with X or XX (selected) vs ___ (unselected)
  - Selected checkbox clauses are treated as "top-level" clauses for upload
  - Unselected clauses are tracked but NOT included in the upload list
  - Prose references (like "see FAR 52.xxx") are filtered out
  - Exports structured JSON file with clause numbers, titles, types (no Source_URL field)
  - **DFARS clause text fetching** - FIXED (2025-03-31): Fetches DFARS (252.x) clauses from the combined Part 252 page using anchor IDs (`#DFARS_{clause_number}`), with in-memory caching to avoid re-downloading the large page
  - **Placeholder detection** - Uses 500-char threshold to identify stale summaries and re-fetch full text from acquisition.gov
  - Endpoints: `/api/contracts/{id}/extract-for-agiloft` and `/api/contracts/{id}/export-clauses-json`

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
  - SOLVED: `clause_type` field must be omitted (Agiloft derives it automatically)

### Export & Reporting
- [x] **Batch export** (PDF, JSON, CSV) with **FULL clause text** from acquisition.gov
- [x] Flowdown report PDF
- [x] Single clause PDF export with full text
- [x] Automatic fetch from acquisition.gov if text is missing or short (<1000 chars)
- [x] **PDF export with proper indentation** - hanging indent styles for (a), (1), (i), (A) patterns
- [x] **Centered "(End of clause)" marker** in PDF

### Authentication
- [x] Custom email/password authentication with JWT
- [x] User registration with validation
- [x] Protected routes for all sensitive features

### UI/UX
- [x] **Search page Clear button** - Resets search query, results, and URL params
- [x] **Search results with type badges** - FAR (blue) and DFARS (purple)

## Bug Fixes - 2025-02-02 (Session 4) ✅

### P0 - Regressions Fixed
1. **Clause Detail Page Text Formatting** - FIXED
   - Root cause: Was returning raw DITA XML instead of formatted HTML
   - Fix: `format_dita_html_for_agiloft()` now detects ListL1/L2/L3 classes and applies inline padding-left styles
   - Result: Proper indentation for (a), (1), (i), (A) patterns

2. **PDF Export Formatting** - FIXED
   - Root cause: `_extract_pdf_paragraphs_from_dita()` didn't detect indentation from HTML classes/styles
   - Fix: Now uses `_detect_level_from_prefix()` for consistent indentation detection
   - Result: Hanging indent styles applied correctly

3. **PDF "(End of clause)" Centering** - FIXED
   - Root cause: Only checked text content, not style attribute
   - Fix: `_extract_pdf_paragraphs_from_dita()` now checks for `text-align:center` in style OR text content
   - Result: "(End of clause)" marker is centered

### P1 - UI Improvements
4. **Search Page Clear Button** - ADDED
   - Added `handleClearSearch()` function
   - Clear button appears when query or results exist
   - Resets: query, results, aiAnalysis, clauseType, useAI, and URL params

## API Endpoints

### Clauses
- `GET /api/clauses/search` - Search clauses (local DB)
- `GET /api/clauses/ai-search` - AI-powered search (requires auth)
- `GET /api/clauses/fetch-live/{number}` - Fetch from acquisition.gov
- `GET /api/clauses/formatted/{number}` - **FIXED** - Get clause with formatted HTML for display
- `POST /api/clauses/sync-from-acquisition-gov` - Sync clause index
- `POST /api/clauses/sync-full-text` - Fetch full text for clauses missing it

### Export
- `POST /api/export/pdf` - **FIXED** - Export single clause to PDF with proper formatting
- `POST /api/export/batch` - Batch export with automatic full text fetch
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

## Key Technical Details

### DITA/HTML Formatting Pipeline
1. `fetch_clause_html_from_acquisition_gov()` - Fetches HTML from acquisition.gov
2. `format_dita_html_for_agiloft()` - Applies indentation styles:
   - Detects ListL1/L2/L3/L4 classes → maps to levels 1-4
   - Uses `_detect_level_from_prefix()` for (a), (1), (i), (A) patterns
   - Applies `_indent_style_for_level()` with hanging indent CSS
3. `_extract_pdf_paragraphs_from_dita()` - For PDF export:
   - Extracts text with indentation level
   - Detects centered markers from style or content

### Indentation Levels
- Level 1: `padding-left: 1.6em` - (a), (b), (c)...
- Level 2: `padding-left: 3.1em` - (1), (2), (3)...
- Level 3: `padding-left: 4.6em` - (i), (ii), (iii)...
- Level 4: `padding-left: 6.1em` - (A), (B), (C)...

## Change Log
- **2025-03-30 (Session 5 continued)**: 
  - Fixed P0 bug - "Generate Checklist" feature failing with ObjectId serialization error. Root cause: MongoDB `insert_one()` mutates dict adding `_id` (ObjectId). Fix: Added `checklist_dict.pop("_id", None)` before return.
  - Fixed P0 bug - Contract Comparison "Key Differences" rendering error. Root cause: AI returns `key_differences` as objects with keys `{topic, contract_1, contract_2, practical_effect}` instead of strings. Fix: Updated `ContractComparison.jsx` to handle both string and object formats.
  - Fixed P0 bug - DFARS AI Search returning 0 results. Root cause: AI search only loaded first 500 clauses from DB (total: 986), excluding most DFARS clauses. Fix: Added intelligent clause type filtering based on query prefix (252. vs 52.) and increased limit to 1000.
  - Fixed P0 bug - Contract clause detection only finding 1 clause instead of 80+. Root cause: Detection algorithm was incorrectly rejecting clauses in numbered list format like "XX (1) 52.203-6" thinking they were references within another clause. Fix: Updated `_detect_clause_headers()` to properly accept numbered list clauses as actual headers when not inside a checkbox section, and added pattern to detect clauses with comma-separated titles.
- **2025-02-02 (Session 4)**: Fixed P0 regressions - Clause Detail formatting, PDF indentation, "(End of clause)" centering. Added Search page Clear button.
- **2025-01-27 (Session 3)**: Added "Sync All Clauses" button, fixed PDF export to include full text, enhanced Agiloft logging
- **2025-01-27 (Session 2)**: Fixed AI Search, PDF export format, upload missing clauses, dashboard button type
- **2025-01-27 (Session 1)**: Fixed note saving, save search, AI toggle, dashboard button, reserved clauses filter
- **2025-01-22**: P0 Agiloft comparison fix, backend modularization

## Next Tasks (P1)
- [ ] Real-time notifications for clause tracking changes
- [ ] Enhanced UI for Agiloft field mapping

## Backlog (P2)
- [ ] Fix "My Notes" feature bugs (shows incorrect data)
- [ ] Fix landing page search input text overlap with icon
- [ ] Filter subparts from clause comparison
- [ ] Clean up "Reserved" clauses from local MongoDB database
- [ ] Email notifications for clause changes
- [ ] Scheduled sync jobs for Agiloft
- [ ] Playwright UI automation fallback for Agiloft
