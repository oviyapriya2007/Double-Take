"""Day 2 Task 1: run NER over every stored chunk, store the entities, and check them.

    python scripts/verify_ner.py            # summary per entity type and per document
    python scripts/verify_ner.py --chunks   # also list the entities found in every chunk

The script runs the NER step twice to show that a rerun replaces entities instead of
duplicating them.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Entity  # noqa: E402
from app.services.entity_storage import extract_and_store_entities_for_all_chunks  # noqa: E402
from app.nlp.ner import extract_entities  # noqa: E402

REQUIRED_TYPES = ["TEMPERATURE", "VOLTAGE", "MODEL_NUMBER", "PRESSURE", "FLOW_RATE"]
XR500_DOCUMENTS = ["A.pdf", "B.pdf", "C.pdf", "D.pdf"]
SAMPLES_PER_TYPE = 8

# (sentence, expected entity type, expected entity text); None means no custom entity.
KNOWN_SENTENCES = [
    ("Maximum pressure is 3.5 MPa.", "PRESSURE", "3.5 MPa"),
    ("Operating temperature: 10°C–40°C", "TEMPERATURE", "10°C–40°C"),
    ("Operating Ambient Temperature: -10°C to 55°C", "TEMPERATURE", "-10°C to 55°C"),
    ("Derate by 0.5°C per 100 meters.", "TEMPERATURE", "0.5°C"),
    ("Analog Control Outputs: 4x 0–10V DC", "VOLTAGE", "0–10V DC"),
    ("Input Supply Voltage: 24 V DC", "VOLTAGE", "24 V DC"),
    ("Relay Output Rating: 250V AC, 5A resistive load", "VOLTAGE", "250V AC"),
    ("Ensure voltage is within 21.6V DC to 26.4V \nDC range.", "VOLTAGE", "21.6V DC to 26.4V \nDC"),
    ("Recommended Coolant Loop Flow Rate: 120 L/min", "FLOW_RATE", "120 L/min"),
    ("The XR-500 controller regulates compressor staging.", "MODEL_NUMBER", "XR-500"),
    ("Replace the AB-1200 pump seal.", "MODEL_NUMBER", "AB-1200"),
    ("Use the RS-485 port for Modbus RTU.", None, None),
]


def one_line(text: str) -> str:
    return " ".join(text.split())


def filename_of(chunk: Chunk) -> str:
    return chunk.document.filename if chunk.document else "(no document)"


def check_known_sentences() -> None:
    print("Known sentences:")
    for (sentence, label, text), found in zip(
        KNOWN_SENTENCES, extract_entities([s for s, _, _ in KNOWN_SENTENCES])
    ):
        pairs = [(e.label, e.text) for e in found]
        print(f"  {one_line(sentence)!r}\n    -> {[(lbl, one_line(t)) for lbl, t in pairs]}")
        if label is None:
            assert not any(lbl in REQUIRED_TYPES for lbl, _ in pairs), f"unexpected entity in {sentence!r}"
        else:
            assert (label, text) in pairs, f"expected {label} {text!r} in {sentence!r}"
    print("  OK\n")


def count_entities(db) -> int:
    return db.scalar(select(func.count()).select_from(Entity))


def run_ner_twice() -> None:
    counts = []
    for attempt in (1, 2):
        with SessionLocal() as db:
            rows = extract_and_store_entities_for_all_chunks(db)
            db.commit()
            counts.append(count_entities(db))
        print(f"Run {attempt}: stored {len(rows)} entities; entities table now has {counts[-1]} rows")
    assert counts[0] == counts[1], "rerunning NER changed the number of stored entities"
    print("  OK: the second run replaced the entities instead of duplicating them\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and verify NER over all stored chunks.")
    parser.add_argument("--chunks", action="store_true", help="list the entities of every chunk")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    check_known_sentences()
    run_ner_twice()

    # Fresh session, so everything below is read back from PostgreSQL.
    with SessionLocal() as db:
        chunks = db.scalars(select(Chunk).options(joinedload(Chunk.document))).all()
        entities = db.scalars(select(Entity).order_by(Entity.start_char)).all()

    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    by_chunk = defaultdict(list)
    for entity in entities:
        by_chunk[entity.chunk_id].append(entity)
        chunk = chunk_by_id[entity.chunk_id]
        assert chunk.text[entity.start_char:entity.end_char] == entity.entity_text, (
            f"offsets of entity {entity.id} do not point at {entity.entity_text!r}"
        )

    print(f"Chunks: {len(chunks)}   Entities read back from PostgreSQL: {len(entities)}\n")

    print("Entities per type (with sample matches):")
    samples = defaultdict(Counter)
    for entity in entities:
        samples[entity.entity_type][one_line(entity.entity_text)] += 1
    for label in sorted(samples, key=lambda lbl: (lbl not in REQUIRED_TYPES, lbl)):
        texts = samples[label]
        shown = ", ".join(f"{text} (x{n})" for text, n in texts.most_common(SAMPLES_PER_TYPE))
        print(f"  {label:<13}{sum(texts.values()):>4}   {shown}")

    types_per_document = defaultdict(Counter)
    for chunk in chunks:
        types_per_document[filename_of(chunk)].update(e.entity_type for e in by_chunk[chunk.id])

    print("\nRequired entity types per document:")
    print(f"  {'document':<22}" + "".join(f"{label:>14}" for label in REQUIRED_TYPES))
    for filename in sorted(types_per_document):
        counts = types_per_document[filename]
        print(f"  {filename:<22}" + "".join(f"{counts[label]:>14}" for label in REQUIRED_TYPES))

    if args.chunks:
        print("\nEntities per chunk:")
        for chunk in sorted(chunks, key=lambda c: (filename_of(c), c.page_number or 0, c.created_at)):
            print(f"\n  {filename_of(chunk)} page {chunk.page_number} | {one_line(chunk.text)[:70]}...")
            for entity in by_chunk[chunk.id]:
                print(f"    {entity.entity_type:<13} {one_line(entity.entity_text)!r} [{entity.start_char}:{entity.end_char}]")

    missing = [
        f"{filename}: {label}"
        for filename in XR500_DOCUMENTS
        if filename in types_per_document
        for label in REQUIRED_TYPES
        if types_per_document[filename][label] == 0
    ]
    assert not missing, f"required entity types not found: {missing}"
    checked = [f for f in XR500_DOCUMENTS if f in types_per_document]
    print(f"\nOK: offsets match the chunk text, and {', '.join(checked) or 'no XR-500 document'} "
          f"each contain all required types ({', '.join(REQUIRED_TYPES)})")


if __name__ == "__main__":
    main()
