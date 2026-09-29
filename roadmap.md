Technical Documentation Contradiction Detector — Complete Roadmap
1. The system, in plain terms
Double-Take is a contradiction detector for technical documentation.
It ingests technical documents such as specifications, procedures, installation documents, maintenance documents, service documents, configuration guides, datasheets, safety documentation and technical reports.
The system extracts the text, divides it into chunks while preserving document and page metadata, and then finds chunks from different documents that are probably discussing the same technical subject.
It does this using:
Named Entity Recognition (NER)
TF-IDF similarity
Sentence embeddings
pgvector similarity search
These techniques narrow the possible comparisons down to a manageable set of candidate pairs.
Claude then performs the final reasoning step. It determines whether the two statements are:
CONTRADICTION
CONSISTENT
UNCERTAIN
and returns its reasoning together with exact evidence from the supplied statements.
The pipeline therefore has two main halves.
Retrieval half
Classical NLP and vector similarity identify statements that may concern the same technical topic.
This includes:
NER
TF-IDF
embeddings
pgvector similarity
candidate-pair generation
Reasoning half
Claude receives a small number of relevant candidate pairs and determines whether they actually conflict.
RAG ensures that the relevant chunks and their metadata are supplied to the model.
A major design principle is:
Similarity finds what should be compared. Similarity does not determine contradiction.
Two statements that agree can be extremely similar. Two statements that conflict can also be extremely similar.
Only the contradiction-analysis stage determines the final relationship.

2. Problem statement
Technical information is often distributed across multiple documents created by different teams and at different times.
The same limit, dimension, operating condition, timing, tolerance, configuration value or technical requirement may appear in several places.
When those statements differ, engineers, technicians, operators or integrators may follow the wrong information.
Manual comparison becomes difficult as the amount of documentation grows because:
the same concept can be described using different terminology;
relevant statements can appear on different pages or sections;
the documents may be of different types;
a simple keyword search finds related text but cannot determine whether it conflicts;
similarity methods cannot distinguish agreement from contradiction;
an LLM cannot efficiently compare every possible statement across a large set of documents.
Double-Take addresses this by first narrowing the search to related technical statements and then asking an LLM to judge those statements using explicitly supplied evidence.

3. Project objective
Build a pipeline that, given a collection of technical documents:
Extracts and chunks the documents while preserving document and page metadata.
Identifies statements that are likely to describe the same technical topic.
Uses NER, TF-IDF and embeddings as complementary retrieval signals.
Creates candidate pairs only between different documents.
Uses pgvector and RAG to retrieve relevant evidence.
Uses Claude to classify each pair as CONTRADICTION, CONSISTENT or UNCERTAIN.
Validates the model response using a structured schema.
Stores the evidence and metadata needed to verify each result.
Provides the results through a FastAPI backend and React dashboard.
Evaluates the retrieval and contradiction-detection approach using the four planned experimental methods.
The system is intended to be document-type agnostic. No contradiction-detection logic depends on whether a document is called a manual, specification, SOP, report or guide.

4. Scope
In scope
Text-based PDF technical documents.
Plain-text documents for testing and evaluation.
Cross-document comparison.
Chunk-level technical statements.
Quantitative and specification-style contradictions.
Three-way classification:
CONTRADICTION
CONSISTENT
UNCERTAIN
NER.
TF-IDF.
Sentence embeddings.
PostgreSQL + pgvector.
Single-hop RAG.
Claude-based contradiction reasoning.
Evidence containing document, section, page and quote.
React dashboard.
Fictional technical documents for demonstration.
SciFact as a proxy evaluation dataset.
Out of scope
OCR for scanned PDFs.
Multi-hop RAG.
AI agents.
Fine-tuned NER models.
Contradictions requiring external knowledge.
Automatic unit conversion or normalization.
Automatic determination of which document revision supersedes another.
Scope limitation
The architecture is designed to be document-type agnostic, but generalisation has not been validated separately for every type of technical document.
The current demonstration data is controlled and fictional, while SciFact is used as a proxy benchmark rather than a native technical-documentation benchmark.

5. Supported technical document types
The design is intended to work with text-based technical documentation such as:
Specifications and requirements
Product specifications
Engineering specifications
Datasheets
Requirements documents
Procedures and operations
Standard Operating Procedures
Installation documents
Maintenance documents
Service documents
Troubleshooting documents
User manuals
Systems and configuration
Equipment documentation
System documentation
Configuration guides
API documentation exported as PDF/text
Technical reference documents
Safety and compliance
Safety documentation
Engineering guidelines
Compliance documents
Standards-related documentation
Reports
Technical reports
Engineering reports
The doc_type field remains a free-text label.
No retrieval or contradiction-analysis stage branches based on doc_type.

6. Overall architecture
The final pipeline is:
Document ingestion
↓
Extraction and cleaning — PyMuPDF
↓
Chunking — LangChain RecursiveCharacterTextSplitter
↓
NER + TF-IDF + Embeddings
↓
Candidate-pair generation
↓
pgvector similarity retrieval
↓
LangChain RAG retrieval
↓
Claude contradiction analysis
↓
Structured result + evidence storage
↓
FastAPI
↓
React dashboard
Two architectural rules are important.
Candidate generation and contradiction detection are separate
Candidate generation only determines:
Are these statements sufficiently related that they are worth comparing?
Claude determines:
Are they actually contradictory, consistent or uncertain?
Metadata travels with the chunk
Document ID, page number and section are attached to chunks during ingestion and carried through the pipeline.
They are not reconstructed at the end.
This allows every final result to point back to its source.

7. Current implementation status
The first end-to-end vertical slice has already been completed.
Built
PostgreSQL and pgvector
PostgreSQL 18 and pgvector run in Docker (pgvector/pgvector:pg18), defined in docker-compose.yml.
Container: double-take-db, published on localhost:5432, data kept in the double-take-pgdata volume.
This container is Double-Take's only PostgreSQL environment.
Database:
double_take
Connection (backend/.env, used by both the backend and Alembic):
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/double_take
The backend runs inside its own Python 3.14 virtual environment.
Database schema
The following tables have been created through SQLAlchemy and Alembic:
documents
chunks
entities
candidate_pairs
contradiction_results
The chunks.embedding field is:
VECTOR(384)
and an ivfflat index exists for vector search.
PDF extraction
pdf_extraction.py uses PyMuPDF to extract:
text
page number
document title
Chunking
chunking.py uses LangChain's RecursiveCharacterTextSplitter.
Current settings:
chunk size: 800 characters
overlap: 100 characters
chunks do not span pages
Each chunk therefore has exactly one page number.
Section metadata currently defaults to:
"unknown"
Chunk storage
chunk_storage.py creates:
one documents record
the corresponding chunks records
Claude comparison
claude_analysis.py compares two selected chunks.
Claude returns:
verdict
topic
reasoning
confidence
evidence
The response is validated through a Pydantic schema.
Evidence quotes are additionally checked to ensure that the quoted evidence actually exists inside the two supplied statements.
Result storage
result_storage.py creates or finds the corresponding candidate_pairs record and stores the Claude result in contradiction_results.
Claude's complete raw response is also stored.
API
FastAPI currently provides:
GET /health
and:
GET /analysis/results
The results endpoint returns each result together with both statements and their:
document
page
section
text
Verification scripts
backend/scripts/ contains scripts for testing:
PDF extraction
chunking
chunk storage
Claude comparison
result storage
sample PDF generation
Frontend
React + Vite + Tailwind have been scaffolded.
The current frontend only displays the Double-Take heading.
It does not yet communicate with the backend.

8. Current demonstration data
Four fictional XR-500 documents are currently stored.
Document A — Installation Manual, Rev 2.1
Document B — Maintenance Manual, Rev 2.1
Document C — Installation Manual, Rev 3.0
Document D — Service Manual, Rev 3.0
These names remain as part of the fictional demonstration dataset.
In general project descriptions they should be referred to as:
the XR-500 demo documents
There are currently 39 chunks:
A: 10
B: 10
C: 10
D: 9
The entities table is currently empty because NER has not yet been implemented.
The documents intentionally contain different values.
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

These documents provide known examples for validating candidate retrieval and contradiction analysis.
Additional demo documents should later introduce other document types such as:
specification
SOP
configuration guide or API reference
At least one demonstration contradiction should occur across two different document types.

9. Operational development note
Before running any database-dependent implementation or testing, start the Docker database from the project root:
docker compose up -d
Check it is running with:
docker compose ps
The container publishes port 5432, so no other process may be using that port.
Day 2 NER work is also currently blocked because Windows Smart App Control is preventing spaCy from loading.
NER implementation cannot be considered complete until spaCy can load successfully.

10. Database schema
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
        verdict IN ('CONTRADICTION','CONSISTENT','UNCERTAIN')
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
doc_type remains free text.
Examples could include:
specification
sop
installation_guide
maintenance_document
service_document
config_guide
technical_report
The pipeline does not branch based on this value.
TF-IDF storage
TF-IDF values are dependent on the corpus being analysed.
Therefore the primary implementation should calculate the TF-IDF representation per analysis run.
Persisting TF-IDF vectors is optional and mainly useful for debugging or reproducibility.

11. Dataset strategy
The project uses two different forms of data.
11.1 Demonstration technical documents
The demonstration dataset consists of fictional technical documentation created specifically for Double-Take.
The existing XR-500 documents remain part of this dataset.
The final demonstration set should contain approximately 8–12 documents, not necessarily 8–12 document pairs.
The final set should include several document types, for example:
installation document
maintenance document
service document
specification sheet
SOP
configuration or API reference
It should contain:
genuine contradiction examples
consistent examples
uncertain examples
at least one contradiction between different document types
The current XR-500 data already contains known contradictions involving:
pressure
flow rate
temperature
These remain useful for retrieval and contradiction tests.

11.2 Benchmark/evaluation data — SciFact
SciFact is a scientific claim-verification dataset.
It contains:
a claim
scientific abstracts
evidence sentences
SUPPORTS / REFUTES / NOT ENOUGH INFO labels
This does not directly match Double-Take's technical-document-vs-technical-document problem.
The project therefore uses SciFact as a proxy benchmark.
The adaptation is:
SciFact claim → Document A statement
evidence sentence → Document B statement
REFUTES → CONTRADICTION
SUPPORTS → CONSISTENT
NOT ENOUGH INFO → UNCERTAIN
This makes SciFact useful for measuring:
retrieval performance
classification performance
It must be described in the report as a proxy rather than a native technical-documentation benchmark.

12. Data preprocessing pipeline
Input
Primary input:
text-based PDF
Plain text can also be used for evaluation and quick testing.
Step 1 — extraction
PyMuPDF extracts text page by page.
Every extracted block retains its page number.
Status: built.
Step 2 — cleaning
Cleaning should:
normalize whitespace
remove obvious repeated headers or footers where possible
remove repeated page-number text
correct obvious PDF extraction artefacts where practical
Do not build a complex document-cleaning system.
Status: not yet implemented as a dedicated stage.
Step 3 — section detection
A simple heuristic can detect headings such as:
1. Introduction
3.2 Operating Conditions
Section 4
If detection fails, use:
unknown
Current implementation already uses this fallback.
Real section detection is a SHOULD HAVE rather than a blocker.
Step 4 — chunking
The current implementation uses:
RecursiveCharacterTextSplitter
Settings:
800 characters
100-character overlap
Each page is chunked separately.
Therefore chunks never cross page boundaries.
Each chunk contains:
document_id
page_number
section
text
Definition of "statement"
For this project, a statement means a chunk.
There is no separate sentence-level statement extraction stage.

13. NER implementation
Use spaCy's:
en_core_web_sm
together with a rule-based EntityRuler.
The statistical model provides general entities, while custom rules identify technical measurements and identifiers that general-purpose NER may miss.
MUST HAVE custom entities
TEMPERATURE
VOLTAGE
MODEL_NUMBER
PRESSURE
FLOW_RATE
PRESSURE and FLOW_RATE are required because the existing XR-500 demonstration contradictions already depend on them.
The rules should be defined in one reusable pattern collection rather than separate custom code for every entity.
SHOULD HAVE / optional entities
If time permits, extend the same pattern collection for:
CURRENT
FREQUENCY
DIMENSION
DURATION
DATA_SIZE
DATE
VERSION
NER output should include:
entity text
entity type
character start
character end
chunk ID
These values are stored in entities.
Role of NER
NER is not responsible for declaring a contradiction.
Its purpose is to improve candidate generation.
For example:
one chunk contains PRESSURE
another chunk contains PRESSURE
That provides evidence that the chunks may be related.
Entity overlap is only one retrieval signal.
TF-IDF and embeddings can still surface relevant pairs when an entity type has not been explicitly modelled.

14. TF-IDF implementation
Fit:
TfidfVectorizer
over the chunks participating in the current analysis.
Calculate cosine similarity between chunks.
Only compare chunks from different documents.
TF-IDF forms:
Method 1
TF-IDF only
It is also one component of the full candidate-pair scoring approach.
Why TF-IDF matters
TF-IDF provides a lexical baseline.
It performs well when two statements use similar terminology.
For example:
Maximum operating pressure is 3.5 MPa.
and:
Maximum operating pressure is 1.8 MPa.
may have very high lexical similarity.
However, TF-IDF may perform poorly when equivalent concepts use different wording.
That motivates the use of embeddings.

15. Embedding generation
Use:
sentence-transformers/all-MiniLM-L6-v2
The model outputs 384-dimensional embeddings, matching:
VECTOR(384)
in PostgreSQL.
Each chunk is encoded once and its vector is stored in:
chunks.embedding
Embeddings form:
Method 2
Embeddings only
They are also used as one signal in candidate-pair generation.
Embeddings help find paraphrased statements where lexical overlap is low.

16. pgvector similarity search
pgvector acts as the vector retrieval layer.
For each source chunk, retrieve the nearest chunks belonging to other documents.
Conceptually:
ORDER BY embedding <=> query_embedding
LIMIT K
with a condition excluding chunks from the same document.
The current ivfflat cosine index is sufficient for the expected dataset size.
There is no need to add another vector database.

17. Candidate statement-pair generation
The current Day 1 implementation selects pairs manually.
Day 2 replaces this with automatic candidate generation.
Use three signals:
combined_score =
    w1 * tfidf_similarity
  + w2 * embedding_similarity
  + w3 * entity_overlap
Entity overlap
A simple approach is Jaccard similarity over detected entity types.
For example:
Chunk A:
PRESSURE
MODEL_NUMBER
Chunk B:
PRESSURE
MODEL_NUMBER
produces strong entity overlap.
Candidate rules
Never compare two chunks from the same document.
Use embedding search to identify top-K cross-document neighbours.
Re-rank using the combined score.
Keep only the best candidate pairs.
Store scores in candidate_pairs.
Store a method tag so evaluation can distinguish retrieval approaches.
Important rule
Candidate generation answers:
Are these chunks probably describing the same subject?
It does not answer:
Do these chunks contradict each other?

18. LangChain RAG pipeline
The RAG design should remain simple.
No agents and no multi-hop reasoning are required.
Use either:
LangChain PGVector integration, or
a thin LangChain-compatible retriever around the existing pgvector query
For a candidate statement from one document, retrieve the most relevant chunks from another document.
The returned evidence includes:
document
page
section
chunk text
This evidence is supplied directly to Claude.
That constitutes the project's single-hop RAG pipeline.

19. Claude API integration
Claude performs the contradiction judgment.
A simplified interface is:
def analyze_contradiction(    statement_a,    statement_b,    evidence_meta_a,    evidence_meta_b):    ...
For each candidate pair, Claude receives only the relevant statements and metadata.
There is no reason to provide complete documents to Claude.
The current implementation already supports a manually selected pair.
Day 3 extends the same functionality across automatically generated candidates.

20. Prompt design
Use a structured prompt similar to:
You are comparing two statements from technical documents
to determine if they contradict each other.

Statement A
Document: {doc_a_title}
Section: {section_a}
Page: {page_a}

{text_a}

Statement B
Document: {doc_b_title}
Section: {section_b}
Page: {page_b}

{text_b}

Relevant entities:

A: {entities_a}
B: {entities_b}

Task:

1. Determine whether the statements refer to the same
   technical topic or specification.

2. If they do, classify the relationship as exactly one of:

   CONTRADICTION
   CONSISTENT
   UNCERTAIN

CONTRADICTION:
The statements make incompatible factual claims about
the same thing.

CONSISTENT:
The statements agree or are compatible.

UNCERTAIN:
There is insufficient information, ambiguous wording,
or the statements are not actually describing the same thing.

3. Base the judgment ONLY on the supplied text.

4. Do not invent facts or evidence.

5. Respond only with valid JSON.
Expected response:
{
  "topic": "string",
  "verdict": "CONTRADICTION",
  "reasoning": "string",
  "confidence": 0.95,
  "evidence": [
    {
      "document": "string",
      "section": "string",
      "page": 1,
      "quote": "string"
    },
    {
      "document": "string",
      "section": "string",
      "page": 2,
      "quote": "string"
    }
  ]
}

21. Structured output validation
Use Pydantic models.
class Evidence(BaseModel):    document: str    section: str    page: int    quote: strclass ContradictionVerdict(BaseModel):    topic: str    verdict: Literal[        "CONTRADICTION",        "CONSISTENT",        "UNCERTAIN"    ]    reasoning: str    confidence: float = Field(ge=0, le=1)    evidence: list[Evidence]
Day 1 already validates the Claude result through Pydantic.
It also checks that evidence quotes actually exist in the supplied statements.
Remaining improvement
If Claude returns malformed JSON:
attempt to parse the response;
if parsing fails, retry once;
explicitly instruct Claude to return only valid JSON;
if the second attempt fails, record/log the failure.
No larger output-repair framework is required.

22. Contradiction detection logic
The logic is deliberately separated into two stages.
Stage 1 — retrieval
NER, TF-IDF, embeddings and pgvector determine which chunks are sufficiently related to compare.
Stage 2 — reasoning
Claude decides whether the relationship is:
contradiction
consistency
uncertainty
This separation is essential.
For example:
Similar and contradictory
Maximum pressure: 3.5 MPa.
Maximum pressure: 1.8 MPa.
Similar and consistent
Cooldown period: 60 seconds.
Wait one minute before restart.
Both sets may have high similarity.
Therefore:
High similarity is necessary for finding relevant comparisons, but similarity alone cannot determine contradiction.

23. Evidence and citation handling
Every stored contradiction result should contain evidence with:
document
section
page
exact quote
Day 1 already validates evidence quotes against the supplied statements.
The frontend should display the evidence next to the original statement so the user can verify the result.
A useful detail page should show:
Statement A
document
page
section
original text
Statement B
document
page
section
original text
Claude judgment
topic
verdict
reasoning
confidence
Evidence
quoted text
source document
source page
source section
Side-by-side evidence comparison is useful but can be removed if time becomes tight.

24. FastAPI endpoints
Already built
GET /health
GET /analysis/results
Remaining core endpoints
POST /documents/upload
GET  /documents

POST /analysis/run

GET /analysis/results
GET /analysis/results/{id}
GET /analysis/results already exists and should be extended rather than replaced if necessary.
Optional evaluation endpoints
POST /evaluation/run
GET  /evaluation/results
These are not required if Day 5 evaluation runs through a standalone Python script.

25. React frontend
The React + Vite + Tailwind scaffold already exists.
The remaining frontend should contain three primary pages.
Upload
Upload.jsx
Responsibilities:
select or drag/drop PDFs
upload documents
start processing
display a simple processing state
No WebSockets are required.
Results
Results.jsx
Display:
topic
verdict
confidence
source documents
basic filters
Possible verdict badges:
CONTRADICTION
CONSISTENT
UNCERTAIN
Contradiction Detail
ContradictionDetail.jsx
Display:
both original statements
document name
section
page
reasoning
confidence
evidence
If time permits, place original chunks and Claude's evidence quotes side-by-side.
Evaluation
Evaluation.jsx
This remains optional.
If implemented, show the Method 1–4 results using Recharts.
If time is tight, evaluation charts can remain in the report only.

26. Contradiction-detection workflow and current status
Stage
What happens
Status
Document ingestion
Technical document enters the system
Core ingestion/storage built
Extraction
PyMuPDF extracts text page by page
Built
Cleaning
Basic extraction cleanup
Remaining
Chunking
800 characters, 100 overlap, one page per chunk
Built
Metadata
Document/page/section kept with chunk
Built; section currently unknown
NER
Detect technical entity types
Not built
TF-IDF
Compute lexical similarity
Not built
Embeddings
Generate MiniLM vectors
Not built
pgvector search
Retrieve semantically related cross-document chunks
Schema/index built; retrieval not built
Candidate generation
Rank related cross-document pairs
Currently manual
RAG
Retrieve evidence for candidates
Not built
Claude analysis
Structured contradiction judgment
Built for a hand-picked pair
Validation
Pydantic + evidence quote validation
Built
Retry
Retry malformed JSON once
Not built
Result storage
Store candidate/result/raw Claude response
Built
Results API
Return results and statement metadata
Built
Browser dashboard
Upload/results/detail UI
Not built
SciFact evaluation
Compare Methods 1–4
Not built


27. Evaluation methodology
There are two separate evaluation questions.
Retrieval evaluation
Question:
Did the system retrieve the correct evidence statement?
Use SciFact evidence sentences as the known relevant evidence.
Metrics:
Precision@K
Recall@K
MRR
Classification evaluation
Question:
Given the evidence, did the system classify the relationship correctly?
Mapping:
REFUTES → CONTRADICTION
SUPPORTS → CONSISTENT
NOT ENOUGH INFO → UNCERTAIN
Metrics:
Precision
Recall
F1
Accuracy
Macro F1 should be reported because the classes may not be balanced.

28. Evaluation metrics
Precision@K
relevant results in top K
-------------------------
             K
Recall@K
relevant results in top K
-------------------------
total relevant results
Mean Reciprocal Rank
For each query:
1 / rank of first relevant result
MRR is the average across queries.
Classification precision
TP / (TP + FP)
Classification recall
TP / (TP + FN)
F1
2 × precision × recall
----------------------
 precision + recall
Accuracy
correct predictions
-------------------
 total predictions

29. Faithfulness checking
The system should also check whether Claude's evidence is grounded in the input.
Day 1 already performs a strict version of this check by rejecting evidence quotes that do not occur in either supplied statement.
This can form the basis for a simple faithfulness measure.
No second LLM is necessary.

30. Experimental methods
Method 1 — TF-IDF only
Uses lexical similarity.
Candidate retrieval is based on TF-IDF.
Strength:
simple baseline
effective where wording is similar
Weakness:
misses paraphrases
cannot reason about contradiction

Method 2 — Embeddings only
Uses MiniLM semantic similarity.
Strength:
detects semantically related statements even when wording changes
Weakness:
semantic similarity still does not mean contradiction

Method 3 — TF-IDF + Embeddings
Combines lexical and semantic similarity.
Entity overlap can also be included in the full candidate-generation score.
Strength:
better candidate retrieval
Weakness:
retrieval still does not determine whether the statements agree or disagree

Method 4 — Full pipeline
Uses:
retrieval
NER
TF-IDF
embeddings
pgvector
RAG
Claude
Claude makes the final classification and provides evidence.
This is the only method that performs genuine contradiction reasoning rather than treating similarity as the answer.

31. Report graphs and tables
The final report should contain only the charts that contribute directly to the evaluation.
MUST HAVE
Method comparison
Bar chart showing:
Precision
Recall
F1
for Methods 1–4 where applicable.
Retrieval comparison
Precision@K for values such as:
K = 1
K = 3
K = 5
Example contradictions
Table showing:
Statement A
Statement B
verdict
evidence
source pages
Dataset statistics
Include:
number of documents
number of chunks
number of entities
number of candidate pairs
number of results
number of contradictions
SHOULD HAVE
MRR
confusion matrix for the final pipeline
These can be removed if time is tight.

32. Revised 5-Day Implementation Roadmap
One-page overview
Day
Focus
End-of-day state
Day 1 — Completed
Foundation + thin vertical slice
PDF → extraction → chunking → hand-picked Claude comparison → result through API
Day 2
Automatic retrieval
NER + TF-IDF + embeddings + pgvector + candidate generation
Day 3
Complete backend pipeline
RAG + automatic Claude analysis + orchestration
Day 4
React dashboard
Upload → run analysis → results → evidence detail
Day 5
Evaluation + report + demo preparation
SciFact metrics, charts, report and rehearsed demo


Day 1 — Foundation + Thin Vertical Slice
Status
Completed.
The intended Day 1 objective has been achieved:
PDF → chunks in PostgreSQL → hand-picked pair → real Claude call → validated result → stored result → FastAPI response.
Therefore Day 1 should not be rebuilt.
What is already complete
PostgreSQL 18 + pgvector running in Docker (docker-compose.yml).
double_take database created.
SQLAlchemy schema implemented.
Alembic initial migration implemented.
Five core tables created.
VECTOR(384) field created.
ivfflat vector index created.
PyMuPDF extraction implemented.
LangChain chunking implemented.
Page metadata preserved.
Chunk storage implemented.
Claude comparison implemented.
Pydantic validation implemented.
Evidence quote validation implemented.
Candidate/result storage implemented.
GET /health implemented.
GET /analysis/results implemented.
Verification scripts implemented.
React/Vite/Tailwind scaffold created.
Four XR-500 demo documents generated and stored.
39 chunks generated.
A manually selected pair can be sent to Claude and the result returned through the API.
Changes to make to the Day 1 implementation
Only make these changes while touching the relevant code later:
1. Keep terminology document-type neutral
Where code comments, examples or labels unnecessarily say "manual", use "technical document" instead.
Do not rename the actual XR-500 document titles.
2. Define statements as chunks
Document that:
In Double-Take, a statement currently means one chunk.
Do not add sentence-level extraction.
3. Keep the existing 800 / 100 chunk configuration
Do not rewrite working chunking simply to match the earlier approximate 200–400-token wording.
The implemented configuration is now the project configuration:
800 characters
100 overlap
chunking separately per page
4. Keep section fallback
section = "unknown"
is acceptable until section detection is implemented.
Do not block later stages on section-heading extraction.
5. Keep Docker PostgreSQL
The docker-compose.yml PostgreSQL + pgvector container is the only development database.
DATABASE_URL must point at this container: postgresql+psycopg://postgres:postgres@localhost:5432/double_take.
6. Add malformed-JSON retry later
The existing Claude validation stays.
The one-retry behavior belongs in Day 3 when the production analysis loop is implemented.
Day 1 checkpoint
Completed:
"I can retrieve a real Claude-generated contradiction result with source evidence through the API, even though the pair was selected manually."

Day 2 — NER, TF-IDF, Embeddings and Automatic Candidate Generation
Main objective
Replace manual selection of candidate pairs with automatic retrieval.
At the end of Day 2:
The system should discover the relevant XR-500 pressure, flow and temperature pairs without their chunk IDs being manually supplied.
Prerequisites
Before development:
Start the Docker database: docker compose up -d
Resolve the current spaCy loading block caused by Windows Smart App Control.
Do not implement an alternative NER architecture unless spaCy genuinely cannot be made usable.

Task 1 — NER
Implement spaCy NER and an EntityRuler.
MUST HAVE entity types
TEMPERATURE
VOLTAGE
MODEL_NUMBER
PRESSURE
FLOW_RATE
Store:
entity text
type
start character
end character
chunk ID
Verification
Run NER across the XR-500 chunks.
Confirm that the known test statements produce entities for:
MPa
L/min
°C
XR-500/model identifiers where present
Query the entities table and manually inspect the output.

Task 2 — TF-IDF
Create the TF-IDF module.
Fit the vectorizer over the chunks in the active document set.
Calculate cosine similarity between chunks from different documents only.
Print or return the top related pairs.
Verification
Known XR-500 pressure, flow and temperature counterparts should appear among the stronger lexical matches.

Task 3 — Embeddings
Use:
all-MiniLM-L6-v2
Generate 384-dimensional embeddings for all chunks.
Store them in:
chunks.embedding
Verification
Select a known XR-500 pressure chunk and perform a pgvector nearest-neighbour search.
A related pressure chunk from another XR-500 document should appear in the top results.

Task 4 — Candidate generation
Implement automatic candidate generation.
Use:
TF-IDF similarity
+
embedding similarity
+
entity-type overlap
Requirements:
cross-document pairs only
top-K candidates
combined score
method tag
scores persisted in candidate_pairs
Start with approximately top 5 embedding matches per source chunk and re-rank them.
Thresholds can be tuned after observing the data.
Verification
Run candidate generation across A, B, C and D.
Confirm that candidate pairs include the known contradictions involving:
maximum pressure
flow rate
ambient temperature
without manually specifying chunk IDs.

End-of-Day 2 state
The system should now perform:
Stored chunks
   ↓
NER
   ↓
TF-IDF
   ↓
Embeddings
   ↓
pgvector similarity
   ↓
Automatic candidate pairs
No manual pair selection should be required.
If behind
Cut first:
extra NER entity types
sophisticated entity-overlap weighting
Do not cut:
embeddings
pgvector
automatic candidate generation

Day 3 — RAG + Full Claude Pipeline
Main objective
Replace the Day 1 single manually selected Claude comparison with an automatic pipeline over Day 2 candidate pairs.
At the end of Day 3:
A single pipeline run should take a document set and produce stored contradiction results automatically.

Task 1 — LangChain retriever
Create the RAG retrieval layer.
Use the existing pgvector embeddings.
Given a candidate/source chunk, retrieve relevant chunks from other documents.
Return:
text
document
page
section
Keep the retriever single-hop.

Task 2 — Final Claude prompt
Use the structured technical-document prompt.
Include:
both statements
document metadata
entities
exact verdict enum
instruction to use only supplied evidence
instruction not to invent facts

Task 3 — malformed JSON retry
Extend the existing Pydantic validation.
Behavior:
Claude response
   ↓
parse + validate
   ↓
valid → continue
   ↓
invalid → retry once
   ↓
still invalid → log/skip
No complex recovery framework is required.

Task 4 — pipeline orchestration
Create the pipeline service.
Conceptually:
documents
↓
chunks
↓
NER / TF-IDF / embeddings
↓
candidate pairs
↓
RAG retrieval
↓
Claude
↓
Pydantic validation
↓
evidence validation
↓
contradiction_results
The orchestrator should work with document IDs rather than hardcoded chunk IDs.

Task 5 — expand demonstration data
The existing XR-500 four-document set stays.
Add enough fictional documents to reach approximately 8–12 demonstration documents.
Do not create unnecessary complexity.
Include at least a few different document types, for example:
specification sheet
SOP
configuration/API reference
Include at least one known cross-type contradiction.
The existing XR-500 pressure, flow and temperature cases remain the main controlled examples.

Verification
The full backend run should produce:
CONTRADICTION examples
CONSISTENT examples
UNCERTAIN examples
Each result should contain:
topic
verdict
reasoning
confidence
Statement A source
Statement B source
page numbers
evidence quotes
End-of-Day 3 state
"I can run one backend pipeline over a document set and get automatically discovered, Claude-classified contradiction results with evidence."

Day 4 — FastAPI + React Dashboard
Main objective
Make the system usable without running individual scripts.

Task 1 — complete FastAPI endpoints
Implement or complete:
POST /documents/upload
GET  /documents

POST /analysis/run

GET  /analysis/results
GET  /analysis/results/{id}
Keep the already working /analysis/results endpoint and extend it as required.

Task 2 — Upload page
Create:
Upload.jsx
Requirements:
upload PDFs
show uploaded document list
allow analysis to be started
basic processing indicator
A simple message such as:
Processing documents...
is enough.
No WebSockets or live job architecture are required.

Task 3 — Results page
Create:
Results.jsx
Display:
topic
verdict
confidence
source documents
Allow simple filtering by verdict.

Task 4 — Detail page
Create:
ContradictionDetail.jsx
Display:
Statement A
Statement B
source document names
pages
sections
verdict
reasoning
confidence
evidence quotes
If time permits, display the Claude evidence beside the original chunk text.

Task 5 — end-to-end browser test
Test:
Upload documents
↓
Run analysis
↓
Wait for processing
↓
View results
↓
Open one result
↓
Inspect evidence
Perform this with newly uploaded copies rather than relying only on existing database records.

End-of-Day 4 state
"The complete project can be demonstrated through the browser without manually running the backend verification scripts."
If behind
Cut:
side-by-side evidence layout
sophisticated progress state
Evaluation frontend page
Do not cut:
Upload
Results
Detail

Day 5 — Evaluation, Charts, Report and Demo Preparation
Main objective
Do not add new pipeline features.
Use Day 5 to validate and present the completed system.

Task 1 — SciFact evaluation script
Create:
evaluation/run_scifact_eval.py
Use a manageable SciFact subset.
Adapt:
claim → Document A statement
evidence sentence → Document B statement
Labels:
REFUTES → CONTRADICTION
SUPPORTS → CONSISTENT
NOT ENOUGH INFO → UNCERTAIN
Evaluate the four methods.

Task 2 — calculate metrics
Retrieval
At minimum:
Precision@K
If time permits:
Recall@K
MRR
Classification
Calculate:
Precision
Recall
F1
Accuracy
Use macro F1 where appropriate.

Task 3 — create report charts
MUST HAVE:
F1 / method comparison
Precision@K comparison
SHOULD HAVE:
confusion matrix
MRR
Generate report charts with Matplotlib.
The frontend Evaluation page is optional.

Task 4 — final demo-data verification
Check that the demonstration documents contain clean examples of:
contradiction
consistency
uncertainty
Do not alter the system to force a desired result.
If an example is ambiguous because it compares different quantities, use a clearer controlled demonstration example.

Task 5 — write the report
Include:
Problem statement
System objective
Architecture
Technical-document scope
Preprocessing
NER
TF-IDF
Embeddings
Candidate generation
pgvector retrieval
RAG
Claude structured reasoning
Demo dataset
SciFact proxy evaluation
Experimental Methods 1–4
Metrics
Results
Limitations
Future improvements

Task 6 — rehearse the demo
Use known demonstration documents.
Do not depend on unpredictable new input during the actual presentation.
Run through the complete flow once on the same development machine before presenting.

End-of-Day 5 state
"The pipeline, UI, quantitative evaluation, report and presentation demo are complete."

33. Testing strategy
Unit-level checks
Extraction
Use a known PDF.
Verify:
text extracted
page count correct
page numbers correct
NER
Use known sentences.
Verify expected entity types.
Example:
Maximum pressure is 3.5 MPa.
should produce a pressure-related entity.
TF-IDF
Test:
obviously similar pair
obviously unrelated pair
The related pair should have higher similarity.
Embeddings
Perform the same test using semantic similarity.

Integration testing
Run the complete pipeline over the fictional demo documents.
Verify:
known contradictions are retrieved
known consistent pairs are not incorrectly marked contradictory
genuinely unrelated or ambiguous cases can produce UNCERTAIN
evidence points to the correct source text

Evaluation testing
The SciFact evaluation acts as the quantitative system test.
A large automated CI system is not required for the five-day implementation.

34. Demo flow
Show or upload two or more conflicting technical documents.
Briefly show extracted chunks and detected entities.
Show automatically generated candidate pairs.
Open one contradiction result.
Show:
Statement A
Statement B
CONTRADICTION verdict
reasoning
confidence
evidence
page numbers
Show one CONSISTENT result.
Show one UNCERTAIN result.
Show the evaluation comparison.
Explain why retrieval similarity alone cannot determine contradiction.
End with limitations.

35. Example contradictions across document types
These examples illustrate the intended behaviour. They are not measured results from the current database.
Statement A
Statement B
Why retrieved
Expected result
Engineering specification: "Maximum operating pressure: 3.5 MPa."
Safety guideline: "Do not operate the system above 1.8 MPa."
Pressure entity + shared topic
CONTRADICTION
SOP: "Wait at least 30 seconds after shutdown before restarting."
Engineering specification: "A minimum cooldown period of 60 seconds is required before restart."
Similar restart/cooldown concept
CONTRADICTION
API reference: "Maximum request size is 10 MB."
Configuration guide: "Maximum request payload: 25 MB."
Semantic similarity between request size and payload
CONTRADICTION
SOP: "Allow the unit to cool for at least one minute before restarting."
Engineering specification: "A minimum cooldown period of 60 seconds is required before restart."
Same technical topic
CONSISTENT
Specification: "Operating temperature: -10°C to 50°C."
Installation document: "Store the unit between -20°C and 60°C."
Temperature entities and lexical similarity
UNCERTAIN

The final example is important because operating temperature and storage temperature are different technical quantities.
The system should not classify every numerical difference as a contradiction.

36. Final MVP checklist
Already completed
PostgreSQL + pgvector environment
Core five-table schema
Alembic migration
PDF extraction
Chunking
Page metadata
Chunk storage
Manual candidate-pair Claude comparison
Claude structured output
Pydantic validation
Evidence quote validation
Result storage
GET /health
GET /analysis/results
Backend verification scripts
React/Vite/Tailwind scaffold
Remaining
Basic cleaning
NER
PRESSURE and FLOW_RATE custom entities
TF-IDF
MiniLM embeddings
pgvector similarity retrieval
Automatic candidate-pair generation
LangChain RAG retrieval
One malformed-JSON retry
Full pipeline orchestration
Add varied technical-document demo examples
Upload API
Analysis-run API
Result-detail API
Upload React page
Results React page
Detail React page
SciFact evaluation
Method 1–4 comparison
Precision / Recall / F1
Precision@K
Report chart
Final report
Demo rehearsal

37. Final tech stack
Frontend
React
Vite
Tailwind
Backend
FastAPI
Python
SQLAlchemy
Alembic
Pydantic
Database
PostgreSQL 18 (Docker, pgvector/pgvector:pg18)
pgvector
VECTOR(384)
ivfflat cosine index
Document processing
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
LangChain single-hop retriever
LLM
Claude API
Evaluation
SciFact proxy dataset
scikit-learn metrics
Matplotlib
Recharts only if time permits
No:
queues
agents
separate vector database
authentication system
multi-hop RAG
OCR
custom fine-tuned NER model

38. Limitations and future improvements
SciFact is only a proxy
SciFact contains scientific claims and scientific evidence.
It does not directly represent conflicts between engineering or enterprise technical documents.
The evaluation therefore measures the approach indirectly.

Generality has not been validated per document type
The architecture contains no document-type-specific contradiction logic.
However, this does not prove equal performance across every type of technical documentation.
Per-document-type evaluation is future work.

Chunk-level statements
The current system treats chunks as statements.
There is no dedicated sentence or atomic-claim extraction stage.
A future version could extract smaller propositions before candidate generation.

Section detection is basic
Section metadata currently defaults to unknown.
Heuristic section detection may not work consistently across complicated PDF layouts.

No OCR
Scanned PDFs are outside the MVP.
They would require OCR before entering the existing pipeline.

No external-knowledge reasoning
The system compares the supplied documents.
It does not determine contradictions that require external scientific or engineering knowledge.

No unit normalisation
For example:
3.5 MPa
and:
35 bar
represent the same approximate value, but the current pipeline does not explicitly normalise units.
Unit-aware comparison is future work.

Revision differences are not automatically resolved
A difference between:
Rev 2.1
Rev 3.0
may be an intended updated specification rather than an unresolved contradiction.
The current system can identify the difference but does not automatically determine whether the newer revision supersedes the older one.
Revision-aware reasoning is future work.

Confidence scores are not calibrated
Claude's confidence is model-reported.
It should not be interpreted as a statistically calibrated probability.
Calibration against evaluation data could be explored later.

Scaling
The current retrieval approach is appropriate for the demonstration dataset and moderate collections.
At much larger scale, additional blocking or retrieval strategies may be required before contradiction analysis.

39. What to explain in the viva
Why not simply send all PDFs to Claude?
Because the expensive and difficult part is determining which statements out of potentially thousands should be compared.
Classical NLP and retrieval reduce the search space first.

Why isn't high similarity enough?
Because related statements can either agree or conflict.
Example:
Maximum pressure is 3.5 MPa.
Maximum pressure is 3.5 MPa.
and:
Maximum pressure is 3.5 MPa.
Maximum pressure is 1.8 MPa.
Both pairs are highly similar.
Only reasoning over the values determines their relationship.

Why use TF-IDF if embeddings are better?
TF-IDF provides:
a simple lexical baseline
interpretability
a useful comparison method
Embeddings provide semantic retrieval where wording changes.
Comparing both demonstrates why semantic retrieval improves candidate generation.

Why use NER?
NER identifies important technical entities and provides another relevance signal.
It can increase the ranking of pairs that discuss the same kind of specification.
It also makes retrieval more explainable.

Why use pgvector?
Embeddings are already stored in PostgreSQL.
pgvector allows vector similarity retrieval without introducing a separate vector database.

Why use RAG?
RAG ensures Claude receives the specific evidence required for a candidate comparison rather than being asked to reason over an entire document collection.

Why have UNCERTAIN?
Some statements may look similar while referring to different quantities.
Example:
operating temperature
storage temperature
Forcing those into CONTRADICTION or CONSISTENT would create false conclusions.
UNCERTAIN allows the system to represent insufficient or ambiguous evidence.

Why use SciFact?
There is no suitable established benchmark containing labelled contradictions between pairs of technical documentation.
SciFact provides labelled claims and evidence and can therefore be adapted as a proxy benchmark.
The limitation is stated explicitly rather than claiming it is a technical-document dataset.

How do you know the system generalises beyond the XR-500 documents?
The pipeline contains no document-type-specific contradiction logic.
The same extraction, chunking, retrieval and reasoning stages can be used for specifications, SOPs, guides, reports and similar documents.
However, this is a design property, not proof of equal performance across all document types.
The controlled demo documents demonstrate the architecture, while SciFact provides proxy quantitative evaluation.
Per-document-type validation remains future work.

40. What to cut first if time runs out
Cut in this order:
Evaluation frontend page.
MRR.
Confusion matrix.
Additional optional NER entity types.
Entity-overlap weighting if necessary.
Side-by-side evidence UI.
Sophisticated section-heading detection.
Detailed processing-progress UI.
Do not cut:
embeddings
pgvector retrieval
automatic candidate generation
Claude contradiction analysis
evidence citations
the three core React pages
core evaluation metrics
demo rehearsal

41. Final expected system
By the end of Day 5, Double-Take should support the following flow:
Technical PDFs
        ↓
PyMuPDF extraction
        ↓
Page-aware chunking
        ↓
NER
        ↓
TF-IDF
        ↓
MiniLM embeddings
        ↓
pgvector similarity
        ↓
Automatic candidate pairs
        ↓
Single-hop RAG
        ↓
Claude
        ↓
CONTRADICTION / CONSISTENT / UNCERTAIN
        ↓
Validated evidence
        ↓
PostgreSQL
        ↓
FastAPI
        ↓
React dashboard
The final system does not claim that similarity itself detects contradictions.
Its central design is:
Retrieval finds the statements worth comparing. Claude determines whether those statements actually contradict each other.
The XR-500 documents remain the controlled fictional demonstration dataset, while SciFact is used separately as the proxy quantitative benchmark. The technical-document architecture, four-method comparison, database design and core five-day scope remain intact; the main changes are broader document-type framing, updated NER entities, clearer dataset separation, explicit chunk-level “statement” definition and limitations around generalisation, units and revisions. Pasted text

