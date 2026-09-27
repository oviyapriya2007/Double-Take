"""Generate the sample PDFs in data/sample_docs/.

sample_manual.pdf    - 4 pages, page 3 intentionally blank.
sample_manual_b.pdf  - 2 pages; its operating temperature contradicts sample_manual.pdf
                       (15-35°C vs 10-40°C) while its supply voltage agrees.
"""

from pathlib import Path

import pymupdf

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "sample_docs"

SAMPLES = {
    "sample_manual.pdf": (
        "XR-200 Installation Manual",
        [
            "XR-200 Installation Manual\n\n"
            "1. Introduction\n"
            "This manual describes the installation of the XR-200 control unit.\n"
            "Read all safety instructions before installing the device.",
            "2. Technical Specifications\n\n"
            "Operating temperature: 10°C to 40°C\n"
            "Supply voltage: 230 V AC, 50 Hz\n"
            "Maximum load: 16 A",
            "",
            "4. Maintenance\n\n"
            "Inspect the cooling fan every 6 months.\n"
            "Replace the air filter every 12 months or after 2000 operating hours.",
        ],
    ),
    "sample_manual_b.pdf": (
        "XR-200 Service Manual",
        [
            "XR-200 Service Manual\n\n"
            "1. Scope\n"
            "This manual is intended for service technicians maintaining the XR-200.",
            "3. Environmental Requirements\n\n"
            "Operating temperature: 15°C to 35°C\n"
            "Supply voltage: 230 V AC, 50 Hz",
        ],
    ),
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, (title, pages) in SAMPLES.items():
        output = OUTPUT_DIR / filename
        with pymupdf.open() as doc:
            for text in pages:
                page = doc.new_page()
                if text:
                    page.insert_text((72, 72), text, fontsize=11)
            doc.set_metadata({"title": title})
            doc.save(output)
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
