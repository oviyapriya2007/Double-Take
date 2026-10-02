Technical Documentation Contradiction Detector — Complete Roadmap
1. The System, in Plain Terms
Double-Take is a contradiction detector for technical documentation.
It reads technical documents such as specifications, procedures, installation documents, maintenance documents, service documents, configuration guides, datasheets, safety documentation and technical reports. It splits them into chunks while preserving document, page and section metadata, then finds chunks from different documents that are probably discussing the same technical topic.
The retrieval stage uses:
Named Entity Recognition (NER)
TF-IDF similarity
Sentence embeddings
PostgreSQL with pgvector
These techniques reduce the number of possible comparisons to a smaller set of candidate pairs.
Claude then performs the final reasoning step. Given two candidate statements and their evidence, it decides whether their relationship is:
CONTRADICTION
CONSISTENT
UNCERTAIN
and returns a structured result containing:
topic
verdict
reasoning
confidence
quoted evidence
document
page
section
The key reason this cannot simply be implemented as:
PDF → Claude → answer
is that Claude should not be expected to determine which two statements out of hundreds or thousands of chunks need to be compared.
The system therefore has two conceptual halves:
Retrieval half
Find statements that may describe the same technical topic.
NER
+
TF-IDF
+
Embeddings
+
pgvector
↓
Candidate pairs
Reasoning half
Determine whether the related statements actually conflict.
Candidate pair
↓
RAG evidence
↓
Claude
↓
CONTRADICTION / CONSISTENT / UNCERTAIN
The most important design principle is:
Similarity determines what is worth comparing. Similarity does not determine contradiction.
Two statements that agree can have extremely high similarity, and two statements that conflict can also have extremely high similarity. The LLM performs the final contradiction judgment.

2. Problem Statement
Technical information is often distributed across multiple documents written by different teams and at different times.
The same operating limit, measurement, tolerance, configuration value, timing requirement or other technical rule may appear in several documents.
For example, one document may say:
Maximum operating pressure: 3.5 MPa
while another says:
Do not operate the system above 1.8 MPa
Manually finding these conflicts becomes difficult because:
documents may contain hundreds of pages;
similar concepts may use different terminology;
relevant statements may appear in different sections;
relevant statements may exist in different types of documents;
keyword search identifies shared words but not factual conflict;
similarity scores identify related statements but cannot determine whether they agree or disagree;
sending entire document collections directly to an LLM is inefficient and gives the model no reliable mechanism for deciding which statements should be compared.
Double-Take addresses this by narrowing the search to likely related statements first and then using Claude to reason over only those statements.

3. Project Objective
Build a system that, given multiple technical documents:
Extracts document text while preserving source metadata.
Splits text into manageable chunks.
Identifies technical entities inside those chunks.
Measures lexical similarity using TF-IDF.
Measures semantic similarity using embeddings.
Stores and searches embeddings using pgvector.
Generates candidate statement pairs only between different documents.
Retrieves the relevant evidence for each candidate pair.
Uses Claude to classify the relationship as CONTRADICTION, CONSISTENT or UNCERTAIN.
Validates the LLM response through Pydantic.
Verifies that quoted evidence actually comes from the provided statements.
Stores the result and source metadata.
Exposes the results through FastAPI.
Displays the results through a React dashboard.
Evaluates retrieval and classification performance using four experimental methods.
The architecture is intended to be document-type agnostic.
No contradiction-detection stage should depend on whether the input document is specifically a manual, specification, SOP, service document or report.

4. Project Scope
In Scope
Text-based PDF documents
Plain-text files for testing/evaluation
Technical documentation
Cross-document comparison
Chunk-level statements
Page-aware metadata
Section metadata where available
NER
TF-IDF
Sentence embeddings
PostgreSQL
pgvector
Docker Compose for the database
Automatic candidate generation
Single-hop RAG
Claude contradiction reasoning
Three-way verdict:
CONTRADICTION
CONSISTENT
UNCERTAIN
Structured evidence
FastAPI backend
React frontend
Fictional demonstration documents
SciFact proxy evaluation
Out of Scope
OCR for scanned PDFs
Multi-hop RAG
Autonomous agents
Fine-tuned NER models
Contradictions requiring outside knowledge
Advanced unit conversion
Automatic document-version precedence
Authentication
Queue infrastructure
Separate vector databases
Scope Limitation
The architecture is designed to work across different technical-document types, but equal performance across every document type has not been validated.
The controlled technical documents demonstrate the application, while SciFact provides proxy quantitative evaluation.

5. Intended Technical Document Types
Double-Take is intended to process text-based technical documentation including:
Specifications and Requirements
product specifications
engineering specifications
requirements documents
datasheets
Procedures and Operations
SOPs
installation documents
maintenance documents
service documents
troubleshooting guides
user manuals
System and Configuration Documentation
equipment documentation
system documentation
configuration guides
API documentation exported as text or PDF
technical reference documents
Safety and Compliance
safety documents
engineering guidelines
compliance documentation
standards-related documentation
Reports
engineering reports
technical reports
The database contains a free-text doc_type field.
The pipeline does not branch based on that value.

6. Final Architecture
Technical documents
        ↓
Document ingestion
        ↓
PyMuPDF extraction
        ↓
Cleaning
        ↓
Page-aware chunking
        ↓
        ├───────────────┐
        ↓               ↓
      NER            TF-IDF
        │               │
        └──────┬────────┘
               ↓
         MiniLM embeddings
               ↓
        Candidate generation
               ↓
 PostgreSQL 18 + pgvector
     running in Docker
               ↓
      Single-hop RAG retrieval
               ↓
             Claude
               ↓
 CONTRADICTION / CONSISTENT / UNCERTAIN
               ↓
      Structured evidence
               ↓
 PostgreSQL result storage
               ↓
            FastAPI
               ↓
             React
Two rules are central to this architecture.
Candidate generation and contradiction detection remain separate
Candidate generation answers:
Are these statements related enough to compare?
Claude answers:
Do these statements actually contradict each other?
Metadata stays attached throughout the pipeline
Each chunk keeps:
document ID
document name
page
section
That metadata travels through retrieval, Claude analysis and result storage rather than being reconstructed at the end.

7. Project Folder Structure
Double-Take/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   │
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── models.py
│   │   │   └── migrations/
│   │   │
│   │   ├── ingestion/
│   │   │   ├── pdf_extraction.py
│   │   │   ├── chunking.py
│   │   │   └── chunk_storage.py
│   │   │
│   │   ├── nlp/
│   │   │   ├── ner.py
│   │   │   ├── tfidf.py
│   │   │   └── embeddings.py
│   │   │
│   │   ├── retrieval/
│   │   │   ├── candidates.py
│   │   │   └── rag.py
│   │   │
│   │   ├── llm/
│   │   │   ├── prompts.py
│   │   │   ├── claude_analysis.py
│   │   │   └── schema.py
│   │   │
│   │   ├── services/
│   │   │   ├── result_storage.py
│   │   │   └── pipeline.py
│   │   │
│   │   └── api/
│   │       ├── documents.py
│   │       ├── analysis.py
│   │       └── eval.py
│   │
│   ├── evaluation/
│   │   ├── run_scifact_eval.py
│   │   └── metrics.py
│   │
│   ├── scripts/
│   │   ├── PDF/chunk verification scripts
│   │   ├── Claude comparison verification
│   │   ├── result-storage verification
│   │   └── sample PDF generation
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Upload.jsx
│   │   │   ├── Results.jsx
│   │   │   ├── ContradictionDetail.jsx
│   │   │   └── Evaluation.jsx
│   │   │
│   │   ├── components/
│   │   │   ├── DocumentCard.jsx
│   │   │   ├── ContradictionCard.jsx
│   │   │   ├── EvidencePanel.jsx
│   │   │   └── MetricsChart.jsx
│   │   │
│   │   └── api/
│   │       └── client.js
│   │
│   ├── package.json
│   └── vite.config.js
│
├── data/
│   ├── sample_docs/
│   └── scifact/
│
├── docker-compose.yml
└── README.md

8. Docker and Database Setup
Double-Take uses Docker Compose as its PostgreSQL and pgvector database environment.
The FastAPI backend and React frontend run directly on the development machine, while PostgreSQL runs inside a Docker container.
React / Vite
      │
      ↓
   FastAPI
      │
      ↓
 SQLAlchemy
      │
      ↓
DATABASE_URL
      │
      ↓
localhost:5432
      │
      ↓
Docker container
      │
      ↓
PostgreSQL 18 + pgvector
The Docker Compose configuration defines one service:
services:
  db:
    image: pgvector/pgvector:pg18
    container_name: double-take-db
    environment:
      POSTGRES_DB: double_take
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql

volumes:
  pgdata:
    name: double-take-pgdata
The container provides:
PostgreSQL 18
pgvector
database double_take
PostgreSQL user postgres
persistent database storage
access through localhost:5432
The named volume is:
double-take-pgdata
This preserves database data across container restarts.
Application Connection
backend/app/database.py reads:
DATABASE_URL
from:
backend/.env
The current connection configuration matches docker-compose.yml.
Example:
postgresql+psycopg://postgres:postgres@localhost:5432/double_take
Alembic uses the same database connection as the backend, so application code and migrations operate against the same Docker PostgreSQL database.
backend/.env.example also uses the Docker database credentials and should remain synchronized with docker-compose.yml.
Starting the Database
From the project root:
docker compose up -d
Check its status with:
docker compose ps
The Docker container is Double-Take's database.
There is no separate PostgreSQL setup required outside Docker.
What Docker Runs
Docker runs:
PostgreSQL 18
pgvector
persistent PostgreSQL storage
Docker does not currently run:
FastAPI
React
Vite
spaCy
TF-IDF
sentence-transformers
LangChain
Claude integration

9. Database Schema
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
    verdict TEXT CHECK (
        verdict IN (
            'CONTRADICTION',
            'CONSISTENT',
            'UNCERTAIN'
        )
    ),
    topic TEXT,
    reasoning TEXT,
    evidence JSONB,
    confidence FLOAT,
    llm_raw_response JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON chunks
USING ivfflat (embedding vector_cosine_ops);
The SQLAlchemy/Alembic implementation already creates these five planned tables.
The chunks.embedding field uses VECTOR(384) because all-MiniLM-L6-v2 generates 384-dimensional embeddings.
TF-IDF Storage
TF-IDF vectors depend on the corpus.
If additional documents are added, the TF-IDF representation can change.
Therefore the main approach is:
fit TF-IDF for the current analysis run;
calculate similarity in memory;
optionally persist values for debugging/reproducibility.
Persisting every TF-IDF vector is not required for the MVP.

10. Current Implementation Status
Environment
Built:
Python 3.14 backend virtual environment
Docker
Docker Compose
PostgreSQL 18 Docker container
pgvector
database double_take
persistent Docker volume
React/Vite/Tailwind scaffold
The backend and Alembic already connect to the Docker database through the existing .env configuration.
No application-code changes were required when standardising the project on Docker.
Database
Built through SQLAlchemy and Alembic:
documents
chunks
entities
candidate_pairs
contradiction_results
Also built:
VECTOR(384)
ivfflat index
Alembic currently reports:
0001 (head)
and the database schema matches the application models.
pgvector
pgvector is enabled in the Docker PostgreSQL database.
Current extension version:
0.8.6
The chunks.embedding field is vector(384) and cosine-distance queries work.
PDF Extraction
pdf_extraction.py uses PyMuPDF.
It currently extracts:
page text
page number
document title
Chunking
chunking.py uses:
RecursiveCharacterTextSplitter
Current configuration:
chunk size = 800 characters
overlap = 100 characters
Each page is split independently.
A chunk therefore cannot cross from one page into another.
Every chunk has exactly one page number.
Current section value:
unknown
Chunk Storage
chunk_storage.py stores:
one row in documents
associated rows in chunks
Claude Comparison
claude_analysis.py compares one selected pair.
It returns:
verdict
topic
reasoning
confidence
evidence
The response is checked against a Pydantic schema.
Evidence quotes are also validated to confirm that they occur inside the supplied statements.
Result Storage
result_storage.py:
finds or creates a candidate_pairs row;
writes the Claude output to contradiction_results;
stores Claude's raw response.
The result-storage code has been verified against the Docker database.
The current persistent Docker database does not yet contain a stored Claude result or candidate pair.
API
Currently built:
GET /health
GET /analysis/results
GET /health returns:
{"status":"ok"}
GET /analysis/results returns HTTP 200.
The current Docker database returns an empty results list because no persistent Claude result has yet been stored in it.
Verification Scripts
backend/scripts/ contains verification scripts for:
PDF extraction
chunking
chunk storage
Claude comparison
result storage
generation of sample PDFs
PDF extraction and chunking have been verified against the current setup.
Frontend
Built:
React
Vite
Tailwind
project scaffold
Current state:
displays the Double-Take heading
does not yet call the API

11. Current Demonstration Dataset
Four fictional XR-500 documents currently exist in the Docker database:
A — Installation Manual, Rev 2.1
B — Maintenance Manual, Rev 2.1
C — Installation Manual, Rev 3.0
D — Service Manual, Rev 3.0
These document titles remain unchanged because they are the actual names of the fictional documents.
In general descriptions they should be called:
the XR-500 demo documents
Current Chunk Counts
A: 10
B: 10
C: 10
D: 9
Total:
39 chunks
The entities table is currently empty because Day 2 NER has not yet been completed.
Deliberate Differences
Topic
A / B
C
D
Maximum fluid pressure
2.8 MPa
3.5 MPa
1.8 MPa
Minimum / nominal flow
40 / 120 L/min
50 / 130 L/min
50 / 130 L/min
Ambient temperature
-10°C to 50°C
-10°C to 55°C
-10°C to 55°C

These controlled differences are useful for checking whether candidate retrieval finds the correct chunks.
The final demonstration set should contain approximately 8–12 technical documents, with some documents that are not manual-style documents, such as:
specification sheet
SOP
configuration guide
API/technical reference
At least one contradiction should cross document types.

12. Dataset Strategy
Two datasets serve different purposes.
12.1 Demonstration Technical Documents
The fictional technical documents are used to demonstrate the actual Double-Take use case.
The final demo collection should contain:
contradictions
consistent statements
ambiguous statements
different technical-document types
The existing XR-500 collection stays.
12.2 SciFact Evaluation Dataset
SciFact is not a technical-document contradiction dataset.
It is a scientific claim-verification dataset.
Each example contains:
a claim;
scientific evidence;
a label;
evidence sentences.
Its labels include:
SUPPORTS
REFUTES
NOT ENOUGH INFO
For Double-Take it is adapted as:
SciFact claim
    ↓
Document A statement

Evidence sentence
    ↓
Document B statement
Label mapping:
REFUTES
    ↓
CONTRADICTION

SUPPORTS
    ↓
CONSISTENT

NOT ENOUGH INFO
    ↓
UNCERTAIN
SciFact therefore acts as a proxy benchmark.
It allows quantitative evaluation of:
retrieval
classification
It should not be presented as a native benchmark for enterprise or engineering technical documentation.

13. Data Preprocessing
Input
Main input:
text-based PDF
Secondary/testing input:
.txt
Step 1 — PDF Extraction
Use PyMuPDF.
Extract text page by page.
Maintain page number metadata.
Status: built.
Step 2 — Cleaning
Perform only practical cleaning:
normalize whitespace;
remove obvious repeated page headers/footers where possible;
remove repeated page-number text where possible;
handle obvious extraction artefacts.
Do not build a large document-cleaning subsystem.
Status: remaining.
Step 3 — Section Detection
Use a simple heuristic for patterns such as:
Section 3.2
3.2 Operating Conditions
4. Installation
Possible approaches:
regex;
simple heading patterns;
PyMuPDF font-size information.
Fallback:
unknown
The fallback is acceptable.
Section detection is not allowed to block the core project.
Step 4 — Chunking
The implemented settings are:
800 characters
100-character overlap
Pages are chunked separately.
Every chunk contains:
document_id
page_number
section
text
Definition of a Statement
In this project:
A statement means a chunk.
There is currently no separate sentence-level or atomic-claim extraction stage.

14. NER Implementation
Use:
spaCy en_core_web_sm
with:
EntityRuler
The standard spaCy model handles general entities while custom rules identify technical entities.
MUST HAVE
Custom entity types:
TEMPERATURE
VOLTAGE
MODEL_NUMBER
PRESSURE
FLOW_RATE
Pressure and flow-rate rules are important because the current XR-500 contradictions involve these measurements.
Example concepts:
3.5 MPa
1.8 MPa
50 L/min
130 L/min
55°C
XR-500
Store:
chunk ID
entity text
entity type
start character
end character
SHOULD HAVE / OPTIONAL
If time permits:
CURRENT
FREQUENCY
DIMENSION
DURATION
DATA_SIZE
DATE
VERSION
The rule definitions should live in one pattern collection rather than separate code paths for every entity.
Purpose of NER
NER does not determine contradiction.
It provides an additional candidate-generation signal.
For example:
Chunk A → PRESSURE
Chunk B → PRESSURE
makes the pair more likely to concern the same specification.

15. TF-IDF Implementation
Use:
scikit-learn TfidfVectorizer
Fit it over all chunks participating in the current analysis.
Calculate cosine similarity.
Only compare chunks belonging to different documents.
Do not generate same-document candidate pairs.
Method 1
TF-IDF alone forms Method 1.
It provides a lexical baseline.
Example:
Maximum operating pressure is 3.5 MPa
and:
Maximum operating pressure is 1.8 MPa
should receive strong lexical similarity.
TF-IDF may perform less well where terminology differs significantly.
That motivates embeddings.

16. Embedding Generation
Use:
sentence-transformers/all-MiniLM-L6-v2
Properties:
dimension: 384
CPU-friendly
Each chunk is encoded and stored in:
chunks.embedding
Method 2
Embeddings alone form Method 2.
They help surface semantically similar chunks even when wording differs.
For example:
maximum request size
and:
request payload limit
may be semantically close despite lower lexical overlap.

17. pgvector
PostgreSQL running in Docker has the pgvector extension enabled.
The chunks table contains:
embedding VECTOR(384)
An ivfflat index is already present.
For a source chunk, retrieve the top-K nearest chunks from other documents using cosine distance.
Conceptually:
SELECT ...
FROM chunks
WHERE document_id != :source_document
ORDER BY embedding <=> :query_embedding
LIMIT :k;
pgvector serves as the vector retrieval backbone.
There is no need to introduce:
Pinecone
Weaviate
Chroma
another vector database

18. Candidate Pair Generation
Day 1 uses a manually selected pair.
Day 2 replaces this with automatic candidate generation.
Use:
combined_score =
    w1 * tfidf_similarity
  + w2 * embedding_similarity
  + w3 * entity_overlap
Entity Overlap
A simple implementation is Jaccard similarity over entity types.
Example:
Chunk A:
PRESSURE
MODEL_NUMBER

Chunk B:
PRESSURE
MODEL_NUMBER
should receive a strong entity-overlap score.
Rules
Candidate generation must:
compare different documents only;
use embedding similarity to retrieve top-K possible matches;
calculate TF-IDF similarity;
calculate entity overlap;
calculate combined score;
keep the best candidate pairs;
persist the scores;
tag pairs with the relevant experimental method.
A practical starting point is:
top 5 embedding neighbours per source chunk
followed by re-ranking.
Thresholds should be tuned empirically.

19. LangChain RAG Pipeline
RAG should remain simple.
No agents are required.
No multi-hop pipeline is required.
Use:
LangChain's pgvector integration, or
a thin custom LangChain-compatible retriever using the current pgvector query.
For each candidate pair, retrieve the relevant evidence.
Returned metadata should include:
document
page
section
text
That evidence is supplied to Claude.
The retrieval stage is therefore:
Candidate
↓
pgvector
↓
Relevant chunks
↓
Metadata
↓
Claude context

20. Claude API Integration
Claude is responsible for the final contradiction judgment.
Conceptually:
def analyze_contradiction(    statement_a,    statement_b,    evidence_meta_a,    evidence_meta_b):    response = client.messages.create(...)    return parse_structured_output(response)
The model should receive only the evidence relevant to the comparison.
Complete documents do not need to be supplied.
The Day 1 code already performs this for one manually selected pair.
Day 3 extends the same mechanism to automatically generated candidate pairs.

21. Prompt Design
The final prompt should follow this structure:
You are comparing two statements from technical documents
to determine whether they contradict each other.

Statement A
Document: {document_a}
Section: {section_a}
Page: {page_a}

"{statement_a}"

Statement B
Document: {document_b}
Section: {section_b}
Page: {page_b}

"{statement_b}"

Relevant entities:

A: {entities_a}
B: {entities_b}

Task:

1. Determine whether the statements refer to the same
   technical topic or specification.

2. Classify their relationship as exactly one of:

CONTRADICTION
CONSISTENT
UNCERTAIN

CONTRADICTION:
The statements make incompatible factual claims about
the same thing.

CONSISTENT:
The statements agree or are compatible.

UNCERTAIN:
The statements are ambiguous, lack enough information,
or are not actually describing the same technical quantity.

3. Base the judgment ONLY on the supplied statements.

4. Do not invent facts.

5. Cite only evidence contained in the supplied text.

6. Return valid JSON only.
Expected JSON:
{
  "topic": "Maximum operating pressure",
  "verdict": "CONTRADICTION",
  "reasoning": "The two statements specify incompatible maximum values.",
  "confidence": 0.96,
  "evidence": [
    {
      "document": "Document C",
      "section": "unknown",
      "page": 2,
      "quote": "Maximum operating pressure is 3.5 MPa."
    },
    {
      "document": "Document D",
      "section": "unknown",
      "page": 3,
      "quote": "Maximum operating pressure is 1.8 MPa."
    }
  ]
}

22. Structured Output Validation
Use Pydantic.
class Evidence(BaseModel):    document: str    section: str    page: int    quote: strclass ContradictionVerdict(BaseModel):    topic: str    verdict: Literal[        "CONTRADICTION",        "CONSISTENT",        "UNCERTAIN"    ]    reasoning: str    confidence: float = Field(ge=0, le=1)    evidence: list[Evidence]
Pydantic validation already exists in the Day 1 implementation.
The current code also rejects an evidence quote if it is not present in either supplied statement.
Remaining Retry Logic
If Claude returns malformed JSON:
First response
    ↓
Parse + validate
    ↓
Invalid
    ↓
Retry once
    ↓
"Return valid JSON only"
    ↓
Parse again
If the second attempt fails:
log the error;
skip/store failure appropriately.
No complicated output-repair framework is required.

23. Contradiction Detection Logic
The separation between retrieval and reasoning must remain explicit.
Retrieval
Determines:
Which statements appear to discuss the same subject?
Uses:
NER
TF-IDF
embeddings
pgvector
Claude
Determines:
Do those statements contradict, agree or remain uncertain?
Example — Similar and Consistent
Wait at least 60 seconds before restarting.

Allow the system to cool for one minute before restart.
Example — Similar and Contradictory
Maximum pressure is 3.5 MPa.

Maximum pressure is 1.8 MPa.
Both examples may have high semantic similarity.
Therefore:
High similarity is necessary for finding relevant comparisons, but it is not evidence of contradiction by itself.

24. Evidence and Citation Handling
Each stored result should contain evidence containing:
document
page
section
quote
The current implementation already verifies that the Claude evidence quote exists in one of the supplied statements.
The frontend should expose that evidence clearly.
A result-detail page should show:
Statement A
document name
page
section
full chunk text
Statement B
document name
page
section
full chunk text
Analysis
topic
verdict
reasoning
confidence
Evidence
exact quote
source document
page
section
If time permits, display the original chunk and Claude's evidence quote side-by-side.

25. FastAPI Endpoints
Already Built
GET /health
GET /analysis/results
Remaining
POST /documents/upload
GET  /documents

POST /analysis/run

GET /analysis/results
GET /analysis/results/{id}
The existing GET /analysis/results endpoint should be expanded rather than unnecessarily rewritten.
Optional Evaluation Endpoints
POST /evaluation/run
GET  /evaluation/results
These can be skipped if SciFact evaluation remains a standalone script.

26. React Frontend
The frontend currently contains only the React/Vite/Tailwind scaffold.
Upload.jsx
Responsibilities:
select/drag PDFs;
upload documents;
show uploaded documents;
trigger analysis;
show a basic processing state.
A simple message is sufficient:
Processing documents...
No WebSockets are required.
Results.jsx
Display:
verdict
topic
confidence
source documents
Allow filtering by:
CONTRADICTION
CONSISTENT
UNCERTAIN
ContradictionDetail.jsx
Display:
Statement A
Statement B
source document
page
section
reasoning
confidence
evidence
Evaluation.jsx
Optional.
If implemented, use Recharts to show Method 1–4 comparisons.
If time is tight, keep evaluation charts in the report only.

27. Evaluation Methodology
The evaluation has two parts.
Retrieval Evaluation
Question:
Did the method find the correct evidence statement?
Use SciFact's labelled evidence.
Metrics:
Precision@K
Recall@K
MRR
Classification Evaluation
Question:
Once evidence is available, was the relationship classified correctly?
Use the mapped labels:
REFUTES → CONTRADICTION
SUPPORTS → CONSISTENT
NOT ENOUGH INFO → UNCERTAIN
Metrics:
Precision
Recall
F1
Accuracy
Macro F1 should be included because the three classes may be imbalanced.

28. Metrics
Precision@K
relevant items in top K
-----------------------
           K
Recall@K
relevant items in top K
-----------------------
total relevant items
Mean Reciprocal Rank
1 / rank of first relevant item
Average this over all queries.
Classification Precision
TP
-------
TP + FP
Classification Recall
TP
-------
TP + FN
F1
2 × Precision × Recall
----------------------
 Precision + Recall
Accuracy
Correct predictions
-------------------
Total predictions

29. Faithfulness
The final pipeline should also measure whether Claude's evidence is grounded in its provided context.
The Day 1 implementation already performs a strong basic faithfulness check:
An evidence quote is rejected if it cannot be found in the supplied statements.
This can be reported as a simple citation-faithfulness mechanism.
No second LLM call is necessary.

30. Experimental Methods
Method 1 — TF-IDF
Uses lexical similarity.
Strength
simple baseline
interpretable
good where wording is similar
Limitation
misses paraphrasing
does not perform contradiction reasoning

Method 2 — Embeddings
Uses MiniLM semantic similarity.
Strength
better semantic matching
detects related wording with fewer shared terms
Limitation
still measures similarity, not contradiction

Method 3 — TF-IDF + Embeddings
Combines lexical and semantic similarity.
The full candidate score may also use entity overlap.
Strength
stronger candidate retrieval
Limitation
still cannot reliably distinguish agreement from disagreement

Method 4 — Full Pipeline
Uses:
NER
+
TF-IDF
+
Embeddings
+
pgvector
+
RAG
+
Claude
This method performs genuine contradiction classification with evidence.

31. Report Graphs and Tables
MUST HAVE
Classification Comparison
Bar chart showing:
Precision
Recall
F1
for the methods where classification is applicable.
Retrieval Comparison
Precision@K for:
K = 1
K = 3
K = 5
Example Results Table
Include:
Statement A
Statement B
verdict
source
evidence
Dataset Statistics
Include:
number of documents
chunks
entities
candidate pairs
final results
contradictions
SHOULD HAVE
Recall@K
MRR
confusion matrix
These can be dropped if implementation time becomes limited.

32. Five-Day Implementation Roadmap
One-Page Overview
Day
Focus
End-of-day state
Day 1
Foundation + thin vertical slice
PDF → extraction → chunks → manually selected Claude pair → stored/API result
Day 2
Automatic retrieval
NER + TF-IDF + embeddings + pgvector + candidate pairs
Day 3
Full backend pipeline
RAG + automatic Claude analysis + pipeline orchestration
Day 4
Dashboard
Upload → analyse → results → evidence
Day 5
Evaluation + report
SciFact evaluation, charts, report and rehearsed demo


Day 1 — Foundation + Thin Vertical Slice
Status
Completed.
The purpose of Day 1 was to establish one complete path through the architecture before implementing automatic retrieval.
The completed code path is:
PDF
↓
Extraction
↓
Chunking
↓
Docker PostgreSQL
↓
Hand-picked chunk pair
↓
Claude
↓
Pydantic validation
↓
Evidence validation
↓
Result storage
↓
FastAPI
Completed Work
Environment
Completed:
backend virtual environment
Python 3.14
React/Vite/Tailwind scaffold
Docker
Docker Compose
PostgreSQL 18 container
pgvector
persistent database volume
Database Configuration
Completed:
docker-compose.yml
        ↓
pgvector/pgvector:pg18
        ↓
double_take
        ↓
localhost:5432
The backend .env and Docker Compose configuration already match.
Alembic uses the same connection configuration.
Schema
Completed:
documents
chunks
entities
candidate_pairs
contradiction_results
Alembic initial migration
VECTOR(384)
ivfflat index
Extraction
Completed with PyMuPDF.
Chunking
Completed with:
800 characters
100 overlap
one page per chunk
Database Storage
Completed.
Claude Comparison
Completed in code for a selected pair.
Validation
Completed:
Pydantic schema
evidence quote verification
Result Storage
Completed and verified.
API
Completed:
GET /health
GET /analysis/results
Sample Data
Present in the Docker database:
four XR-500 demo documents
39 chunks
Frontend Scaffold
Completed.

Day 1 Changes Still Required
Do not rebuild Day 1.
Only make these adjustments when touching the affected code.
1. Use Document-Neutral Terminology
Replace unnecessary generic references to "manuals" with:
technical documents
Do not rename actual XR-500 document titles.
2. Define Statement as Chunk
Document:
A statement in the current implementation is a chunk.
Do not introduce separate sentence extraction.
3. Keep Current Chunk Settings
Retain:
800 characters
100 overlap
page-by-page splitting
4. Keep Section Fallback
Retain:
unknown
until basic section detection is implemented.
5. Keep Docker PostgreSQL
The database for Double-Take is the PostgreSQL 18 + pgvector container defined in docker-compose.yml.
Keep:
DATABASE_URL
pointed at that database.
6. Keep Database Access Environment-Based
Application code should continue using the configured DATABASE_URL.
Do not add Docker-specific connection logic to FastAPI or Alembic.
7. Recreate a Persistent Day 1 Claude Result if Needed
The Docker database currently contains the XR-500 documents and chunks but no persisted Claude result.
A Day 1 result can be recreated using an XR-500 pair when needed.
8. Add JSON Retry Later
The malformed-JSON retry will be added on Day 3 when full pipeline orchestration is implemented.
Day 1 Checkpoint
The Day 1 code path is complete:
"I can send a selected pair through Claude, validate and store the result, and retrieve results through the API."

Day 2 — Automatic Retrieval
Main Objective
Replace the manually selected Day 1 candidate pair with automatically discovered candidate pairs.
By the end of Day 2:
Known XR-500 pressure, flow and temperature relationships should be surfaced without specifying chunk IDs manually.
Before Starting
Start the Docker database from the project root:
docker compose up -d
Check it with:
docker compose ps
spaCy
Windows Smart App Control is currently preventing spaCy from loading.
Resolve that environment issue before considering the NER task complete.

Task 1 — NER
Implement:
spaCy en_core_web_sm
+
EntityRuler
MUST HAVE:
TEMPERATURE
VOLTAGE
MODEL_NUMBER
PRESSURE
FLOW_RATE
Run NER across all stored chunks.
Insert results into entities.
Verify
Known XR-500 text should detect examples involving:
°C
MPa
L/min
XR-500/model identifiers

Task 2 — TF-IDF
Implement TfidfVectorizer.
Calculate cosine similarity for cross-document chunks.
Print/store the strongest pairs.
Verify
Known pressure, temperature and flow chunks should appear among the strong matches.

Task 3 — Embeddings
Use:
all-MiniLM-L6-v2
Generate vectors for all chunks.
Store in:
chunks.embedding
Verify
Use a pressure-related source chunk.
A semantically related pressure chunk from another document should appear in its nearest neighbours.

Task 4 — Candidate Pair Generation
Combine:
TF-IDF
+
embedding similarity
+
entity overlap
Requirements:
cross-document only;
top-K filtering;
combined score;
persist candidate pairs;
method tag.
Verify
Run against Documents A–D.
Confirm that the system finds candidate pairs for:
maximum pressure
ambient temperature
flow rate
without manually selecting them.
End-of-Day State
Stored chunks
↓
NER
↓
TF-IDF
↓
Embeddings
↓
Docker PostgreSQL + pgvector
↓
Automatic candidate pairs
If Behind
Cut first:
optional NER entity types
entity-overlap sophistication
Do not cut:
embeddings
pgvector
automatic candidate generation
Checkpoint
"I can run candidate generation and receive ranked cross-document statement pairs without choosing them myself."

Day 3 — RAG + Full Claude Pipeline
Main Objective
Replace the single manually selected Claude call with automatic processing of the candidate pairs created on Day 2.

Task 1 — LangChain Retriever
Create a thin retrieval layer over pgvector.
Input:
candidate/source chunk
Output:
matching chunks
text
document
section
page
Do not build multi-hop retrieval.

Task 2 — Finalise Claude Prompt
Include:
Statement A
Statement B
metadata
NER entities
three-way verdict
evidence requirements
do-not-invent-facts instruction

Task 3 — Add JSON Retry
Process:
Claude
↓
Pydantic parse
↓
Invalid?
↓
Retry once
↓
Still invalid?
↓
Log / skip

Task 4 — Pipeline Orchestrator
Create:
services/pipeline.py
Pipeline:
documents
↓
chunks
↓
NER
↓
TF-IDF
↓
embeddings
↓
candidate generation
↓
RAG retrieval
↓
Claude
↓
Pydantic
↓
evidence validation
↓
result storage
It must operate from document IDs rather than hardcoded chunk IDs.

Task 5 — Expand Demo Documents
Keep the existing XR-500 documents.
Expand the final demo collection to roughly 8–12 documents.
Include some different document types.
Do not create unnecessary complexity.
Include at least:
one specification-style document;
one SOP-style document;
one configuration/API-style document;
one contradiction across different document types.

Verify
The pipeline should produce examples of all three outcomes:
CONTRADICTION
CONSISTENT
UNCERTAIN
Every result should include:
topic
verdict
reasoning
confidence
both source statements
evidence
document
page
section
End-of-Day State
"I can trigger the backend pipeline on a document set and automatically receive contradiction results with source evidence."

Day 4 — API + React Dashboard
Main Objective
Make Double-Take demonstrable entirely through the browser.

Task 1 — Complete API
Required:
POST /documents/upload
GET /documents
POST /analysis/run
GET /analysis/results
GET /analysis/results/{id}

Task 2 — Upload Page
Create:
Upload.jsx
Support:
PDF selection
drag/drop
upload
run analysis
simple processing indicator

Task 3 — Results Page
Create:
Results.jsx
Display:
topic
verdict
confidence
source documents
Filters:
contradiction
consistent
uncertain

Task 4 — Detail Page
Create:
ContradictionDetail.jsx
Show:
both statements
source names
page
section
verdict
reasoning
confidence
evidence
Side-by-side evidence is optional.

Task 5 — Full Browser Test
Test:
Upload
↓
Process
↓
Analyse
↓
View results
↓
Open detail
↓
Inspect evidence
Test this with newly uploaded document copies rather than only using existing database rows.
If Behind
Cut:
elaborate progress reporting
side-by-side evidence
Evaluation.jsx
Do not cut:
Upload
Results
Detail
Checkpoint
"A person can use and understand Double-Take without opening the terminal."

Day 5 — Evaluation, Report and Demo Preparation
Main Objective
Do not introduce new core features.
Validate the system and prepare the final presentation.

Task 1 — SciFact Script
Create:
evaluation/run_scifact_eval.py
Use a manageable subset.
Apply the proxy mapping.
Run all four methods.

Task 2 — Calculate Metrics
MUST HAVE:
Precision
Recall
F1
Precision@K
SHOULD HAVE:
Recall@K
MRR
Accuracy
confusion matrix

Task 3 — Generate Charts
Use Matplotlib for the report.
Generate at minimum:
F1 comparison
Precision@K comparison
Optional:
confusion matrix
MRR visualization

Task 4 — Verify Demo Data
Make sure the final demonstration contains clear examples of:
contradiction
consistency
uncertainty
Do not change the algorithm merely to force preferred demo results.
Use controlled examples that genuinely match the intended relationship.

Task 5 — Write the Report
Include:
Problem statement
Objective
Architecture
Docker/database setup
Document scope
Preprocessing
NER
TF-IDF
Embeddings
Candidate generation
pgvector
RAG
Claude
Structured output
Technical demo dataset
SciFact proxy evaluation
Methods 1–4
Metrics
Results
Limitations
Future work

Task 6 — Demo Rehearsal
Use known documents.
Avoid depending on unpredictable live input.
Run the complete flow once on the actual development machine before the presentation.
Checkpoint
"The pipeline, dashboard, evaluation, report and demo have all been completed and tested."

33. Operational Development Setup
The PostgreSQL + pgvector database runs through Docker Compose.
From the project root:
docker compose up -d
Check the database container:
docker compose ps
The expected service is:
double-take-db
The backend connects through:
localhost:5432
using the DATABASE_URL configured in backend/.env.
Useful database verification:
docker exec double-take-db psql -U postgres -d double_take -c "select version();"
Verify pgvector:
docker exec double-take-db psql -U postgres -d double_take -c "select extversion from pg_extension where extname='vector';"
Run Alembic from the backend:
.\.venv\Scripts\alembic.exe current
and:
.\.venv\Scripts\alembic.exe check
The FastAPI application does not require Docker-specific code. It connects using SQLAlchemy and DATABASE_URL.

34. Testing Strategy
Extraction Test
Verify:
correct page count;
extracted text;
page metadata.
Chunking Test
Verify:
chunks do not cross pages;
page number is correct;
chunk length is reasonable;
overlap exists.
NER Test
Example:
The maximum operating pressure is 3.5 MPa.
Expected:
PRESSURE
Example:
Nominal flow is 130 L/min.
Expected:
FLOW_RATE
TF-IDF Test
Compare:
known related statements
obviously unrelated statements
Related statements should rank higher.
Embedding Test
Repeat similar/dissimilar checks semantically.
pgvector Test
Confirm a cosine-distance query over:
chunks.embedding
returns related cross-document chunks.
Candidate Generation Test
Confirm:
cross-document only;
known contradiction pair appears;
unrelated content is not consistently ranked highly.
Claude Test
Check:
CONTRADICTION example;
CONSISTENT example;
UNCERTAIN example.
Evidence Test
Verify every evidence quote exists in its supplied statement.
Integration Test
Run the full pipeline from documents through stored results.
Database Test
Verify:
Docker container is running;
database double_take is available;
pgvector extension is enabled;
Alembic is at head;
schema matches the models.
Browser Test
Run:
upload → analyse → results → detail
at least twice with fresh document uploads.

35. Demo Flow
Start the Docker database.
Start FastAPI.
Start the React frontend.
Open Double-Take.
Upload conflicting technical documents.
Briefly explain extraction and chunking.
Show detected entities.
Show automatically generated candidate pairs.
Open a known contradiction.
Show:
both statements;
document names;
pages;
verdict;
reasoning;
confidence;
evidence.
Show one CONSISTENT result.
Show one UNCERTAIN result.
Show the Method 1–4 evaluation.
Explain why similarity alone cannot detect contradiction.
Finish with limitations.

36. Example Cross-Document Comparisons
Statement A
Statement B
Retrieval clue
Expected result
Engineering specification: "Maximum operating pressure: 3.5 MPa."
Safety document: "Do not operate the system above 1.8 MPa."
PRESSURE + semantic similarity
CONTRADICTION
SOP: "Wait at least 30 seconds before restarting."
Specification: "A minimum cooldown of 60 seconds is required before restart."
Duration/restart semantics
CONTRADICTION
API reference: "Maximum request size is 10 MB."
Configuration guide: "Maximum request payload is 25 MB."
Embeddings
CONTRADICTION
SOP: "Allow the unit to cool for one minute before restart."
Specification: "A minimum cooldown of 60 seconds is required."
Shared topic
CONSISTENT
Specification: "Operating temperature: -10°C to 50°C."
Installation document: "Store the unit between -20°C and 60°C."
TEMPERATURE
UNCERTAIN

The final example demonstrates why a numerical difference does not automatically mean contradiction.
"Operating temperature" and "storage temperature" are different quantities.

37. Final MVP Checklist
Completed
Backend scaffold
Frontend scaffold
Docker
Docker Compose
PostgreSQL 18 Docker database
pgvector
Persistent Docker volume
Backend .env connected to Docker database
Alembic connected to the same Docker database
SQLAlchemy models
Alembic migration
Five core tables
VECTOR(384)
ivfflat index
PDF extraction
Page-aware chunking
800-character chunks
100-character overlap
Chunk database storage
Claude comparison code for selected pair
Pydantic response validation
Evidence quote validation
Result storage code
Raw Claude response storage
GET /health
GET /analysis/results
Verification scripts
Four XR-500 demo documents
39 chunks stored in Docker PostgreSQL
Remaining
Store/recreate a persistent Day 1 Claude result in the Docker database
Basic cleaning
NER
TEMPERATURE rule
VOLTAGE rule
MODEL_NUMBER rule
PRESSURE rule
FLOW_RATE rule
TF-IDF
MiniLM embeddings
pgvector nearest-neighbour retrieval
Automatic candidate generation
Entity-overlap scoring
LangChain RAG
Malformed-JSON retry
Pipeline orchestration
Additional demo technical-document types
Upload API
Document-list API
Analysis-run API
Result-detail API
Upload React page
Results React page
Detail React page
SciFact evaluation
Method 1–4 comparison
Precision
Recall
F1
Precision@K
Report charts
Final report
Demo rehearsal

38. Final Technology Stack
Frontend
React
Vite
Tailwind
Backend
FastAPI
Python 3.14
SQLAlchemy
Alembic
Pydantic
psycopg
Database
PostgreSQL 18
Docker Compose
pgvector/pgvector:pg18
pgvector 0.8.6
VECTOR(384)
ivfflat cosine index
Docker named volume double-take-pgdata
Document Processing
PyMuPDF
LangChain RecursiveCharacterTextSplitter
NLP
spaCy
EntityRuler
scikit-learn TF-IDF
cosine similarity
sentence-transformers
all-MiniLM-L6-v2
Retrieval
PostgreSQL
pgvector
LangChain
LLM
Claude API
Evaluation
SciFact
scikit-learn metrics
Matplotlib
Recharts if time permits
Not Used
queue system
agents
separate vector database
authentication
multi-hop RAG
OCR
custom NER training
Docker for FastAPI
Docker for React

39. Limitations and Future Improvements
SciFact Is a Proxy Dataset
SciFact evaluates scientific claims.
It is not a native benchmark for specification or enterprise technical-document conflicts.
Its results should therefore be interpreted as proxy quantitative evidence rather than exact real-world enterprise performance.
Document-Type Generalisation
The architecture is document-type agnostic.
However, performance has not been independently measured for every technical-document category.
Per-type validation is future work.
Chunk-Level Statements
A statement currently means a chunk.
This can contain more than one sentence or proposition.
Future work could introduce atomic claim extraction.
Section Detection
The current section value is:
unknown
until section detection is implemented.
Even after adding heuristics, complex PDF layouts may cause inaccurate section labels.
No OCR
Scanned PDFs are not supported by the MVP.
No External Knowledge
The system reasons from the supplied documents only.
It cannot determine contradictions requiring knowledge that is absent from both documents.
No Unit Normalisation
Example:
3.5 MPa
and:
35 bar
are approximately equivalent, but the current pipeline does not explicitly normalize units.
Future work could add unit parsing and conversion.
Revision Awareness
A difference between:
Rev 2.1
and:
Rev 3.0
may reflect a legitimate specification update rather than an unresolved contradiction.
The current system identifies the difference but does not determine which revision supersedes the other.
Confidence Is Not Calibrated
Claude's confidence value is model-generated.
It should not be interpreted as a statistically calibrated probability.
Scale
The current top-K candidate retrieval is suitable for the project dataset.
Much larger document collections may need additional blocking or retrieval strategies.

40. Viva Questions to Be Ready For
Why not just send the PDFs to Claude?
Because the system first needs to determine which statements should be compared.
If thousands of chunks exist, the possible pair count becomes very large.
NER, TF-IDF, embeddings and vector search reduce the candidate space before Claude reasons over it.
Why use TF-IDF when embeddings exist?
TF-IDF provides:
a simple baseline;
lexical similarity;
interpretability;
a useful academic comparison.
Embeddings then demonstrate the benefit of semantic retrieval.
Why use NER?
NER highlights technical values and concepts such as:
pressure
temperature
model numbers
voltage
flow rate
It improves retrieval and makes candidate generation more explainable.
Why use pgvector?
It allows embeddings to be stored and searched directly inside the PostgreSQL database already used by Double-Take.
There is no need for a separate vector database.
Why RAG?
RAG gives Claude only the evidence relevant to the current comparison.
It avoids supplying entire document collections to the model.
Why isn't similarity the contradiction detector?
Because similar statements can agree.
For example:
Cooldown is 60 seconds.
Cooldown is one minute.
They are highly similar and consistent.
A similarity model cannot reliably make that logical distinction.
Why is UNCERTAIN needed?
Because two related-looking chunks may actually discuss different quantities.
For example:
Operating temperature
and:
Storage temperature
may contain similar units and words but are not necessarily contradictory.
Why use SciFact?
There is no suitable established public benchmark for labelled contradictions between technical documents.
SciFact contains labelled claims and evidence, allowing a proxy evaluation.
How do you know this works beyond manuals?
The core logic does not branch on document type.
The same pipeline applies to:
specifications
SOPs
configuration guides
reports
maintenance documents
service documents
However, equal performance across all document types has not been proven and remains future work.
How is Docker used?
Docker Compose runs Double-Take's PostgreSQL 18 + pgvector database.
The database service uses:
pgvector/pgvector:pg18
and exposes PostgreSQL through:
localhost:5432
The backend and Alembic both use the same DATABASE_URL to connect to this container.
FastAPI and React run directly on the development machine.

41. What to Cut First if Time Runs Out
Cut in this order:
Evaluation.jsx
confusion matrix
MRR
optional NER types
sophisticated entity-overlap weighting
side-by-side evidence layout
sophisticated section detection
advanced progress indicators
Do not cut:
TF-IDF
embeddings
pgvector
candidate generation
Claude contradiction analysis
evidence
Upload page
Results page
Detail page
core evaluation metrics
demo rehearsal

42. Final Expected System
At the end of Day 5:
Technical PDFs
      ↓
PyMuPDF extraction
      ↓
Basic cleaning
      ↓
Page-aware chunks
      ↓
NER
      ↓
TF-IDF
      ↓
MiniLM embeddings
      ↓
Docker PostgreSQL + pgvector
      ↓
Automatic candidate generation
      ↓
Single-hop RAG
      ↓
Claude
      ↓
Pydantic validation
      ↓
Evidence validation
      ↓
Docker PostgreSQL result storage
      ↓
FastAPI
      ↓
React dashboard
The database environment is:
docker compose up -d
        ↓
double-take-db
        ↓
pgvector/pgvector:pg18
        ↓
PostgreSQL 18 + pgvector
        ↓
double_take
        ↓
localhost:5432
The backend and Alembic use the same database through DATABASE_URL.
The central design of Double-Take remains:
Retrieval finds the statements worth comparing. Claude determines whether those statements actually contradict each other.


