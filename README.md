# Double-Take

**Contradiction detection for technical documentation.**

Double-Take reads text-based technical PDFs (specifications, installation and maintenance
manuals, SOPs, configuration guides, datasheets, reports), finds statements in *different*
documents that describe the same technical value or rule, and asks Claude whether each pair
**contradicts**, **agrees** or is **uncertain** — with verbatim evidence quotes from both sources.

> Maximum operating pressure: **3.5 MPa** — *Installation Manual, Rev 3.0, p. 2*
> Do not operate the system above **1.8 MPa** — *Service Manual, Rev 3.0, p. 3*
> → **CONTRADICTION**

The central design rule:

> **Similarity decides what is worth comparing. Similarity never decides contradiction.**
> Retrieval (NER, TF-IDF, embeddings, pgvector) narrows thousands of possible chunk pairs down
> to a few dozen candidates; Claude makes the final judgment on each.

---

## Contents

- [Architecture](#architecture)
- [How the pipeline works](#how-the-pipeline-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [API reference](#api-reference)
- [Frontend](#frontend)
- [Database schema](#database-schema)
- [Configuration](#configuration)
- [Testing and verification](#testing-and-verification)
- [Limitations](#limitations)

---

## Architecture

```mermaid
flowchart LR
    Browser["React + Vite UI<br/>localhost:5173"] -->|"fetch / JSON"| API["FastAPI<br/>localhost:8000"]
    API --> Pipeline["Analysis pipeline"]
    Pipeline --> NLP["spaCy NER · TF-IDF<br/>MiniLM embeddings<br/>technical-claim regex"]
    Pipeline --> Claude["Anthropic Claude API"]
    API --> DB[("PostgreSQL 18 + pgvector<br/>Docker · localhost:5432")]
    Pipeline --> DB
    API --> Files["backend/uploads/*.pdf"]
```

- **Database** — PostgreSQL 18 with the pgvector extension, run by Docker Compose. This is the
  only containerised component.
- **Backend** — FastAPI, SQLAlchemy and Alembic, run directly on the development machine.
- **Frontend** — React 19, React Router and Tailwind CSS 4, served by the Vite dev server.

---

## How the pipeline works

### 1. Ingestion (on upload)

| Step | Implementation | Notes |
|---|---|---|
| Validate | `services/document_ingestion.py` | `.pdf` extension and `%PDF-` signature required |
| Extract | `services/pdf_extraction.py` (PyMuPDF) | Text page by page, 1-based page numbers, PDF metadata title |
| Chunk | `services/chunking.py` (LangChain `RecursiveCharacterTextSplitter`) | 800 characters, 100 overlap, each page split separately so a chunk never crosses pages |
| Store | `services/chunk_storage.py` | One `documents` row, many `chunks` rows; the PDF is saved to `backend/uploads/<document_id>.pdf` |

A multi-file upload is all-or-nothing: if any file fails, the transaction is rolled back and the
saved files are removed. PDFs without extractable text (scanned documents) are rejected.

### 2. Analysis (`services/pipeline.py` → `run_pipeline`)

```
documents → chunks → NER + embeddings → candidate pairs → pgvector retrieval
          → Claude → validation → deduplication → stored results
```

1. **NER** (`nlp/ner.py`, `nlp/entity_patterns.py`) — spaCy `en_core_web_sm` plus an
   `EntityRuler` with rule-based technical entities: `TEMPERATURE`, `VOLTAGE`, `PRESSURE`,
   `FLOW_RATE`, `MODEL_NUMBER`. Of spaCy's statistical labels, only `DATE`, `PERCENT` and
   `QUANTITY` are kept.
2. **Embeddings** (`nlp/embeddings.py`) — `sentence-transformers/all-MiniLM-L6-v2`, 384-dimensional
   unit vectors stored in `chunks.embedding`.

   NER and embeddings are computed only for chunks that do not have them yet.
3. **Candidate generation** (`retrieval/candidates.py`) — every cross-document chunk pair is scored
   with four signals:

   | Signal | Source | Measures |
   |---|---|---|
   | TF-IDF cosine | `nlp/tfidf.py` (refit per run) | Shared wording |
   | Embedding cosine | stored MiniLM vectors | Shared meaning |
   | Entity overlap | Jaccard of entity types | Same kinds of quantities |
   | Technical compatibility | `nlp/technical_claims.py` | Comparable values with the same unit and context |

   ```
   combined = 0.8 × (0.35·tfidf + 0.45·embedding + 0.20·entity) + 0.2 × technical
   ```

   Pairs below `MIN_COMBINED_SCORE` (default `0.15`) are dropped; at most 60 pairs are kept, at
   most 5 per pair of documents, and every document is guaranteed at least one pair.
   `services/candidate_storage.py` persists them idempotently.
4. **Retrieval** (`retrieval/retriever.py`) — `CrossDocumentRetriever`, a LangChain retriever over
   pgvector cosine distance, returns the top 5 chunks from *other* documents with their document,
   page and section metadata.
5. **Claude** (`services/claude_analysis.py`) — both statements, their metadata and entities are
   sent to Claude, which returns **zero or more findings** per pair (one per comparable claim):

   ```json
   {
     "findings": [
       {
         "topic": "maximum operating pressure",
         "verdict": "CONTRADICTION",
         "reasoning": "The statements give incompatible maximum values.",
         "confidence": 0.96,
         "evidence": [
           {"document": "C.pdf", "section": null, "page": 2, "quote": "Maximum operating pressure is 3.5 MPa."},
           {"document": "D.pdf", "section": null, "page": 3, "quote": "Do not operate the system above 1.8 MPa."}
         ]
       }
     ]
   }
   ```

   - The reply is validated with Pydantic; malformed output is retried once.
   - Every evidence quote must occur verbatim (whitespace-normalised) in one of the two statements.
6. **Deduplication** (`services/finding_deduplication.py`) — overlapping chunks can surface the same
   fact through several pairs. Findings with the same documents, verdict and normalised evidence
   quotes are stored only once, across pairs and across runs.
7. **Storage** (`services/result_storage.py`) — one `contradiction_results` row per finding,
   including Claude's raw response. The pipeline commits after every pair, so a rerun skips pairs
   that already have results, and a failing pair is rolled back and counted in `errors` without
   stopping the run.

---

## Tech stack

| Area | Technologies |
|---|---|
| Frontend | React 19, React Router, Tailwind CSS 4, Vite, oxlint |
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Pydantic, psycopg 3 |
| Database | PostgreSQL 18, pgvector (`VECTOR(384)`, ivfflat cosine index), Docker Compose |
| Document processing | PyMuPDF, LangChain text splitters |
| NLP / retrieval | spaCy + EntityRuler, scikit-learn TF-IDF, sentence-transformers (MiniLM), LangChain retriever |
| LLM | Anthropic Claude API |

---

## Project structure

```
Double-Take/
├── docker-compose.yml          # PostgreSQL 18 + pgvector
├── roadmap.md                  # Original design document and plan
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/versions/       # Database migrations
│   ├── app/
│   │   ├── main.py             # FastAPI app and endpoints
│   │   ├── database.py         # Engine, session, DATABASE_URL
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── schemas.py          # API response/request models
│   │   ├── nlp/                # NER, entity patterns, TF-IDF, embeddings, technical claims
│   │   ├── retrieval/          # Candidate generation, pgvector retriever
│   │   └── services/           # Ingestion, chunking, storage, Claude, dedup, pipeline
│   ├── scripts/                # verify_*.py and diagnose_*.py stage checks
│   ├── tests/                  # unittest test suite
│   └── uploads/                # Uploaded PDFs (created at runtime)
├── frontend/
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx             # Layout and routes
│       ├── api.js              # API client
│       ├── pages/              # Upload, Results, ContradictionDetail
│       └── components/         # Verdict, Confidence, SourceChip, Status, ...
└── data/                       # Fictional demo PDFs (e.g. XR-500 documents A–D)
```

---

## Getting started

### Prerequisites

- Docker with Docker Compose
- Python 3.13+
- Node.js 20+ and npm
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Start the database

From the project root:

```bash
docker compose up -d
docker compose ps        # double-take-db should be running
```

### 2. Set up the backend

```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt` also installs the spaCy `en_core_web_sm` model.

Create `backend/.env` from the example and add your API key:

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/double_take
ANTHROPIC_API_KEY=sk-ant-...
```

Apply the migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at <http://localhost:8000>; interactive docs are at <http://localhost:8000/docs>.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

### 4. Try it

1. On **Upload**, drop two or more PDFs — for example `data/sample_docs/A.pdf` to `D.pdf`.
2. Click **Upload**, then **Run analysis**. The request waits until every candidate pair has been
   analysed, which can take a few minutes.
3. Click **View results** and open any finding to see both statements with the evidence highlighted.

The first analysis is slower because the MiniLM model (~90 MB) is downloaded and spaCy is loaded.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check: `{"status": "ok"}` |
| `POST` | `/documents/upload` | Upload one or more PDFs (multipart field `files`, optional `doc_type`) |
| `GET` | `/documents` | List all documents with chunk counts, newest first |
| `POST` | `/analysis/run` | Run the pipeline on a set of documents (synchronous) |
| `GET` | `/analysis/results` | List results, optionally limited to `?document_ids=<id>,<id>,...` |
| `GET` | `/analysis/results/{id}` | One result with both source statements |

### `POST /documents/upload`

```bash
curl -F "files=@data/sample_docs/A.pdf" -F "files=@data/sample_docs/C.pdf" \
     http://localhost:8000/documents/upload
```

Returns `201` with a list of documents:

```json
[
  {
    "id": "6f1c…",
    "filename": "A.pdf",
    "title": "XR-500 Installation Manual",
    "doc_type": null,
    "uploaded_at": "2026-10-03T05:45:00Z",
    "chunk_count": 10,
    "page_count": 4
  }
]
```

Errors: `415` if a file is not a PDF, `422` if it has no extractable text.

### `POST /analysis/run`

```bash
curl -X POST http://localhost:8000/analysis/run \
     -H "Content-Type: application/json" \
     -d '{"document_ids": ["<id-1>", "<id-2>"]}'
```

```json
{
  "document_ids": ["<id-1>", "<id-2>"],
  "documents": 2,
  "chunks": 20,
  "candidates_processed": 10,
  "results_stored": 7,
  "skipped_existing": 0,
  "errors": 0
}
```

Errors: `404` for unknown document IDs, `400` if fewer than two documents have chunks.

### `GET /analysis/results` and `GET /analysis/results/{id}`

Each result looks like:

```json
{
  "id": "…",
  "verdict": "CONTRADICTION",
  "topic": "maximum operating pressure",
  "reasoning": "…",
  "confidence": 0.96,
  "evidence": [{"document": "C.pdf", "section": null, "page": 2, "quote": "…"}],
  "candidate_pair_id": "…",
  "method": "combined",
  "statement_a": {
    "chunk_id": "…", "document_id": "…", "filename": "C.pdf", "title": "…",
    "doc_type": null, "section": "unknown", "page_number": 2, "text": "full chunk text"
  },
  "statement_b": { "…": "…" },
  "created_at": "…"
}
```

With `document_ids`, only results whose two statements both belong to those documents are returned.

---

## Frontend

| Route | Page | What it shows |
|---|---|---|
| `/upload` | `Upload.jsx` | Drag-and-drop upload, uploaded document cards, **Run analysis** with an elapsed-time indicator and a run summary |
| `/results` | `Results.jsx` | Contradictions first as side-by-side cards, then collapsible Uncertain / Consistent groups; search, sort, and a toggle between the current analysis and all stored results |
| `/results/:id` | `ContradictionDetail.jsx` | Verdict, topic, confidence, reasoning, both full statements with evidence highlighted, and the evidence quotes grouped by statement |

The document IDs of the latest analysis are kept in `localStorage`, so **Results** opens on the
current analysis by default.

---

## Database schema

| Table | Key columns |
|---|---|
| `documents` | `id`, `filename`, `title`, `doc_type`, `uploaded_at` |
| `chunks` | `id`, `document_id`, `section`, `page_number`, `text`, `tfidf_vector`, `embedding VECTOR(384)` |
| `entities` | `id`, `chunk_id`, `entity_text`, `entity_type`, `start_char`, `end_char` |
| `candidate_pairs` | `id`, `chunk_a_id`, `chunk_b_id`, `tfidf_score`, `embedding_score`, `entity_overlap_score`, `combined_score`, `method` |
| `contradiction_results` | `id`, `candidate_pair_id`, `verdict`, `topic`, `reasoning`, `evidence JSONB`, `confidence`, `llm_raw_response JSONB` |

Deleting a document cascades to its chunks and their entities. `verdict` is constrained to
`CONTRADICTION`, `CONSISTENT` or `UNCERTAIN`.

Useful checks:

```bash
docker exec double-take-db psql -U postgres -d double_take -c "select extversion from pg_extension where extname='vector';"
cd backend && alembic current
```

---

## Configuration

Backend settings are read from `backend/.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | SQLAlchemy URL of the Docker database |
| `ANTHROPIC_API_KEY` | Yes (for analysis) | — | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-5` | Claude model used for comparisons |
| `MIN_COMBINED_SCORE` | No | `0.15` | Minimum candidate score sent to Claude |

Frontend:

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL |

The backend allows CORS requests from `http://localhost:5173` and `http://127.0.0.1:5173` only.

---

## Testing and verification

The test suite uses `unittest` and runs against the Docker database. No test calls Claude.

```bash
cd backend
python -m unittest discover -s tests
```

`backend/scripts/` contains scripts that check one stage at a time against real data, for example:

```bash
python scripts/verify_pdf_extraction.py
python scripts/verify_ner.py
python scripts/verify_candidates.py
python scripts/verify_pipeline.py --limit 5     # calls Claude at most 5 times
```

Frontend lint and production build:

```bash
cd frontend
npm run lint
npm run build
```

---

## Limitations

- **Text-based PDFs only** — scanned PDFs (OCR) are not supported.
- **A statement is a chunk** — about 800 characters, which may contain several claims; Claude
  returns one finding per comparable claim.
- **Sections are not detected yet** — every chunk's section is `unknown`.
- **No unit normalisation** — `3.5 MPa` and `35 bar` are not recognised as equivalent.
- **No revision awareness** — a difference between Rev 2.1 and Rev 3.0 may be a legitimate update,
  but it is still reported.
- **Confidence is model-generated**, not a calibrated probability.
- **Synchronous analysis** — `POST /analysis/run` blocks until all pairs are processed; there is no
  job queue or live progress.
- **Quadratic candidate scoring** — every cross-document chunk pair is scored, which suits small and
  medium document sets.
- **No authentication** — intended for local use.
