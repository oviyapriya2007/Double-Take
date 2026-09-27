# DOUBLE-TAKE
## Technical Documentation Contradiction Detector — Project Specification

*This document is the technical source of truth for Cursor. It documents architecture, decisions, schema, pipeline, and the Day 1–5 build plan. No implementation code below — specification only.*

---

## 1. Project Summary

Double-Take detects potential contradictions between technical documents (installation manuals, service manuals, SOPs, specifications). Given two or more documents, it identifies statement pairs that may conflict and produces a structured verdict with supporting evidence.

**Example:**
- Document A: "Operating temperature: 10°C–40°C"
- Document B: "Operating temperature: 15°C–35°C"

**Output for each detected pair:**
- topic
- statement A / statement B
- verdict: `CONTRADICTION` | `CONSISTENT` | `UNCERTAIN`
- explanation (reasoning)
- confidence
- document name, section, page (for both statements)
- supporting evidence (cited quotes)

### Core academic principle
**Similarity does not mean contradiction.** TF-IDF, embeddings, and entity overlap are used only to identify *candidate* statement pairs — they narrow the search space. The LLM (Claude) performs the actual semantic judgment. This distinction must remain visible throughout the architecture, code structure, and UI.

### Required course concepts (must have real, functional roles — not just appear in the report)
- **NER** — spaCy, extracts technical entities used in candidate scoring and UI display
- **TF-IDF** — scikit-learn, lexical similarity signal + Method 1 baseline
- **Embeddings** — sentence-transformers, semantic similarity signal + Method 2 baseline, stored in pgvector
- **RAG** — LangChain retriever over pgvector, supplies evidence to Claude
- **Prompt Engineering** — structured prompt + structured output for the final verdict

---

## 2. Tech Stack (Locked)

| Layer | Choice |
|---|---|
| Frontend | React, Vite, Tailwind CSS, Recharts (only if needed) |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL, pgvector |
| NLP | spaCy, scikit-learn, sentence-transformers |
| Document processing | PyMuPDF, LangChain `RecursiveCharacterTextSplitter` |
| RAG | LangChain, PostgreSQL + pgvector |
| LLM | Claude API |

**Explicitly excluded:** Pinecone, Chroma, MongoDB, Redis, any separate vector database, microservices, Kubernetes, agents, model fine-tuning, custom model training, unnecessary authentication, unnecessary cloud infrastructure.

**Rule:** do not introduce new technologies or replace locked ones without a genuinely serious technical problem — and if that happens, it must be flagged as a decision point, not silently changed.

---

## 3. Local Environment Decision — Docker → Native PostgreSQL

**Original plan:** Docker Compose running PostgreSQL + pgvector.

**Change:** Docker Desktop could not be used on the development laptop (CHUWI CoreBook X) — the BIOS did not expose a usable virtualization setting, and Docker Desktop reported virtualization support not detected.

**Resolution:** switched the *local installation method only*, not the architecture:

- Windows local PostgreSQL 18.6 installation
- Database `double_take` created
- pgvector extension installed and verified:
  ```sql
  SELECT extname FROM pg_extension WHERE extname = 'vector';
  -- returns: vector
  ```

**This is not an architecture change.** PostgreSQL + pgvector remains the database and vector-search layer. Do not switch to SQLite, Chroma, Pinecone, or any other database because Docker is unavailable.

---

## 4. Embedding Model

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Dimension: **384**
- Therefore: `chunks.embedding = VECTOR(384)`

---

## 5. Database Schema (Exact)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    title TEXT,
    doc_type TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    section TEXT,
    page_number INT,
    text TEXT NOT NULL,
    tfidf_vector JSONB,
    embedding VECTOR(384),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    entity_text TEXT,
    entity_type TEXT,
    start_char INT,
    end_char INT
);

CREATE TABLE candidate_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_a_id UUID REFERENCES chunks(id),
    chunk_b_id UUID REFERENCES chunks(id),
    tfidf_score FLOAT,
    embedding_score FLOAT,
    entity_overlap_score FLOAT,
    combined_score FLOAT,
    method TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE contradiction_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_pair_id UUID REFERENCES candidate_pairs(id),
    verdict TEXT CHECK (verdict IN ('CONTRADICTION','CONSISTENT','UNCERTAIN')),
    topic TEXT,
    reasoning TEXT,
    evidence JSONB,
    confidence FLOAT,
    llm_raw_response JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops);
```

**Notes:**
- `tfidf_vector` (JSONB) may be stored for inspection/debugging. TF-IDF is corpus-dependent — the vectorizer itself is fit **per analysis run**, not persisted as a fixed model.
- `method` on `candidate_pairs` tags which signal(s) surfaced a pair (`tfidf`, `embedding`, `combined`) — needed for the Day 5 method comparison.
- `evidence` and `llm_raw_response` are JSONB to keep Claude's structured output and citations queryable without extra tables.

---

## 6. Core Pipeline

```
Technical PDFs
  → PyMuPDF extraction
  → Cleaning
  → LangChain chunking (RecursiveCharacterTextSplitter)
  → NER (spaCy)
  → TF-IDF (scikit-learn)
  → Sentence embeddings (MiniLM-L6-v2)
  → pgvector storage/retrieval
  → Candidate pair generation
  → RAG retrieval (LangChain + pgvector)
  → Claude comparison
  → Structured verdict
  → Evidence + page references
  → React dashboard
```

Metadata (document, section, page) is attached at chunking time and carried through every downstream stage — it is never re-derived later.

---

## 7. Candidate Pair Generation

```
combined_score = w1 * tfidf_similarity
                + w2 * embedding_similarity
                + w3 * entity_overlap
```

Rules:
- Only cross-document pairs are compared (never within the same document).
- This stage identifies **potentially related** statements only.
- It must **never** directly label a pair as a contradiction — that decision belongs exclusively to the Claude stage.
- Each generated pair is tagged with `method`, so Day 5 evaluation can separate TF-IDF-only, embedding-only, and combined candidate sets.

---

## 8. Claude's Role

Claude receives the two candidate statements plus their retrieved evidence and metadata, and returns:

```json
{
  "verdict": "CONTRADICTION | CONSISTENT | UNCERTAIN",
  "topic": "...",
  "reasoning": "...",
  "confidence": 0.0,
  "evidence": [
    {"document": "...", "section": "...", "page": 0, "quote": "..."}
  ]
}
```

Claude must:
- compare the actual claims, not just their similarity
- explicitly distinguish contradiction from agreement
- avoid inventing facts not present in the supplied evidence
- cite only the supplied evidence
- return `UNCERTAIN` when the evidence is insufficient or the statements aren't clearly about the same topic

Output is validated against a Pydantic schema before being written to the database; one retry is allowed on malformed JSON.

---

## 9. Folder Structure

```
Double-Take/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── services/
│   ├── alembic/
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/
├── data/
│   ├── sample_docs/
│   └── scifact/
└── README.md
```

---

## 10. Evaluation Dataset

- **Quantitative evaluation:** SciFact (claim-verification dataset). Must be described honestly as a **proxy/adapted benchmark**, not a native technical-manual dataset. Mapping: claim → "Document A statement", evidence-abstract sentences → "Document B statements", REFUTES → CONTRADICTION, SUPPORTS → CONSISTENT, NOT ENOUGH INFO → UNCERTAIN.
- **Demo dataset:** 8–12 hand-built technical-document examples, separate from SciFact, including known contradictions, known consistent statements, and at least one ambiguous case.

### Method comparison (Day 5)
| Method | Description |
|---|---|
| 1 | TF-IDF only |
| 2 | Embeddings only |
| 3 | TF-IDF + Embeddings |
| 4 | TF-IDF + Embeddings + RAG + Claude |

### Metrics (use only where genuinely appropriate — do not invent results)
Precision, Recall, F1, Accuracy, Precision@K, Recall@K, MRR, Faithfulness, Context Relevance, Answer Relevance.

---

## 11. Day 1 — Foundation + Thin Vertical Slice

**Goal:** Upload/extract → chunk → database → one hardcoded Claude comparison → API result.

**Tasks:**
1. Repository scaffold
2. Local PostgreSQL + pgvector setup
3. SQLAlchemy models
4. Alembic migration
5. PDF extraction with PyMuPDF
6. Chunking with `RecursiveCharacterTextSplitter`
7. Insert chunks into PostgreSQL
8. Hardcode one known contradictory chunk pair
9. Call Claude
10. Parse structured JSON
11. Store contradiction result
12. `GET /analysis/results` endpoint

**Deliberately NOT implemented on Day 1:** real NER, TF-IDF, embeddings, automatic candidate generation. These come Day 2.

**Database checkpoint:**
```
alembic upgrade head
\dt
```
Verify all five tables exist: `documents`, `chunks`, `entities`, `candidate_pairs`, `contradiction_results`.

**Checkpoint:** a real Claude-generated contradiction verdict with evidence is retrievable via API, from a manually-chosen pair.

---

## 12. Day 2 — Real Retrieval

**Implement:**
1. spaCy NER + EntityRuler (custom patterns: TEMPERATURE, VOLTAGE, MODEL_NUMBER, etc.)
2. TF-IDF cosine similarity
3. `all-MiniLM-L6-v2` embeddings
4. Store 384-dim embeddings in pgvector
5. pgvector similarity search
6. Candidate pair generation
7. Combined scoring
8. Cross-document filtering

**Checkpoint:** the known contradictory pair from Day 1 appears automatically in the generated candidate list, without being hardcoded.

---

## 13. Day 3 — Full RAG + Claude

**Implement:**
1. LangChain retriever over pgvector
2. RAG pipeline
3. Final Claude prompt (structured, evidence-grounded)
4. Pydantic structured output
5. One retry for malformed JSON
6. Pipeline orchestration
7. Evidence/citation handling
8. Full run over demo documents

**Output must include:** CONTRADICTION / CONSISTENT / UNCERTAIN results, reasoning, evidence, document/page references.

**Checkpoint:** triggering one function/endpoint produces real contradiction results with citations across the full demo document set — no manual steps.

---

## 14. Day 4 — React Dashboard

Simple, professional UI. No unnecessary authentication, settings, accounts, notifications, or complex state management.

**Pages/components:**
- Upload
- Results
- Contradiction Detail
- Evaluation (if time permits)

**Must display:** verdict, topic, confidence, both statements, reasoning, evidence, document, page, section.

**Checkpoint:** the full project can be demoed in a browser, start to finish, with no terminal visible.

---

## 15. Day 5 — Evaluation + Polish

1. Run SciFact-adapted evaluation across Methods 1–4; compute metrics.
2. Generate graphs/tables (F1 by method, Precision@K, confusion matrix for Method 4).
3. Bug-fix pass.
4. Write report (architecture, dataset honesty note on SciFact, methods, results, limitations).
5. Rehearse demo flow using the 8–12 hand-built demo documents.

**Checkpoint:** metrics table + charts exist, report is written, demo has been rehearsed end-to-end at least once.

---

## 16. Implementation Principles

- Appropriate scope for a 3rd-year undergraduate project — not production-grade.
- Prioritize a working end-to-end pipeline over sophistication.
- Preserve the locked architecture and tech stack.
- Do not add technologies without a clear, stated reason.
- Do not replace PostgreSQL + pgvector.
- Keep components modular and explainable in a viva.
- Every milestone must be independently testable.
- Implement milestone-by-milestone — never build the whole project in one step.

---

## 17. Current State

**Completed:**
- React + Vite + Tailwind scaffold
- FastAPI scaffold + `/health` endpoint
- PostgreSQL 18.6 installed locally
- `double_take` database created
- pgvector installed and verified

**Current next task:** SQLAlchemy + Alembic database implementation (Day 1, tasks 3–4).