"""spaCy NER: en_core_web_sm plus an EntityRuler holding the technical patterns.

NER only records what a chunk talks about (temperatures, pressures, model numbers, ...).
Those entities are later one signal for choosing candidate pairs; NER never decides
whether two statements contradict each other.
"""

from dataclasses import dataclass
from functools import lru_cache

import spacy
from spacy.language import Language

from app.nlp.entity_patterns import CUSTOM_LABELS, build_patterns

SPACY_MODEL = "en_core_web_sm"

# The other statistical labels (CARDINAL, ORG, GPE, PERSON, ...) are mostly noise on
# technical documents, e.g. "DC" tagged as a place and "mA" as a person.
SPACY_LABELS_KEPT = {"DATE", "PERCENT", "QUANTITY"}

STORED_LABELS = set(CUSTOM_LABELS) | SPACY_LABELS_KEPT


@dataclass
class DetectedEntity:
    text: str
    label: str
    start_char: int
    end_char: int


@lru_cache(maxsize=1)
def load_nlp() -> Language:
    """Load en_core_web_sm once and add the EntityRuler in front of its statistical NER."""
    try:
        nlp = spacy.load(SPACY_MODEL)
    except OSError as exc:
        raise RuntimeError(
            f"spaCy model {SPACY_MODEL!r} is not installed. "
            f"Run: python -m spacy download {SPACY_MODEL}"
        ) from exc
    # Placed before "ner" so the statistical model keeps the rule matches and only
    # labels the remaining text.
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    ruler.add_patterns(build_patterns())
    return nlp


def extract_entities(texts: list[str]) -> list[list[DetectedEntity]]:
    """Entities for each text, with character offsets into that exact text."""
    return [
        [
            DetectedEntity(ent.text, ent.label_, ent.start_char, ent.end_char)
            for ent in doc.ents
            if ent.label_ in STORED_LABELS
        ]
        for doc in load_nlp().pipe(texts)
    ]
