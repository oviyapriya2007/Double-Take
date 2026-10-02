"""API tests against the Docker PostgreSQL database (start it with: docker compose up -d).

    python -m unittest discover -s tests

No test calls Claude. The upload test deletes the documents and files it creates.
"""

import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

from app.database import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CandidatePair, Chunk, ContradictionResult, Document  # noqa: E402
from app.services.document_ingestion import UPLOAD_DIR  # noqa: E402


def make_pdf(*page_texts: str) -> bytes:
    """A PDF with one page per text; an empty text gives a page without text."""
    with pymupdf.open() as doc:
        for text in page_texts:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        return doc.tobytes()


def document_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Document))


def stored_uploads() -> set[Path]:
    return set(UPLOAD_DIR.glob("*.pdf")) if UPLOAD_DIR.is_dir() else set()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_cors_allows_vite_dev_server(self):
        response = self.client.get("/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")


class DocumentUploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.created_ids: list[uuid.UUID] = []

    def tearDown(self):
        if self.created_ids:
            with SessionLocal() as db:
                db.execute(delete(Document).where(Document.id.in_(self.created_ids)))
                db.commit()
            for document_id in self.created_ids:
                (UPLOAD_DIR / f"{document_id}.pdf").unlink(missing_ok=True)

    def upload(self, *files: tuple[str, bytes], **data):
        return self.client.post(
            "/documents/upload",
            files=[("files", (name, content, "application/pdf")) for name, content in files],
            data=data,
        )

    def test_upload_stores_documents_chunks_and_files(self):
        response = self.upload(
            ("first.pdf", make_pdf("Maximum operating pressure: 3.5 MPa.")),
            ("second.pdf", make_pdf("Do not operate above 1.8 MPa.", "", "Ambient 10-40 C.")),
            doc_type="specification",
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.created_ids = [uuid.UUID(item["id"]) for item in body]

        self.assertEqual([item["filename"] for item in body], ["first.pdf", "second.pdf"])
        self.assertEqual([item["page_count"] for item in body], [1, 2])
        self.assertTrue(all(item["chunk_count"] >= 1 for item in body))
        self.assertTrue(all(item["doc_type"] == "specification" for item in body))
        self.assertTrue(all(item["uploaded_at"] for item in body))

        with SessionLocal() as db:
            for item, document_id in zip(body, self.created_ids):
                chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == document_id)))
                self.assertEqual(len(chunks), item["chunk_count"])
        for document_id in self.created_ids:
            self.assertTrue((UPLOAD_DIR / f"{document_id}.pdf").is_file())

        listed = {item["id"]: item for item in self.client.get("/documents").json()}
        for item in body:
            self.assertIn(item["id"], listed)
            self.assertEqual(listed[item["id"]]["chunk_count"], item["chunk_count"])

    def test_non_pdf_is_rejected(self):
        before = document_count()
        response = self.client.post(
            "/documents/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))]
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(document_count(), before)

    def test_pdf_extension_without_pdf_content_is_rejected(self):
        response = self.upload(("fake.pdf", b"not really a pdf"))
        self.assertEqual(response.status_code, 415)

    def test_unreadable_or_textless_pdf_stores_nothing(self):
        before_count, before_files = document_count(), stored_uploads()
        for content in (b"%PDF-1.7\ngarbage", make_pdf("")):
            with self.subTest(content=content[:20]):
                response = self.upload(("good.pdf", make_pdf("Pressure 3.5 MPa.")), ("bad.pdf", content))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("bad.pdf", response.json()["detail"])
        self.assertEqual(document_count(), before_count)
        self.assertEqual(stored_uploads(), before_files)

    def test_upload_without_files_is_rejected(self):
        self.assertEqual(self.client.post("/documents/upload").status_code, 422)

    def test_openapi_describes_files_as_binary_array(self):
        schema = self.client.get("/openapi.json").json()
        body = schema["paths"]["/documents/upload"]["post"]["requestBody"]["content"]
        ref = body["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[-1]
        form = schema["components"]["schemas"][ref]
        self.assertEqual(form["required"], ["files"])
        self.assertEqual(form["properties"]["files"]["type"], "array")
        self.assertEqual(
            form["properties"]["files"]["items"], {"type": "string", "format": "binary"}
        )
        self.assertIn("doc_type", form["properties"])


class DocumentListTest(unittest.TestCase):
    def test_lists_documents_with_metadata(self):
        response = TestClient(app).get("/documents")
        self.assertEqual(response.status_code, 200)
        for item in response.json():
            self.assertEqual(
                set(item), {"id", "filename", "title", "doc_type", "uploaded_at", "chunk_count"}
            )


class AnalysisRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_needs_at_least_two_document_ids(self):
        response = self.client.post("/analysis/run", json={"document_ids": [str(uuid.uuid4())]})
        self.assertEqual(response.status_code, 422)

    def test_unknown_document_ids_are_404(self):
        ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        response = self.client.post("/analysis/run", json={"document_ids": ids})
        self.assertEqual(response.status_code, 404)
        self.assertIn(ids[0], response.json()["detail"])

    def test_same_document_twice_is_400(self):
        documents = self.client.get("/documents").json()
        if not documents:
            self.skipTest("no stored documents")
        document_id = documents[0]["id"]
        response = self.client.post("/analysis/run", json={"document_ids": [document_id, document_id]})
        self.assertEqual(response.status_code, 400)


class AnalysisResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_list_has_fields_for_results_page(self):
        response = self.client.get("/analysis/results")
        self.assertEqual(response.status_code, 200)
        for item in response.json():
            for field in ("id", "verdict", "topic", "confidence", "reasoning", "created_at"):
                self.assertIn(field, item)
            for side in ("statement_a", "statement_b"):
                self.assertIn("filename", item[side])
                self.assertIn("page_number", item[side])

    def test_detail_matches_list_entry(self):
        results = self.client.get("/analysis/results").json()
        if not results:
            self.skipTest("no stored analysis results")
        response = self.client.get(f"/analysis/results/{results[0]['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), results[0])
        self.assertIsNotNone(response.json()["evidence"])

    def test_unknown_result_is_404(self):
        response = self.client.get(f"/analysis/results/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_malformed_result_id_is_422(self):
        self.assertEqual(self.client.get("/analysis/results/not-a-uuid").status_code, 422)


class AnalysisResultsFilterTest(unittest.TestCase):
    """GET /analysis/results?document_ids=... against rows that are rolled back afterwards."""

    def setUp(self):
        self.db = SessionLocal()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

        # The current analysis compares A and B; old_a is an earlier upload of A.
        self.doc_a, self.doc_b, self.old_a = (
            self.add(Document(filename=name)) for name in ("A.pdf", "B.pdf", "A.pdf")
        )
        self.current = self.add_result(self.doc_a, self.doc_b, "current A/B finding")
        self.current_reversed = self.add_result(self.doc_b, self.doc_a, "current B/A finding")
        self.old = self.add_result(self.old_a, self.doc_b, "old upload finding")

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.db.rollback()
        self.db.close()

    def add(self, row):
        self.db.add(row)
        self.db.flush()
        return row

    def add_result(self, document_a: Document, document_b: Document, topic: str) -> ContradictionResult:
        chunk_a = self.add(Chunk(document_id=document_a.id, text=f"{topic} (A side)"))
        chunk_b = self.add(Chunk(document_id=document_b.id, text=f"{topic} (B side)"))
        pair = self.add(CandidatePair(chunk_a_id=chunk_a.id, chunk_b_id=chunk_b.id, method="test"))
        return self.add(ContradictionResult(
            candidate_pair_id=pair.id, verdict="CONTRADICTION", topic=topic,
            reasoning="test", confidence=0.9, evidence=[],
        ))

    def result_ids(self, query: str = "") -> set[str]:
        response = self.client.get(f"/analysis/results{query}")
        self.assertEqual(response.status_code, 200, response.text)
        return {item["id"] for item in response.json()}

    def test_no_filter_returns_every_stored_result(self):
        ids = self.result_ids()
        self.assertTrue({str(self.current.id), str(self.current_reversed.id), str(self.old.id)} <= ids)
        self.assertEqual(ids, {str(row.id) for row in self.db.scalars(select(ContradictionResult))})

    def test_filter_returns_only_results_between_those_documents(self):
        response = self.client.get(f"/analysis/results?document_ids={self.doc_a.id},{self.doc_b.id}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            {item["id"] for item in body}, {str(self.current.id), str(self.current_reversed.id)}
        )
        wanted = {str(self.doc_a.id), str(self.doc_b.id)}
        for item in body:
            self.assertIn(item["statement_a"]["document_id"], wanted)
            self.assertIn(item["statement_b"]["document_id"], wanted)

    def test_filter_order_and_whitespace_do_not_matter(self):
        expected = {str(self.current.id), str(self.current_reversed.id)}
        self.assertEqual(self.result_ids(f"?document_ids= {self.doc_b.id} , {self.doc_a.id} ,"), expected)

    def test_old_results_are_excluded_but_not_deleted(self):
        ids = self.result_ids(f"?document_ids={self.doc_a.id},{self.doc_b.id}")
        self.assertNotIn(str(self.old.id), ids)
        self.assertIn(str(self.old.id), self.result_ids(f"?document_ids={self.old_a.id},{self.doc_b.id}"))
        self.assertIsNotNone(self.db.get(ContradictionResult, self.old.id))

    def test_one_side_in_the_requested_documents_is_not_enough(self):
        self.assertEqual(self.result_ids(f"?document_ids={self.doc_b.id}"), set())

    def test_unknown_document_ids_return_no_results(self):
        self.assertEqual(self.result_ids(f"?document_ids={uuid.uuid4()},{uuid.uuid4()}"), set())

    def test_invalid_document_ids_are_422(self):
        for value in ("not-a-uuid", f"{self.doc_a.id},nope", "", " , "):
            with self.subTest(value=value):
                response = self.client.get("/analysis/results", params={"document_ids": value})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("document_ids", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
