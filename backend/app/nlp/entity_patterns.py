"""Rule-based patterns for technical entities, loaded into spaCy's EntityRuler by ner.py.

All custom entity types live in the two rule lists below:

- MEASUREMENT_RULES: a label plus the way its unit is written ("24V DC", "2.8 MPa", ...).
- PATTERN_RULES: a label plus a ready-made spaCy token pattern (model numbers, ...).

build_patterns() turns both lists into EntityRuler patterns, so a further type such as
CURRENT, FREQUENCY, DIMENSION, DURATION, DATA_SIZE, DATE or VERSION is added by appending
a rule here rather than by writing new matching code.
"""

from dataclasses import dataclass

NUMBER = r"[-+−]?\d+(?:\.\d+)?"

# A number, or a range the tokenizer keeps as one token: "0–10" in "0–10 V".
NUMBER_OR_RANGE = rf"{NUMBER}(?:[–~-]{NUMBER})?"

# Words joining the two ends of a range: "-10°C to 55°C", "10-40°C".
RANGE_WORDS = ["to", "–", "-", "~"]

# PDF text can wrap a value over two lines ("26.4V \nDC"); spaCy keeps the line break as
# its own whitespace token, so one is allowed between any two tokens of a match.
LINE_BREAK = {"IS_SPACE": True, "OP": "?"}


@dataclass(frozen=True)
class MeasurementRule:
    label: str
    unit: str
    """Regex for the unit token, written apart ("24 V") or glued to the number ("24V")."""
    tail: tuple[dict, ...] = ()
    """Tokens after the unit, e.g. "/" "min" in "L/min"."""
    tail_optional: bool = False
    """True when the tail may be left out, e.g. DC in "24V DC"."""


@dataclass(frozen=True)
class PatternRule:
    label: str
    pattern: tuple[dict, ...]


MEASUREMENT_RULES = [
    # spaCy always splits the degree sign off: "10°C" -> 10 | ° | C.
    MeasurementRule("TEMPERATURE", r"°", tail=({"TEXT": {"IN": ["C", "F"]}},)),
    MeasurementRule(
        "VOLTAGE",
        r"[kmµ]?V|VDC|VAC|Vdc|Vac",
        tail=({"TEXT": {"IN": ["DC", "AC"]}},),
        tail_optional=True,
    ),
    MeasurementRule("PRESSURE", r"[kM]?Pa|m?bar|psi[ag]?|PSI"),
    MeasurementRule(
        "FLOW_RATE",
        r"[Ll]|m³|m3|gal",
        tail=({"ORTH": "/"}, {"LOWER": {"IN": ["min", "h", "hr", "s"]}}),
    ),
    MeasurementRule("FLOW_RATE", r"[Ll]/min|m³/h|m3/h|[Ll][Pp][Mm]|GPM|gpm"),
]

# Interface standards that look like model numbers but are not.
NOT_MODEL_NUMBERS = ["RS-232", "RS-422", "RS-485"]

PATTERN_RULES = [
    # 2-3 capital letters, optional hyphen, 3-5 digits, optional 1-2 letter suffix:
    # XR-500, XR500, PT1000, CR2032, AB-1200C. Zero-padded numbers ("MNT-001" inside
    # document IDs) are sequence numbers, not models, so the digits cannot start with 0.
    PatternRule(
        "MODEL_NUMBER",
        (
            {
                "TEXT": {
                    "REGEX": r"^[A-Z]{2,3}-?[1-9]\d{2,4}[A-Z]{0,2}$",
                    "NOT_IN": NOT_MODEL_NUMBERS,
                }
            },
        ),
    ),
    # A compact range "10°C–40°C" is tokenized as 10 | ° | C–40 | ° | C.
    PatternRule(
        "TEMPERATURE",
        (
            {"TEXT": {"REGEX": rf"^{NUMBER}$"}},
            {"ORTH": "°"},
            {"TEXT": {"REGEX": rf"^[CF][–~-]{NUMBER}$"}},
            {"ORTH": "°"},
            {"TEXT": {"IN": ["C", "F"]}},
        ),
    ),
]

CUSTOM_LABELS = sorted({rule.label for rule in [*MEASUREMENT_RULES, *PATTERN_RULES]})


def _glued_value(rule: MeasurementRule) -> list[dict]:
    """One token holding number and unit: "24V", "3.5MPa", and ranges like "0–10V"."""
    unit = f"(?:{rule.unit})"
    return [{"TEXT": {"REGEX": rf"^{NUMBER}(?:{unit}?[–~-]{NUMBER})?{unit}$"}}]


def _separate_value(rule: MeasurementRule) -> list[dict]:
    """Number (or one-token range) and unit as separate tokens: "2.8 MPa", "0–10 V"."""
    return [
        {"TEXT": {"REGEX": rf"^{NUMBER_OR_RANGE}$"}},
        {"TEXT": {"REGEX": rf"^(?:{rule.unit})$"}},
    ]


def _value_patterns(rule: MeasurementRule) -> list[list[dict]]:
    """Every token sequence that writes a single value of this measurement."""
    tails = [list(rule.tail)]
    if rule.tail_optional:
        tails.append([])
    return [start + tail for start in (_glued_value(rule), _separate_value(rule)) for tail in tails]


def _allow_line_breaks(tokens: list[dict]) -> list[dict]:
    pattern = []
    for index, token in enumerate(tokens):
        if index:
            pattern.append(LINE_BREAK)
        pattern.append(token)
    return pattern


def _measurement_patterns(rule: MeasurementRule) -> list[list[dict]]:
    """Single values, plus ranges whose first end may be a bare number ("10 to 40°C")."""
    values = _value_patterns(rule)
    bare_number = [{"TEXT": {"REGEX": rf"^{NUMBER}$"}}]
    range_word = [{"LOWER": {"IN": RANGE_WORDS}}]
    ranges = [low + range_word + high for low in [*values, bare_number] for high in values]
    return values + ranges


def build_patterns() -> list[dict]:
    """All custom patterns in EntityRuler format: {"label": ..., "pattern": [...]}."""
    patterns = [
        {"label": rule.label, "pattern": _allow_line_breaks(tokens)}
        for rule in MEASUREMENT_RULES
        for tokens in _measurement_patterns(rule)
    ]
    patterns += [{"label": rule.label, "pattern": list(rule.pattern)} for rule in PATTERN_RULES]
    return patterns
