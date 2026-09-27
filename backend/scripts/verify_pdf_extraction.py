"""Extract a PDF and print each page number with a short text preview."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pdf_extraction import extract_pages  # noqa: E402

DEFAULT_PDF = Path(__file__).resolve().parents[2] / "data" / "sample_docs" / "sample_manual.pdf"


def main() -> None:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    pages = extract_pages(pdf_path)

    print(f"{pdf_path.name}: {len(pages)} non-empty page(s)\n")
    for page in pages:
        preview = page.text.replace("\n", " ")[:70]
        print(f"[page {page.page_number}] {preview}")


if __name__ == "__main__":
    main()
