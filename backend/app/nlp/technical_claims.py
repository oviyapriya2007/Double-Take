"""Technical-claim compatibility: do two chunks state claims about the same technical thing?

A chunk's claims are found with regular expressions only (no model, deterministic):

- quantity:      a number or range with a unit ("8.0 bar", "-10°C to 55°C", "5% to 90%")
- interval:      a quantity whose unit is a time unit ("every 1,000 hours", "36 months")
- specification: a hyphenated variant term next to a quantity ("5 A slow-blow")

Units are not looked up in a list of physical quantities: whatever short token directly
follows a number is taken as its unit, unless it is an ordinary word.

Each claim keeps its context: the content words around it on its line, without framing
words such as "maximum" or "every". Two claims are comparable when they are the same kind,
quantities share a unit, and their contexts share words. The score is higher when both are
framed the same way (both limits/ranges, both schedules) or, for specifications, when the
variant terms differ.

This is a retrieval signal only. A high score means two chunks state claims about the
same kind of thing, never that those claims agree or contradict each other.
"""

import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

QUANTITY = "quantity"
INTERVAL = "interval"
SPECIFICATION = "specification"

TIME_UNITS = {
    **dict.fromkeys(["ms", "msec"], "millisecond"),
    **dict.fromkeys(["s", "sec", "secs", "second", "seconds"], "second"),
    **dict.fromkeys(["min", "mins", "minute", "minutes"], "minute"),
    **dict.fromkeys(["h", "hr", "hrs", "hour", "hours"], "hour"),
    **dict.fromkeys(["day", "days"], "day"),
    **dict.fromkeys(["wk", "wks", "week", "weeks"], "week"),
    **dict.fromkeys(["mo", "mos", "month", "months"], "month"),
    **dict.fromkeys(["yr", "yrs", "year", "years"], "year"),
}
# Durations (timeouts, response times) are only compared with durations, and service
# intervals only with service intervals, whatever the exact time unit.
LONG_TIME_UNITS = {"hour", "day", "week", "month", "year"}

# Word starts (or symbols) that frame a value as a limit, range or rating.
CONSTRAINT_CUES = (
    "max", "min", "limit", "threshold", "allow", "rate", "operat", "accept", "exceed",
    "nominal", "range", "trip", "toleran", "capacit", "upper", "lower", "absolute", "peak",
    "below", "above", "under", "over", "least", "most", "within", "between",
    "<", ">", "≤", "≥", "±",
)
# Word starts that frame a time value as a recurring schedule.
INTERVAL_CUES = (
    "every", "each", "interval", "period", "replac", "inspect", "servic", "overhaul",
    "schedul", "calibrat", "clean", "check", "lubricat", "renew", "annual", "monthly",
    "weekly", "daily",
)
CUE_WORDS = tuple(cue for cue in CONSTRAINT_CUES + INTERVAL_CUES if cue.isalpha())

BEFORE_WORDS = 6
"""Content words kept from before a claim on its line."""
AFTER_WORDS = 4
"""Content words kept from after a claim on its line."""
MIN_CONTEXT_WORDS = 2
"""Below this, earlier lines are added (table cells are often split over several lines)."""
MAX_EXTRA_LINES = 6
SPECIFICATION_MAX_GAP = 40
"""A variant term counts as a specification only within this many characters of a quantity."""
SHARED_WORDS_FOR_FULL_MATCH = 2
"""Shared context words needed for full context credit; one shared word gives half."""
UNFRAMED_FACTOR = 0.75
"""Score multiplier when the two claims are not framed the same way."""

UNIT = r"°\s?[A-Za-z]|%|[A-Za-zµΩ][A-Za-zµΩ²³]*(?:[/·][A-Za-z]+)*"
# Not part of an identifier such as "XR-500", "CR2032" or "v2.4.1".
NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)[-+−]?\d+(?:[.,]\d+)*")
UNIT_AFTER = re.compile(rf"[ \t]*\n?[ \t]*({UNIT})(?![\w/·]|-[A-Za-z])")
RANGE_JOIN = re.compile(rf"[ \t]*(?:({UNIT})[ \t]*)?\n?[ \t]*(?:to|–|—|-|~)[ \t]*\n?[ \t]*")
VARIANT_TERM = re.compile(r"(?<![\w-])[A-Za-z]{2,}(?:-[A-Za-z]{2,})+(?![\w-])")
CONTEXT_WORD = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class TechnicalClaim:
    kind: str
    """QUANTITY, INTERVAL or SPECIFICATION."""
    text: str
    unit: str
    """Normalised unit ("°c", "bar", "hour"); empty for a specification."""
    term: str
    """The lower-cased variant term of a specification; empty otherwise."""
    context: frozenset[str]
    framed: bool
    """Quantity: stated as a limit, range or rating. Interval: stated as a schedule."""


@dataclass(frozen=True)
class _Quantity:
    start: int
    end: int
    unit: str
    is_range: bool


def extract_technical_claims(text: str) -> list[TechnicalClaim]:
    """The quantity and interval claims in a chunk of text, then its specification claims."""
    quantities = _find_quantities(text)
    masked = _blank(text, [(q.start, q.end) for q in quantities])

    claims = []
    for q in quantities:
        context, cue_text = _context(masked, text, q.start, q.end)
        if q.unit in TIME_UNITS.values():
            kind, framed = INTERVAL, _has_cue(cue_text, INTERVAL_CUES)
        else:
            kind, framed = QUANTITY, q.is_range or _has_cue(cue_text, CONSTRAINT_CUES)
        claims.append(TechnicalClaim(kind, text[q.start:q.end], q.unit, "", context, framed))

    for match in VARIANT_TERM.finditer(text):
        if not any(match.start() - q.end <= SPECIFICATION_MAX_GAP
                   and q.start - match.end() <= SPECIFICATION_MAX_GAP for q in quantities):
            continue
        term_masked = _blank(masked, [match.span()])
        context, _ = _context(term_masked, text, match.start(), match.end())
        claims.append(TechnicalClaim(
            SPECIFICATION, match.group(), "", match.group().lower(), context, False
        ))
    return claims


def claim_compatibility(a: TechnicalClaim, b: TechnicalClaim) -> float:
    """How comparable two claims are, from 0 (unrelated) to 1."""
    if a.kind != b.kind or (a.kind == QUANTITY and a.unit != b.unit):
        return 0.0
    if a.kind == INTERVAL and (a.unit in LONG_TIME_UNITS) != (b.unit in LONG_TIME_UNITS):
        return 0.0
    shared = _shared_word_count(a.context, b.context)
    if not shared:
        return 0.0
    framed = a.term != b.term if a.kind == SPECIFICATION else a.framed and b.framed
    context_score = min(1.0, shared / SHARED_WORDS_FOR_FULL_MATCH)
    return context_score * (1.0 if framed else UNFRAMED_FACTOR)


def technical_compatibility(claims_a: list[TechnicalClaim], claims_b: list[TechnicalClaim]) -> float:
    """The best claim_compatibility between any claim of one chunk and any of the other."""
    best = 0.0
    for a in claims_a:
        for b in claims_b:
            best = max(best, claim_compatibility(a, b))
            if best == 1.0:
                return best
    return best


def _canonical_unit(raw: str) -> str | None:
    """The normalised unit, or None when the token after a number is an ordinary word."""
    unit = re.sub(r"\s", "", raw)
    lower = unit.lower()
    if lower in TIME_UNITS:
        return TIME_UNITS[lower]
    if not unit.isalpha():
        return lower
    # Longer words and capitalised words ("3.2 Air Filter") are text, not units.
    if len(unit) > 4 or (len(unit) >= 3 and unit.istitle()):
        return None
    if lower in ENGLISH_STOP_WORDS and not unit.isupper():
        return None
    return lower


def _find_quantities(text: str) -> list[_Quantity]:
    numbers = list(NUMBER.finditer(text))
    quantities: list[_Quantity] = []
    for index, number in enumerate(numbers):
        unit_match = UNIT_AFTER.match(text, number.end())
        unit = _canonical_unit(unit_match.group(1)) if unit_match else None
        if unit is None:
            continue
        start, is_range = number.start(), False
        if index:
            previous = numbers[index - 1]
            join = RANGE_JOIN.fullmatch(text, previous.end(), number.start())
            if join and (join.group(1) is None or _canonical_unit(join.group(1)) == unit):
                start, is_range = previous.start(), True
                if quantities and quantities[-1].start == previous.start():
                    quantities.pop()
        quantities.append(_Quantity(start, unit_match.end(), unit, is_range))
    return quantities


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace the spans with spaces, keeping line breaks and every other offset."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _content_words(text: str) -> list[str]:
    words = (match.group().lower() for match in CONTEXT_WORD.finditer(text))
    return [
        word for word in words
        if word not in ENGLISH_STOP_WORDS and word not in TIME_UNITS
        and not word.startswith(CUE_WORDS)
    ]


def _context(masked: str, text: str, start: int, end: int) -> tuple[frozenset[str], str]:
    """(content words around the span, raw lower-cased text to look for framing cues in)."""
    region_start = masked.rfind("\n", 0, start) + 1
    line_end = masked.find("\n", end)
    line_end = len(masked) if line_end == -1 else line_end
    before = _content_words(masked[region_start:start])[-BEFORE_WORDS:]
    after = _content_words(masked[end:line_end])[:AFTER_WORDS]
    for _ in range(MAX_EXTRA_LINES):
        if len(before) + len(after) >= MIN_CONTEXT_WORDS or region_start == 0:
            break
        previous_start = masked.rfind("\n", 0, region_start - 1) + 1
        before = (_content_words(masked[previous_start:region_start]) + before)[-BEFORE_WORDS:]
        region_start = previous_start
    return frozenset(before + after), text[region_start:line_end].lower()


def _has_cue(text: str, cues: tuple[str, ...]) -> bool:
    words = re.findall(r"[a-z]+", text)
    return any(cue in text for cue in cues if not cue.isalpha()) or any(
        word.startswith(tuple(cue for cue in cues if cue.isalpha())) for word in words
    )


def _words_match(x: str, y: str) -> bool:
    """Same word, an abbreviation ("temp"/"temperature") or a shared stem ("operate"/"operating")."""
    if x == y:
        return True
    shorter, longer = sorted((x, y), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return True
    return len(_common_prefix(x, y)) >= 6


def _common_prefix(x: str, y: str) -> str:
    n = 0
    while n < min(len(x), len(y)) and x[n] == y[n]:
        n += 1
    return x[:n]


def _shared_word_count(a: frozenset[str], b: frozenset[str]) -> int:
    smaller, larger = sorted((a, b), key=len)
    return sum(any(_words_match(word, other) for other in larger) for word in smaller)
