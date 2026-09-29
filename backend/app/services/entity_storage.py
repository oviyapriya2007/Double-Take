import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Chunk, Entity
from app.nlp.ner import extract_entities


def extract_and_store_entities(db: Session, chunks: list[Chunk]) -> list[Entity]:
    """Run NER over the chunks and replace their stored entities with the new result.

    The chunks' existing entities are deleted first, so running this again leaves the
    same entities instead of duplicates. The caller is responsible for committing.
    """
    if not chunks:
        return []
    detected = extract_entities([chunk.text for chunk in chunks])

    db.execute(delete(Entity).where(Entity.chunk_id.in_([chunk.id for chunk in chunks])))
    rows = [
        Entity(
            chunk_id=chunk.id,
            entity_text=entity.text,
            entity_type=entity.label,
            start_char=entity.start_char,
            end_char=entity.end_char,
        )
        for chunk, entities in zip(chunks, detected)
        for entity in entities
    ]
    db.add_all(rows)
    db.flush()
    return rows


def extract_and_store_entities_for_all_chunks(db: Session) -> list[Entity]:
    """extract_and_store_entities over every chunk in the database."""
    return extract_and_store_entities(db, list(db.scalars(select(Chunk))))


def load_entity_types(db: Session, chunk_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    """The set of stored entity types for each of these chunks (chunks without entities are left out)."""
    types: dict[uuid.UUID, set[str]] = defaultdict(set)
    rows = db.execute(
        select(Entity.chunk_id, Entity.entity_type).where(Entity.chunk_id.in_(chunk_ids)).distinct()
    )
    for chunk_id, entity_type in rows:
        types[chunk_id].add(entity_type)
    return dict(types)
