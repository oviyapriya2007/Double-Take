import uuid
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.pdf_extraction import ExtractedPage

# ~800 characters keeps a spec table row or a short procedure together, and stays
# within all-MiniLM-L6-v2's 256-token input limit. The overlap keeps a sentence
# that straddles a boundary readable in both neighbouring chunks.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

DEFAULT_SECTION = "unknown"


@dataclass
class TextChunk:
    document_id: uuid.UUID
    page_number: int
    section: str
    text: str


def chunk_pages(
    pages: list[ExtractedPage],
    document_id: uuid.UUID,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Split extracted pages into chunks that keep their source page number.

    Each page is split on its own, so a chunk never spans two pages and
    always carries exactly one page_number.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunks: list[TextChunk] = []
    for page in pages:
        for piece in splitter.split_text(page.text):
            text = piece.strip()
            if text:
                chunks.append(
                    TextChunk(
                        document_id=document_id,
                        page_number=page.page_number,
                        section=DEFAULT_SECTION,
                        text=text,
                    )
                )
    return chunks
